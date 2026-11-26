"""P4: portal identity mapping, notifications panel and mobile markers."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSWORD = "dolgapass123"


def _env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.incident_service import IncidentService
    from services.schemas import (
        COMMENT_COLS,
        DEV_COLS,
        EMP_COLS,
        INCIDENT_COLS,
        KB_COLS,
        NOTIF_COLS,
        REQUEST_COLS,
    )

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "portal_mobile.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(app_mod, "requests", DbStore(db, "requests", REQUEST_COLS))
    monkeypatch.setattr(app_mod, "incidents", DbStore(db, "incidents", INCIDENT_COLS))
    monkeypatch.setattr(app_mod, "comments", DbStore(db, "comments", COMMENT_COLS))
    monkeypatch.setattr(
        app_mod, "notifications", DbStore(db, "notifications", NOTIF_COLS)
    )
    monkeypatch.setattr(app_mod, "kb_articles", DbStore(db, "kb_articles", KB_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setitem(app_mod.PATHS, "db", db)

    app_mod.employees.append_row(
        {
            "EmployeeID": "EMP-001",
            "FirstName": "Александар",
            "LastName": "Тест",
            "UserName": "alek",
            "Email": "alek@example.com",
        }
    )
    app_mod.auth_svc.create_user("alek", PASSWORD, role="citac")
    app_mod.auth_svc.create_user("unlinked", PASSWORD, role="citac")
    app_mod.auth_svc.create_user("adm", PASSWORD, role="admin")

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    inc = svc.create(title="Мобилен тикет", employee_id="EMP-001", performed_by="alek")
    return app_mod, inc["IncidentID"]


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user):
    return client.post("/login", data={"username": user, "password": PASSWORD})


def test_portal_pages_carry_mobile_markers(monkeypatch):
    app_mod, iid = _env(monkeypatch)
    try:
        client = app_mod.app.test_client()
        _login(client, "alek")

        home = client.get("/portal").get_data(as_text=True)
        assert 'name="viewport"' in home
        assert "navbar-toggler" in home
        assert "portal-sticky-cta" in home
        assert "table-responsive" in home

        ticket = client.get(f"/portal/ticket/{iid}").get_data(as_text=True)
        assert "portal-ticket-head" in ticket
        assert "text-break" in ticket
        assert "table-responsive" in client.get("/portal/tickets").get_data(
            as_text=True
        )
    finally:
        _wipe_users()


def test_portal_mobile_css_rules_exist():
    import pathlib

    css = (
        pathlib.Path(__file__).resolve().parent.parent / "static" / "css" / "app.css"
    ).read_text(encoding="utf-8")
    assert ".portal-sticky-cta" in css
    assert "@media (max-width: 575px)" in css
    assert ".portal-notif-panel" in css


def test_unlinked_citac_sees_mapping_message_but_admin_does_not(monkeypatch):
    app_mod, _ = _env(monkeypatch)
    try:
        unlinked = app_mod.app.test_client()
        _login(unlinked, "unlinked")
        html = unlinked.get("/portal").get_data(as_text=True)
        assert "не е поврзан" in html
        assert 'href="/employees"' in html

        adm = app_mod.app.test_client()
        _login(adm, "adm")
        admin_html = adm.get("/portal").get_data(as_text=True)
        assert "не е поврзан" not in admin_html
    finally:
        _wipe_users()


def test_portal_notifications_list_and_mark_read(monkeypatch):
    app_mod, iid = _env(monkeypatch)
    try:
        for nid, text in (("N1", "Тикетот е решен"), ("N2", "Нов коментар")):
            app_mod.notifications.append_row(
                {
                    "NotifID": nid,
                    "UserName": "alek",
                    "Kind": "incident",
                    "RefID": iid,
                    "Text": text,
                    "Created": "2026-11-23 09:00",
                    "ReadAt": "",
                }
            )

        client = app_mod.app.test_client()
        _login(client, "alek")
        html = client.get("/portal").get_data(as_text=True)
        assert "portal-notif-panel" in html
        assert "Тикетот е решен" in html
        assert "Нов коментар" in html
        assert 'class="badge rounded-pill bg-danger' in html

        assert (
            client.post(
                "/portal/notifications/read", data={"notif_id": "N1"}
            ).status_code
            == 302
        )
        rows = {r["NotifID"]: r for r in app_mod.notifications.records()}
        assert rows["N1"]["ReadAt"]
        assert rows["N2"]["ReadAt"] == ""

        client.post("/portal/notifications/read", data={})
        assert all(r["ReadAt"] for r in app_mod.notifications.records())

        html_after = client.get("/portal").get_data(as_text=True)
        assert "Нема нови известувања" in html_after
    finally:
        _wipe_users()


def test_login_page_is_mobile_ready(monkeypatch):
    app_mod, _ = _env(monkeypatch)
    try:
        html = app_mod.app.test_client().get("/login").get_data(as_text=True)
        assert "auth-shell" in html
        assert "auth-card" in html
        assert 'name="viewport"' in html
    finally:
        _wipe_users()


def test_auth_shell_css_exists():
    import pathlib

    css = (
        pathlib.Path(__file__).resolve().parent.parent
        / "static"
        / "css"
        / "app.css"
    ).read_text(encoding="utf-8")
    assert ".auth-shell" in css
    assert ".auth-card" in css
    assert "@media (max-width: 767px)" in css
