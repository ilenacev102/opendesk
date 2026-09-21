"""Phase E: hardening (TDD). Rate limiter unit + abuse tests on isolated app."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import ratelimit as rl


def test_bucket_allows_then_blocks():
    rl.reset()
    assert all(rl.is_allowed("k", 3, 60, now=1000.0 + i) for i in range(3))
    assert rl.is_allowed("k", 3, 60, now=1003.0) is False


def test_window_slides():
    rl.reset()
    assert rl.is_allowed("k2", 1, 60, now=1000.0) is True
    assert rl.is_allowed("k2", 1, 60, now=1030.0) is False
    assert rl.is_allowed("k2", 1, 60, now=1061.0) is True


def test_keys_are_independent():
    rl.reset()
    assert rl.is_allowed("a", 1, 60, now=1000.0) is True
    assert rl.is_allowed("b", 1, 60, now=1000.0) is True
    assert rl.is_allowed("a", 1, 60, now=1000.0) is False


def _hard_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "h.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    rl.reset()
    return app_mod


def test_login_bruteforce_blocked(monkeypatch):
    app_mod = _hard_env(monkeypatch)
    c = app_mod.app.test_client()
    codes = [
        c.post("/login", data={"username": "x", "password": "y"}).status_code
        for _ in range(40)
    ]
    assert 429 in codes


def test_foreign_origin_post_rejected(monkeypatch):
    app_mod = _hard_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/login",
        data={"username": "x", "password": "y"},
        headers={"Origin": "https://evil.example"},
    )
    assert r.status_code == 403


def test_same_origin_post_allowed(monkeypatch):
    app_mod = _hard_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/login",
        data={"username": "x", "password": "y"},
        headers={"Origin": "http://localhost"},
    )
    assert r.status_code in (200, 302)


def test_non_csv_upload_rejected(monkeypatch):
    import io

    app_mod = _hard_env(monkeypatch)
    r = app_mod.app.test_client().post(
        "/import",
        data={
            "kind": "devices",
            "file": (io.BytesIO(b"MZ\x90\x00evil"), "payload.exe"),
        },
    )
    assert r.status_code == 200
    assert app_mod.devices.records() == []
