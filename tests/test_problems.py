"""Tests for ITIL Problem Management (/problems) and cascading incident resolution."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_problem_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, INCIDENT_COLS, PROBLEM_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "prob.db")
    problems_store = DbStore(db, "problems", PROBLEM_COLS)
    inc_store = DbStore(db, "incidents", INCIDENT_COLS)
    dev_store = DbStore(db, "devices", DEV_COLS)
    hist_store = DbStore(db, "history", HISTORY_COLS)

    monkeypatch.setattr(app_mod, "problems", problems_store)
    monkeypatch.setattr(app_mod, "incidents", inc_store)
    monkeypatch.setattr(app_mod, "devices", dev_store)
    monkeypatch.setattr(app_mod, "history", HistoryService(hist_store))
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setitem(app_mod.PATHS, "db", db)

    # Seed 3 open incidents
    inc_store.append_row({
        "IncidentID": "I-101",
        "AssetID": "AST-01",
        "Title": "Нема пристап до сметководство",
        "Status": "open",
    })
    inc_store.append_row({
        "IncidentID": "I-102",
        "AssetID": "AST-02",
        "Title": "Падна серверот за база",
        "Status": "in_progress",
    })
    inc_store.append_row({
        "IncidentID": "I-103",
        "AssetID": "AST-03",
        "Title": "Грешка 500 на апликација",
        "Status": "open",
    })

    return app_mod


def test_create_problem_ticket(monkeypatch):
    app_mod = _setup_problem_env(monkeypatch)
    c = app_mod.app.test_client()

    resp = c.post(
        "/problems/new",
        data={
            "title": "Главен прекин на базата на податоци PostgreSQL",
            "description": "Повеќе корисници не можат да се најават во ERP системот.",
            "workaround": "Користење на read-only реплика",
            "owner": "nikola.admin",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    problems = app_mod.problems.records()
    assert len(problems) == 1
    p = problems[0]
    assert p["ProblemID"].startswith("PRB-")
    assert "Главен прекин" in p["Title"]
    assert p["Status"] == "investigating"
    assert p["Owner"] == "nikola.admin"


def test_link_incidents_to_problem(monkeypatch):
    app_mod = _setup_problem_env(monkeypatch)
    c = app_mod.app.test_client()

    # Create problem
    c.post(
        "/problems/new",
        data={"title": "Прекин на свич во рек 2"},
    )
    pid = app_mod.problems.records()[0]["ProblemID"]

    # Link incidents I-101 and I-102
    r1 = c.post("/problems/link-incident", data={"problem_id": pid, "incident_id": "I-101"}, follow_redirects=True)
    assert r1.status_code == 200
    r2 = c.post("/problems/link-incident", data={"problem_id": pid, "incident_id": "I-102"}, follow_redirects=True)
    assert r2.status_code == 200

    assert app_mod.incidents.find("IncidentID", "I-101")["LinkedTo"] == pid
    assert app_mod.incidents.find("IncidentID", "I-102")["LinkedTo"] == pid
    assert app_mod.incidents.find("IncidentID", "I-103")["LinkedTo"] == ""

    # Page renders linked count
    page = c.get("/problems").get_data(as_text=True)
    assert pid in page
    assert "I-101" in page


def test_cascading_resolution_closes_all_linked_incidents(monkeypatch):
    app_mod = _setup_problem_env(monkeypatch)
    c = app_mod.app.test_client()

    # Create problem & link 2 incidents
    c.post("/problems/new", data={"title": "Мрежен дефект"})
    pid = app_mod.problems.records()[0]["ProblemID"]
    c.post("/problems/link-incident", data={"problem_id": pid, "incident_id": "I-101"})
    c.post("/problems/link-incident", data={"problem_id": pid, "incident_id": "I-102"})

    # Resolving without root_cause must fail
    fail_res = c.post(
        "/problems/resolve",
        data={"problem_id": pid, "root_cause": ""},
        follow_redirects=True,
    )
    assert fail_res.status_code == 200
    assert app_mod.problems.find("ProblemID", pid)["Status"] == "investigating"

    # Resolving with root_cause cascades
    resp = c.post(
        "/problems/resolve",
        data={
            "problem_id": pid,
            "root_cause": "Дефектно напојување на главниот рутер Cisco.",
            "workaround": "Заменето со резервно модуларно напојување.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200

    # Problem is resolved
    prob = app_mod.problems.find("ProblemID", pid)
    assert prob["Status"] == "resolved"
    assert "Дефектно напојување" in prob["RootCause"]
    assert prob["ResolvedAt"] != ""

    # Both linked incidents are closed with root_cause note
    inc1 = app_mod.incidents.find("IncidentID", "I-101")
    assert inc1["Status"] == "closed"
    assert f"Решено преку Проблем {pid}" in inc1["Notes"]

    inc2 = app_mod.incidents.find("IncidentID", "I-102")
    assert inc2["Status"] == "closed"
    assert f"Решено преку Проблем {pid}" in inc2["Notes"]

    # Unlinked incident I-103 remains open
    inc3 = app_mod.incidents.find("IncidentID", "I-103")
    assert inc3["Status"] == "open"
