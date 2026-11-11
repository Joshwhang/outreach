"""outreach - command line entry point."""
from __future__ import annotations

import argparse
import sys
from collections import Counter
from datetime import date, timedelta
from pathlib import Path

from . import config
from .addresses import fill_emails
from .firms import FirmBook
from .models import Contact, STATUS_DRAFTED, STATUS_IN_GMAIL, STATUS_NEW

# Substrings written into the Confidence column that mean "do not send without a human check"
UNVERIFIED_MARKERS = {"SHARES NAME", "LIKELY WRONG", "CHECK BOTH"}
# Match tiers below 'strong' are held too; clearing the Confidence cell releases a contact.
UNVERIFIED_TIERS = ("review", "weak")
PUSH_CONFIRM_ABOVE = 10


def _unverified(c: Contact) -> bool:
    conf = (c.confidence or "").strip()
    if not conf:
        return False                      # manually added contacts carry no inference
    up = conf.upper()
    return any(m in up for m in UNVERIFIED_MARKERS) or conf.lower().startswith(UNVERIFIED_TIERS)
from .ranking import enrich
from .sheet import ContactSheet, SheetError

FOLLOW_UP_DAYS = 7


def _today() -> str:
    return date.today().isoformat()


def _canonicalize(contacts: list[Contact], firms: FirmBook) -> list[str]:
    """Snap firm names to firms.csv, set firm_type, derive level/priority. Returns warnings."""
    warnings = []
    for c in contacts:
        f = firms.get(c.firm)
        if f:
            c.firm, c.firm_type = f.name, f.type
            if not c.location and f.hq:
                c.location = f"{f.hq} (firm HQ)"
        else:
            warnings.append(f"{c.name}: firm '{c.firm}' not in firms.csv (kept as typed; add it to firms.csv for emails)")
        enrich(c)
    return warnings


def _ingest(sheet: ContactSheet, firms: FirmBook, new: list[Contact], label: str) -> None:
    warnings = _canonicalize(new, firms)
    added, skipped = sheet.add(new)
    filled, w2 = fill_emails(added, firms)
    sheet.save()
    print(f"{label}: {len(added)} added, {len(skipped)} duplicates skipped, {filled} emails guessed")
    for w in warnings + w2:
        print(f"  ! {w}")
    for c in added:
        print(f"  + P{c.priority} {c.name:<24} {c.title[:34]:<34} {c.firm[:22]:<22} {c.email}")


# --- commands -------------------------------------------------------------

def cmd_init(a) -> int:
    ok = True
    print(f"resume:   {config.RESUME_PDF} {'ok' if config.RESUME_PDF.exists() else 'MISSING'}")
    print(f"tracker:  {config.TRACKER_XLSX} {'ok' if config.TRACKER_XLSX.exists() else 'missing (sync disabled)'}")
    print(f"contacts: {config.CONTACTS_XLSX} {'exists' if config.CONTACTS_XLSX.exists() else 'will be created'}")
    print(f"firms:    {len(FirmBook.load().firms)} in firms.csv")
    from . import llm
    print(f"llm:      {llm.describe()}")
    print(f"models:   resume={config.MODEL_RESUME}  drafts={config.MODEL_DRAFT}  priority-1 drafts={config.MODEL_DRAFT_P1}")
    print(f"keys:     "
          f"apollo={'set' if config.APOLLO_API_KEY else 'no (manual add only)'} "
          f"hunter={'set' if config.HUNTER_API_KEY else 'no (no verification)'} "
          f"gmail={'credentials.json ok' if config.GOOGLE_CREDENTIALS.exists() else 'credentials.json missing'}")
    if not config.RESUME_PDF.exists():
        print("Put your resume at the path above (or set RESUME_PDF in .env).")
        return 1
    if llm.ready():
        from .resume import load_facts
        facts = load_facts(refresh=a.refresh_resume)
        print(f"resume facts: {facts.name}, {facts.school} '{facts.class_year[-2:]}, {facts.major}; "
              f"{len(facts.hooks)} hooks -> {config.RESUME_FACTS_JSON.name}")
    else:
        print("Fix the llm line above (run `claude auth login` in a terminal, or set ANTHROPIC_API_KEY in .env).")
        ok = False
    sheet = ContactSheet()
    if not config.CONTACTS_XLSX.exists():
        sheet.save()
        print(f"created {config.CONTACTS_XLSX.name}")
    return 0 if ok else 1



def cmd_firms(a) -> int:
    fb = FirmBook.load()
    rows = fb.active(a.type) if a.type else [f for f in fb.firms]
    if a.search:
        q = a.search.lower()
        rows = [f for f in rows if q in f.name.lower() or any(q in x.lower() for x in f.aliases) or q in f.offices.lower()]
    for f in rows:
        print(f"{f.type:<3} {f.tier:<8} {f.name:<42} {f.domain:<28} {f.pattern:<11} ({f.pattern_confidence}) {f.hq}")
    print(f"{len(rows)} firms")
    return 0


def cmd_add(a) -> int:
    firms = FirmBook.load()
    sheet = ContactSheet()
    from .sources.manual import parse_csv, parse_pipe_lines
    if a.csv:
        new = parse_csv(Path(a.csv), default_firm=a.firm or "")
    else:
        if sys.stdin.isatty():
            print("Paste contacts, one per line:  Name | Title | Firm | LinkedIn URL | Notes")
            print("(Firm optional if --firm given. Finish with an empty line or Ctrl-D.)")
        lines = []
        for line in sys.stdin:
            if not line.strip():
                break
            lines.append(line)
        new = parse_pipe_lines("".join(lines), default_firm=a.firm or "")
    if not new:
        print("no contacts parsed")
        return 1
    if a.referred_by:
        for c in new:
            c.referred_by = a.referred_by
    _ingest(sheet, firms, new, "add")
    return 0


def cmd_import_leads(a) -> int:
    from .sources.warmleads import TIERS, load_leads
    firms = FirmBook.load()
    sheet = ContactSheet()
    tiers = tuple(TIERS) if "all" in a.tier else tuple(a.tier)
    leads, st = load_leads(Path(a.path), firms, sheet=a.sheet, tiers=tiers,
                           min_confidence=a.min_confidence, keep_unmapped=a.keep_unmapped)
    print(f"read {st.read} rows: {len(leads)} importable, {st.skipped_tier} wrong tier, "
          f"{st.skipped_low_conf} below confidence {a.min_confidence}, "
          f"{st.skipped_no_firm} with no current firm, {st.unmapped_firm} firms not in firms.csv"
          + (" (kept)" if a.keep_unmapped else " (skipped)"))
    if st.flagged_duplicate:
        print(f"  {st.flagged_duplicate} share a name with another lead - marked in Confidence")
    if a.limit:
        leads = leads[: a.limit]
    if a.dry_run:
        for c in leads:
            print(f"  P? {c.name:<22} {c.firm[:24]:<24} {c.confidence}")
        return 0
    _ingest(sheet, firms, leads, "import-leads")
    print("\nThese identities are INFERRED from a name match. Open the Verify URL column and "
          "confirm each person on BrokerCheck before sending.")
    return 0


def cmd_find(a) -> int:
    from .sources.apollo import ApolloClient, ApolloError
    firms = FirmBook.load()
    sheet = ContactSheet()
    try:
        client = ApolloClient()
    except ApolloError as e:
        print(e)
        return 1
    if a.all:
        targets = firms.active(a.type)
    else:
        f = firms.get(a.firm or "")
        if not f:
            print(f"firm '{a.firm}' not found - try `outreach firms --search {a.firm!r}`")
            return 1
        targets = [f]
    total_new: list[Contact] = []
    for f in targets:
        try:
            found = client.search(f, titles=a.title or None, locations=a.location or None, max_results=a.limit)
        except ApolloError as e:
            print(f"{f.name}: {e}")
            return 1
        print(f"{f.name}: {len(found)} people from Apollo")
        if a.enrich:
            for c in found:
                try:
                    client.enrich(c, f, reveal_phone=a.phone)
                except ApolloError as e:
                    print(f"  enrich failed for {c.name}: {e}")
        total_new.extend(found)
    if total_new:
        _ingest(sheet, firms, total_new, "find")
    return 0


def cmd_email(a) -> int:
    firms = FirmBook.load()
    sheet = ContactSheet()
    targets = sheet.select(firm=a.firm, group=a.group)
    if a.id:
        wanted = set(a.id)
        targets = [c for c in sheet.contacts if c.id in wanted]
    if a.skip_flagged:
        targets = [c for c in targets if not _unverified(c)]
    if a.verify and not config.HUNTER_API_KEY:
        print("HUNTER_API_KEY not set - add to .env to verify. Running without verification.")
        a.verify = False
    def report(c):
        sheet.save()
        print(f"  {c.email_status:<9} {c.name:<22} {c.email}")
    filled, warnings = fill_emails(targets, firms, verify=a.verify, on_each=report if a.verify else None)
    sheet.save()
    print(f"{filled} emails {'verified' if a.verify else 'guessed'}; "
          f"{sum(1 for c in sheet.contacts if not c.email)} contacts still without an email")
    for w in warnings:
        print(f"  ! {w}")
    return 0


def cmd_draft(a) -> int:
    from .drafts import draft_for
    from .resume import load_facts
    firms = FirmBook.load()
    sheet = ContactSheet()
    facts = load_facts()
    todo = [c for c in sheet.select(firm=a.firm, priority=a.priority)
            if c.email and (a.redo or not c.draft)]
    if a.id:
        todo = [c for c in sheet.contacts if c.id in a.id]
    todo = todo[: a.limit] if a.limit else todo
    if not todo:
        print("nothing to draft (all selected contacts already have drafts, or lack an email)")
        return 0
    done, failed = 0, 0
    stale: list[Contact] = []
    for c in todo:
        f = firms.get(c.firm)
        if not f:
            print(f"  skip {c.name}: firm '{c.firm}' not in firms.csv")
            continue
        try:
            d = draft_for(c, f, facts, a.model, style=a.style)
        except Exception as e:  # keep going; report at the end
            failed += 1
            print(f"  ! {c.name}: {type(e).__name__}: {e}")
            continue
        changed = (d.subject, d.body) != (c.subject, c.draft)
        c.subject, c.draft, c.draft_model = d.subject, d.body, d.model
        if c.status == STATUS_NEW:
            c.status = STATUS_DRAFTED
        elif c.status == STATUS_IN_GMAIL and changed:
            c.status = STATUS_DRAFTED       # the Gmail copy is now stale - push again, delete the old one
            stale.append(c)
        c.date_drafted = _today()
        done += 1
        print(f"  drafted P{c.priority} {c.name} <{c.email}> - {len(d.body.split())} words [{d.model}]")
        if a.show:
            print("    " + d.subject)
            print("    " + d.body.replace("\n", "\n    "))
        sheet.save()  # save after each so a crash loses nothing
    if stale:
        print(f"\n{len(stale)} redrafted contact(s) already had a Gmail draft with the OLD text. "
              f"Delete those in Gmail, then `outreach push` to create fresh ones:")
        for c in stale:
            print(f"  {c.name} <{c.email}>")
    used = Counter(c.draft_model for c in todo if c.draft_model)
    print(f"{done} drafted, {failed} failed" + (f" ({', '.join(f'{n}x {m}' for m, n in used.most_common())})" if used else ""))
    return 0 if not failed else 1


def cmd_push(a) -> int:
    from .gmail import GmailError, create_draft
    sheet = ContactSheet()
    todo = sheet.select(firm=a.firm, status=STATUS_DRAFTED, limit=a.limit, group=a.group)
    if a.id:
        todo = [c for c in sheet.contacts if c.id in a.id]
    todo = [c for c in todo if c.draft and c.email]
    dead = [c for c in todo if c.email_status == "invalid"]
    if dead:
        print(f"{len(dead)} contact(s) have an address Hunter reports as invalid - not pushing them:")
        for c in dead:
            print(f"  {c.id} {c.name} <{c.email}> - try alternates or check their current employer")
        todo = [c for c in todo if c not in dead]
    # An inferred identity that is also a known namesake is the one case where a warm opener
    # ("we both played for Pomona-Pitzer") can land on a stranger. Make that deliberate.
    risky = [c for c in todo if _unverified(c)]
    if risky and not a.force:
        print(f"{len(risky)} contact(s) flagged as unverified identities - not pushing them:")
        for c in risky:
            print(f"  {c.id} {c.name} ({c.firm}) - {c.confidence}")
            print(f"       verify: {c.verify_url or 'no link'}")
        print("Confirm on BrokerCheck, clear the flag in the Confidence column, or re-run with --force.")
        todo = [c for c in todo if c not in risky]
    if not todo:
        print("nothing to push (no contacts with status 'Drafted')")
        return 0
    # Guard against an unfiltered push sweeping up the whole queue after a bulk --redo.
    if len(todo) > PUSH_CONFIRM_ABOVE and not (a.firm or a.id or a.limit or a.all or a.group):
        print(f"{len(todo)} contacts would be pushed. Narrow with --firm / --id / --limit, "
              f"or pass --all if you mean it.")
        return 1
    if a.dry_run:
        for c in todo:
            print(f"  would push {c.name} <{c.email}>: {c.subject}")
        return 0
    pushed = 0
    for c in todo:
        try:
            draft_id = create_draft(c, attach_resume=not a.no_attach)
        except GmailError as e:
            print(f"  ! {e}")
            return 1
        except Exception as e:
            print(f"  ! {c.name}: {type(e).__name__}: {e}")
            continue
        c.status, c.date_pushed = STATUS_IN_GMAIL, _today()
        c.follow_up_due = (date.today() + timedelta(days=FOLLOW_UP_DAYS)).isoformat()
        pushed += 1
        print(f"  gmail draft {draft_id} -> {c.name} <{c.email}>")
        sheet.save()
    print(f"{pushed} drafts created in Gmail. Open Gmail > Drafts, read each one, then send.")
    return 0


def cmd_roster(a) -> int:
    """Pull public Claremont athletic rosters - a candidate list of people with a real tie to you."""
    from .sources.rosters import ALL_SPORTS, FINANCE_HEAVY, SCHOOLS, fetch_many
    sports = {"all": ALL_SPORTS, "finance": FINANCE_HEAVY}.get(
        a.sport[0] if len(a.sport) == 1 else "", a.sport)
    years = range(a.from_year, a.to_year + 1)
    entries = fetch_many(a.school, sports, years, use_cache=not a.no_cache)
    if a.name:
        q = a.name.lower()
        entries = [e for e in entries if q in f"{e.first} {e.last}".lower()]
    entries.sort(key=lambda e: (-e.year, e.last.lower()))
    print(f"\n{len(entries)} distinct athletes, {SCHOOLS[a.school][0]}, "
          f"{'/'.join(a.sport)} {a.from_year}-{a.to_year}\n")
    for e in entries:
        print(f"{e.first} {e.last} | | | | {e.tie}")
    if a.out:
        Path(a.out).write_text("\n".join(f"{e.first} {e.last} | | | | {e.tie}" for e in entries) + "\n")
        print(f"\nwritten to {a.out}")
    print("\nThese are names only - nobody here is known to work in finance yet.")
    print("Look them up (LinkedIn shows employer AND school, so the tie is confirmed rather than guessed),")
    print("fill in Title and Firm, then pipe the lines into `outreach add`.")
    return 0


def cmd_show(a) -> int:
    sheet = ContactSheet()
    rows = sheet.select(firm=a.firm, priority=a.priority, status=a.status)
    if a.id:
        rows = [c for c in sheet.contacts if c.id in a.id]
    if not a.notes:
        rows = [c for c in rows if c.draft]
    if not rows:
        print("nothing to show" + ("" if a.notes else " - run `outreach draft` first"))
        return 0
    for c in rows[: a.limit] if a.limit else rows:
        head = (f"\n{'=' * 78}\n{c.id}  P{c.priority}  {c.name}"
                f"{' - ' + c.title if c.title else ''}\n"
                f"{c.firm}  |  {c.email or 'no email'}"
                f"{' (' + c.email_status + ')' if c.email_status else ''}  |  {c.status}")
        if a.notes:
            bits = [head]
            for label, val in (("tie", c.notes), ("confidence", c.confidence),
                               ("verify", c.verify_url), ("phone", c.phone)):
                if val:
                    bits.append(f"{label}: {val}")
            bits.append("-" * 78)
            bits.append(c.reply_notes or "(no notes yet)")
            print("\n".join(bits))
        else:
            print(f"{head}  |  {c.draft_model}\nSubject: {c.subject}\n{'-' * 78}\n{c.draft}")
    print(f"\n{len(rows)} contact(s)")
    return 0


def cmd_auth_gmail(a) -> int:
    from .gmail import GmailError, _service
    if not config.GOOGLE_CREDENTIALS.exists():
        print(f"{config.GOOGLE_CREDENTIALS} not found - follow the Gmail setup steps in README.md")
        return 1
    try:
        svc = _service()
        profile = svc.users().getProfile(userId="me").execute()
    except GmailError as e:
        print(e)
        return 1
    print(f"authorized as {profile.get('emailAddress')} - token cached in {config.GOOGLE_TOKEN.name}")
    sender = config.SENDER_FROM or profile.get("emailAddress", "")
    print(f"drafts send from: {sender}")
    print(f"signature + Reply-To: {config.SENDER_EMAIL}")
    if config.SENDER_FROM and config.SENDER_FROM != profile.get("emailAddress"):
        print(f"  note: Gmail will rewrite From to {profile.get('emailAddress')} unless "
              f"{config.SENDER_FROM} is a verified 'Send mail as' alias on that account")
    return 0


def cmd_sync(a) -> int:
    from .tracker import sync
    firms = FirmBook.load()
    sheet = ContactSheet()
    if not config.TRACKER_XLSX.exists():
        print(f"tracker not found: {config.TRACKER_XLSX}")
        return 1
    changes = sync(sheet.best_by_firm(), firms, force=a.force, dry_run=a.dry_run)
    for firm, label, status in changes:
        print(f"  {'would set' if a.dry_run else 'set'} {firm:<22} -> {label} [{status}]")
    print(f"{len(changes)} tracker rows {'would change' if a.dry_run else 'updated'}"
          + ("" if a.dry_run or not changes else f" (backup in {config.BACKUP_DIR.name}/)"))
    return 0


def cmd_status(a) -> int:
    sheet = ContactSheet()
    cs = sheet.contacts
    print(f"{len(cs)} contacts in {config.CONTACTS_XLSX.name}")
    print("by priority:", dict(sorted(Counter(c.priority for c in cs).items())))
    print("by status:  ", dict(Counter(c.status for c in cs)))
    print("emails:     ", dict(Counter(c.email_status or "none" for c in cs)))
    by_firm = Counter(c.firm for c in cs)
    for firm, n in by_firm.most_common():
        print(f"  {n:>3}  {firm}")
    due = [c for c in cs if c.follow_up_due and c.follow_up_due <= _today() and c.status in (STATUS_IN_GMAIL, "Sent")]
    if due:
        print(f"follow-ups due: {len(due)}")
        for c in due:
            print(f"  {c.name} ({c.firm}) sent/pushed {c.date_sent or c.date_pushed}")
    return 0


# --- parser ------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="outreach", description="Finance networking outreach tool")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("init", help="check setup, parse resume, create the contacts workbook")
    s.add_argument("--refresh-resume", action="store_true", help="re-parse resume.pdf even if cached")
    s.set_defaults(fn=cmd_init)

    s = sub.add_parser("firms", help="list firms in firms.csv")
    s.add_argument("--type", nargs="*", help="IB AM WM RE PE")
    s.add_argument("--search")
    s.set_defaults(fn=cmd_firms)

    s = sub.add_parser("add", help="add contacts by pasting lines or importing a CSV")
    s.add_argument("--firm", help="default firm for lines without one")
    s.add_argument("--csv", help="CSV with Name/First/Last, Title, Firm, LinkedIn, Notes, Email columns")
    s.add_argument("--referred-by", help='e.g. "Jane Smith" - the draft then opens with the referral')
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("import-leads", help="import a warm-leads workbook (rosters x BrokerCheck)")
    s.add_argument("path")
    s.add_argument("--sheet", default="Warm Leads")
    s.add_argument("--tier", nargs="+", default=["strong"],
                   help="strong / review / weak / all (default: strong)")
    s.add_argument("--min-confidence", type=float, default=0.75)
    s.add_argument("--keep-unmapped", action="store_true",
                   help="keep leads whose firm is not in firms.csv (no email will be generated)")
    s.add_argument("--limit", type=int)
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_import_leads)

    s = sub.add_parser("find", help="search Apollo for people at a firm")
    s.add_argument("--firm")
    s.add_argument("--all", action="store_true", help="every active firm (use with --type)")
    s.add_argument("--type", nargs="*")
    s.add_argument("--title", action="append", help="repeatable, e.g. --title Analyst --title Associate")
    s.add_argument("--location", action="append", help="repeatable, e.g. --location 'Los Angeles, California'")
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--enrich", action="store_true", help="spend Apollo credits to reveal emails")
    s.add_argument("--phone", action="store_true", help="also request phone numbers when enriching")
    s.set_defaults(fn=cmd_find)

    s = sub.add_parser("email", help="fill work emails from firm patterns; --verify uses Hunter")
    s.add_argument("--firm")
    s.add_argument("--verify", action="store_true")
    s.add_argument("--group")
    s.add_argument("--id", nargs="*", help="only these contact IDs")
    s.add_argument("--skip-flagged", action="store_true",
                   help="skip contacts whose identity is unverified (review tier / shares a name)")
    s.set_defaults(fn=cmd_email)

    s = sub.add_parser("draft", help="write personalized drafts with Claude")
    s.add_argument("--firm")
    s.add_argument("--priority", type=int, help="only priority <= N")
    s.add_argument("--limit", type=int)
    s.add_argument("--id", nargs="*", help="specific contact IDs")
    s.add_argument("--redo", action="store_true", help="regenerate existing drafts")
    s.add_argument("--show", action="store_true", help="print each draft")
    s.add_argument("--style", choices=["template", "claude"], default="template",
                   help="template (default): Josh's fixed email with the tie sentence adapted per contact; "
                        "claude: model-written middle paragraph")
    s.add_argument("--model", choices=["auto", *config.MODEL_ALIASES], default="auto",
                   help=f"auto (default): opus for priority 1, {config.MODEL_DRAFT} for the rest. "
                        "Force one model to control usage.")
    s.set_defaults(fn=cmd_draft)

    s = sub.add_parser("push", help="create Gmail drafts for status=Drafted contacts")
    s.add_argument("--firm")
    s.add_argument("--group", help='e.g. "Wealth Management"')
    s.add_argument("--limit", type=int)
    s.add_argument("--id", nargs="*")
    s.add_argument("--no-attach", action="store_true", help="don't attach resume.pdf")
    s.add_argument("--force", action="store_true",
                   help="push even contacts flagged as unverified identities")
    s.add_argument("--all", action="store_true",
                   help=f"allow pushing more than {PUSH_CONFIRM_ABOVE} contacts without a filter")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_push)

    s = sub.add_parser("roster", help="list athletes from public Claremont team rosters")
    s.add_argument("--school", choices=["pp", "cms"], default="pp",
                   help="pp = Pomona-Pitzer (Sagehens), cms = Claremont-Mudd-Scripps")
    s.add_argument("--sport", nargs="+", default=["football"],
                   help="URL slug(s) e.g. football mens-golf; or 'finance' for the sports whose "
                        "alumni most often end up in finance; or 'all' for every sport")
    s.add_argument("--name", help="filter to names containing this string")
    s.add_argument("--from-year", type=int, default=2014)
    s.add_argument("--to-year", type=int, default=2022)
    s.add_argument("--out", help="write the lines to a file")
    s.add_argument("--no-cache", action="store_true")
    s.set_defaults(fn=cmd_roster)

    s = sub.add_parser("show", help="print existing drafts from the sheet")
    s.add_argument("--firm")
    s.add_argument("--priority", type=int)
    s.add_argument("--status")
    s.add_argument("--id", nargs="*")
    s.add_argument("--limit", type=int)
    s.add_argument("--notes", action="store_true",
                   help="print call notes instead of the outbound draft (includes contacts with no draft)")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("auth-gmail", help="authorize Gmail (opens a browser once)")
    s.set_defaults(fn=cmd_auth_gmail)

    s = sub.add_parser("sync", help="write best contact per firm into the internship tracker")
    s.add_argument("--force", action="store_true", help="overwrite non-empty Networking Contact cells")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("status", help="pipeline summary")
    s.set_defaults(fn=cmd_status)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except SheetError as e:
        print(f"spreadsheet error: {e}")
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
