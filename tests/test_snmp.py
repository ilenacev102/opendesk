"""Discovery Pro todo 4: SNMP printer sweep optional (TDD)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class FakeSession:
    def __init__(self, host, community, data=None, fail=False):
        self.host = host
        self.community = community
        self._data = data or {}
        self.fail = fail

    def get_many(self, oids):
        if self.fail:
            raise TimeoutError(f"no response from {self.host}")
        return {oid: self._data.get(oid, "") for oid in oids}


PRINTER_OIDS = [
    "1.3.6.1.2.1.1.1.0",
    "1.3.6.1.2.1.1.5.0",
    "1.3.6.1.2.1.43.5.1.1.17.1",
]

PRINTER_A = {
    "1.3.6.1.2.1.1.1.0": "HP LaserJet Pro M404dn",
    "1.3.6.1.2.1.1.5.0": "PRN-FLOOR1",
    "1.3.6.1.2.1.43.5.1.1.17.1": "VNB3R12345",
}

PRINTER_B = {
    "1.3.6.1.2.1.1.1.0": "Canon i-SENSYS MF445dw",
    "1.3.6.1.2.1.1.5.0": "PRN-FLOOR2",
    "1.3.6.1.2.1.43.5.1.1.17.1": "W31234567",
}


def _factory(mapping):
    def _make(host, community):
        entry = mapping.get(host)
        if entry is None:
            return FakeSession(host, community, fail=True)
        return FakeSession(host, community, data=entry)

    return _make


def test_sweep_maps_printers():
    from services.snmp_service import PRINTER_OIDS as OIDS
    from services.snmp_service import sweep

    assert set(OIDS) == set(PRINTER_OIDS)
    rows, errors = sweep(
        ["10.0.0.11", "10.0.0.12"],
        "public",
        session_factory=_factory({"10.0.0.11": PRINTER_A, "10.0.0.12": PRINTER_B}),
    )
    assert errors == []
    by_ip = {r["Hostname"]: r for r in rows}
    assert by_ip["PRN-FLOOR1"]["SerialNumber"] == "VNB3R12345"
    assert by_ip["PRN-FLOOR1"]["Manufacturer"] == "HP"
    assert by_ip["PRN-FLOOR2"]["SerialNumber"] == "W31234567"
    assert all(r["Source"] == "snmp" for r in rows)


def test_unreachable_skipped_not_aborted():
    from services.snmp_service import sweep

    rows, errors = sweep(
        ["10.0.0.11", "10.0.0.99"],
        "public",
        session_factory=_factory({"10.0.0.11": PRINTER_A}),
    )
    assert len(rows) == 1
    assert len(errors) == 1
    assert "10.0.0.99" in errors[0]


def test_empty_serial_skipped():
    from services.snmp_service import sweep

    rows, errors = sweep(
        ["10.0.0.13"],
        "public",
        session_factory=_factory(
            {
                "10.0.0.13": {
                    "1.3.6.1.2.1.1.1.0": "Generic Printer",
                    "1.3.6.1.2.1.1.5.0": "PRN-X",
                    "1.3.6.1.2.1.43.5.1.1.17.1": "",
                }
            }
        ),
    )
    assert rows == []
    assert len(errors) == 1


def test_no_lib_clean_error(monkeypatch):
    import services.snmp_service as snmp
    from services.snmp_service import SnmpError

    monkeypatch.setattr(snmp, "_HAS_PYSNMP", False)
    try:
        snmp.live_session("10.0.0.11", "public")
        assert False, "expected SnmpError"
    except SnmpError as exc:
        assert "pysnmp" in str(exc).lower()
