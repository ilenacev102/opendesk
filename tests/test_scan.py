"""Brz vnes 4: scan mode (toggle, focus hooks, script wiring)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_scan_assets_wired():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(
        os.path.join(base, "static", "js", "scan-mode.js"), encoding="utf-8"
    ) as fh:
        js = fh.read()
    assert "scan" in js and "AudioContext" in js
    with open(os.path.join(base, "templates_web", "base.html"), encoding="utf-8") as fh:
        assert "scan-mode.js" in fh.read()


def _scan_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HISTORY_COLS, HistoryService
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "sc.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(app_mod, "employees", DbStore(db, "employees", EMP_COLS))
    monkeypatch.setattr(
        app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    return app_mod


def test_quick_return_scan_toggle(monkeypatch):
    app_mod = _scan_env(monkeypatch)
    html = app_mod.app.test_client().get("/quick-return?scan=1").get_data(as_text=True)
    assert "SCAN" in html and "data-scan" in html
    plain = app_mod.app.test_client().get("/quick-return").get_data(as_text=True)
    assert "Скен-режим" in plain


def _pwa_env(monkeypatch):
    import app as app_mod
    from services.db_service import DbStore
    from services.popis_service import PopisService
    from services.schemas import DEV_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "pwa.db")
    monkeypatch.setattr(app_mod, "devices", DbStore(db, "devices", DEV_COLS))
    monkeypatch.setattr(
        app_mod, "popis_svc", PopisService(db, os.path.join(tmp, "Popis.csv"))
    )
    monkeypatch.setattr(app_mod, "backup_all", lambda stores: None)
    for aid in ("AST001", "AST002", "AST003"):
        app_mod.devices.append_row(
            {"AssetID": aid, "SerialNumber": f"S-{aid}", "Status": "Available"}
        )
    pid = app_mod.popis_svc.start("location", "Магацин", ["AST001", "AST002"])
    return app_mod, pid


def test_pwa_scan_page_renders(monkeypatch):
    app_mod, pid = _pwa_env(monkeypatch)
    html = app_mod.app.test_client().get(f"/popis/{pid}/scan").get_data(as_text=True)
    assert f'data-pid="{pid}"' in html
    assert "<video" in html
    assert "Рачен внес" in html


def test_pwa_found_json_appends(monkeypatch):
    app_mod, pid = _pwa_env(monkeypatch)
    c = app_mod.app.test_client()
    r = c.post(f"/popis/{pid}/found", json={"asset_id": "AST001"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["ok"] is True
    assert data["asset_id"] == "AST001"
    assert "AST001" in app_mod.popis_svc.get(pid)["FoundIDs"]


def test_pwa_unknown_asset_404(monkeypatch):
    app_mod, pid = _pwa_env(monkeypatch)
    c = app_mod.app.test_client()
    r = c.post(f"/popis/{pid}/found", json={"asset_id": "NOPE"})
    assert r.status_code == 404
    assert r.get_json()["ok"] is False


def test_pwa_unknown_popis_404(monkeypatch):
    app_mod, pid = _pwa_env(monkeypatch)
    r = app_mod.app.test_client().post("/popis/NOPE/found", json={"asset_id": "AST001"})
    assert r.status_code == 404


def test_pwa_closed_popis_rejects(monkeypatch):
    app_mod, pid = _pwa_env(monkeypatch)
    app_mod.popis_svc.finish(pid)
    r = app_mod.app.test_client().post(
        f"/popis/{pid}/found", json={"asset_id": "AST001"}
    )
    assert r.status_code == 404


def test_pwa_csrf_header_accepted_and_required(monkeypatch):
    app_mod, pid = _pwa_env(monkeypatch)
    app_mod.app.config["CSRF_ENABLED"] = True
    try:
        c = app_mod.app.test_client()
        c.get(f"/popis/{pid}/scan")
        with c.session_transaction() as sess:
            tok = sess.get("_csrf_token")
        assert tok
        r = c.post(f"/popis/{pid}/found", json={"asset_id": "AST001"})
        assert r.status_code == 403
        r2 = c.post(
            f"/popis/{pid}/found",
            json={"asset_id": "AST001"},
            headers={"X-CSRF-Token": tok},
        )
        assert r2.status_code == 200
    finally:
        app_mod.app.config["CSRF_ENABLED"] = False
