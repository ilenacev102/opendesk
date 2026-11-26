# AGENTS.md

## Project
IT ServiceDesk: local Flask + SQLite (Postgres optional) app for IT asset lifecycle,
inventory, ticketing/SLA, CMDB and audit; Macedonian UI; one process, one backup.
Deploy: Docker/gunicorn. Sources of truth: `ARCHITECTURE.md` (tech), `VISION.md`
(scope), `ROADMAP.md` (plan), `CHANGELOG.md` (history), `DESIGN.md` (tokens).

## Setup
- Python 3.12, venv: `python3 -m venv .venv && source .venv/bin/activate`
- Install: `pip install -r requirements.txt -r requirements-dev.txt`
- Dev: `python3 app.py` (127.0.0.1:5000) or `./start.sh` (detached, PID in `.pid`, log in `logs/server.log`)
- PDF export needs LibreOffice (`soffice`); without it DOCX still works.

## Validation
- Iterate: `python3 -m pytest tests/test_<area>.py -q`
- Gate: `python3 -m pytest tests/ -q` then
  `python3 -m ruff check services/ routes/ utils/ tests/ app.py config.py`
- Baseline (2026-11-23): 652 passed, 4 skipped, ruff clean.
- Tests use a tmp DB (`tests/conftest.py`); never point tests at `data/servicedesk.db`.

## Conventions
- Layers: `routes/` validate input + render; business rules in `services/`;
  no SQL and no domain decisions in routes (`ARCHITECTURE.md` §2).
- Mutations: every state change writes a history row in the same
  `BEGIN IMMEDIATE` transaction; follow `services/assignment_service.py`.
- Schema: declare columns in `services/schemas.py` (`*_COLS`; service-owned
  lists are re-exported, never re-declared). `ALTER TABLE ... ADD COLUMN`
  migrations are applied by `services/db_service.py` (SQLite) and
  `services/pg_store.py` (Postgres) when a store opens; cover legacy fixtures
  via `tests/test_migrate_check.py`.
- Auth: every new route gets a row in `tests/test_auth_matrix.py`
  (admin/magacioner/citac allow/deny).
- UI: Jinja only; icons from the `templates_web/_icons.html` sprite; colors via
  CSS variables in `static/css/app.css` (`DESIGN.md`); no inline script without
  the CSP nonce; no emoji (`tests/test_ui.py`).
- Imports (CSV/Intune/LDAP/heartbeat) always go preview → confirm; assigned
  devices are never overwritten (`VISION.md` "Што НЕ правиме").

## Boundaries
- Do not edit: `.venv/`, `data/`, `transactions/`, `documents/`, `backup/`,
  `logs/`, `.omo/`, `.codegraph`, `*.db*`.
- Never commit: `.servicedesk_secret`, `.env`, runtime data, DB files, logs.
- Ask before: destructive/dropping migrations, touching real data, adding
  runtime dependencies, starting/stopping the local server, commit/push.
- Report a vulnerability; do not exploit it. `SECURITY.md` is the threat model.
