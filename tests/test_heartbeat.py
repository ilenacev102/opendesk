"""Discovery Pro todo 1: heartbeat API endpoint (TDD)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAYLOAD = {
    "hostname": "PC-01",
    "serial": "HB001",
    "manufacturer": "Dell",
    "model": "Latitude 5440",
    "os": "Win11",
}


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, STAGING_COLS

    import tempfile

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "hb.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "staging", DbStore(db, "staging", STAGING_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("agent", "dolgapass123", role="magacioner")
    plain = app_mod.token_svc.create("agent", "heartbeat")
    return app_mod, {"Authorization": f"Bearer {plain}"}


def _wipe_auth():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.execute("DELETE FROM api_tokens")
    con.commit()
    con.close()


def test_heartbeat_new_match_conflict(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers)
        assert r.status_code == 200
        assert r.get_json()["verdict"] == "new"
        r2 = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers)
        assert r2.get_json()["verdict"] == "match"
        app_mod.devices.update_where(
            "SerialNumber", "HB001", {"Status": "Assigned", "EmployeeID": "E1"}
        )
        r3 = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers)
        assert r3.get_json()["verdict"] == "conflict"
    finally:
        _wipe_auth()


def test_heartbeat_missing_serial_400(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post(
            "/api/v1/discovery/heartbeat", json={"hostname": "PC-02"}, headers=headers
        )
        assert r.status_code == 400
    finally:
        _wipe_auth()


def test_heartbeat_no_token_401(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD)
        assert r.status_code == 401
    finally:
        _wipe_auth()


def test_heartbeat_bad_token_401(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post(
            "/api/v1/discovery/heartbeat",
            json=PAYLOAD,
            headers={"Authorization": "Bearer wrong"},
        )
        assert r.status_code == 401
    finally:
        _wipe_auth()


def test_heartbeat_rate_limited(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        last = None
        for _ in range(125):
            last = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers)
        assert last is not None
        assert last.status_code == 429
        assert last.headers.get("Retry-After") == "60"
    finally:
        from services import ratelimit as rl

        rl.reset()
        _wipe_auth()
