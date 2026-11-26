"""Sprint 6: outgoing webhooks — service, async dispatch, admin UI, event wiring."""

import hashlib
import hmac as hmac_mod
import json
import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schemas import WEBHOOK_COLS


def _store(db, table, cols):
    from services.db_service import DbStore

    return DbStore(db, table, cols)


def _db():
    return os.path.join(tempfile.mkdtemp(), "webhooks.db")


def _svc(store):
    from services import webhook_service

    return webhook_service


def test_webhook_create_validates_name_and_url():
    from services import webhook_service
    from utils.validators import ValidationError

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    with pytest.raises(ValidationError):
        webhook_service.create(webhooks, "", "https://x.y/hook")
    with pytest.raises(ValidationError):
        webhook_service.create(webhooks, "Slack", "ftp://not-http")
    with pytest.raises(ValidationError):
        webhook_service.create(webhooks, "Slack", "not-a-url")
    with pytest.raises(ValidationError):
        webhook_service.create(
            webhooks, "Slack", "https://", events="problem.resolved"
        )  # no host
    with pytest.raises(ValidationError):
        webhook_service.create(
            webhooks,
            "Slack",
            "https://x.y/hook with space",
            events="problem.resolved",
        )
    with pytest.raises(ValidationError):
        webhook_service.create(
            webhooks,
            "Slack",
            "https://x.y/hook\nX-Evil: 1",
            events="problem.resolved",
        )
    row = webhook_service.create(
        webhooks, "Slack", "https://x.y/hook", events="problem.resolved"
    )
    assert row["Url"] == "https://x.y/hook"
    assert len(webhooks.records()) == 1


def test_webhook_create_rejects_unknown_events():
    from services import webhook_service
    from utils.validators import ValidationError

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    with pytest.raises(ValidationError):
        webhook_service.create(
            webhooks, "Slack", "https://x.y/hook", events="incident.created"
        )
    with pytest.raises(ValidationError):
        webhook_service.create(webhooks, "Slack", "https://x.y/hook", events="")
    assert webhooks.records() == []


def test_webhook_create_assigns_defaults():
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    row = webhook_service.create(
        webhooks,
        "Ops Channel",
        "https://hooks.slack.com/services/T/B/XXX",
        events="incident.critical_created, problem.resolved",
    )
    assert row["WebhookID"].startswith("WH")
    assert row["Active"] == "YES"
    assert row["Secret"] != ""
    assert set(row["Events"].split(", ")) == {
        "incident.critical_created",
        "problem.resolved",
    }


def test_webhook_set_active_toggle():
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    row = webhook_service.create(
        webhooks, "W", "https://x.y/hook", events="problem.resolved"
    )
    webhook_service.set_active(webhooks, row["WebhookID"], active=False)
    assert webhooks.find("WebhookID", row["WebhookID"])["Active"] == "NO"
    webhook_service.set_active(webhooks, row["WebhookID"], active=True)
    assert webhooks.find("WebhookID", row["WebhookID"])["Active"] == "YES"


def test_webhook_delete():
    from services import webhook_service
    from utils.validators import ValidationError

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    row = webhook_service.create(
        webhooks, "W", "https://x.y/hook", events="problem.resolved"
    )
    webhook_service.delete(webhooks, row["WebhookID"])
    assert webhooks.records() == []
    with pytest.raises(ValidationError):
        webhook_service.delete(webhooks, row["WebhookID"])


def _sync_pool(monkeypatch, svc):
    """Replace the async pool with a synchronous executor for determinism."""

    class SyncExecutor:
        def submit(self, fn, *args):
            fn(*args)

    monkeypatch.setattr(svc, "_get_pool", lambda: SyncExecutor())


def test_dispatch_only_matching_active_webhooks(monkeypatch):
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    wh_crit = webhook_service.create(
        webhooks, "Critical", "https://a.y/hook", events="incident.critical_created"
    )
    webhook_service.create(
        webhooks, "Problems", "https://b.y/hook", events="problem.resolved"
    )
    wh_off = webhook_service.create(
        webhooks, "Off", "https://c.y/hook", events="incident.critical_created"
    )
    webhook_service.set_active(webhooks, wh_off["WebhookID"], active=False)

    delivered = []
    monkeypatch.setattr(
        webhook_service,
        "_deliver",
        lambda url, body, headers: delivered.append((url, body, headers)),
    )
    _sync_pool(monkeypatch, webhook_service)

    scheduled = webhook_service.dispatch(
        webhooks,
        "incident.critical_created",
        {"IncidentID": "I-1", "Title": "Пожар"},
    )
    assert scheduled == [wh_crit["WebhookID"]]
    assert len(delivered) == 1
    url, body, headers = delivered[0]
    assert url == "https://a.y/hook"
    data = json.loads(body)
    assert data["event"] == "incident.critical_created"
    assert data["data"]["IncidentID"] == "I-1"


def test_dispatch_signs_body_with_secret(monkeypatch):
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    webhook_service.create(
        webhooks,
        "Signed",
        "https://s.y/hook",
        events="problem.resolved",
        secret="topsecret",
    )
    captured = {}
    monkeypatch.setattr(
        webhook_service,
        "_deliver",
        lambda url, body, headers: captured.update(body=body, headers=headers),
    )
    _sync_pool(monkeypatch, webhook_service)
    webhook_service.dispatch(webhooks, "problem.resolved", {"ProblemID": "P-1"})

    data = json.loads(captured["body"])
    assert data["data"]["ProblemID"] == "P-1"
    sig = captured["headers"]["X-Signature"]
    expected = hmac_mod.new(
        b"topsecret", captured["body"].decode("utf-8").encode("utf-8"), hashlib.sha256
    ).hexdigest()
    assert sig == expected


def test_dispatch_never_raises_on_delivery_failure(monkeypatch):
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    row = webhook_service.create(
        webhooks, "Broken", "https://d.y/hook", events="problem.resolved"
    )

    def boom(url, body, headers):
        raise OSError("network down")

    monkeypatch.setattr(webhook_service, "_deliver", boom)
    scheduled = webhook_service.dispatch(
        webhooks, "problem.resolved", {"ProblemID": "P-1"}
    )
    assert scheduled == [row["WebhookID"]]  # fire-and-forget: no exception


def test_dispatch_unknown_event_no_targets(monkeypatch):
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    webhook_service.create(webhooks, "W", "https://x.y/hook", events="problem.resolved")
    monkeypatch.setattr(webhook_service, "_deliver", lambda *a: None)
    assert webhook_service.dispatch(webhooks, "incident.critical_created", {}) == []


def test_webhook_create_rejects_private_and_local_targets():
    """M1: loopback/link-local/RFC1918/metadata targets must be rejected at create."""
    from services import webhook_service
    from utils.validators import ValidationError

    for bad in (
        "http://127.0.0.1:9000/hook",
        "http://169.254.169.254/latest/meta-data",
        "http://10.0.0.5/hook",
        "http://192.168.1.10/hook",
        "http://localhost:5000/hook",
    ):
        with pytest.raises(ValidationError):
            webhook_service.create({}, "Slack", bad, events="incident.critical_created")


def test_webhook_create_allows_public_target(monkeypatch):
    from services import webhook_service

    monkeypatch.setattr(webhook_service, "_resolve", lambda url: ["93.184.216.34"])
    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    row = webhook_service.create(
        webhooks, "Slack", "https://hooks.example.com/x", events="problem.resolved"
    )
    assert row["Url"] == "https://hooks.example.com/x"


def test_webhook_dispatch_skips_private_target(monkeypatch):
    """Dispatch re-checks the URL (DNS rebinding / legacy rows); private → skip."""
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    webhook_service.create(
        webhooks, "Hook", "https://hooks.example.com/x", events="problem.resolved"
    )
    monkeypatch.setattr(webhook_service, "_resolve", lambda url: ["127.0.0.1"])
    delivered = []
    monkeypatch.setattr(
        webhook_service, "_deliver", lambda url, body, headers: delivered.append(url)
    )
    scheduled = webhook_service.dispatch(
        webhooks, "problem.resolved", {"ProblemID": "P-1"}
    )
    assert scheduled == []  # skipped, not scheduled
    assert delivered == []


def test_webhook_dispatch_never_raises_on_private_target(monkeypatch):
    from services import webhook_service

    webhooks = _store(_db(), "webhooks", WEBHOOK_COLS)
    webhook_service.create(
        webhooks, "Hook", "https://hooks.example.com/x", events="problem.resolved"
    )
    monkeypatch.setattr(webhook_service, "_resolve", lambda url: ["127.0.0.1"])
    monkeypatch.setattr(webhook_service, "_deliver", lambda *a: None)
    # fire-and-forget: validation must never escape dispatch
    assert webhook_service.dispatch(webhooks, "problem.resolved", {}) == []


def test_webhook_opener_does_not_follow_redirects():
    """M2: a redirect must never re-send X-Signature to a new host."""
    import urllib.request

    from services import webhook_service

    no_redirect = [
        h for h in webhook_service._opener.handlers if type(h).__name__ == "_NoRedirect"
    ]
    assert no_redirect, "opener must install a no-redirect handler"
    h = no_redirect[0]
    assert (
        h.redirect_request(None, None, 302, "Moved", {}, "http://evil.example/") is None
    )
    # sanity: default handler would follow
    dummy = urllib.request.Request("http://evil.example/")
    assert (
        urllib.request.HTTPRedirectHandler().redirect_request(
            dummy, None, 302, "Moved", {}, "http://evil.example/"
        )
        is not None
    )


@pytest.fixture()
def hooks_env(monkeypatch):
    import app as app_mod
    from services import ratelimit as rl
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import ISSUE_TYPE_COLS, PROJECT_COLS

    rl.reset()
    db = _db()
    monkeypatch.setattr(app_mod, "webhooks", _store(db, "webhooks", WEBHOOK_COLS))
    monkeypatch.setattr(app_mod, "projects", _store(db, "projects", PROJECT_COLS))
    monkeypatch.setattr(
        app_mod, "project_types", _store(db, "issue_types", ISSUE_TYPE_COLS)
    )
    monkeypatch.setattr(
        app_mod, "history", HistoryService(_store(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)

    def _wipe():
        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()

    _wipe()
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")

    def _client(user):
        c = app_mod.app.test_client()
        c.post("/login", data={"username": user, "password": "dolgapass123"})
        return c

    try:
        yield {"app": app_mod, "client": _client}
    finally:
        _wipe()


def test_settings_webhooks_admin_only(hooks_env):
    assert hooks_env["client"]("adm").get("/settings/webhooks").status_code == 200
    assert hooks_env["client"]("mag").get("/settings/webhooks").status_code == 403


def test_create_webhook_via_form(hooks_env):
    c = hooks_env["client"]("adm")
    r = c.post(
        "/settings/webhooks",
        data={
            "name": "Ops",
            "url": "https://hooks.slack.com/services/T/B/X",
            "events": "incident.critical_created",
        },
    )
    assert r.status_code == 302
    rows = hooks_env["app"].webhooks.records()
    assert len(rows) == 1
    assert rows[0]["Name"] == "Ops"


def test_delete_webhook_via_form(hooks_env):
    from services import webhook_service

    c = hooks_env["client"]("adm")
    row = webhook_service.create(
        hooks_env["app"].webhooks, "Ops", "https://x.y/h", events="problem.resolved"
    )
    r = c.post(f"/settings/webhooks/{row['WebhookID']}/delete")
    assert r.status_code == 302
    assert hooks_env["app"].webhooks.records() == []


def test_toggle_webhook_via_form(hooks_env):
    from services import webhook_service

    c = hooks_env["client"]("adm")
    row = webhook_service.create(
        hooks_env["app"].webhooks, "Ops", "https://x.y/h", events="problem.resolved"
    )
    r = c.post(f"/settings/webhooks/{row['WebhookID']}/toggle")
    assert r.status_code == 302
    assert (
        hooks_env["app"].webhooks.find("WebhookID", row["WebhookID"])["Active"] == "NO"
    )


def test_real_deliver_uses_urllib(monkeypatch):
    """The production _deliver POSTs JSON via urllib with timeout."""
    from services import webhook_service

    captured = {}

    class FakeResponse:
        status = 200

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        captured["headers"] = dict(req.headers)
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(webhook_service, "_urlopen", fake_urlopen)
    webhook_service._deliver(
        "https://x.y/h", b'{"event":"problem.resolved"}', {"X-Signature": "abc"}
    )
    assert captured["url"] == "https://x.y/h"
    assert captured["timeout"] == webhook_service.TIMEOUT_S


def _wiring_env(hooks_env, monkeypatch):
    """Patch the incidents store so a real POST /incidents/new can run."""
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import INCIDENT_COLS

    db = app_mod.webhooks.db_path
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    return app_mod


def test_critical_incident_creation_fires_webhook(hooks_env, monkeypatch):
    """Wiring: creating a critical incident through the route dispatches
    incident.critical_created to active matching webhooks."""
    from services import webhook_service

    app_mod = _wiring_env(hooks_env, monkeypatch)
    webhook_service.create(
        app_mod.webhooks,
        "Slack",
        "https://x.y/hook",
        events="incident.critical_created",
    )

    delivered = []
    monkeypatch.setattr(
        webhook_service,
        "_deliver",
        lambda url, body, headers: delivered.append((url, json.loads(body))),
    )
    _sync_pool(monkeypatch, webhook_service)

    c = hooks_env["client"]("mag")
    r = c.post(
        "/incidents/new",
        data={"Title": "Серверот гори", "Priority": "urgent"},
    )
    assert r.status_code == 302
    assert len(delivered) == 1
    url, body = delivered[0]
    assert url == "https://x.y/hook"
    assert body["event"] == "incident.critical_created"
    assert body["data"]["Title"] == "Серверот гори"


def test_medium_incident_creation_fires_no_webhook(hooks_env, monkeypatch):
    """Wiring: non-critical incidents dispatch nothing."""
    from services import webhook_service

    app_mod = _wiring_env(hooks_env, monkeypatch)
    webhook_service.create(
        app_mod.webhooks,
        "Slack",
        "https://x.y/hook",
        events="incident.critical_created",
    )

    delivered = []
    monkeypatch.setattr(
        webhook_service,
        "_deliver",
        lambda url, body, headers: delivered.append((url, body)),
    )
    _sync_pool(monkeypatch, webhook_service)

    c = hooks_env["client"]("mag")
    r = c.post("/incidents/new", data={"Title": "Мал дефект", "Priority": "medium"})
    assert r.status_code == 302
    assert delivered == []


def test_change_creation_fires_cab_pending_webhook(monkeypatch):
    """Wiring: creating a change request dispatches change.cab_pending."""
    import app as app_mod
    from services import webhook_service
    from services.db_service import DbStore
    from services.schemas import CHANGE_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "chg.db")
    monkeypatch.setattr(app_mod, "changes", DbStore(db, "changes", CHANGE_COLS))
    monkeypatch.setattr(app_mod, "webhooks", _store(db, "webhooks", WEBHOOK_COLS))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)

    webhook_service.create(
        app_mod.webhooks, "Ops", "https://x.y/hook", events="change.cab_pending"
    )
    delivered = []
    monkeypatch.setattr(
        webhook_service,
        "_deliver",
        lambda url, body, headers: delivered.append((url, json.loads(body))),
    )
    _sync_pool(monkeypatch, webhook_service)

    c = app_mod.app.test_client()
    r = c.post(
        "/changes/new",
        data={
            "title": "Надградба на kernel",
            "risk_level": "high",
            "rollback_plan": "GRUB snapshot враќање",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    chg = app_mod.changes.records()[0]
    assert len(delivered) == 1
    url, body = delivered[0]
    assert url == "https://x.y/hook"
    assert body["event"] == "change.cab_pending"
    assert body["data"]["ChangeID"] == chg["ChangeID"]
    assert body["data"]["Title"] == "Надградба на kernel"


def test_problem_resolution_fires_resolved_webhook(monkeypatch):
    """Wiring: resolving a problem dispatches problem.resolved."""
    import app as app_mod
    from services import webhook_service
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, INCIDENT_COLS, PROBLEM_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "prob.db")
    monkeypatch.setattr(app_mod, "problems", DbStore(db, "problems", PROBLEM_COLS))
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "webhooks", _store(db, "webhooks", WEBHOOK_COLS))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)

    webhook_service.create(
        app_mod.webhooks, "Ops", "https://x.y/hook", events="problem.resolved"
    )
    delivered = []
    monkeypatch.setattr(
        webhook_service,
        "_deliver",
        lambda url, body, headers: delivered.append((url, json.loads(body))),
    )
    _sync_pool(monkeypatch, webhook_service)

    c = app_mod.app.test_client()
    c.post("/problems/new", data={"title": "Прекин на мрежа"})
    pid = app_mod.problems.records()[0]["ProblemID"]
    r = c.post(
        "/problems/resolve",
        data={
            "problem_id": pid,
            "root_cause": "Дефектно напојување",
            "workaround": "Резервно напојување",
        },
        follow_redirects=True,
    )
    assert r.status_code == 200
    assert len(delivered) == 1
    url, body = delivered[0]
    assert url == "https://x.y/hook"
    assert body["event"] == "problem.resolved"
    assert body["data"]["ProblemID"] == pid
