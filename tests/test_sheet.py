from pathlib import Path

from outreach.models import Contact, STATUS_DRAFTED, STATUS_SENT
from outreach.sheet import ContactSheet, SheetError


def test_roundtrip_and_dedup(tmp_path: Path):
    p = tmp_path / "c.xlsx"
    s = ContactSheet(p)
    added, skipped = s.add([
        Contact(firm="Baird", first="Jane", last="Doe", title="Analyst", priority=2, draft="Hi Jane,\n\nline"),
        Contact(firm="Baird", first="jane", last="DOE", title="dupe"),
        Contact(firm="PIMCO", first="Al", last="Bo", priority=1, claremont_alum=True),
    ])
    assert len(added) == 2 and len(skipped) == 1
    s.save()

    s2 = ContactSheet(p)
    assert [c.name for c in s2.contacts] == ["Al Bo", "Jane Doe"]  # sorted by priority
    assert s2.contacts[0].id == "C0002" and s2.contacts[1].id == "C0001"
    assert s2.contacts[0].claremont_alum is True
    assert s2.contacts[1].draft == "Hi Jane,\n\nline"
    # re-adding is a no-op
    added, skipped = s2.add([Contact(firm="PIMCO", first="Al", last="Bo")])
    assert not added and len(skipped) == 1


def test_select_and_best_by_firm(tmp_path: Path):
    s = ContactSheet(tmp_path / "c.xlsx")
    s.add([
        Contact(firm="Baird", first="A", last="One", priority=2, status=STATUS_DRAFTED, email="a@x"),
        Contact(firm="Baird", first="B", last="Two", priority=2, status=STATUS_SENT, email="b@x"),
        Contact(firm="Baird", first="C", last="Three", priority=1),
    ])
    assert [c.first for c in s.select(status=STATUS_DRAFTED)] == ["A"]
    assert [c.first for c in s.select(priority=1)] == ["C"]
    assert s.best_by_firm()["Baird"].first == "C"  # priority beats status


def test_header_mismatch_refused(tmp_path: Path):
    from openpyxl import Workbook
    p = tmp_path / "bad.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "Contacts"; ws.append(["Wrong", "Header"]); wb.save(p)
    try:
        ContactSheet(p)
    except SheetError as e:
        assert "Header mismatch" in str(e)
    else:
        raise AssertionError("expected SheetError")


def test_older_header_migrates(tmp_path: Path):
    """A workbook written before a column was appended still loads; the new column reads empty."""
    from openpyxl import Workbook, load_workbook
    from outreach.models import COLUMNS
    p = tmp_path / "old.xlsx"
    wb = Workbook(); ws = wb.active; ws.title = "Contacts"
    ws.append(COLUMNS[:-1])
    row = Contact(firm="Baird", first="Jane", last="Doe", draft="hi").to_row()[:-1]
    ws.append(row); wb.save(p)

    s = ContactSheet(p)
    assert s.migrated_from == len(COLUMNS) - 1
    assert s.contacts[0].name == "Jane Doe" and s.contacts[0].draft_model == ""
    s.save()
    assert [c.value for c in load_workbook(p)["Contacts"][1]] == COLUMNS


def test_conversations_tab_holds_only_people_talked_to(tmp_path: Path):
    from outreach.sheet import CONVOS
    from openpyxl import load_workbook
    p = tmp_path / "c.xlsx"
    s = ContactSheet(p)
    s.add([
        Contact(firm="Merrill", first="Jack", last="D", status="Chat Done",
                reply_notes="said start as a client associate"),
        Contact(firm="PIMCO", first="Eben", last="A", status="Chat Done", reply_notes="fixed income"),
        Contact(firm="Baird", first="No", last="Contact", status="Drafted"),
    ])
    s.save()
    wb = load_workbook(p)
    assert wb.sheetnames[0] == CONVOS          # first tab, so it's what opens
    ws = wb[CONVOS]
    names = [ws.cell(row=r, column=1).value for r in range(2, ws.max_row + 1)]
    assert names == ["Jack D", "Eben A"] and "No Contact" not in names   # sorted by firm
    assert ws.cell(row=2, column=8).value == "said start as a client associate"
