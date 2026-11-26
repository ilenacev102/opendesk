"""P2.7: the SNMP sweep has a real, testable entry point."""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_cli_prints_rows_as_json(monkeypatch, capsys):
    import scripts.snmp_sweep as cli

    seen = {}

    def fake_sweep(hosts, community):
        seen["hosts"] = hosts
        seen["community"] = community
        return [{"Hostname": "prn-1", "SerialNumber": "SN1"}], []

    monkeypatch.setattr(cli, "sweep", fake_sweep)
    assert cli.main(["--hosts", "10.0.0.1, 10.0.0.2", "--community", "ro"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["rows"] == [{"Hostname": "prn-1", "SerialNumber": "SN1"}]
    assert seen == {"hosts": ["10.0.0.1", "10.0.0.2"], "community": "ro"}


def test_cli_reports_missing_library(monkeypatch, capsys):
    import scripts.snmp_sweep as cli
    from services.snmp_service import SnmpError

    def boom(hosts, community):
        raise SnmpError("SNMP библиотеката недостасува")

    monkeypatch.setattr(cli, "sweep", boom)
    assert cli.main(["--hosts", "10.0.0.1"]) == 2
    assert "недостасува" in capsys.readouterr().err
