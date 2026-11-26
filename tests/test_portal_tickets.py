"""P3: portal ticket detail, comments, CSAT, reopen and "my tickets"."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASSWORD = "dolgapass123"


def _env(monkeypatch):
    import config
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.incident_service import IncidentService
    from services.ratelimit import reset as reset_limits
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
    db = os.path.join(tmp, "portal_tickets.db")
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
    monkeypatch.setattr(config, "DOCUMENTS_DIR", os.path.join(tmp, "documents"))
    reset_limits()

    for username, emp_id, first in (
        ("alek", "EMP-001", "Александар"),
        ("bora", "EMP-002", "Борис"),
    ):
        app_mod.employees.append_row(
            {
                "EmployeeID": emp_id,
                "FirstName": first,
                "LastName": "Тест",
                "UserName": username,
                "Email": f"{username}@example.com",
            }
        )
        app_mod.auth_svc.create_user(username, PASSWORD, role="citac")
    app_mod.auth_svc.create_user("mag", PASSWORD, role="magacioner")

    svc = IncidentService(
        app_mod.incidents,
        app_mod.history,
        db_path=getattr(app_mod.incidents, "db_path", None),
    )
    return app_mod, svc


def _wipe_users():
    import sqlite3

    import app as app_mod

    con = sqlite3.connect(app_mod.DB_PATH)
    con.execute("DELETE FROM users")
    con.commit()
    con.close()


def _login(client, user):
    return client.post("/login", data={"username": user, "password": PASSWORD})


def _incident(svc, title="Екранот трепка", employee="EMP-001", assignee="mag"):
    return svc.create(
        title=title,
        employee_id=employee,
        assignee=assignee,
        due_date="2026-12-01",
        performed_by="alek",
    )


def test_owner_opens_ticket_foreign_forbidden_and_anon_redirected(monkeypatch):
    import config

    app_mod, svc = _env(monkeypatch)
    try:
        inc = _incident(svc)
        iid = inc["IncidentID"]
        app_mod.comments.append_row(
            {
                "CommentID": "C1",
                "IncidentID": iid,
                "Author": "mag",
                "Body": "Јавен коментар",
                "Created": "2026-11-20 10:00",
            }
        )
        folder = os.path.join(config.DOCUMENTS_DIR, "incidents", iid)
        os.makedirs(folder, exist_ok=True)
        with open(os.path.join(folder, "log.txt"), "w", encoding="utf-8") as fh:
            fh.write("ok")

        alek = app_mod.app.test_client()
        _login(alek, "alek")
        r = alek.get(f"/portal/ticket/{iid}")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert "Екранот трепка" in html
        assert "Јавен коментар" in html
        assert "2026-12-01" in html
        assert "log.txt" in html

        download = alek.get(f"/portal/ticket/{iid}/attach/log.txt")
        assert download.status_code == 200
        assert download.get_data(as_text=True) == "ok"
        assert (
            alek.get(f"/portal/ticket/{iid}/attach/..%2F..%2Fsecret.txt").status_code
            == 404
        )

        bora = app_mod.app.test_client()
        _login(bora, "bora")
        assert bora.get(f"/portal/ticket/{iid}").status_code == 403
        assert bora.get(f"/portal/ticket/{iid}/attach/log.txt").status_code == 403

        anon = app_mod.app.test_client()
        assert anon.get(f"/portal/ticket/{iid}").status_code == 302

        assert alek.get("/portal/ticket/NOPE").status_code == 404
    finally:
        _wipe_users()


def test_comment_post_appends_audits_and_blocks_foreign(monkeypatch):
    from services import portal_service

    app_mod, svc = _env(monkeypatch)
    try:
        iid = _incident(svc)["IncidentID"]
        alek = app_mod.app.test_client()
        _login(alek, "alek")

        assert (
            alek.post(f"/portal/ticket/{iid}/comment", data={"body": "Прв"}).status_code
            == 302
        )
        rows = app_mod.comments.filter_eq("IncidentID", iid)
        assert [r["Body"] for r in rows] == ["Прв"]
        assert rows[0]["Author"] == "alek"
        assert [
            h["Action"]
            for h in app_mod.history.store.records()
            if h.get("Action") == "PORTAL_COMMENT"
        ] == ["PORTAL_COMMENT"]

        alek.post(f"/portal/ticket/{iid}/comment", data={"body": "   "})
        assert len(app_mod.comments.filter_eq("IncidentID", iid)) == 1

        bora = app_mod.app.test_client()
        _login(bora, "bora")
        assert (
            bora.post(f"/portal/ticket/{iid}/comment", data={"body": "Туѓ"}).status_code
            == 403
        )
        assert len(app_mod.comments.filter_eq("IncidentID", iid)) == 1

        monkeypatch.setattr(portal_service, "COMMENT_LIMIT", 2)
        from services.ratelimit import reset as reset_limits

        reset_limits()
        assert (
            alek.post(f"/portal/ticket/{iid}/comment", data={"body": "А"}).status_code
            == 302
        )
        assert (
            alek.post(f"/portal/ticket/{iid}/comment", data={"body": "Б"}).status_code
            == 302
        )
        assert (
            alek.post(f"/portal/ticket/{iid}/comment", data={"body": "В"}).status_code
            == 429
        )
    finally:
        _wipe_users()


def test_csat_only_resolved_and_owner(monkeypatch):
    app_mod, svc = _env(monkeypatch)
    try:
        iid = _incident(svc)["IncidentID"]
        alek = app_mod.app.test_client()
        _login(alek, "alek")

        assert (
            alek.post(f"/portal/ticket/{iid}/rate", data={"score": "5"}).status_code
            == 302
        )
        assert (app_mod.incidents.find("IncidentID", iid) or {}).get(
            "Satisfaction", ""
        ) == ""

        svc.transition(iid, "in-progress", performed_by="mag")
        svc.transition(iid, "resolved", performed_by="mag")

        alek.post(f"/portal/ticket/{iid}/rate", data={"score": "9"})
        assert (app_mod.incidents.find("IncidentID", iid) or {}).get(
            "Satisfaction", ""
        ) == ""

        alek.post(f"/portal/ticket/{iid}/rate", data={"score": "5"})
        assert app_mod.incidents.find("IncidentID", iid)["Satisfaction"] == "5"
        assert [
            h["Action"]
            for h in app_mod.history.store.records()
            if h.get("Action") == "INC_RATE"
        ] == ["INC_RATE"]

        bora = app_mod.app.test_client()
        _login(bora, "bora")
        assert (
            bora.post(f"/portal/ticket/{iid}/rate", data={"score": "1"}).status_code
            == 403
        )
        assert app_mod.incidents.find("IncidentID", iid)["Satisfaction"] == "5"
    finally:
        _wipe_users()


def test_reopen_rules_and_notification(monkeypatch):
    app_mod, svc = _env(monkeypatch)
    try:
        iid = _incident(svc)["IncidentID"]
        alek = app_mod.app.test_client()
        _login(alek, "alek")

        assert alek.post(f"/portal/ticket/{iid}/reopen").status_code == 302
        assert app_mod.incidents.find("IncidentID", iid)["Status"] == "open"

        svc.transition(iid, "in-progress", performed_by="mag")
        svc.transition(iid, "resolved", performed_by="mag")
        assert alek.post(f"/portal/ticket/{iid}/reopen").status_code == 302
        assert app_mod.incidents.find("IncidentID", iid)["Status"] == "open"
        notes = app_mod.notifications.filter_eq("UserName", "mag")
        assert len(notes) == 1
        assert notes[0]["Kind"] == "incident"
        assert notes[0]["RefID"] == iid

        svc.transition(iid, "in-progress", performed_by="mag")
        svc.transition(iid, "resolved", performed_by="mag")
        alek.post(f"/portal/ticket/{iid}/reopen")
        assert app_mod.incidents.find("IncidentID", iid)["Status"] == "resolved"
    finally:
        _wipe_users()


def test_my_tickets_filter_and_pagination(monkeypatch):
    app_mod, svc = _env(monkeypatch)
    try:
        for n in range(12):
            row = _incident(svc, title=f"Тикет {n}")
            if n % 2:
                svc.transition(row["IncidentID"], "in-progress", performed_by="mag")
                svc.transition(row["IncidentID"], "resolved", performed_by="mag")

        alek = app_mod.app.test_client()
        _login(alek, "alek")

        page1 = alek.get("/portal/tickets")
        assert page1.status_code == 200
        assert page1.get_data(as_text=True).count('class="portal-ticket-row"') == 10

        page2 = alek.get("/portal/tickets?page=2")
        assert page2.get_data(as_text=True).count('class="portal-ticket-row"') == 2

        resolved = alek.get("/portal/tickets?status=resolved")
        assert resolved.get_data(as_text=True).count('class="portal-ticket-row"') == 6

        assert alek.get("/portal/tickets?page=abc").status_code == 200

        other = app_mod.app.test_client()
        _login(other, "bora")
        empty = other.get("/portal/tickets")
        assert empty.status_code == 200
        assert "Нема тикети" in empty.get_data(as_text=True)
    finally:
        _wipe_users()


def test_full_portal_flow_apply_comment_resolve_rate_reopen(monkeypatch):
    app_mod, svc = _env(monkeypatch)
    try:
        alek = app_mod.app.test_client()
        _login(alek, "alek")
        r = alek.post(
            "/portal/incident",
            data={
                "title": "Не печати",
                "priority": "medium",
                "notes": "Хартијата заглавува",
            },
        )
        assert r.status_code == 302
        iid = app_mod.incidents.records()[0]["IncidentID"]

        alek.post(f"/portal/ticket/{iid}/comment", data={"body": "И сега повторно"})
        svc.transition(iid, "in-progress", performed_by="mag")
        svc.transition(iid, "resolved", performed_by="mag")
        alek.post(f"/portal/ticket/{iid}/rate", data={"score": "4"})
        alek.post(f"/portal/ticket/{iid}/reopen")

        inc = app_mod.incidents.find("IncidentID", iid)
        assert inc["Status"] == "open"
        assert inc["Satisfaction"] == "4"
        actions = [h["Action"] for h in app_mod.history.store.records()]
        for action in (
            "INC_CREATE",
            "PORTAL_COMMENT",
            "INC_RESOLVE",
            "INC_RATE",
            "INC_REOPEN",
        ):
            assert action in actions, action
    finally:
        _wipe_users()
