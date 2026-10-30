"""Discovery Pro todo 3: heartbeat reconcile/confirm reuse + concurrency."""

import os
import sys
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PAYLOAD = {
    "hostname": "PC-FLOW",
    "serial": "FLOW001",
    "manufacturer": "Dell",
    "model": "Latitude",
    "os": "Win11",
}


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, STAGING_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "flow.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "staging", DbStore(db, "staging", STAGING_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.auth_svc.create_user("agent", "dolgapass123", role="magacioner")
    plain = app_mod.token_svc.create("agent", "flow")
    return app_mod, {"Authorization": f"Bearer {plain}"}


def _wipe_auth():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.execute("DELETE FROM api_tokens")
    con.commit()
    con.close()


def test_flow_counts_and_summary(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        c = app_mod.app.test_client()
        r = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers)
        assert r.get_json()["verdict"] == "new"
        dev = app_mod.devices.find("SerialNumber", "FLOW001")
        assert dev is not None and dev["Status"] == "Available"
        summaries = [
            h
            for h in app_mod.history.store.records()
            if h.get("Action") == "DISCOVERY_IMPORT"
        ]
        assert len(summaries) == 1
        assert (
            "Source" in summaries[0].get("Reason", "")
            or "agent" in summaries[0].get("Reason", "").lower()
            or "new=1" in summaries[0].get("Reason", "")
        )
        r2 = c.post("/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers)
        assert r2.get_json()["verdict"] == "match"
    finally:
        from services import ratelimit as rl

        rl.reset()
        _wipe_auth()


def test_concurrent_same_serial_single_row(monkeypatch):
    app_mod, headers = _env(monkeypatch)
    try:
        errors = []

        def _hit():
            try:
                client = app_mod.app.test_client()
                resp = client.post(
                    "/api/v1/discovery/heartbeat", json=PAYLOAD, headers=headers
                )
                assert resp.status_code in (200, 429)
            except Exception as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=_hit) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors
        rows = app_mod.devices.filter_eq("SerialNumber", "FLOW001")
        assert len(rows) == 1
        ids = [d["AssetID"] for d in app_mod.devices.records()]
        assert len(ids) == len(set(ids))
    finally:
        from services import ratelimit as rl

        rl.reset()
        _wipe_auth()
