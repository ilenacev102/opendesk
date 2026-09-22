"""Popis scan/finish must be atomic under concurrent access."""

import json
import os
import sys
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.popis_service import PopisService


def _svc(tmpdir):
    return PopisService(os.path.join(tmpdir, "p.db"), os.path.join(tmpdir, "p.csv"))


def test_concurrent_scans_do_not_lose_updates(tmp_path):
    svc = _svc(str(tmp_path))
    assets = [f"AST-{i:03d}" for i in range(20)]
    pid = svc.start("location", "HQ", assets)

    errors = []

    def scan_many(ids):
        try:
            for aid in ids:
                svc.scan(pid, aid)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=scan_many, args=(assets[:10],))
    t2 = threading.Thread(target=scan_many, args=(assets[10:],))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert not errors, errors
    rec = svc.get(pid)
    assert rec is not None
    found = set(rec["FoundIDs"])
    assert found == set(assets), f"lost scans: missing {set(assets) - found}"


def test_scan_rejects_when_closed(tmp_path):
    svc = _svc(str(tmp_path))
    pid = svc.start("location", "HQ", ["AST-001"])
    svc.finish(pid)
    assert svc.scan(pid, "AST-001") is None


def test_finish_idempotent_status(tmp_path):
    svc = _svc(str(tmp_path))
    pid = svc.start("location", "HQ", ["AST-001", "AST-002"])
    svc.scan(pid, "AST-001")
    result = svc.finish(pid)
    assert result is not None
    assert result["missing"] == ["AST-002"]
    rec = svc.get(pid)
    assert rec is not None
    assert rec["Status"] == "CLOSED"
