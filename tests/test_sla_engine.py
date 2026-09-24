"""Ticketing Pro todo 2: SLA business-hours engine (TDD)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_due_skips_weekend():
    from services.sla_service import due_date

    policies = [{"Priority": "urgent", "WarnHours": "1", "BreachHours": "2"}]
    assert due_date("2026-09-18 15:00", "urgent", policies) == "2026-09-21 09:00"


def test_due_skips_holiday():
    from services.sla_service import due_date

    policies = [{"Priority": "urgent", "WarnHours": "1", "BreachHours": "2"}]
    assert (
        due_date("2026-09-18 15:00", "urgent", policies, holidays={"2026-09-21"})
        == "2026-09-22 09:00"
    )


def test_due_unknown_priority_defaults_medium():
    from services.sla_service import DEFAULT_POLICIES, due_date

    assert due_date("2026-09-21 08:00", "nope", DEFAULT_POLICIES) == due_date(
        "2026-09-21 08:00", "medium", DEFAULT_POLICIES
    )


def test_due_garbage_created_raises():
    import pytest

    from services.sla_service import DEFAULT_POLICIES, due_date

    with pytest.raises(ValueError):
        due_date("not-a-date", "medium", DEFAULT_POLICIES)


def test_level_boundaries():
    from services.sla_service import level
    from datetime import date

    assert level("2026-10-01", "2026-09-30", today=date(2026, 9, 29)) == "ok"
    assert level("2026-10-01", "2026-09-30", today=date(2026, 9, 30)) == "warning"
    assert level("2026-10-01", "2026-09-30", today=date(2026, 10, 1)) == "warning"
    assert level("2026-10-01", "2026-09-30", today=date(2026, 10, 2)) == "breached"


def test_level_garbage_never_breaches():
    from services.sla_service import level

    assert level("", "") == "ok"
    assert level("garbage", "garbage") == "ok"


def test_seed_defaults_idempotent():
    import tempfile

    from services.db_service import DbStore
    from services.schemas import SLA_POLICY_COLS
    from services.sla_service import DEFAULT_POLICIES, seed_defaults

    tmp = tempfile.mkdtemp()
    store = DbStore(os.path.join(tmp, "s.db"), "sla_policies", SLA_POLICY_COLS)
    assert seed_defaults(store) == len(DEFAULT_POLICIES)
    assert seed_defaults(store) == 0
    assert len(store.records()) == len(DEFAULT_POLICIES)
