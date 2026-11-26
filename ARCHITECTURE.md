# OpenDesk Architecture & Technical Source of Truth

> Verified against: `routes/`, `services/`, `tests/`, `config.py`.

## 1. C4 Summary

- **Context:** Enterprise LAN & On-Premises Application.
  - **Actors:** `admin`, `magacioner` (operator/inventory manager), `citac` (viewer/auditor).
  - **External Systems (Read-Only integrations except heartbeat & SMTP):** SMTP (notifications), IMAP (email-to-ticket polling), LDAP/Active Directory (user sync), Intune Graph (device discovery), SNMP (printer/network sweep), OIDC Identity Provider (Entra ID, Google Workspace, Keycloak), LibreOffice (`soffice` for PDF compilation).
- **Containers:** Single Flask process (gunicorn in Docker) + SQLite (default WAL-mode) or PostgreSQL (`SERVICEDESK_DB_URL`) + isolated storage directories (`documents/`, `backup/`, `logs/`).
- **Components:** `app.py` (core initialization, auth guard, store factories, CSP headers) + Blueprints in `routes/` (admin, api, catalog, cmdb, files, incidents, inventory, kb, operations, popis, reports, system) + pure domain business rules in `services/` + pure Jinja templates in `templates_web/`.

---

## 2. Layering & Architectural Rules

```
HTTP (routes/)  ──>  services/ (business rules)  ──>  stores/ (db_service/open_store)  ──>  SQLite / Postgres
```

- **Routes:** Only validate user input, verify authentication, invoke domain services, and render templates or redirect. **No direct SQL and no business decisions inside routes.**
- **Services:** Pure domain logic; unaware of HTTP requests or responses. Return typed results or raise explicit domain exceptions (`ValidationError`, `StoreError`).
- **Templates:** Jinja only; design tokens via CSS variables in `static/css/app.css` (`DESIGN.md`).
- **Audit Trails:** Every mutation writes an audit log (`History`) row inside the very same database transaction.

---

## 3. Asset Lifecycle State Machine

```
Available  <──>  Assigned  ──>  Broken  ──>  Repair  ──>  Repaired  ──>  Available
                   │
                   └──> Broken  ──>  Unrepairable  ──>  Disposed
```

- **Transitions:** Strictly guarded state engine. Devices under active repair cannot be reassigned without completing repair closure.
- **Disposal Guard:** Assets cannot be disposed while assigned to an employee; assignment must be returned first.
- **Bulk Operations:** Multi-asset offboarding and transfers execute under a single transaction and single unified handoff document.

---

## 4. Concurrency & Transactions

- `BEGIN IMMEDIATE` on SQLite for all multi-table mutations (device update + transaction record + history audit log) ensuring atomic commits or complete rollbacks.
- Database connections enforce `journal_mode=WAL` and `busy_timeout=5000`.
- Concurrent Heartbeat race handling: Secondary workers fail gracefully on integrity collisions and reconcile smoothly.

---

## 5. Storage & Migrations

- `StoreProtocol` with `open_store()` factory: Default SQLite (`SERVICEDESK_DB`), optional PostgreSQL via `SERVICEDESK_DB_URL`.
- Seamless SQLite to PostgreSQL migration via `services/pg_mover.py` (dry-run, row verification, zero-loss transfer).
- Consistent hot backups capturing write-ahead logs (WAL) cleanly.
