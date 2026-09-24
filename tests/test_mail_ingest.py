"""Ticketing Pro todo 8: email-to-ticket inbox preview/confirm (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FAKE_MAILS = [
    {
        "uid": "101",
        "from": "korisnik@firma.mk",
        "subject": "Принтерот молчи",
        "body": "Во канцеларија 3 не печати од вчера.",
        "message_id": "<m101>",
    },
    {
        "uid": "102",
        "from": "korisnik@firma.mk",
        "subject": "Re: [I-000001] Принтер",
        "body": "Уште го има проблемот.",
        "message_id": "<m102>",
    },
    {
        "uid": "103",
        "from": "drug@firma.mk",
        "subject": "Принтерот молчи",
        "body": "Исто и кај мене.",
        "message_id": "<m101>",
    },
]


class FakeIMAP:
    def __init__(self, mails, fail=False):
        self._mails = mails
        self.fail = fail

    def fetch_unseen(self):
        if self.fail:
            raise ConnectionError("unreachable")
        return list(self._mails)


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import COMMENT_COLS, INCIDENT_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "mail.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "comments", DbStore(db, "comments", COMMENT_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    from services.incident_service import IncidentService

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    inc = svc.create(asset_id="AST001", title="Принтер", performed_by="admin")
    assert inc["IncidentID"] == "I000001"
    return app_mod


def test_reconcile_verdicts(monkeypatch):
    from services.mail_ingest import reconcile

    app_mod = _env(monkeypatch)
    try:
        out = reconcile(FAKE_MAILS, app_mod.incidents, app_mod.comments)
        by_uid = {m["uid"]: m["verdict"] for m in out}
        assert by_uid == {"101": "new", "102": "reply", "103": "duplicate"}
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()


def test_confirm_writes_incidents_and_comment(monkeypatch):
    from services.mail_ingest import confirm, reconcile

    app_mod = _env(monkeypatch)
    try:
        rows = reconcile(FAKE_MAILS, app_mod.incidents, app_mod.comments)
        counts = confirm(
            rows,
            app_mod.incidents,
            app_mod.comments,
            app_mod.history,
            performed_by="admin",
            db_path=getattr(app_mod.incidents, "db_path", None),
        )
        assert counts == {"new": 1, "replies": 1, "skipped": 1}
        assert len(app_mod.incidents.records()) == 2
        assert len(app_mod.comments.records()) == 1
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()


def test_unreachable_zero_writes(monkeypatch):
    import pytest

    from services.mail_ingest import MailError, fetch_unseen

    app_mod = _env(monkeypatch)
    try:
        with pytest.raises(MailError):
            fetch_unseen(connection_factory=lambda: FakeIMAP([], fail=True))
        assert len(app_mod.incidents.records()) == 1
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()
