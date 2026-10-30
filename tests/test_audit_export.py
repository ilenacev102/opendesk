"""MS-6: one-click audit evidence export."""

import os
import sys
import tempfile
from datetime import date

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _row(day, action="ASSIGN", asset="AST001"):
    return {
        "DateTime": day + " 10:00",
        "Action": action,
        "AssetID": asset,
        "PerformedBy": "mag",
        "Reason": "Доделено",
    }


def test_empty_period_returns_nothing():
    from services.audit_export import export_changes

    rows = [_row("2026-01-05")]
    assert export_changes(rows, "2026-02-01", "2026-02-28") == []


def test_period_with_two_records_mapped():
    from services.audit_export import export_changes

    rows = [_row("2026-01-05"), _row("2026-01-20", action="RETURN"), _row("2026-03-01")]
    out = export_changes(rows, "2026-01-01", "2026-01-31")
    assert [(e["who"], e["what"], e["why"]) for e in out] == [
        ("mag", "ASSIGN AST001", "Доделено"),
        ("mag", "RETURN AST001", "Доделено"),
    ]


def test_bad_range_rejected():
    from services.audit_export import export_changes

    with pytest.raises(ValueError):
        export_changes([], "2026-02-01", "2026-01-01")
    with pytest.raises(ValueError):
        export_changes([], "не-датум", "2026-01-01")


def test_audit_export_route(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService

    tmp = tempfile.mkdtemp()
    hist = HistoryService(DbStore(os.path.join(tmp, "ae.db"), "history", HISTORY_COLS))
    today = date.today().isoformat()
    hist.log(
        "ASSIGN", "AST001", "", "Assigned", "EMP001", "", "Доделено", "", "mag", ""
    )
    monkeypatch.setattr(app_mod, "history", hist)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        assert c.get("/reports/audit-export?from=x&to=y").status_code == 400
        r = c.get(f"/reports/audit-export?from={today}&to={today}")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        assert "when,who,what,why" in body
        assert "ASSIGN AST001" in body
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()
