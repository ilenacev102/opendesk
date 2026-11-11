"""Tests for Change Advisory Board (CAB) & Change Requests (/changes)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _setup_change_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.schemas import CHANGE_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "chg.db")
    changes_store = DbStore(db, "changes", CHANGE_COLS)

    monkeypatch.setattr(app_mod, "changes", changes_store)
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    monkeypatch.setitem(app_mod.PATHS, "db", db)

    return app_mod


def test_submit_change_request_requires_rollback(monkeypatch):
    app_mod = _setup_change_env(monkeypatch)
    c = app_mod.app.test_client()

    # Submit without rollback plan must fail validation
    resp_fail = c.post(
        "/changes/new",
        data={
            "title": "Миграција на база",
            "risk_level": "high",
            "rollback_plan": "",
        },
        follow_redirects=True,
    )
    assert resp_fail.status_code == 200
    assert len(app_mod.changes.records()) == 0

    # Submit valid change request
    resp = c.post(
        "/changes/new",
        data={
            "title": "Надградба на Linux kernel на кластерот",
            "risk_level": "critical",
            "impact_scope": "Сите веб сервиси во кластерот",
            "scheduled_start": "2026-11-15T02:00",
            "scheduled_end": "2026-11-15T04:00",
            "rollback_plan": "Враќање на претходниот kernel преку GRUB snapshot.",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    recs = app_mod.changes.records()
    assert len(recs) == 1
    chg = recs[0]
    assert chg["ChangeID"].startswith("CHG-")
    assert chg["RiskLevel"] == "critical"
    assert chg["Status"] == "pending_cab"


def test_cab_approval_and_implementation(monkeypatch):
    app_mod = _setup_change_env(monkeypatch)
    c = app_mod.app.test_client()

    # Create change
    c.post(
        "/changes/new",
        data={
            "title": "Конфигурација на нов VLAN",
            "risk_level": "medium",
            "rollback_plan": "Restore backup switch config",
        },
    )
    cid = app_mod.changes.records()[0]["ChangeID"]

    # CAB Approve
    appr_resp = c.post(
        "/changes/decision",
        data={"change_id": cid, "decision": "approve"},
        follow_redirects=True,
    )
    assert appr_resp.status_code == 200
    chg = app_mod.changes.find("ChangeID", cid)
    assert chg["Status"] == "approved"
    assert chg["ApprovedBy"] != ""

    # Implement change
    impl_resp = c.post(
        "/changes/implement",
        data={"change_id": cid, "result": "implemented"},
        follow_redirects=True,
    )
    assert impl_resp.status_code == 200
    assert app_mod.changes.find("ChangeID", cid)["Status"] == "implemented"


def test_cab_rejection(monkeypatch):
    app_mod = _setup_change_env(monkeypatch)
    c = app_mod.app.test_client()

    c.post(
        "/changes/new",
        data={
            "title": "Ризична интервенција во работно време",
            "risk_level": "high",
            "rollback_plan": "Нема",
        },
    )
    cid = app_mod.changes.records()[0]["ChangeID"]

    # CAB Reject
    rej_resp = c.post(
        "/changes/decision",
        data={"change_id": cid, "decision": "reject"},
        follow_redirects=True,
    )
    assert rej_resp.status_code == 200
    assert app_mod.changes.find("ChangeID", cid)["Status"] == "rejected"
