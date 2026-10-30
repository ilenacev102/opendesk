"""Analytics todo 3: monthly email summary manual trigger (TDD service)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

STATS = {
    "total_devices": 42,
    "assigned": 30,
    "warranty_fc": {"expired": 2, "d30": 3, "d60": 1, "d90": 0},
    "costs_total": 125000.0,
    "inc_open": 5,
    "breach_open": 2,
    "escalated": 1,
    "mttr": 26.0,
    "month": "2026-09",
}


def test_summary_email_composes():
    from services.notify_service import summary_email

    to, subject, body = summary_email("a@x.mk", STATS)
    assert to == "a@x.mk"
    assert "2026-09" in subject
    for needle in ("42", "MTTR", "26.0", "пробиени", "ескалирани", "Гарантна"):
        assert needle in body, needle


def test_summary_email_empty_stats():
    from services.notify_service import summary_email

    to, subject, body = summary_email("a@x.mk", {})
    assert to == "a@x.mk"
    assert isinstance(body, str) and body != ""


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "mon.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")
    return app_mod


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user, pw="dolgapass123"):
    return client.post("/login", data={"username": user, "password": pw})


def test_monthly_trigger_redirects_and_flashes(monkeypatch):
    app_mod = _env(monkeypatch)
    monkeypatch.setenv("SERVICEDESK_ADMIN_EMAIL", "a@x.mk")
    try:
        c = app_mod.app.test_client()
        _login(c, "adm")
        r = c.post("/reports/monthly-summary")
        assert r.status_code == 302
        with c.session_transaction() as sess:
            flashes = sess.get("_flashes", [])
        assert any(
            "извештај" in msg or "Digest" in msg or "mail" in msg for _, msg in flashes
        ), flashes
    finally:
        _wipe_users()


def test_citac_monthly_blocked(monkeypatch):
    app_mod = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        _login(c, "cit")
        assert c.post("/reports/monthly-summary").status_code == 403
    finally:
        _wipe_users()
