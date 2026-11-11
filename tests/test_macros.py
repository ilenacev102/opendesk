"""Sprint 6: canned response macros — service validation, admin UI, comment picker."""

import os
import sqlite3
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.schemas import MACRO_COLS


def _store(db, table, cols):
    from services.db_service import DbStore

    return DbStore(db, table, cols)


def _db():
    return os.path.join(tempfile.mkdtemp(), "macros.db")


def test_macro_create_validates_required_fields():
    from services import macro_service
    from utils.validators import ValidationError

    macros = _store(_db(), "macros", MACRO_COLS)
    with pytest.raises(ValidationError):
        macro_service.create(macros, "", "body")
    with pytest.raises(ValidationError):
        macro_service.create(macros, "   ", "body")
    with pytest.raises(ValidationError):
        macro_service.create(macros, "Наслов", "  ")
    assert macros.records() == []


def test_macro_create_assigns_id_and_defaults():
    from services import macro_service

    db = _db()
    macros = _store(db, "macros", MACRO_COLS)
    m1 = macro_service.create(
        macros,
        "Испратете скриншот",
        "Ве молиме испратете скриншот од проблемот.",
        category="Општо",
    )
    m2 = macro_service.create(
        macros, "Рестартирај", "Рестартирајте го уредот и обидете се повторно."
    )
    assert m1["MacroID"].startswith("MAC")
    assert m2["MacroID"] != m1["MacroID"]
    assert m1["Category"] == "Општо"
    assert m2["Category"] == ""
    assert len(macros.records()) == 2


def test_macro_delete():
    from services import macro_service

    macros = _store(_db(), "macros", MACRO_COLS)
    m = macro_service.create(macros, "T", "B")
    macro_service.delete(macros, m["MacroID"])
    assert macros.records() == []
    with pytest.raises(Exception):
        macro_service.delete(macros, "MAC-NOPE")


@pytest.fixture()
def macros_env(monkeypatch):
    """App with temp macros store + one incident; admin/magacioner/citac users."""
    import app as app_mod
    from services import ratelimit as rl
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import INCIDENT_COLS, ISSUE_TYPE_COLS, PROJECT_COLS

    rl.reset()
    db = _db()
    monkeypatch.setattr(app_mod, "macros", _store(db, "macros", MACRO_COLS))
    monkeypatch.setattr(app_mod, "incidents", _store(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "projects", _store(db, "projects", PROJECT_COLS))
    monkeypatch.setattr(
        app_mod, "project_types", _store(db, "issue_types", ISSUE_TYPE_COLS)
    )
    monkeypatch.setattr(
        app_mod, "history", HistoryService(_store(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    app_mod.incidents.append_row(
        {
            "IncidentID": "I-1",
            "Title": "дефект",
            "Status": "open",
            "ProjectID": "PRJ-1",
        }
    )
    app_mod.projects.append_row({"ProjectID": "PRJ-1", "Name": "Проект"})

    def _wipe():
        con = sqlite3.connect(app_mod.DB_PATH)
        con.execute("DELETE FROM users")
        con.commit()
        con.close()

    _wipe()
    app_mod.auth_svc.create_user("adm", "dolgapass123", role="admin")
    app_mod.auth_svc.create_user("mag", "dolgapass123", role="magacioner")
    app_mod.auth_svc.create_user("cit", "dolgapass123", role="citac")

    def _client(user):
        c = app_mod.app.test_client()
        c.post("/login", data={"username": user, "password": "dolgapass123"})
        return c

    try:
        yield {"app": app_mod, "client": _client}
    finally:
        _wipe()


def test_settings_macros_admin_only(macros_env):
    r_admin = macros_env["client"]("adm").get("/settings/macros")
    assert r_admin.status_code == 200
    assert macros_env["client"]("mag").get("/settings/macros").status_code == 403
    assert macros_env["client"]("cit").get("/settings/macros").status_code == 403


def test_create_macro_via_form(macros_env):
    c = macros_env["client"]("adm")
    r = c.post(
        "/settings/macros",
        data={
            "title": "Испратете скриншот",
            "body": "Ве молиме прикачете скриншот.",
            "category": "Општо",
        },
    )
    assert r.status_code == 302
    rows = macros_env["app"].macros.records()
    assert len(rows) == 1
    assert rows[0]["Title"] == "Испратете скриншот"


def test_create_macro_empty_body_rejected(macros_env):
    c = macros_env["client"]("adm")
    r = c.post("/settings/macros", data={"title": "T", "body": "   "})
    assert r.status_code == 302
    assert macros_env["app"].macros.records() == []


def test_delete_macro(macros_env):
    from services import macro_service

    c = macros_env["client"]("adm")
    m = macro_service.create(macros_env["app"].macros, "T", "B")
    r = c.post(f"/settings/macros/{m['MacroID']}/delete")
    assert r.status_code == 302
    assert macros_env["app"].macros.records() == []


def test_api_macros_lists_for_logged_users(macros_env):
    for user in ("adm", "mag"):
        r = macros_env["client"](user).get("/api/v1/macros")
        assert r.status_code == 200
        assert b"[]\n" == r.data or r.get_json() == []
    macros_env["client"]("cit").get("/api/v1/macros")


def test_api_macros_requires_login(macros_env):
    c = macros_env["app"].app.test_client()
    r = c.get("/api/v1/macros")
    assert r.status_code in (302, 401)


def test_incident_page_has_macro_picker(macros_env):
    from services import macro_service

    macro_service.create(macros_env["app"].macros, "Скриншот", "Прикачете скриншот.")
    c = macros_env["client"]("mag")
    r = c.get("/incident/I-1")
    assert r.status_code == 200
    body = r.get_data(as_text=True)
    assert "macroPicker" in body
    assert "Скриншот" in body
    assert "Прикачете скриншот." in body
