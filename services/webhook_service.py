"""Outgoing webhooks: CRUD + async signed dispatch to Slack/Teams/Mattermost."""

import hashlib
import hmac
import json
import logging
import urllib.request
from concurrent.futures import ThreadPoolExecutor

from utils.helpers import next_id, stamp
from utils.validators import ValidationError

log = logging.getLogger("servicedesk")

EVENTS = frozenset(
    {"incident.critical_created", "change.cab_pending", "problem.resolved"}
)

TIMEOUT_S = 10

_pool = None


def _get_pool():
    global _pool
    if _pool is None:
        _pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="sd-hook")
    return _pool


def _parse_events(raw):
    """Comma-separated event string → validated frozenset.

    Raises:
        ValidationError: any unknown or missing event.
    """
    events = {e.strip() for e in str(raw or "").split(",") if e.strip()}
    if not events:
        raise ValidationError("Изберете барем еден настан за вебхукот.")
    unknown = events - EVENTS
    if unknown:
        raise ValidationError(f"Непознати настани: {', '.join(sorted(unknown))}.")
    return events


def create(webhooks, name, url, events="", secret=""):
    """Create an outgoing webhook target.

    Raises:
        ValidationError: empty name, non-http(s) URL, or unknown events.
    """
    name = (name or "").strip()
    url = (url or "").strip()
    if not name:
        raise ValidationError("Името на вебхукот е задолжително.")
    if not (url.startswith("http://") or url.startswith("https://")):
        raise ValidationError("URL мора да започнува со http:// или https://.")
    parsed = _parse_events(events)
    row = {
        "WebhookID": next_id(webhooks, "WebhookID", "WH"),
        "Name": name,
        "Url": url,
        "Events": ", ".join(sorted(parsed)),
        "Secret": (secret or "").strip() or secrets_token(),
        "Active": "YES",
        "Created": stamp(),
    }
    webhooks.append_row(row)
    return row


def secrets_token():
    import secrets

    return secrets.token_hex(16)


def delete(webhooks, webhook_id):
    row = webhooks.find("WebhookID", webhook_id)
    if row is None:
        raise ValidationError("Вебхукот не постои.")
    webhooks.delete_where("WebhookID", webhook_id)
    return row


def set_active(webhooks, webhook_id, active):
    row = webhooks.find("WebhookID", webhook_id)
    if row is None:
        raise ValidationError("Вебхукот не постои.")
    webhooks.update_where(
        "WebhookID", webhook_id, {"Active": "YES" if active else "NO"}
    )
    return row


def for_event(webhooks, event):
    """Active webhook rows subscribed to the event."""
    return [
        r
        for r in webhooks.records()
        if r.get("Active") == "YES"
        and event in [e.strip() for e in str(r.get("Events", "")).split(",")]
    ]


def _urlopen(req, timeout):
    return urllib.request.urlopen(req, timeout=timeout)


def _deliver(url, body, headers):
    """One HTTP POST; every failure is logged, never raised."""
    try:
        req = urllib.request.Request(url, data=body, headers=headers, method="POST")
        with _urlopen(req, TIMEOUT_S):
            pass
    except Exception as exc:
        log.warning("Webhook delivery failed url=%s: %s", url, exc)


def dispatch(webhooks, event, data):
    """Fire-and-forget JSON payload to every active webhook subscribed to event.

    Body: {"event": <event>, "data": <data>, "sent_at": <stamp>}.
    Signed with X-Signature (HMAC-SHA256 hex) when the webhook has a secret.
    Returns the list of webhook IDs scheduled for delivery.
    """
    targets = for_event(webhooks, event)
    if not targets:
        return []
    payload = {"event": event, "data": data, "sent_at": stamp()}
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    scheduled = []
    pool = _get_pool()
    for wh in targets:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "servicedesk-webhook/1.0",
            "X-SD-Event": event,
        }
        secret = (wh.get("Secret") or "").strip()
        if secret:
            headers["X-Signature"] = hmac.new(
                secret.encode("utf-8"), body, hashlib.sha256
            ).hexdigest()
        pool.submit(_deliver, wh.get("Url", ""), body, dict(headers))
        scheduled.append(wh.get("WebhookID", ""))
    return scheduled
