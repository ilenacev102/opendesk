<div align="center">

# ⚡ OpenDesk

### The Modern, Resilient Open-Source IT Asset Management (ITAM) & ServiceDesk Platform

[![CI Quality Gate](https://github.com/ilenacev102/servicedesk/actions/workflows/ci.yml/badge.svg)](https://github.com/ilenacev102/servicedesk/actions/workflows/ci.yml)
[![Tests Passing](https://img.shields.io/badge/tests-654%20passed-brightgreen.svg)](tests/)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![License: AGPL v3](https://img.shields.io/badge/license-AGPLv3-blue.svg)](LICENSE)
[![Docker Ready](https://img.shields.io/badge/docker-ready-2496ED.svg)](docker-compose.demo.yml)

**OpenDesk** is a deterministic, blazingly fast IT operations platform combining enterprise-grade **IT Asset Lifecycle Management (ITAM)**, **Audits & Field Inventory Scans (PWA barcode/QR)**, and an **SLA-driven ServiceDesk / Ticketing System (ITSM)** — built into a single, resilient architecture.

Created & Maintained by [@ilenacev102](https://github.com/ilenacev102).

[Quickstart](#-quickstart-in-60-seconds) • [Architecture](#-architecture--design-principles) • [Key Features](#-key-features) • [Contributing](#-contributing) • [Security](#-security-policy)

</div>

---

## 🌟 Why OpenDesk?

Most IT teams are forced to glue together separate, heavyweight tools:
- **Snipe-IT** does great asset tracking, but lacks native ticketing, incident SLA engines, and sprint-based project workflows.
- **GLPI** has features, but suffers from legacy PHP complexity and bloated UI/UX.
- **ServiceNow / Jira** are proprietary, expensive, and lock your sensitive company topology in third-party clouds.

**OpenDesk solves this with a unified, self-hosted platform:**
1. **Zero-Fluff Single Process:** Single Flask monolith with SQLite default (WAL-mode with `BEGIN IMMEDIATE` transaction guarantees) or PostgreSQL.
2. **Deterministic Lifecycle:** Complete asset lifecycle (`Available ↔ Assigned → Broken → Repair → Disposed`) with automated custody trails.
3. **PWA Mobile Audits:** Built-in mobile barcode/QR scanning with offline queues for warehouse/office field audits.
4. **Strict SLA & Automation:** Working hours calendar (Mon-Fri 08-16 + holidays), auto-escalations without assignee stealing, email-to-ticket deduplication, and CMDB dependency topologies.
5. **Privacy & Offline First:** Zero external cloud dependencies. Your IT infrastructure stays on your LAN.

---

## 🚀 Quickstart in 60 Seconds

### Option A: Docker Compose (Recommended)

Run the fully configured instant demo:

```bash
# Clone the repository
git clone https://github.com/ilenacev102/servicedesk.git
cd servicedesk

# Spin up OpenDesk in 1-click
docker compose -f docker-compose.demo.yml up
```

Open your browser at **[http://localhost:5000](http://localhost:5000)**.
- **Username:** `admin`
- **Password:** `Admin123!`

---

### Option B: Local Development

```bash
# 1. Create and activate a Python 3.12 venv
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 3. Launch OpenDesk
python3 app.py
```

On first launch, navigate to `http://127.0.0.1:5000/setup` to initialize your master administrator credentials.

---

## 🛡️ Architecture & Design Principles

OpenDesk adheres to strict enterprise software development rules:

```
HTTP (routes/)  ──>  services/ (pure business rules)  ──>  stores/ (atomic DB transactions)
```

- **Clean Layers:** Routes validate incoming requests and render templates. **Zero raw SQL in routes.**
- **Transaction Guarantee (`BEGIN IMMEDIATE`):** Every mutation (asset changes, assignments, repairs, disposals) writes an audit history entry in the same atomic transaction. No partial state writes.
- **Preview-First Ingestion:** External data imports (CSV, Intune Graph, LDAP/AD, Heartbeat agents, SNMP) always go through `Preview -> Confirm`. **Assigned devices are never silently overwritten.**
- **Multi-Language (i18n):** Native support for English (`en`) and Macedonian (`mk`), extensible via clean JSON dictionary files in `locales/`.

---

## 📊 Core Capabilities

| Module | What It Does |
|---|---|
| **Asset Management (ITAM)** | Hardware, software licenses, consumables, accessories, and warranty expiration forecasting (30/60/90 days). |
| **Field Audits & Barcodes** | Instant QR/Barcode label generation and camera-driven mobile PWA scanner with offline queue. |
| **ServiceDesk & Ticketing** | SLA breach tracking, business-hours calculation, CSAT surveys, knowledge base (KB) linking, and mail ingestion. |
| **CMDB & Topologies** | Asset-to-owner, asset-to-rack, network dependencies, and service relationship mapping (`/cmdb/<id>`). |
| **Automated Agents** | Lightweight heartbeat discovery scripts (`agents/heartbeat.sh`, `heartbeat.ps1`) reporting system state over secure Bearer tokens. |
| **Identity & SSO** | Native OpenID Connect (OIDC) supporting Google Workspace, Microsoft Entra ID, Keycloak, alongside LDAP/Active Directory read-only sync. |

---

## 🧪 Quality Gate & Automated Testing

OpenDesk maintains a rock-solid, production-ready test suite:

```bash
# Run 650+ unit, integration, and security tests
pytest tests/ -v -q

# Run static analysis and linting
ruff check services/ routes/ utils/ tests/ app.py config.py
```

Every pull request is automatically verified against our GitHub Actions CI pipeline.

---

## 🤝 Contributing

We welcome contributions from engineers worldwide! OpenDesk operates under a **Benevolent Dictator for Life (BDFL)** governance model:
- Read [CONTRIBUTING.md](CONTRIBUTING.md) for architectural guidelines and PR submission workflows.
- Check out our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- All pull requests require green CI builds and explicit approval by [@ilenacev102](https://github.com/ilenacev102).

---

## 📜 License

OpenDesk is licensed under the **GNU Affero General Public License v3 (AGPLv3)**. See [LICENSE](LICENSE) for details.
