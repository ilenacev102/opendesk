"""Ticketing Pro todo 7: KB links + resolve-from-article (TDD)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS, KB_COLS, KB_LINK_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "kbl.db")
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "kb_articles", DbStore(db, "kb_articles", KB_COLS))
    monkeypatch.setattr(app_mod, "kb_links", DbStore(db, "kb_links", KB_LINK_COLS))
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
    inc = svc.create(asset_id="AST001", title="Принтер молчи", performed_by="admin")
    svc.transition(inc["IncidentID"], "in-progress", performed_by="admin")
    app_mod.kb_articles.append_row(
        {
            "ArticleID": "KB000001",
            "Title": "Принтер не печати",
            "Body": "Провери кабел.",
            "Tags": "принтер",
            "Created": "2026-09-01 10:00",
            "Updated": "2026-09-01 10:00",
        }
    )
    return app_mod, inc["IncidentID"]


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def test_link_and_list(monkeypatch):
    from services.kb_link_service import KbLinkService

    app_mod, iid = _env(monkeypatch)
    try:
        svc = KbLinkService(
            app_mod.kb_links,
            app_mod.incidents,
            app_mod.kb_articles,
            app_mod.history,
            db_path=getattr(app_mod.kb_links, "db_path", None),
        )
        svc.link(iid, "KB000001", performed_by="admin")
        linked = svc.for_incident(iid)
        assert [a["ArticleID"] for a in linked] == ["KB000001"]
    finally:
        _wipe_users()


def test_duplicate_link_blocked(monkeypatch):
    import pytest

    from services.kb_link_service import KbLinkService

    app_mod, iid = _env(monkeypatch)
    try:
        svc = KbLinkService(
            app_mod.kb_links,
            app_mod.incidents,
            app_mod.kb_articles,
            app_mod.history,
            db_path=getattr(app_mod.kb_links, "db_path", None),
        )
        svc.link(iid, "KB000001", performed_by="admin")
        with pytest.raises(ValueError):
            svc.link(iid, "KB000001", performed_by="admin")
        assert len(app_mod.kb_links.records()) == 1
    finally:
        _wipe_users()


def test_link_unknown_sides_rejected(monkeypatch):
    import pytest

    from services.kb_link_service import KbLinkService

    app_mod, iid = _env(monkeypatch)
    try:
        svc = KbLinkService(
            app_mod.kb_links,
            app_mod.incidents,
            app_mod.kb_articles,
            app_mod.history,
            db_path=getattr(app_mod.kb_links, "db_path", None),
        )
        with pytest.raises(ValueError):
            svc.link("I999999", "KB000001", performed_by="admin")
        with pytest.raises(ValueError):
            svc.link(iid, "KB999999", performed_by="admin")
    finally:
        _wipe_users()


def test_resolve_from_article(monkeypatch):
    from services.kb_link_service import KbLinkService

    app_mod, iid = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        svc = KbLinkService(
            app_mod.kb_links,
            app_mod.incidents,
            app_mod.kb_articles,
            app_mod.history,
            db_path=getattr(app_mod.kb_links, "db_path", None),
        )
        svc.link(iid, "KB000001", performed_by="admin")
        resolved = svc.resolve_from_article(iid, "KB000001", performed_by="admin")
        assert resolved["Status"] == "resolved"
        assert resolved["ClosedAt"] != ""
        assert "KB000001" in resolved.get("Notes", "")
        html = c.get(f"/incident/{iid}").get_data(as_text=True)
        assert "KB000001" in html
    finally:
        _wipe_users()
