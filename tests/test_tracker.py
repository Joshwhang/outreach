from pathlib import Path

from openpyxl import Workbook, load_workbook

from outreach.models import Contact, STATUS_SENT
from outreach.tracker import sync


def make_tracker(p: Path):
    wb = Workbook(); ws = wb.active; ws.title = "Tracker"
    ws.append(["Firm", "Type", "Program", "Location", "Apps Open", "Deadline", "Status", "Date Applied",
               "Networking Contact", "Contact Status", "Notes"])
    ws.append(["Baird", "IB", "", "", "", "", "", "", "e.g. Jane Doe, Analyst", "Coffee chat done", ""])
    ws.append(["Robert W. Baird", "IB", "", "", "", "", "", "", None, "Not contacted", ""])
    ws.append(["PIMCO", "AM", "", "", "", "", "", "", "My own note", "Ongoing", ""])
    ws.append(["Hines", "RE", "", "", "", "", "", "", None, None, ""])
    ws.append(["How to use:", None])
    wb.save(p)


def test_sync_fills_empty_and_example_cells_only(tmp_path: Path, firms, monkeypatch):
    monkeypatch.setattr("outreach.tracker.BACKUP_DIR", tmp_path / "bk")
    p = tmp_path / "t.xlsx"; make_tracker(p)
    best = {
        "Baird": Contact(firm="Baird", first="Al", last="Bo", title="Analyst", status=STATUS_SENT, claremont_alum=True),
        "PIMCO": Contact(firm="PIMCO", first="C", last="D", title="VP"),
    }
    changes = sync(best, firms, path=p)
    assert [c[0] for c in changes] == ["Baird", "Robert W. Baird"]
    ws = load_workbook(p)["Tracker"]
    assert ws["I2"].value == "Al Bo, Analyst, Claremont alum" and ws["J2"].value == "Emailed"
    assert ws["I3"].value == "Al Bo, Analyst, Claremont alum"
    assert ws["I4"].value == "My own note"  # untouched
    assert (tmp_path / "bk").exists() and list((tmp_path / "bk").iterdir())


def test_sync_force_and_dry_run(tmp_path: Path, firms, monkeypatch):
    monkeypatch.setattr("outreach.tracker.BACKUP_DIR", tmp_path / "bk")
    p = tmp_path / "t.xlsx"; make_tracker(p)
    best = {"PIMCO": Contact(firm="PIMCO", first="C", last="D", title="VP")}
    assert sync(best, firms, path=p, dry_run=True) == []
    changes = sync(best, firms, path=p, force=True, dry_run=True)
    assert changes == [("PIMCO", "C D, VP", "Not contacted")]
    assert load_workbook(p)["Tracker"]["I4"].value == "My own note"  # dry run wrote nothing
