# Outreach Tool — Design

**Goal:** A Python CLI that builds a ranked list of people at IB / AM / WM firms, fills in their work email, drafts a short personalized cold email from Joshua's resume, pushes drafts to Gmail, and keeps everything in a spreadsheet that also syncs into the existing internship tracker.

## Decisions (from brainstorm)
- Contact sourcing: **both** Apollo API (when key configured) and manual paste/CSV import.
- Output: new `Outreach Contacts.xlsx` (source of truth) **plus** auto-fill of the tracker's `Networking Contact` / `Contact Status` columns.
- Resume: `resume.pdf` in the project root → parsed once by Claude into `resume_facts.json`.
- Personalization: **hybrid** — fixed skeleton (greeting, ask, sign-off) + Claude writes only the middle paragraph.
- Delivery: **Gmail drafts** via Gmail API OAuth. Never auto-send.
- Firms: ~110 seeded in `firms.csv` (BB, EB, MM, regional IB; AM; WM; plus every firm in the tracker). All active by default.
- People: all levels. Ranked, not filtered.

## Data files (live in the parent folder of `outreach/`)
| File | Role |
|---|---|
| `resume.pdf` | input |
| `Internship Tracker Summer 2027.xlsx` | existing; only cols I/J written, backed up first |
| `Outreach Contacts.xlsx` | created/maintained by tool |
| `outreach/firms.csv` | firm master list + email patterns |
| `outreach/resume_facts.json` | cached resume extraction |
| `outreach/.env` | API keys |
| `outreach/credentials.json`, `token.json` | Google OAuth |

## Contacts sheet columns
`ID, Priority, Firm, Firm Type, First, Last, Title, Level, Group, Location, School, Claremont Alum, LinkedIn, Email, Email Status, Email Alternates, Phone, Source, Notes, Subject, Draft, Status, Date Drafted, Date Pushed, Date Sent, Follow-up Due, Reply Notes`

- **Level** derived from title: Analyst / Associate / VP / Director / MD / Other.
- **Priority**: 1 Claremont alum · 2 Analyst/Associate · 3 SoCal office · 4 other. Lowest applicable wins.
- **Email Status**: `from_api` · `verified` · `guessed` · `risky` · `invalid`.
- **Status** lifecycle: `New → Drafted → In Gmail → Sent → Replied → Chat Done` (or `Bounced`, `No Response`). `Sent` and later are set by the user in the sheet; the tool only advances to `In Gmail`.
- Dedup key: normalized `first+last+firm`.

## Modules
- `config.py` — paths, env, constants.
- `models.py` — `Contact` dataclass ↔ sheet row.
- `firms.py` — load `firms.csv`, alias lookup, pattern expansion (`first.last`, `flast`, `firstl`, `first_last`, `first`, `lastf`, `last.first`).
- `resume.py` — pypdf text → Claude structured extraction (`ResumeFacts` pydantic) → json cache.
- `sources/apollo.py` — `mixed_people/search` by org name + titles + locations; optional `people/match` enrich for email/phone.
- `sources/manual.py` — parse `Name | Title | Firm | LinkedIn | Notes` lines or a CSV.
- `addresses.py` — generate primary + alternates from firm pattern; optional Hunter `email-verifier`; Hunter `domain-search` fallback when a firm has no pattern.
- `ranking.py` — level detection, Claremont detection, SoCal detection, priority.
- `drafts.py` — skeleton per firm type + Claude middle paragraph (`claude-opus-5`, structured output). Hard limits: middle ≤ 70 words, whole email ≤ 160 words, no em-dashes, no "I hope this finds you well".
- `sheet.py` — openpyxl read/write of the contacts workbook with header validation and styles.
- `tracker.py` — backup, then write best contact + status per firm into tracker cols I/J (only empty cells unless `--force`).
- `gmail.py` — OAuth, build MIME with resume attachment, `drafts().create`.
- `cli.py` — argparse subcommands: `init, find, add, email, draft, push, sync, status, firms`.

## Error handling
- Missing API key → the command that needs it exits with a one-line instruction; other commands unaffected.
- Apollo 401/403/429 → clear message; no partial writes.
- Claude API errors → retry via SDK defaults; on failure the row is left undrafted and reported.
- Sheet header mismatch → refuse to write, tell the user.
- Tracker write always preceded by a timestamped backup in `outreach/backups/`.

## Testing
pytest on pure logic: pattern expansion, ranking, manual parser, dedup, skeleton assembly, sheet round-trip (tmp file). API modules tested with fakes; live calls not in tests.
