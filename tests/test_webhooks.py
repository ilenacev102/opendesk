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
    assert webhooks.records() == []


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
    row = webhook_service.create(
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


@pytest.fixture()
def hooks_env(monkeypatch):
    import app as app_mod
    from services import ratelimit as rl
    from services.db_service import DbStore
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
