"""LLM access with two interchangeable backends.

  claude-code  - shells out to the Claude Code CLI (`claude -p`). Bills your Claude subscription.
                 Needs `claude auth login` done once in a terminal. Default when no API key is set.
  api          - Anthropic SDK with ANTHROPIC_API_KEY. Pay-per-token.

Select with LLM_BACKEND=claude-code|api|auto in .env (default auto).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from typing import TypeVar

from pydantic import BaseModel

from .config import API_MODEL_IDS, MODEL_DRAFT

T = TypeVar("T", bound=BaseModel)

# Only these reach the child `claude` process. The desktop app's session variables
# (ANTHROPIC_BASE_URL, CLAUDECODE, CLAUDE_CODE_*) would make it think it is a nested session.
_CLEAN_ENV_KEYS = ("HOME", "PATH", "USER", "LANG", "TMPDIR", "SHELL")


class LLMError(RuntimeError):
    pass


def backend() -> str:
    b = os.environ.get("LLM_BACKEND", "auto").lower()
    if b in ("claude-code", "api"):
        return b
    return "api" if os.environ.get("ANTHROPIC_API_KEY") else "claude-code"


def _system_text(system) -> str:
    if isinstance(system, str):
        return system
    return "\n\n".join(b["text"] for b in system if b.get("type") == "text")


# --- claude-code backend -------------------------------------------------------

def claude_bin() -> str:
    b = os.environ.get("CLAUDE_BIN") or shutil.which("claude")
    if not b:
        raise LLMError("Claude Code CLI not found. Install it (npm i -g @anthropic-ai/claude-code) or set CLAUDE_BIN, "
                       "or set ANTHROPIC_API_KEY to use the API instead.")
    return b


def claude_code_ready() -> tuple[bool, str]:
    try:
        b = claude_bin()
    except LLMError as e:
        return False, str(e)
    env = {k: os.environ[k] for k in _CLEAN_ENV_KEYS if k in os.environ}
    try:
        out = subprocess.run([b, "auth", "status", "--json"], env=env, capture_output=True, text=True, timeout=30)
        info = json.loads(out.stdout or "{}")
    except Exception as e:  # noqa: BLE001
        return False, f"could not run `claude auth status`: {e}"
    if not info.get("loggedIn"):
        return False, "Claude Code CLI is not logged in - run `claude auth login` in a terminal"
    return True, f"claude-code ({info.get('subscriptionType', '?')} subscription, {info.get('email', '')})"


def _complete_claude_code(system, user: str, model: type[T], model_name: str) -> T:
    schema = model.model_json_schema()
    cmd = [
        claude_bin(), "-p", "--output-format", "json", "--no-session-persistence",
        "--tools", "", "--model", model_name,
        "--json-schema", json.dumps(schema),
        "--system-prompt", _system_text(system),
        user,
    ]
    env = {k: os.environ[k] for k in _CLEAN_ENV_KEYS if k in os.environ}
    env["TERM"] = "dumb"
    proc = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0 and not proc.stdout.strip():
        raise LLMError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:400]}")
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        raise LLMError(f"unexpected output from claude: {proc.stdout[:300]}") from e
    if data.get("is_error"):
        msg = str(data.get("result", ""))
        if "log" in msg.lower() and "in" in msg.lower() or "OAuth" in msg:
            msg += "  ->  run `claude auth login` in a terminal, then retry"
        raise LLMError(msg)
    payload = data.get("structured_output")
    if payload is None:
        try:
            payload = json.loads(data.get("result") or "")
        except json.JSONDecodeError as e:
            raise LLMError(f"claude returned non-JSON: {str(data.get('result'))[:300]}") from e
    return model.model_validate(payload)


# --- api backend ----------------------------------------------------------------

_client = None


def api_client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.Anthropic()
    return _client


def _complete_api(system, user: str, model: type[T], model_name: str) -> T:
    resp = api_client().messages.parse(
        model=API_MODEL_IDS.get(model_name, model_name),
        max_tokens=16000,
        system=system,
        messages=[{"role": "user", "content": user}],
        output_format=model,
    )
    if resp.parsed_output is None:
        raise LLMError("no structured output returned")
    return resp.parsed_output


# --- public ---------------------------------------------------------------------

def complete_structured(system, user: str, model: type[T], model_name: str | None = None) -> T:
    """system: str or list of {'type':'text','text':...} blocks.

    model_name is a tier alias ('opus' / 'sonnet' / 'haiku'); it selects the CLI --model flag on the
    claude-code backend and maps to an API model id on the api backend.
    """
    model_name = model_name or MODEL_DRAFT
    if backend() == "api":
        return _complete_api(system, user, model, model_name)
    return _complete_claude_code(system, user, model, model_name)


def describe() -> str:
    if backend() == "api":
        return "api (ANTHROPIC_API_KEY)"
    ok, msg = claude_code_ready()
    return msg if ok else f"claude-code NOT READY: {msg}"


def ready() -> bool:
    if backend() == "api":
        return True
    return claude_code_ready()[0]
