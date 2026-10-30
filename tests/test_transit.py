"""MS-3: status transition table (pure, no I/O)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_allowed_ship_and_receive():
    from services.transit_service import can_move

    assert can_move("Available", "InTransit") is True
    assert can_move("InTransit", "Available") is True
    assert can_move("Broken", "Repair") is True
    assert can_move("Repair", "Repaired") is True


def test_forbidden_skips():
    from services.transit_service import can_move

    assert can_move("Assigned", "Disposed") is False
    assert can_move("Repair", "Available") is False
    assert can_move("Disposed", "Available") is False


def test_unknown_states():
    from services.transit_service import allowed, can_move

    assert can_move("Foo", "Available") is False
    assert can_move("Available", "Bar") is False
    assert can_move("", "") is False
    assert allowed("Foo") == ()


def test_round_trip_and_no_self_move():
    from services.transit_service import can_move

    assert can_move("Available", "Assigned") is True
    assert can_move("Assigned", "InTransit") is True
    assert can_move("InTransit", "Assigned") is True
    assert can_move("Available", "Available") is False
