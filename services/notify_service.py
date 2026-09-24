"""Phase A.3: SMTP notifications. Never raises - returns False on failure."""

import datetime
import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger("servicedesk")


def get_config():
    return {
        "host": os.environ.get("SERVICEDESK_SMTP_HOST", "").strip(),
        "port": (os.environ.get("SERVICEDESK_SMTP_PORT", "587") or "587").strip(),
        "user": os.environ.get("SERVICEDESK_SMTP_USER", ""),
        "password": os.environ.get("SERVICEDESK_SMTP_PASS", ""),
        "from_addr": os.environ.get("SERVICEDESK_SMTP_FROM", "").strip(),
        "admin_email": os.environ.get("SERVICEDESK_ADMIN_EMAIL", "").strip(),
    }


def configured() -> bool:
    cfg = get_config()
    return bool(cfg["host"] and cfg["from_addr"])


def send_email(to: str, subject: str, body: str) -> bool:
    cfg = get_config()
    if not cfg["host"] or not cfg["from_addr"] or not (to or "").strip():
        return False
    msg = EmailMessage()
    msg["From"] = cfg["from_addr"]
    msg["To"] = to.strip()
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(cfg["host"], int(cfg["port"]), timeout=10) as smtp:
            smtp.starttls()
            if cfg["user"]:
                smtp.login(cfg["user"], cfg["password"])
            smtp.send_message(msg)
        return True
    except Exception:
        log.exception("Notify failed to=%s", to)
        return False


def assignment_email(emp_email, emp_name, asset_id, device_desc, tid):
    if not (emp_email or "").strip():
        return None
    subject = f"Задолжување: {asset_id}"
    body = (
        f"Почитуван/а {emp_name},\n\n"
        f"Задолжен ви е уред {asset_id} ({device_desc}).\n"
        f"Број на трансакција: {tid}.\n\n"
        "IT ServiceDesk"
    )
    return emp_email.strip(), subject, body


def return_email(emp_email, emp_name, asset_id, tid):
    if not (emp_email or "").strip():
        return None
    subject = f"Раздолжување: {asset_id}"
    body = (
        f"Почитуван/а {emp_name},\n\n"
        f"Раздолжен ви е уредот {asset_id}.\n"
        f"Број на трансакција: {tid}.\n\n"
        "IT ServiceDesk"
    )
    return emp_email.strip(), subject, body


def warranty_expiring(rows, days=30):
    today = datetime.date.today()
    limit = today + datetime.timedelta(days=days)
    out = []
    for r in rows or []:
        raw = (r.get("WarrantyUntil") or "").strip()
        try:
            until = datetime.date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if today <= until <= limit:
            out.append(r)
    return out


def breached_incidents(rows, today=None):
    """Incidents with passed DueDate, excluding resolved ones.

    Empty/garbage dates never breach (same contract as incident breach()).
    """
    from services.incident_service import breach as _breach

    today = today or datetime.date.today()
    out = []
    for r in rows or []:
        if (r.get("Status", "") or "") == "resolved":
            continue
        if _breach(r.get("DueDate", ""), today):
            out.append(r)
    return out


def digest_email(admin_email, expiring_rows, breached_rows=None):
    lines = [
        f"- {r.get('AssetID', '')} "
        f"({r.get('Manufacturer', '')} {r.get('Model', '')}): "
        f"{r.get('WarrantyUntil', '')}"
        for r in expiring_rows
    ]
    subject = f"Гаранции што истекуваат ({len(expiring_rows)})"
    body = "Уреди со гаранција што истекува наскоро:\n\n" + "\n".join(lines)
    breached_rows = breached_rows or []
    if breached_rows:
        blines = [
            f"- {r.get('IncidentID', '')} "
            f"({r.get('Title', '')}, {r.get('Assignee', '')}): "
            f"{r.get('DueDate', '')}"
            for r in breached_rows
        ]
        subject += f", пробиени рокови ({len(breached_rows)})"
        body += "\n\nИнциденти со пробиен рок:\n\n" + "\n".join(blines)
    return admin_email, subject, body
