# outreach

I built this with Claude Code during my sophomore fall at Pitzer while recruiting for finance internships. Cold emailing was taking me too long, mostly on finding the right people, guessing their work emails, and keeping track of who I had already contacted. This tool handles that busywork so I can spend my time on the conversations themselves. I still read and send every email myself.

This public copy has the code, tests, and firm list only. My contacts, spreadsheets, and credentials are not included.

## What it does

Cold-email networking tool for finance recruiting. Builds a ranked contact list at IB / AM / WM firms, guesses work emails from each firm's pattern, writes a short personalized email from your resume, pushes drafts to Gmail, and keeps everything in `Outreach Contacts.xlsx` (also syncing the best contact per firm into `Internship Tracker Summer 2027.xlsx`).

Nothing is ever sent automatically. `push` creates Gmail *drafts*; you read and hit send.

## Setup (once)

```bash
git clone https://github.com/Joshwhang/outreach.git && cd outreach
python3 -m venv .venv && .venv/bin/pip install -e .
cp .env.example .env          # then edit .env
```

**LLM (pick one):**

- *Claude subscription (default, no API key):* the tool shells out to the Claude Code CLI, which bills your Pro/Max plan. Log the CLI in once from Terminal:

  ```bash
  claude auth login
  ```

- *API key (pay per token):* set `ANTHROPIC_API_KEY` in `.env`. `LLM_BACKEND=auto` uses the key if present, otherwise the CLI.

Other keys (all optional):

| Key | Needed for | Where |
|---|---|---|
| Google `credentials.json` | `push` (Gmail drafts) | see below |
| `HUNTER_API_KEY` | `email --verify` | hunter.io, free tier 50/mo |
| `APOLLO_API_KEY` | `find` (API search needs a paid Apollo plan) | app.apollo.io |

### Gmail setup (one time, ~5 minutes)

1. **console.cloud.google.com** → project picker → **New Project** → name it `outreach` → Create.
2. Search **Gmail API** → **Enable**.
3. **APIs & Services → OAuth consent screen** → *External* → app name `outreach`, your email for both support fields → Save. On **Audience**, under *Test users*, **Add users** → your Gmail address. (Leave it in Testing mode; no Google review needed.)
4. **Credentials → Create credentials → OAuth client ID** → Application type **Desktop app** → Create → **Download JSON**.
5. Save that file as `credentials.json` in the repo folder:

   ```bash
   mv ~/Downloads/client_secret_*.json credentials.json
   ```

6. Authorize (opens a browser once; token cached in `token.json`):

   ```bash
   .venv/bin/outreach auth-gmail
   ```

   Google will warn the app is unverified — it is your own app; click **Advanced → Go to outreach (unsafe)**.

**Sending from your .edu:** drafts are stamped `From: jowhang@pitzer.edu`. For that to work, add it in Gmail → Settings → Accounts → *Send mail as* → Add another email address, and confirm the verification email. Without that alias Gmail sends from your gmail.com address instead. To use gmail.com deliberately, set `SENDER_EMAIL` in `.env`.

Then:

```bash
.venv/bin/outreach init
```

That parses `resume.pdf` once into `resume_facts.json` and creates the contacts workbook.

## Daily use

```bash
alias outreach="$PWD/.venv/bin/outreach"

# 1. add people (from LinkedIn, the Claremont alumni directory, Handshake...)
outreach add --firm "Houlihan Lokey"
#   paste lines:  Name | Title | Firm | LinkedIn URL | Notes     (blank line to finish)
outreach add --csv ~/Downloads/people.csv

# or, with an Apollo key:
outreach find --firm Baird --title Analyst --title Associate --location "Los Angeles, California"
outreach find --all --type IB --limit 20

# 2. emails are guessed on add; verify with Hunter if you have a key
outreach email --verify

# 3. drafts (Claude writes only the middle paragraph; the ask + sign-off are fixed)
outreach draft --priority 1 --show          # alumni first (auto-uses opus)
outreach draft --firm PIMCO --limit 5       # sonnet by default
outreach draft --model sonnet               # force sonnet everywhere to save Opus quota
outreach draft --id C0007 --redo            # regenerate one

# 4. push to Gmail drafts, then send from Gmail after reading each
outreach push --limit 10
outreach push --dry-run

# 5. bookkeeping
outreach sync            # best contact per firm -> tracker cols I/J (backup made first)
outreach status          # counts + follow-ups due
outreach firms --search "Los Angeles"
```

Anything you type in the sheet (Status = Sent / Replied / Chat Done, Reply Notes, Follow-up Due) is preserved on the next save and flows into `sync` and `status`.

## Finding people: the roster angle

`outreach roster` pulls public Pomona-Pitzer and CMS team rosters. Former athletes are the
warmest cold contacts you have - a shared team beats a shared school - and the rosters are
published by the colleges themselves.

```bash
outreach roster --school pp --sport football --from-year 2014 --to-year 2022
outreach roster --school cms --sport football mens-golf mens-basketball --out cms.txt
```

Output is pre-formatted for `outreach add`; fill in Title and Firm for the ones who went into
finance. Sport slugs come from the URL on the athletics site (`football`, `mens-basketball`,
`womens-soccer`, `mens-golf`, ...). Pages are cached under `cache/rosters/`.

This gives you *names*, not jobs - look each one up to find where they work now. LinkedIn shows
employer and school on the same profile, so the tie is confirmed rather than inferred.

## Model usage

Drafts run on your Claude subscription, so each one spends quota. The tool tiers by priority:

| Contacts | Model | Why |
|---|---|---|
| Priority 1 (Claremont alumni) | `opus` | highest-value emails, best writing |
| Priority 2-4 | `sonnet` | nearly as good, far cheaper |

Override per run with `--model opus|sonnet|haiku`, or change the defaults in `.env`
(`MODEL_DRAFT`, `MODEL_DRAFT_P1`, `MODEL_RESUME`). The model used is recorded in the sheet's
*Draft Model* column. Haiku is measurably weaker here - it drops the specific hook and writes
generic filler - so use `sonnet` as your floor unless you are just testing plumbing.

## How ranking works

| Priority | Rule |
|---|---|
| 1 | Claremont alum (school or notes mention Pitzer / Pomona / CMC / HMC / Scripps) |
| 2 | Analyst or Associate |
| 3 | SoCal office (LA, Irvine, Newport Beach, San Diego, Pasadena...) |
| 4 | everyone else |

## Email patterns

`firms.csv` has 130+ firms with a primary pattern (`first.last`, `flast`, ...) and a `pattern_confidence` column. `low` means unverified: send to one known person first or use `--verify`. Alternates go in the *Email Alternates* column so you can retry after a bounce. Edit the CSV freely; set `active=no` to hide a firm from `find --all`.

## Tests

```bash
.venv/bin/pytest -q
```
