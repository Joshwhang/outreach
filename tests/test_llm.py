import json
import subprocess

import pytest
from pydantic import BaseModel

from outreach import llm


class Out(BaseModel):
    greeting: str


def _fake_run(payload, returncode=0):
    def run(cmd, **kw):
        _fake_run.cmd = cmd
        return subprocess.CompletedProcess(cmd, returncode, stdout=json.dumps(payload), stderr="")
    return run


def test_claude_code_structured_output(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude-code")
    monkeypatch.setattr(llm, "claude_bin", lambda: "/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run({"is_error": False, "structured_output": {"greeting": "hi there"}}))
    out = llm.complete_structured([{"type": "text", "text": "sys A"}, {"type": "text", "text": "sys B"}], "hello", Out)
    assert out.greeting == "hi there"
    cmd = _fake_run.cmd
    assert cmd[0] == "/bin/claude" and "-p" in cmd and cmd[-1] == "hello"
    assert cmd[cmd.index("--system-prompt") + 1] == "sys A\n\nsys B"
    assert json.loads(cmd[cmd.index("--json-schema") + 1])["required"] == ["greeting"]


def test_claude_code_falls_back_to_result_json(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude-code")
    monkeypatch.setattr(llm, "claude_bin", lambda: "/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run({"is_error": False, "result": '{"greeting": "yo"}'}))
    assert llm.complete_structured("s", "u", Out).greeting == "yo"


def test_claude_code_not_logged_in(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude-code")
    monkeypatch.setattr(llm, "claude_bin", lambda: "/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run({"is_error": True, "result": "Not logged in · Please run /login"}))
    with pytest.raises(llm.LLMError, match="claude auth login"):
        llm.complete_structured("s", "u", Out)


def test_backend_selection(monkeypatch):
    monkeypatch.delenv("LLM_BACKEND", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert llm.backend() == "claude-code"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert llm.backend() == "api"
    monkeypatch.setenv("LLM_BACKEND", "claude-code")
    assert llm.backend() == "claude-code"


def test_model_name_reaches_cli(monkeypatch):
    monkeypatch.setenv("LLM_BACKEND", "claude-code")
    monkeypatch.setattr(llm, "claude_bin", lambda: "/bin/claude")
    monkeypatch.setattr(subprocess, "run", _fake_run({"is_error": False, "structured_output": {"greeting": "x"}}))
    llm.complete_structured("s", "u", Out, "haiku")
    cmd = _fake_run.cmd
    assert cmd[cmd.index("--model") + 1] == "haiku"
