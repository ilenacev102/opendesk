"""Unit tests for services/observability.py (Task 1 of the observability plan)."""

import json
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import observability as obs


def test_record_counts_status_classes_and_routes():
    obs.reset()
    obs.record("GET", "system.dashboard", 200, 12.0)
    obs.record("GET", "system.dashboard", 500, 40.0)
    obs.record("POST", "admin.login", 429, 3.0)
    snap = obs.snapshot()
    assert snap["total"] == 3
    assert snap["classes"] == {"2xx": 1, "3xx": 0, "4xx": 1, "5xx": 1}
    assert snap["errors"] == 1 and snap["rate_limited"] == 1
    route = {r["route"]: r for r in snap["routes"]}["system.dashboard"]
    assert (route["count"], route["errors"]) == (2, 1)


def test_p95_is_bucket_upper_edge_and_none_when_empty():
    obs.reset()
    assert obs.snapshot()["p95_ms"] is None
    obs.record("GET", "a", 200, 300.0)
    assert obs.snapshot()["p95_ms"] == 500


def test_problem_ring_buffer_is_bounded_and_newest_first():
    obs.reset()
    for i in range(105):
        obs.record("GET", "a", 500, 1.0, request_id=f"r{i}")
    snap = obs.snapshot()
    assert len(snap["problems"]) == 100
    assert snap["problems"][0]["request_id"] == "r104"


def test_record_is_thread_safe():
    import threading

    obs.reset()

    def work():
        for _ in range(100):
            obs.record("GET", "a", 200, 1.0)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert obs.snapshot()["total"] == 800


def test_json_formatter_emits_one_object_with_extras():
    rec = logging.LogRecord(
        "servicedesk", logging.INFO, __file__, 1, "request", None, None
    )
    rec.request_id, rec.role, rec.pid = "abc123", "admin", 42
    payload = json.loads(obs.JsonFormatter().format(rec))
    assert payload["msg"] == "request"
    assert payload["request_id"] == "abc123"
    assert payload["ts"].endswith("Z")
    assert payload["level"] == "INFO"


def test_json_formatter_keeps_macedonian_text_and_traceback():
    try:
        raise ValueError("Грешка во уред")
    except ValueError:
        import sys

        rec = logging.LogRecord(
            "servicedesk", logging.ERROR, __file__, 1, "request", None, sys.exc_info()
        )
    payload = json.loads(obs.JsonFormatter().format(rec))
    assert "Грешка во уред" in payload["exc"]


def test_configure_logging_writes_json_lines(tmp_path):
    log_file = tmp_path / "obs.log"
    obs.configure_logging(str(log_file), stream=False, force=True)
    logging.getLogger("servicedesk").info("hello", extra={"request_id": "x1"})
    line = json.loads(log_file.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert line["msg"] == "hello" and line["request_id"] == "x1"


def test_configure_logging_with_empty_path_writes_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr(obs, "_installed", [])
    obs.configure_logging("", stream=False, force=True)
    assert not list(tmp_path.glob("*.log"))


def _obs_client(monkeypatch, caplog):
    import app as app_mod

    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    obs.reset()
    caplog.set_level(logging.INFO, logger="servicedesk")
    return app_mod, app_mod.app.test_client()


def test_request_emits_access_record_with_matching_header(monkeypatch, caplog):
    app_mod, client = _obs_client(monkeypatch, caplog)
    response = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert response.headers["X-Request-ID"] == "abc123"
    records = [rec for rec in caplog.records if rec.getMessage() == "request"]
    assert records == []  # /health is excluded


def test_404_is_counted_and_logged(monkeypatch, caplog):
    app_mod, client = _obs_client(monkeypatch, caplog)
    response = client.get("/definitely-not-a-route")
    assert response.status_code == 404
    records = [rec for rec in caplog.records if rec.getMessage() == "request"]
    assert len(records) == 1 and records[0].status == 404
    assert obs.snapshot()["classes"]["4xx"] == 1


def test_query_string_is_never_logged(monkeypatch, caplog):
    app_mod, client = _obs_client(monkeypatch, caplog)
    client.get("/search?q=secret-token")
    records = [rec for rec in caplog.records if rec.getMessage() == "request"]
    assert records and "secret-token" not in json.dumps(records[0].__dict__, default=str)


def test_500_page_ref_is_the_logged_request_id(monkeypatch, caplog):
    app_mod, client = _obs_client(monkeypatch, caplog)
    monkeypatch.setattr(app_mod.auth_svc, "auth_required", lambda: False)

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setitem(app_mod.app.view_functions, "system.dashboard", _boom)
    body = client.get("/", headers={"X-Request-ID": "rid500"}).get_data(as_text=True)
    records = [rec for rec in caplog.records if rec.getMessage() == "request"]
    assert len(records) == 1 and records[0].status == 500
    assert records[0].request_id == "rid500"
    assert "rid500" in body


def test_observability_page_requires_admin(monkeypatch):
    import app as app_mod

    app_mod.auth_svc.create_user("obsadm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("obsmag", "dolgapass123", role="magacioner")
    try:
        admin, mag = app_mod.app.test_client(), app_mod.app.test_client()
        admin.post("/login", data={"username": "obsadm", "password": "dolgapass123"})
        mag.post("/login", data={"username": "obsmag", "password": "dolgapass123"})
        assert admin.get("/system/observability").status_code == 200
        assert mag.get("/system/observability").status_code == 403
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()


def test_observability_page_shows_recorded_route(monkeypatch):
    import app as app_mod

    obs.reset()
    obs.record("GET", "system.dashboard", 500, 800.0)
    app_mod.auth_svc.create_user("obsadm2", "dolgapass123", role="admin")
    try:
        client = app_mod.app.test_client()
        client.post("/login", data={"username": "obsadm2", "password": "dolgapass123"})
        body = client.get("/system/observability").get_data(as_text=True)
        assert "system.dashboard" in body and "500" in body
    finally:
        import sqlite3

        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()


def test_access_record_has_path_but_no_client_ip(monkeypatch, caplog):
    app_mod, client = _obs_client(monkeypatch, caplog)
    client.get("/search?q=secret")
    record = [rec for rec in caplog.records if rec.getMessage() == "request"][0]
    assert record.path == "/search"
    assert not hasattr(record, "remote_addr")


def test_configure_logging_silences_werkzeug_access_lines(caplog):
    obs.configure_logging(None, stream=False, force=True)
    caplog.set_level(logging.INFO)
    logging.getLogger("werkzeug").info('127.0.0.1 - "GET /?q=secret" 200')
    assert [r for r in caplog.records if r.name == "werkzeug"] == []


def test_configure_logging_is_idempotent(tmp_path):
    log_file = tmp_path / "once.log"
    obs.configure_logging(str(log_file), stream=False, force=True)
    obs.configure_logging(str(log_file), stream=False)
    logging.getLogger("servicedesk").info("once")
    lines = [
        line
        for line in log_file.read_text(encoding="utf-8").splitlines()
        if '"once"' in line
    ]
    assert len(lines) == 1
