# IT ServiceDesk

Локална веб-апликација (Flask + SQLite) за евиденција на ИТ опрема во мала/средна
фирма: задолжување, раздолжување (поединечно и групно offboarding), замена,
сервис, расход, пакети опрема, попис, ревизорска историја, DOCX/PDF документи,
извештаи, филтри, сортирање и пребарување. Интерфејсот е на македонски.

> **Напомена:** има автентикација со улоги (`admin`/`magacioner`/`citac`) —
> првото стартување отвора `/setup` за прв администратор. Поддржана е и SSO
> најава преку OIDC (Entra ID / Google) на `/login/sso` — првиот login креира
> `citac`, улогите ги менува администратор. И покрај тоа,
> наменето е за доверлива локална мрежа: rate-limitот е per-process во
> `memory`-режим, а за повеќе workers користете споделен `file`-режим
> (види `SECURITY.md`). Не го изложувајте директно на интернет.
> Поставете `SERVICEDESK_SECRET`.

## Брз старт

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python3 app.py
# http://127.0.0.1:5000
```

или со Docker:

```bash
docker compose up --build
# http://127.0.0.1:5000
```

## Конфигурација (env)

| Променлива | Default | Опис |
|---|---|---|
| `SERVICEDESK_PORT` | `5000` | Порта |
| `SERVICEDESK_SECRET` | локално се креира приватен клуч | Flask secret — задолжителен за Docker deploy |
| `SERVICEDESK_HOST` | `127.0.0.1` | Мрежен интерфејс за локално стартување |
| `SERVICEDESK_CSRF` | `1` | CSRF-заштита на POST (`0` ја исклучува) |
| `SERVICEDESK_DB` | `data/servicedesk.db` | SQLite датотека (тестови користат tmp-база) |
| `SERVICEDESK_DB_URL` | — | Postgres-опција (инаку SQLite default) |
| `SERVICEDESK_ADMIN_USER` / `SERVICEDESK_ADMIN_PASS` | — | Прв администратор при старт ако нема корисници |
| `SERVICEDESK_SMTP_HOST` / `PORT` / `USER` / `PASS` / `FROM` | — | SMTP нотификации; без нив mail тивко се прескокнува |
| `SERVICEDESK_ADMIN_EMAIL` | — | Примач на digest / месечен извештај |
| `SERVICEDESK_TEMPLATES_DIR` | `templates/` | Приватни брендирани DOCX-шаблони |
| `SERVICEDESK_LDAP_URL` / `BIND_DN` / `PASSWORD` / `BASE` / `FILTER` | — | LDAP/AD read-only sync (`/users/sync`, само admin) |
| `SERVICEDESK_RATELIMIT` / `SERVICEDESK_RATELIMIT_FILE` | `memory` | `file` се дели меѓу workers |
| `SERVICEDESK_IMAP_HOST` / `PORT` / `USER` / `PASSWORD` / `MAILBOX` / `SSL` | — | Email-to-ticket intake, само рачен trigger |
| `SERVICEDESK_OIDC_ISSUER` / `CLIENT_ID` / `CLIENT_SECRET` / `NAME` | — | SSO најава преку OIDC (Entra ID / Google / Keycloak) |
| `SERVICEDESK_INTUNE_TENANT` / `CLIENT_ID` / `CLIENT_SECRET` | — | Intune Graph sync, само рачен trigger |
| `SERVICEDESK_SNMP_COMMUNITY` | — | SNMP printer sweep (read-only) |

Целосен список со примери: `.env.example`.

PDF-извозот бара LibreOffice (`soffice`); без него DOCX работи, PDF враќа
уредна грешка. Податоците живеат во `data/`, документите во `documents/`,
бекапите во `backup/` — сè git-игнорирано (примерок-структурата се креира сама).
SQLite backup-ите се конзистентни snapshots, вклучително и незапишани WAL промени.

За Docker, прво поставете secret (на пример во `.env`):

```bash
SERVICEDESK_SECRET=<долг случаен таен клуч>
```

Compose по default го објавува сервисот само на `127.0.0.1:5000`. За доверлива LAN
употреба експлицитно поставете `SERVICEDESK_BIND=0.0.0.0` и заштитете го со firewall/VPN.

## Функционалности

- Животен циклус на уред: Available ↔ Assigned → Broken → Repair → Repaired,
  Unrepairable → Disposed; валидации на секој премин
- Bulk offboarding, пакети опрема, попис со скенирање и записник
- Discovery увоз (Intune/SCCM CSV) со преглед пред запис (`/import`)
- Heartbeat агенти (`agents/heartbeat.sh`, `agents/heartbeat.ps1`) што се
  пријавуваат на `POST /api/v1/discovery/heartbeat` со Bearer токен;
  SNMP printer sweep (read-only) и Intune Graph sync со преглед пред запис
- Минимални инциденти со рокови и breach-ознаки (`/incidents`), CMDB-врски по уред (`/cmdb/<id>`)
- Проекти и типови тикети (`/projects`) со workflow по тип и автоматски
  default-проект („IT ServiceDesk")
- SLA работни часови со авто-ескалација, коментари и прилози по инцидент, дупликати
- База на знаење (`/kb`) со поврзување написи и решавање од напис
- Email-to-ticket сандаче (`/incidents/inbox`) со преглед пред запис
- PWA скенер за попис со телефон-камера и offline ред (скенер-страница `/popis/<pid>/scan`, на пр. `/popis/P000001/scan`)
- Аналитика на контролна табла (`/` преку `analytics_service`): инциденти по
  статус, гарантна прогноза (30/60/90 дена), трошоци по локација, MTTR и
  пробиени рокови; месечен
  mail-извештај на копче (`/reports/monthly-summary`)
- LDAP/AD read-only sync со dry-run (`/users/sync`, само admin), Postgres-опција преку `SERVICEDESK_DB_URL`
- Трансакциска атомарност (`BEGIN IMMEDIATE`), WAL-режим, audit trail за секоја
  мутација, import со rollback при грешка
- Command palette (Ctrl+K), fuzzy autocomplete, сортирачки табели, breadcrumbs,
  светла/темна тема, responsive, print-приказ

## Развој

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/   # 441 тест: unit + integration + UI-guardови
```

Структура: `app.py` (ядро: init, auth-гард, stores, services) · `routes/`
(blueprints: admin, api, catalog, cmdb, files, incidents, inventory, kb,
operations, popis, projects, reports, system) · `services/` (бизнис-логика) · `utils/` (валидатори,
помошни) · `templates_web/` (Jinja) · `static/` (CSS/JS) · `tests/`.
Дизајн-токени: `DESIGN.md`. Детален дневник на измени: `CHANGELOG.md`.
Визија: `VISION.md` · Архитектура: `ARCHITECTURE.md` · План: `ROADMAP.md` · Спец за нови features: `SPEC-FEATURES-2.md` · Безбедност: `SECURITY.md`.

## Придонес

Fork → feature гранка → `pytest` зелено → pull request со опис на македонски
или англиски. Без commit на `data/`, `documents/`, `backups/`, `*.db`.

## Лиценца

MIT — види `LICENSE`.
