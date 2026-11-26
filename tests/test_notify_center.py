"""F2: in-app notifications (bell)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _store():
    from services.db_service import DbStore
    from services.schemas import NOTIF_COLS

    tmp = tempfile.mkdtemp()
    return DbStore(os.path.join(tmp, "notif.db"), "notifications", NOTIF_COLS)


def test_push_and_unread():
    from services.notify_center import push, unread

    store = _store()
    row = push(store, "mag", "incident", "I-1", "Ескалиран тикет I-1.")
    assert row is not None
    assert row["NotifID"].startswith("N")
    assert len(unread(store, "mag")) == 1
    assert unread(store, "drug") == []


def test_mark_read_one_and_all():
    from services.notify_center import mark_read, push, unread

    store = _store()
    push(store, "mag", "incident", "I-1", "a")
    push(store, "mag", "transit", "A1", "b")
    first = unread(store, "mag")[0]["NotifID"]
    assert mark_read(store, "mag", first) == 1
    assert len(unread(store, "mag")) == 1
    assert mark_read(store, "mag") == 1
    assert unread(store, "mag") == []


def test_empty_username_never_writes():
    from services.notify_center import push

    store = _store()
    assert push(store, "", "incident", "I-1", "x") is None
    assert push(store, "   ", "incident", "I-1", "x") is None
    assert store.records() == []


def test_kind_gate():
    import pytest

    from services.notify_center import validate_kind
    from utils.validators import ValidationError

    assert validate_kind("incident") == "incident"
    with pytest.raises(ValidationError):
        validate_kind("spam")


def test_notifications_page_and_badge(monkeypatch):
    from services import ratelimit as rl

    rl.reset()
    import app as app_mod
    from services.db_service import DbStore
    from services.notify_center import push
    from services.schemas import NOTIF_COLS

    tmp = tempfile.mkdtemp()
    notif_store = DbStore(os.path.join(tmp, "notif_ui.db"), "notifications", NOTIF_COLS)
    push(notif_store, "mag", "incident", "I-1", "Ескалиран тикет I-1.")
    monkeypatch.setattr(app_mod, "notifications", notif_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    try:
        c = app_mod.app.test_client()
        c.post("/login", data={"username": "mag", "password": "dolgapass123"})
        body = c.get("/notifications").get_data(as_text=True)
        assert "I-1" in body
        home = c.get("/").get_data(as_text=True)
        assert 'aria-label="Известувања, 1 непрочитани"' in home
        assert 'nav-unread-badge">1<' in home
        assert c.post("/notifications/read", data={}).status_code == 302
        after = c.get("/").get_data(as_text=True)
        assert "nav-unread-badge" not in after
        assert 'aria-label="Известувања"' in after
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()
