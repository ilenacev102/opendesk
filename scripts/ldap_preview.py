"""LDAP scheduled preview: fetch + reconcile, never writes.

Read-only by design: calls fetch_users() + reconcile() only, never sync().
Intended for cron: `0 6 * * * ... python3 scripts/ldap_preview.py >> logs/ldap_preview.log 2>&1`
Exit codes: 0 ok, 2 not configured/unreachable.

Usage: python3 scripts/ldap_preview.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def format_summary(report):
    """Pure formatter: reconcile report -> one log line."""
    matched = len(report.get("matched", []))
    staged = len(report.get("staged", []))
    return f"LDAP preview: matched={matched} staged={staged}"


def run_preview(svc, connection_factory=None):
    """Fetch + reconcile via service; returns report dict (no writes)."""
    users = svc.fetch_users(connection_factory=connection_factory)
    return svc.reconcile(users)


def main(argv=None):
    from services.ldap_service import LdapError, LdapService, configured

    if not configured():
        print("LDAP preview: skipped (SERVICEDESK_LDAP_URL/BASE not set)")
        return 2
    import app as app_mod

    svc = LdapService(
        app_mod.employees,
        app_mod.ldapmap,
        app_mod.history,
        db_path=getattr(app_mod.ldapmap, "db_path", None),
    )
    try:
        report = run_preview(svc)
    except LdapError as exc:
        print(f"LDAP preview: FAILED ({exc})")
        return 2
    print(format_summary(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
