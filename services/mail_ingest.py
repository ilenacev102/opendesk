"""Email-to-ticket intake: IMAP poll, reconcile, confirm.

Manual trigger only (no daemon). Reply detection via [I-XXXXXX] subject tag.
Dedupe by Message-ID within the batch and against prior MAIL_* history.
Passwords live only in env and never enter logs or history.
"""

import email
import email.header
import email.utils
import imaplib
import os
import re

from services.db_service import db_transaction
from utils.helpers import next_id_in, stamp

ENV_HOST = "SERVICEDESK_IMAP_HOST"
ENV_PORT = "SERVICEDESK_IMAP_PORT"
ENV_USER = "SERVICEDESK_IMAP_USER"
ENV_PASSWORD = "SERVICEDESK_IMAP_PASSWORD"
ENV_MAILBOX = "SERVICEDESK_IMAP_MAILBOX"

REPLY_RE = re.compile(r"\[I-(\d+)\]", re.IGNORECASE)


class MailError(ValueError):
    """Friendly mail intake failure (unconfigured, unreachable, bad parse)."""


def configured() -> bool:
    return bool(
        os.environ.get(ENV_HOST, "").strip() and os.environ.get(ENV_USER, "").strip()
    )


def _decode(value) -> str:
    if not value:
        return ""
    parts = email.header.decode_header(value)
    out = []
    for chunk, charset in parts:
        if isinstance(chunk, bytes):
            try:
                out.append(chunk.decode(charset or "utf-8", errors="replace"))
            except (LookupError, UnicodeError):
                out.append(chunk.decode("utf-8", errors="replace"))
        else:
            out.append(chunk)
    return "".join(out)


def _body_of(msg) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get_filename():
                payload = part.get_payload(decode=True) or b""
                charset = part.get_content_charset() or "utf-8"
                try:
                    return payload.decode(charset, errors="replace")
                except (LookupError, UnicodeError):
                    return payload.decode("utf-8", errors="replace")
        return ""
    payload = msg.get_payload(decode=True)
    if payload is None:
        text = msg.get_payload()
        return text if isinstance(text, str) else ""
    charset = msg.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, UnicodeError):
        return payload.decode("utf-8", errors="replace")


def _live_fetch():
    host = os.environ.get(ENV_HOST, "").strip()
    user = os.environ.get(ENV_USER, "").strip()
    if not host or not user:
        raise MailError(f"Mail не е конфигуриран: поставете {ENV_HOST} и {ENV_USER}.")
    try:
        port = int(os.environ.get(ENV_PORT, "").strip() or "993")
    except ValueError:
        port = 993
    use_ssl = os.environ.get("SERVICEDESK_IMAP_SSL", "1").strip() != "0"
    mailbox = os.environ.get(ENV_MAILBOX, "").strip() or "INBOX"
    password = os.environ.get(ENV_PASSWORD, "")
    try:
        if use_ssl:
            conn = imaplib.IMAP4_SSL(host, port)
        else:
            conn = imaplib.IMAP4(host, port)
        conn.login(user, password)
        conn.select(mailbox, readonly=True)
        _, data = conn.search(None, "UNSEEN")
        mails = []
        for uid_raw in (data[0] or b"").split():
            uid = uid_raw.decode("ascii", errors="replace")
            _, fetched = conn.fetch(uid, "(RFC822)")
            raw = b""
            if fetched and fetched[0]:
                payload = fetched[0][1]
                raw = payload if isinstance(payload, bytes) else b""
            msg = email.message_from_bytes(raw)
            mails.append(
                {
                    "uid": uid,
                    "from": _decode(msg.get("From", "")),
                    "subject": _decode(msg.get("Subject", "")),
                    "body": _body_of(msg).strip(),
                    "message_id": (msg.get("Message-ID", "") or "").strip(),
                }
            )
        try:
            conn.close()
        except Exception:
            pass
        conn.logout()
        return mails
    except MailError:
        raise
    except Exception as exc:
        raise MailError(f"Mail серверот е недостапен: {exc}")


def fetch_unseen(connection_factory=None):
    if connection_factory is not None:
        try:
            return list(connection_factory().fetch_unseen())
        except MailError:
            raise
        except Exception as exc:
            raise MailError(f"Mail серверот е недостапен: {exc}")
    return _live_fetch()


def _reply_target(subject, incidents):
    match = REPLY_RE.search(subject or "")
    if not match:
        return None
    iid = f"I{int(match.group(1)):06d}"
    return incidents.find("IncidentID", iid)


def reconcile(mails, incidents, comments, history=None):
    seen_ids = set()
    if history is not None:
        for h in history.store.records():
            if (h.get("Action", "") or "") in ("MAIL_NEW", "MAIL_REPLY"):
                mid = (h.get("Reason", "") or "").strip()
                if mid.startswith("Message-ID:"):
                    seen_ids.add(mid[len("Message-ID:") :].strip())
    out = []
    for mail in mails or []:
        mid = (mail.get("message_id", "") or "").strip()
        if mid and mid in seen_ids:
            out.append({**mail, "verdict": "duplicate", "reason": "Веќе примен mail."})
            continue
        if mid:
            seen_ids.add(mid)
        target = _reply_target(mail.get("subject", ""), incidents)
        if target is not None:
            out.append(
                {
                    **mail,
                    "verdict": "reply",
                    "reason": f"Одговор на {target['IncidentID']}.",
                    "incident_id": target["IncidentID"],
                }
            )
        else:
            out.append({**mail, "verdict": "new", "reason": ""})
    return out


def confirm(rows, incidents, comments, history, performed_by="admin", db_path=None):
    counts = {"new": 0, "replies": 0, "skipped": 0}

    def _apply(con):
        for row in rows:
            verdict = row.get("verdict", "new")
            if verdict == "duplicate":
                counts["skipped"] += 1
                continue
            if verdict == "reply":
                target = incidents.find("IncidentID", row.get("incident_id", ""))
                if target is None:
                    counts["skipped"] += 1
                    continue
                cid = next_id_in(comments, "CommentID", "C", con)
                body = (row.get("body", "") or "").strip()
                comments.append_row(
                    {
                        "CommentID": cid,
                        "IncidentID": target["IncidentID"],
                        "Author": (row.get("from", "") or "").strip(),
                        "Body": body,
                        "Created": stamp(),
                    },
                    con=con,
                )
                mid = (row.get("message_id", "") or "").strip()
                history.log(
                    "MAIL_REPLY",
                    target["IncidentID"],
                    "",
                    "",
                    "",
                    "",
                    f"Message-ID:{mid}" if mid else "Одговор преку mail.",
                    "",
                    performed_by,
                    "",
                    con=con,
                )
                counts["replies"] += 1
            else:
                iid = next_id_in(incidents, "IncidentID", "I", con)
                sender = (row.get("from", "") or "").strip()
                subject = (row.get("subject", "") or "").strip() or "(без наслов)"
                body = (row.get("body", "") or "").strip()
                notes = f"Од mail: {sender}\n{body[:500]}".strip()
                incidents.append_row(
                    {
                        "IncidentID": iid,
                        "AssetID": "",
                        "EmployeeID": "",
                        "Title": subject[:200],
                        "Priority": "medium",
                        "Status": "open",
                        "Assignee": "",
                        "DueDate": "",
                        "Created": stamp(),
                        "ClosedAt": "",
                        "Notes": notes,
                    },
                    con=con,
                )
                mid = (row.get("message_id", "") or "").strip()
                history.log(
                    "MAIL_NEW",
                    iid,
                    "",
                    "open",
                    "",
                    "",
                    subject[:120],
                    f"Message-ID:{mid}" if mid else "",
                    performed_by,
                    "",
                    con=con,
                )
                counts["new"] += 1

    if db_path:
        with db_transaction(db_path) as con:
            _apply(con)
    else:
        _apply(None)
    return counts
