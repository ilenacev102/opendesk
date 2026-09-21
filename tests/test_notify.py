"""Phase A.3: SMTP notifications (TDD). SMTP is faked, no network."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services import notify_service as notify


class FakeSMTP:
    instances = []

    def __init__(self, host, port, timeout=10):
        self.host = host
        self.port = port
        self.sent = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def starttls(self):
        pass

    def login(self, user, password):
        self.user = user

    def send_message(self, msg):
        self.sent.append(msg)


@pytest.fixture
def smtp_env(monkeypatch):
    monkeypatch.setenv("SERVICEDESK_SMTP_HOST", "mail.example.mk")
    monkeypatch.setenv("SERVICEDESK_SMTP_PORT", "587")
    monkeypatch.setenv("SERVICEDESK_SMTP_USER", "srv")
    monkeypatch.setenv("SERVICEDESK_SMTP_PASS", "sekret")
    monkeypatch.setenv("SERVICEDESK_SMTP_FROM", "servicedesk@example.mk")
    monkeypatch.setenv("SERVICEDESK_ADMIN_EMAIL", "admin@example.mk")
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    FakeSMTP.instances.clear()


def test_not_configured_returns_false_without_sending(monkeypatch):
    monkeypatch.delenv("SERVICEDESK_SMTP_HOST", raising=False)
    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)
    FakeSMTP.instances.clear()
    assert notify.send_email("a@x.mk", "Subj", "Body") is False
    assert FakeSMTP.instances == []


def test_send_email_happy_path(smtp_env):
    assert notify.send_email("pera@example.mk", "Наслов", "Текст") is True
    assert len(FakeSMTP.instances) == 1
    msg = FakeSMTP.instances[0].sent[0]
    assert msg["To"] == "pera@example.mk"
    assert "Наслов" in str(msg["Subject"])


def test_smtp_failure_returns_false(smtp_env, monkeypatch):
    class BoomSMTP(FakeSMTP):
        def send_message(self, msg):
            raise OSError("network down")

    monkeypatch.setattr("smtplib.SMTP", BoomSMTP)
    assert notify.send_email("a@x.mk", "S", "B") is False


def test_assignment_email_content():
    to, subject, body = notify.assignment_email(
        "ana@example.mk", "Ана Тест", "LAP001", "Lenovo T14", "AS-7"
    )
    assert to == "ana@example.mk"
    assert "LAP001" in subject
    assert "Ана Тест" in body and "AS-7" in body


def test_assignment_email_no_address_returns_none():
    assert notify.assignment_email("", "Ана", "LAP001", "X", "AS-1") is None


def test_return_email_content():
    to, subject, body = notify.return_email(
        "ana@example.mk", "Ана Тест", "LAP001", "RT-3"
    )
    assert to == "ana@example.mk"
    assert "LAP001" in subject and "RT-3" in body


def test_warranty_expiring_selects_window():
    import datetime

    today = datetime.date.today()
    rows = [
        {
            "AssetID": "A1",
            "WarrantyUntil": (
                today.replace(day=1) if today.day > 28 else today
            ).isoformat(),
        },
        {"AssetID": "A2", "WarrantyUntil": "2000-01-01"},
        {"AssetID": "A3", "WarrantyUntil": ""},
        {"AssetID": "A4", "WarrantyUntil": "not-a-date"},
    ]
    soon = (today + datetime.timedelta(days=5)).isoformat()
    rows[0]["WarrantyUntil"] = soon
    out = notify.warranty_expiring(rows, days=30)
    assert [r["AssetID"] for r in out] == ["A1"]


def test_digest_email_lists_devices():
    to, subject, body = notify.digest_email(
        "admin@example.mk",
        [{"AssetID": "A1", "WarrantyUntil": "2026-10-01", "Model": "T14"}],
    )
    assert to == "admin@example.mk"
    assert "A1" in body
