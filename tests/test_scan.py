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
    from services.history_service import HistoryService, HISTORY_COLS
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
