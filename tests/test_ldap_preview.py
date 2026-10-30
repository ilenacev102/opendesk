"""Backlog LDAP scheduled-preview: read-only, never writes."""

import importlib.util
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "scripts",
    "ldap_preview.py",
)


def _load():
    spec = importlib.util.spec_from_file_location("ldap_preview", _SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_format_summary_counts():
    mod = _load()
    line = mod.format_summary({"matched": [{"a": 1}, {"b": 2}], "staged": [{"c": 3}]})
    assert line == "LDAP preview: matched=2 staged=1"


def test_run_preview_read_only():
    mod = _load()

    class FakeSvc:
        def __init__(self):
            self.writes = 0

        def fetch_users(self, connection_factory=None):
            return [{"UserName": "u1"}, {"UserName": "u2"}]

        def reconcile(self, users):
            assert len(users) == 2
            return {"matched": [users[0]], "staged": [users[1]]}

    report = mod.run_preview(FakeSvc())
    assert len(report["matched"]) == 1
    assert len(report["staged"]) == 1


def test_main_exits_2_when_unconfigured(monkeypatch, capsys):
    mod = _load()
    monkeypatch.delenv("SERVICEDESK_LDAP_URL", raising=False)
    monkeypatch.delenv("SERVICEDESK_LDAP_BASE", raising=False)
    assert mod.main([]) == 2
    assert "skipped" in capsys.readouterr().out
