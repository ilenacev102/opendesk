"""CSP nonce: header nonce matches inline script nonces (no blocked JS)."""

import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_nonce_matches_header_and_body():
    import app as app_mod
    from services.db_service import DbStore
    from services.history_service import HistoryService, HISTORY_COLS
    from services.schemas import DEV_COLS, EMP_COLS

    tmp = tempfile.mkdtemp()
    db = os.path.join(tmp, "n.db")
    import unittest.mock as mock

    with (
        mock.patch.object(app_mod, "devices", DbStore(db, "devices", DEV_COLS)),
        mock.patch.object(app_mod, "employees", DbStore(db, "employees", EMP_COLS)),
        mock.patch.object(
            app_mod, "history", HistoryService(DbStore(db, "history", HISTORY_COLS))
        ),
        mock.patch.object(app_mod, "backup_all", lambda stores: None),
    ):
        r = app_mod.app.test_client().get("/")
    assert r.status_code == 200
    csp = r.headers.get("Content-Security-Policy", "")
    m = re.search(r"'nonce-([A-Za-z0-9_-]+)'", csp)
    assert m, csp
    html = r.get_data(as_text=True)
    nonces = set(re.findall(r'<script nonce="([A-Za-z0-9_-]+)"', html))
    assert nonces, "no nonced inline scripts rendered"
    assert nonces == {m.group(1)}, (nonces, m.group(1))


def test_no_bare_inline_scripts():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    tpl = os.path.join(base, "templates_web")
    bad = []
    for name in os.listdir(tpl):
        if not name.endswith(".html"):
            continue
        with open(os.path.join(tpl, name), encoding="utf-8") as fh:
            for i, line in enumerate(fh, 1):
                if "<script>" in line:
                    bad.append(f"{name}:{i}")
    assert bad == [], bad
