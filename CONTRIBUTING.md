# Contributing to ServiceDesk

Thank you for your interest in contributing to ServiceDesk! We are building the most reliable, deterministic, and complete open-source IT Asset Management (ITAM) and ServiceDesk platform in the world.

To maintain our high engineering bar and ensure production-grade stability, please review these guidelines before submitting code.

---

## Code of Conduct

By participating in this project, you agree to abide by our standards of respectful, inclusive, and professional collaboration.

---

## Architectural Principles (Non-Negotiable)

Before writing any feature or fix, review [ARCHITECTURE.md](ARCHITECTURE.md) and [VISION.md](VISION.md). Every contribution must respect:

1. **Layer Separation:**
   - `routes/`: Request validation, authentication guard, rendering/redirects. **No SQL queries or core business logic in routes.**
   - `services/`: Business rules and database operations. Services return results or raise domain errors; they do not know about HTTP requests.
   - `templates_web/`: UI layer using pure Jinja. No inline scripts without CSP nonce. Design tokens must use CSS variables from `static/css/app.css` (`DESIGN.md`).

2. **Transactional Integrity (`BEGIN IMMEDIATE`):**
   - Every mutation touching an asset, transaction record, or relation **must record an audit history row** inside the same atomic database transaction. Never commit partial state.

3. **Defensive Ingestion (Zero Overwrites):**
   - Ingestion from external sources (CSV, Intune, LDAP, Heartbeat, SNMP) is always preview-first (`Preview -> Confirm`). **Assigned devices are never silently overwritten.**

4. **Zero Secrets in Code:**
   - All credentials and sensitive values come from environment variables. Never commit credentials, tokens, local database dumps, or logs.

---

## Local Development Setup

### 1. Requirements
- Python 3.12+
- Optional: Docker & Docker Compose
- Optional: LibreOffice (`soffice`) for PDF conversion tests

### 2. Virtual Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### 3. Running the Server Locally
```bash
python3 app.py
```
Open [http://127.0.0.1:5000](http://127.0.0.1:5000) in your browser. On a fresh database, visit `/setup` to create your initial administrator.

---

## Quality Gate & Testing

Before submitting a Pull Request, your branch must satisfy the following checks:

```bash
# 1. Run all unit and integration tests (650+ tests must pass)
pytest tests/ -q

# 2. Run Ruff linter and formatting checks
ruff check services/ routes/ utils/ tests/ app.py config.py
```

### Writing New Tests
- Every new route must have an entry in `tests/test_auth_matrix.py` specifying access permissions (`admin`, `magacioner`, `citac`).
- Tests run against an isolated temporary database via `tests/conftest.py`. **Never point automated tests at `data/servicedesk.db`.**

---

## Submitting Pull Requests

1. **Fork & Branch:** Create a feature branch with a descriptive name (`git checkout -b feat/i18n-support`).
2. **Commit Style:** Use clean, imperative commit messages (`feat: add multi-language support`).
3. **Documentation:** Update `CHANGELOG.md` and relevant markdown docs if your change adds new configuration parameters or endpoints.
4. **Open PR:** Submit your pull request against the `main` branch with details on the change and test evidence.
