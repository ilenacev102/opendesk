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


_mail_pool = None


def _get_mail_pool():
    global _mail_pool
    if _mail_pool is None:
        from concurrent.futures import ThreadPoolExecutor

        _mail_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sd-mail")
    return _mail_pool


def send_email_async(to: str, subject: str, body: str):
    """Dispatch email via background thread without blocking the HTTP request."""
    try:
        pool = _get_mail_pool()
        return pool.submit(send_email, to, subject, body)
    except Exception:
        log.exception("Failed to submit async email to=%s", to)
        return None



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


def _expiring_on(rows, field, days=30):
    today = datetime.date.today()
    limit = today + datetime.timedelta(days=days)
    out = []
    for r in rows or []:
        raw = (r.get(field, "") or "").strip()
        try:
            until = datetime.date.fromisoformat(raw[:10])
        except ValueError:
            continue
        if today <= until <= limit:
            out.append(r)
    return out


def contracts_expiring(rows, days=30):
    """Contracts with ValidUntil in [today, today + days]; garbage skipped."""
    return _expiring_on(rows, "ValidUntil", days)


def licenses_expiring(rows, days=30):
    """Licenses with ExpiryDate in [today, today + days]; garbage skipped."""
    return _expiring_on(rows, "ExpiryDate", days)


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


def summary_email(admin_email, stats):
    """Monthly summary: totals, warranty forecast, tickets, MTTR."""
    stats = stats or {}
    month = stats.get("month", "")
    fc = stats.get("warranty_fc", {}) or {}
    lines = [
        f"Месечен извештај{f' за {month}' if month else ''}",
        "",
        f"Вкупно уреди: {stats.get('total_devices', 0)} "
        f"(задолжени: {stats.get('assigned', 0)})",
        f"Вкупни трошоци: {stats.get('costs_total', 0)} ден.",
        "",
        "Гарантна прогноза: истечени "
        f"{fc.get('expired', 0)}, 30 дена {fc.get('d30', 0)}, "
        f"60 дена {fc.get('d60', 0)}, 90 дена {fc.get('d90', 0)}.",
        "",
        f"Отворени инциденти: {stats.get('inc_open', 0)}, "
        f"пробиени рокови: {stats.get('breach_open', 0)}, "
        f"ескалирани: {stats.get('escalated', 0)}.",
        f"MTTR: {stats.get('mttr', '—')} ч.",
    ]
    if stats.get("csat") is not None:
        lines.append(f"CSAT: {stats.get('csat')}/5.")
    if stats.get("contracts_30") is not None:
        lines.append(f"Договори што истекуваат (30д): {stats.get('contracts_30')}.")
    body = "\n".join(lines)
    subject = f"Месечен извештај{f' {month}' if month else ''}"
    return admin_email, subject, body


def digest_email(
    admin_email,
    expiring_rows,
    breached_rows=None,
    escalated_rows=None,
    forecast_rows=None,
    contract_rows=None,
    license_rows=None,
):
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
    escalated_rows = escalated_rows or []
    if escalated_rows:
        elines = [
            f"- {r.get('IncidentID', '')} "
            f"({r.get('Title', '')}, {r.get('Priority', '')})"
            for r in escalated_rows
        ]
        subject += f", ескалирани ({len(escalated_rows)})"
        body += "\n\nЕскалирани инциденти:\n\n" + "\n".join(elines)
    forecast_rows = forecast_rows or []
    if forecast_rows:
        flines = [
            f"- {r.get('IncidentID', '')} "
            f"({r.get('Title', '')}, {r.get('Assignee', '')}): "
            f"{r.get('DueDate', '')}"
            for r in forecast_rows
        ]
        subject += f", ќе пробијат ({len(forecast_rows)})"
        body += "\n\nЌе пробијат наскоро:\n\n" + "\n".join(flines)
    contract_rows = contract_rows or []
    if contract_rows:
        clines = [
            f"- {r.get('ContractID', '')} "
            f"({r.get('Title', '')}, {r.get('Supplier', '')}): "
            f"{r.get('ValidUntil', '')}"
            for r in contract_rows
        ]
        subject += f", договори ({len(contract_rows)})"
        body += "\n\nДоговори што истекуваат:\n\n" + "\n".join(clines)
    license_rows = license_rows or []
    if license_rows:
        llines = [
            f"- {r.get('LicenseID', '')} "
            f"({r.get('Software', '')}): "
            f"{r.get('ExpiryDate', '')}"
            for r in license_rows
        ]
        subject += f", лиценци ({len(license_rows)})"
        body += "\n\nЛиценци што истекуваат:\n\n" + "\n".join(llines)
    return admin_email, subject, body
