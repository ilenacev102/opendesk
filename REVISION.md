# ServiceDesk — Ревизија и Оценка за Jira-like SMB Edition

> **Датум:** 2026-10-05  
> **Верзија:** v1 (базирано на ROADMAP, VISION, ARCHITECTURE, SPEC-FEATURES-2, CHANGELOG)

---

## 1. Тренутна состојба — Што ИМАМЕ (Jira-еквиваленти)

| Jira концепт | ServiceDesk реализација | Статус |
|---|---|---|
| **Issues / Тикети** | `Incidents` (со SLA, коментари, прилози, дупликати, KB-врски) | ✅ Солидно |
| **Projects** | `/projects` + default „IT ServiceDesk", типови по проект (Phase 1) | ✅ Постои |
| **Boards (Kanban/Scrum)** | **Нема** — само листи/филтри | ❌ Нема |
| **Backlog + Sprint** | **Нема** | ❌ Нема |
| **Workflows (status transitions)** | Hardcoded device lifecycle + incident status | ⚠️ Ограничено |
| **Custom Fields** | `field_defs` / `field_values` (generic EAV) | ✅ Постои |
| **User Roles** | `admin` / `magacioner` / `citac` | ✅ Основно |
| **Notifications** | Email (SMTP) + In-app (SPEC F2) | ✅ Постои |
| **Search / JQL** | Филтер-бар + fuzzy autocomplete (Ctrl+K) | ⚠️ Основно |
| **Reports / Dashboards** | Analytics dashboard (MTTR, breach, warranty, costs) | ✅ Добро |
| **Knowledge Base** | `/kb` со Artikel + "Реши од напис" | ✅ Постои |
| **Asset/CMDB** | Devices + CMDB view (`/cmdb/<id>`) + relationships | ✅ Солидно |
| **SLA / Time Tracking** | SLA engine (working hours, escalation, pause rules) | ✅ Солидно |
| **Email-to-Ticket** | IMAP intake со Message-ID dedupe + preview | ✅ Постои |
| **Audit Trail** | History service (секоја мутација) | ✅ Одлично |
| **Documents (DOCX/PDF)** | Задолжувања, враќања, попис, offboarding | ✅ Одлично |
| **Inventory/Discovery** | CSV, Intune, Heartbeat, SNMP, LDAP (read-only) | ✅ Солидно |

---

## 2. Што ФАЛИ за "Jira Lite" за мали бизниси

### 2.1 Core Ticketing (Must-have)
| Функција | Jira термин | Зашто е критично за SMB |
|---|---|---|
| **Projects** | Projects | Сега сè е смесено — IT, HR, Finance тикети заедно |
| **Issue Types** | Task, Bug, Story, Epic, Service Request | Различни процеси за различни типови работ |
| **Custom Workflows** | Workflow Designer | Сега е hardcoded — не може да се прилагоди по екип/тип |
| **Boards (Kanban)** | Board | Визуелен преглед на работен ток — "каде е мој тикет" |
| **Sprints / Backlog** | Sprint, Backlog | Планскање на работна недела/спринт (барем 2-неделни) |
| **Epics / Parent-Child** | Epic → Stories/Tasks | Групирање на голема работа (напр. "Nova мрежа" → подзадачи) |

### 2.2 Collaboration (Must-have)
| Функција | Jira термин | Зашто е критично за SMB |
|---|---|---|
| **@mentions в коментари** | Mentions | Тагање на колега — "Види го ова @jane" |
| **Watchers / Подписuvани** | Watchers | Аплицирање на екипови на тикет без да се assignee |
| **Activity Stream** | Activity | Историја на секоја промена на тикетот (веќе има во history) |

### 2.3 Planning & Tracking (Should-have)
| Функција | Jira термин | Зашто е вредно за SMB |
|---|---|---|
| **Story Points / Estimation** | Story Points | Relative sizing за капацитет |
| **Time Logging** | Worklog | "Колку време ми требаше" — за fact-based planning |
| **Burndown / Velocity Charts** | Reports | Визуелен tracking на спринт |
| **Versions / Releases** | Fix Versions | "Ова оди во v2.1" — пратеник за deploy |

### 2.4 Administration (Should-have)
| Функција | Jira термин | Зашто е вредно за SMB |
|---|---|---|
| **Project-level Permissions** | Permission Schemes | HR екип види само HR проекти |
| **Notification Schemes** | Notification Schemes | Кој добива мејл за какво |
| **Custom Statuses per Project** | Statuses | "Code Review" за dev, "Approved" за finance |

---

## 3. Арhitektтура — Што е готово, што треба да се менува

### ✅ Не се менува (Solid Foundation)
- Flask + SQLite/Postgres монолит
- `services/` layer за business logic (чист, тестираibilen)
- `db_service` StoreProtocol —Works за нова табела
- Auth + Roles + CSRF + CSP + Rate-limit
- Transactional integrity (`BEGIN IMMEDIATE`, WAL)
- Audit trail (history) за секоја мутација
- Blueprint-based routes — лако додавање нови модули
- Comprehensive test suite (397 passed + 3 skipped, проверено 2026-10-05)

### ⚠️ Треба проширување (Minimal Changes)
| Компонента | Потребна промена |
|---|---|
| `services/schemas.py` | Нови табели: `projects`, `issue_types`, `workflows`, `sprints`, `boards`, `epics`, `worklogs`, `watchers`, `mentions` |
| `services/` | Нови сервиси: `project_service`, `workflow_service`, `board_service`, `sprint_service`, `worklog_service` |
| `routes/` | Нови blueprints: `projects`, `boards`, `sprints`, `worklogs` |
| `templates_web/` | Нови шаблони: board view, backlog, sprint planning, project settings |
| `static/` | JS за drag-drop board, sprint chart, mention autocomplete |

### ❌ Не треба (Over-engineering за SMB)
- Microservices / Event sourcing / CQRS
- Real-time WebSockets (long-polling e доволно)
- Complex permission schemes (project-level roles е доволно)
- Plugin marketplace / App ecosystem
- Advanced JQL parser (SQL WHERE + UI builder е доволно)

---

## 4. Mapping: ServiceDesk терминологија → Jira терминологија

| ServiceDesk | Jira Equivalent | Напомена |
|---|---|---|
| `Incident` | **Issue** (Service Request / Incident type) | Сега е единствен тип |
| `Device` / `Asset` | **Asset** (CMDB) | Веќе има CMDB view |
| `Employee` | **User** / **Reporter** / **Assignee** | Веќе има |
| `SLA Policy` | **SLA** | Веќе има working hours + escalation |
| `KB Article` | **Knowledge Base** | Веќе има |
| `History` | **Activity / Changelog** | Веќе има (потребно UI) |
| `Assignment` | **Assignment** (Asset → User) | Asset management, не issue assignment |
| — | **Project** | **НОВО** |
| — | **Board / Column / Status** | **НОВО** |
| — | **Sprint / Backlog** | **НОВО** |
| — | **Epic / Parent Issue** | **НОВО** |
| — | **Worklog** | **НОВО** |
| — | **Version / Release** | **НОВО** |

---

## 5. Ризици и Одлуки

| Ризик | Митигација |
|---|---|
| **Scope creep** — Jira е голема | **Строг MVP scope** (види JIRA-LIKE-PLAN.md) — само што SMB денес неможат без тоа |
| **Complexity на workflows** | **Hardcoded default workflows** по issue type; customization v2 |
| **UI complexity (boards)** | **Read-only board v1** (drag-drop v2); 서버-side rendering за MVP |
| **Migration на постоечки incidents** | **Default project "IT ServiceDesk"** — сите постоечки incidentи им припаѓаат |
| **Performance на boards** | **Pagination + virtual scroll** од ден 1; 500+ тикети на board не е SMB use case |

---

## 6. Препорака: MVP Scope за "Jira Lite SMB"

### Phase 0 — Foundation (речиси готово, ~2 дена преостанато) 
Проверено со grep (2026-10-05):
- ✅ F1: My Work dashboard (готово)
- ✅ F2: In-app notifications (завршено)
- ✅ F3: Breach forecast (завршено)
- ✅ F4: Reservations — overlap-валидација + неделен calendar view (`/reservations/calendar`)
- ✅ F5: KB ratings — оценки 1–5 (upsert), просек и рангирање на листата
- ✅ F6: Contract reminders (завршено)

### Phase 1 — Projects & Issue Types (Week 3-4) **MVP CORE**
- Projects table + CRUD (admin)
- Issue Types (Service Request, Incident, Task, Change) со default workflows
- Миграција: сите постоечки incidents → default project "IT ServiceDesk", type "Incident"
- Project-level roles (Project Lead, Member, Viewer)

### Phase 2 — Kanban Board (Week 5-6) **MVP CORE**
- Board per project (columns = statuses од workflow)
- Read-only board v1 (drag-drop v2)
- Quick filters (assignee, type, priority)
- "My Board" view (филтрирано по assignee=me)

### Phase 3 — Backlog & Sprints (Week 7-8) **MVP CORE**
- Backlog view (issues без sprint, ordered by priority)
- Sprint create/start/complete
- Sprint planning: drag из backlog во sprint
- Burndown chart (server-rendered Chart.js)

### Phase 4 — Collaboration & Polish (Week 9-10)
- @mentions в коментари + notification
- Watchers на issue
- Worklog (time tracking) на issue
- Epic link поле на issue (parent-child)
- Version/Release поле

### Phase 5 — Admin & Reporting (Week 11-12)
- Project settings UI (workflow, columns, notification scheme)
- Cross-project dashboard (admin)
- Export/Import project template (JSON)

---

## 7. Success Metrics (Definition of Done за целиот план)

| Метрика | Цел |
|---|---|
| **Time to "My Board" за нов user** | < 3 клика од login |
| **Create issue → на board** | < 30 сек (UI + save) |
| **Sprint planning за 5-член екип** | < 15 мин сетап + планирање |
| **Test coverage за нов код** | ≥ 90% (постоечки pattern) |
| **Load: Board load p95** | < 500ms за 200 issues |
| **Zero regression на постоечки features** | `pytest tests/` зелен на секој merge |

---

## 8. Следните чекори

1. **Одобри MVP scope** (Phase 1-3 = 6-8 недели)
2. **Почни со Phase 1** — Projects + Issue Types (најмалку ризик, најголема вредност)
3. **Искористи SPEC-FEATURES-2 F1-F6** како паралелен трек (веќе spec-irani)
4. **Секој фаза = demo + metrics** (како ROADMAP правило)