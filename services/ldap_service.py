"""LDAP read-only sync: fetch users, reconcile with employees, stage mapping.

Read-only by design: never writes to the directory, never stores passwords,
never deactivates local users. Sync is a manual admin action with dry-run.
"""

import os

from services.db_service import db_transaction
from utils.helpers import stamp

ENV_URL = "SERVICEDESK_LDAP_URL"
ENV_BIND_DN = "SERVICEDESK_LDAP_BIND_DN"
ENV_PASSWORD = "SERVICEDESK_LDAP_PASSWORD"
ENV_BASE = "SERVICEDESK_LDAP_BASE"
ENV_FILTER = "SERVICEDESK_LDAP_FILTER"
DEFAULT_FILTER = "(objectClass=user)"
ATTRS = ["cn", "mail", "department", "sAMAccountName"]


class LdapError(ValueError):
    """Friendly LDAP failure (unreachable, unconfigured, bad search)."""


def configured() -> bool:
    return bool(
        os.environ.get(ENV_URL, "").strip() and os.environ.get(ENV_BASE, "").strip()
    )


def _map_entry(entry):
    dn = str(entry.get("dn", "") or "")
    cn = str(entry.get("cn", "") or "").strip()
    mail = str(entry.get("mail", "") or "").strip()
    dept = str(entry.get("department", "") or "").strip()
    sam = str(entry.get("samaccountname", "") or "").strip().lower()
    if sam:
        username = sam
    elif mail and "@" in mail:
        username = mail.split("@")[0].lower()
    else:
        username = cn.lower().replace(" ", ".")
    return {
        "DN": dn,
        "cn": cn,
        "mail": mail,
        "Email": mail,
        "UserName": username,
        "Department": dept,
    }


def _normalize_search(raw, conn):
    if isinstance(raw, list):
        return raw
    if not raw:
        result = getattr(conn, "result", "")
        raise LdapError(f"LDAP пребарувањето не успеа: {result}")
    out = []
    for e in getattr(conn, "entries", []) or []:
        out.append(
            {
                "dn": getattr(e, "entry_dn", ""),
                "cn": str(getattr(e, "cn", "") or ""),
                "mail": str(getattr(e, "mail", "") or ""),
                "department": str(getattr(e, "department", "") or ""),
                "samaccountname": str(getattr(e, "sAMAccountName", "") or ""),
            }
        )
    return out


def _live_connection():
    import ldap3

    url = os.environ.get(ENV_URL, "").strip()
    base = os.environ.get(ENV_BASE, "").strip()
    if not url or not base:
        raise LdapError(f"LDAP не е конфигуриран: поставете {ENV_URL} и {ENV_BASE}.")
    bind_dn = os.environ.get(ENV_BIND_DN, "").strip()
    password = os.environ.get(ENV_PASSWORD, "")
    try:
        server = ldap3.Server(url, connect_timeout=10)
        conn = ldap3.Connection(
            server,
            user=bind_dn or None,
            password=password or None,
            auto_bind=True,
        )
    except Exception as exc:
        raise LdapError(f"LDAP поврзувањето не успеа: {exc}")
    return conn


class LdapService:
    def __init__(self, employees, ldapmap, history, db_path=None):
        self.employees = employees
        self.ldapmap = ldapmap
        self.history = history
        self.db_path = db_path

    def _tx(self):
        if self.db_path:
            return db_transaction(self.db_path)
        from contextlib import nullcontext

        return nullcontext(None)

    def fetch_users(self, connection_factory=None):
        base = os.environ.get(ENV_BASE, "").strip()
        filt = os.environ.get(ENV_FILTER, "").strip() or DEFAULT_FILTER
        if connection_factory is None:
            if not configured():
                raise LdapError(
                    f"LDAP не е конфигуриран: поставете {ENV_URL} и {ENV_BASE}."
                )
            connection_factory = _live_connection
        try:
            conn = connection_factory()
            raw = conn.search(base, filt, attributes=ATTRS)
        except LdapError:
            raise
        except Exception as exc:
            raise LdapError(f"LDAP серверот е недостапен: {exc}")
        try:
            entries = _normalize_search(raw, conn)
        except LdapError:
            raise
        except Exception as exc:
            raise LdapError(f"LDAP одговорот е невалиден: {exc}")
        return [_map_entry(e) for e in entries]

    def reconcile(self, users):
        by_email, by_username = {}, {}
        for emp in self.employees.records():
            email = (emp.get("Email", "") or "").strip().lower()
            uname = (emp.get("UserName", "") or "").strip().lower()
            if email:
                by_email.setdefault(email, emp)
            if uname:
                by_username.setdefault(uname, emp)
        matched, staged = [], []
        for user in users:
            emp = None
            if user.get("Email"):
                emp = by_email.get(user["Email"].strip().lower())
            if emp is None and user.get("UserName"):
                emp = by_username.get(user["UserName"].strip().lower())
            if emp is None:
                staged.append(user)
            else:
                matched.append({"ldap": user, "employee": emp})
        return {"matched": matched, "staged": staged}

    def sync(self, users, dry_run=True, performed_by="admin"):
        result = self.reconcile(users)
        counts = {
            "dry_run": bool(dry_run),
            "matched": len(result["matched"]),
            "staged": len(result["staged"]),
        }
        if dry_run:
            return counts
        with self._tx() as con:
            for user in users:
                data = {
                    "UserName": user.get("UserName", ""),
                    "DN": user.get("DN", ""),
                    "LastSync": stamp().split(" ")[0],
                }
                changed = self.ldapmap.update_where(
                    "UserName", data["UserName"], data, con=con
                )
                if not changed:
                    self.ldapmap.append_row(data, con=con)
            self.history.log(
                "LDAP_SYNC",
                "",
                "",
                "",
                "",
                "",
                f"matched={counts['matched']} staged={counts['staged']}",
                "",
                performed_by,
                "",
                con=con,
            )
        return counts
