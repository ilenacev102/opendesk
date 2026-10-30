"""F3: breach forecast (pure) + digest section."""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _inc(iid, status, due):
    return {"IncidentID": iid, "Status": status, "DueDate": due, "Title": "t"}


def test_garbage_never_forecast():
    from services.sla_service import forecast, will_breach

    assert will_breach("", 2) is False
    assert will_breach("не-датум", 2) is False
    assert forecast([], 2) == []
    assert forecast([_inc("I-1", "open", "")], 2) == []


def test_window_and_sorting():
    from services.sla_service import forecast

    today = date.today()
    incs = [
        _inc("I-1", "open", (today + timedelta(days=5)).isoformat()),
        _inc("I-2", "open", (today + timedelta(days=2)).isoformat()),
        _inc("I-3", "open", (today + timedelta(days=1)).isoformat()),
        _inc("I-4", "resolved", (today + timedelta(days=1)).isoformat()),
        _inc("I-5", "open", (today - timedelta(days=1)).isoformat()),
    ]
    out = forecast(incs, 2, today.isoformat())
    assert [i["IncidentID"] for i in out] == ["I-3", "I-2"]


def test_digest_without_forecast_unchanged():
    from services.notify_service import digest_email

    to, subject, body = digest_email("a@x.mk", [], [], [])
    assert "Ќе пробијат" not in body
    assert "Ќе пробијат" not in subject
    assert to == "a@x.mk"


def test_digest_with_forecast_section():
    from services.notify_service import digest_email

    rows = [
        {
            "IncidentID": "I-9",
            "Title": "vend",
            "Assignee": "mag",
            "DueDate": "2026-10-01",
        }
    ]
    to, subject, body = digest_email("a@x.mk", [], [], [], rows)
    assert "Ќе пробијат наскоро" in body
    assert "I-9" in body
    assert "ќе пробијат (1)" in subject
