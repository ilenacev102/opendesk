# JIRA-LIKE-PLAN — „Jira Lite за мали бизниси"

> **Статус:** v1 (2026-10-05), ревизиран 2026-10-05: Phase 0 и Phase 1
> завршени (suite 397 passed, 3 skipped). Редослед: Phase 0 → 1 → 2 → 3 → 4 → 5.
> Секоја фаза = еден demo + метрика. Секоја задача е мал диф со точни фајлови
> и точни тестови (MS-шемата од ROADMAP.md).

---

## Филозофија

- **Мали бизниси ≠ Jira.** Градиме само она што екипа од 3–20 луѓе го користи дневно.
- **Hardcoded defaults, не drag-drop designer.** Workflow-ите се дефинирани по тип
  на тикет; custom workflow е v2 (не MVP).
- **Еден проект по дефиниција.** Ако малиот бизнис има само ИТ — функционира веднаш.
- **Постоечките тикети остануваат недопрени.** Миграција = додавање ProjectID/Type
  со default вредност, ништо се не брише.

---

## Фаза 0 — Паралелен трек (SPEC-FEATURES-2) — завршено (2026-10-05)

Проверено со grep (2026-10-05) — **статус на спекот**:

| # | Feature | Статус | Доказ |
|---|---|---|---|
| F1 | Моја работа табла `/my-work` | ✅ готово | `services/mywork_service.py`, `tests/test_mywork.py` |
| F2 | In-app известувања (ѕвонче) | ✅ готово | `services/notify_center.py`, `tests/test_notify_center.py` |
| F3 | Breach-прогноза | ✅ готово | `sla_service.forecast` + `will_breach`, `tests/test_forecast.py` |
| F4 | Резервации календар | ✅ готово | `services/reservation_service.py`, `/reservations/calendar`, `tests/test_reserv_calendar.py` |
| F5 | KB оценки и рангирање | ✅ готово | `services/kb_rating.py`, `POST /kb/<id>/rate`, `tests/test_kb_rating.py` |
| F6 | Договорни опомени | ✅ готово | `notify_service.contracts_expiring`, `routes/reports.py` |

**Преостанато во Phase 0:** ништо — F4 (calendar-рута + шаблон) и F5
(rating-табела + routes) се имплементирани на 2026-10-05.

---

## Phase 1 — Проекти и типови на тикети (MVP CORE) — завршено (2026-10-05)

### Цел
Секој тикет припаѓа на проект и има тип. Нов проект = празна табла, не фрлање
на постоечкото.

### 1.1 Шема (`services/schemas.py`)

```python
PROJECT_COLS = ["ProjectID", "Name", "Key", "Lead", "Description",
                "Status", "Created", "Updated"]   # Status: active|archived
ISSUE_TYPE_COLS = ["TypeID", "ProjectID", "Name", "Icon", "DefaultPriority",
                   "Workflow", "Active"]            # Workflow: key, не JSON
ISSUE_PROJECT_COLS = ["IncidentID", "ProjectID", "TypeID", "EpicLink",
                      "StoryPoints", "SprintID", "Rank"]  # проширување на Incident
```

**Клучна одлука:** Incident останува Incident. Новите полиња (`ProjectID`,
`TypeID`, `EpicLink`, `StoryPoints`, `SprintID`, `Rank`) се додаваат со
авто-миграција (`ALTER TABLE` — веќе постоечка шема во `test_migrate_check`).

### 1.2 Сервис (`services/project_service.py` — нов)

- `create(store, name, key, lead)` — Key = uppercase акутроним, unique, 2–6 карактери
- `default_project(store)` — го враќа „IT ServiceDesk" или го креира ако не постои
- `ensure_defaults(store)` — при старт: креира default project + 4 типови
  (Service Request, Incident, Task, Change) со default workflow-и
- `validate_type(type_id, project_id)` — типот мора да припаѓа на проектот

### 1.3 Дефинирани workflow-и (hardcoded, не конфигурираливи во MVP)

**Вистински статуси во код** (`services/incident_service.py:13`):
`STATUSES = ("open", "in-progress", "resolved")` — само 3, lowercase/hyphen.

```python
WORKFLOWS = {
  # колоните ГО ПОЧИТУВААТ постоечкиот incident flow 1:1
  "incident":  ["open", "in-progress", "resolved"],
  # нови типови додаваат нови колони (не го крши постоечкиот flow)
  "request":   ["open", "in-progress", "resolved"],
  "task":      ["open", "in-progress", "resolved"],
  "change":    ["open", "in-progress", "resolved"],
}
```

- **0 миграција на податоци**: сите постоечки `Incident.Status` вредности
  (`open`/`in-progress`/`resolved`) веќе се колони во workflow-от.
- Extended статуси (On Hold, Closed, Triage…) се **v2** — ќе бараат миграција
  на `STATUSES` tuple + transition-правила + SLA pause-интеграција
  (`PAUSE_REASONS` веќе постои во `sla_service.py`). Не е во MVP.

### 1.4 Рути (`routes/projects.py` — нов blueprint)

| Метод | Рута | Улога | Опис |
|---|---|---|---|
| GET | `/projects` | сите | Листа проекти |
| GET | `/projects/<id>` | сите | Детал проект (типови, број тикети) |
| POST | `/projects` | admin | Креирај проект |
| POST | `/projects/<id>/archive` | admin | Архивирај (samoStatus=archived) |
| POST | `/projects/<id>/types` | admin | Додај тип на тикет |

### 1.5 Миграција на постоечки тикети

- При прв старт по Phase 1: `ensure_defaults()` → сите постоечки
  `Incident` редови добиваат `ProjectID=default`, `TypeID=incident`.
- Idempotent: ако веќе имаат ProjectID — не се допираат.

### 1.6 Тестови `tests/test_projects.py` (6+)

1. Креирање проект: unique key, дупликат key = ValidationError
2. `ensure_defaults` е idempotent (2 повика = 1 проект)
3. Тип припаѓа на погрешен проект = одбиено
4. Миграција: 3 постоечки тикети + ensure = ProjectID пополнет за сите
5. `/projects` 200, citac може да чита
6. POST `/projects` citac = 403

**Прифаќање:** `pytest tests/` зелен; постоечките 375 теста недопрени.
**Статус:** ✅ исполнено 2026-10-05 — suite 397 passed, 3 skipped.
**Rollback:** избриши blueprint + сервис (колоните остануваат, се игнорираат).

---

## Phase 2 — Kanban табла (MVP CORE) — 2 недели

### Цел
Еден поглед: сè што е во тек, по колони. „Каде е мојот тикет" за < 5 секунди.

### 2.1 Табла (`services/board_service.py` — нов)

Чисти функции, без I/O во core-логиката:

- `columns_for(workflow_key)` → листа колони од WORKFLOWS
- `group_issues(issues, columns)` → `{column: [issues]}` — непознат статус
  паѓа во првата колона (без губење)
- `apply_filters(issues, assignee=None, itype=None, priority=None)` — чист филтер
- `board_payload(issues, workflow_key, filters)` → JSON-ready dict за template

### 2.2 Рута (`routes/boards.py` — нов)

| Метод | Рута | Улога | Опис |
|---|---|---|---|
| GET | `/projects/<id>/board` | сите | Read-only Kanban |
| GET | `/projects/<id>/board?mine=1` | сите | Само мои тикети |
| GET | `/my-board` | сите | Сите проекти, филтрирано assignee=јас |

### 2.3 UI (`templates_web/board.html` — нов)

- CSS grid со колони (постоечки design tokens од `DESIGN.md`)
- Секоја картичка: ID, наслов, приоритет-беџ, assignee-аватар, дедлaјн
- Hover → tooltip со детали; click → `/incidents/<id>` (постоечки detail)
- Колона header: бројач + работен load
- **Без drag-drop во MVP** (v2 — интеракција = POST статус change,
  веќе постои преку `incident_service` transition validation)

### 2.4 Интеграција со постоечки филтри

- `assignee` dropdown ← веќе постојки корисници
- `priority` ← веќе постојки
- Quick filter „мои" = `assignee == current_user`

### 2.5 Тестови `tests/test_board.py` (5+)

1. 3 тикета во 3 статуса → 3 колони со точни броеви
2. Непознат статус → паѓа во прва колона (не губи тикет)
3. Филтер `mine=1` → само мои
4. `/projects/<id>/board` 200, citac 200 (читање)
5. Празна табла → 200 со „нема тикети" empty-state

**Прифаќање:** board p95 < 500ms при 200 тикети; 0 тикети невидливи.
**Rollback:** избриши blueprint + шаблон.

---

## Phase 3 — Backlog и спринтови (MVP CORE) — 2 недели

### Цел
Планирање на 2-неделни циклуси. Backlog → Sprint → Burndown.

### 3.1 Шема (`services/schemas.py`)

```python
SPRINT_COLS = ["SprintID", "ProjectID", "Name", "Goal", "StartDate",
               "EndDate", "Status", "Created"]
# Status: planned | active | completed
```

Полето `SprintID` веќе е додадено во Phase 1 (на Incident).

### 3.2 Сервис (`services/sprint_service.py` — нов)

- `create(project_id, name, start, end)` — валидација: end > start,
  нема два active sprinta во ист проект
- `start(sprint_id)` — активира, ги врзува Backlog-тиковите од `Rank`
- `complete(sprint_id)` — ги поместува останатите тикети назад во Backlog
  (без губење)
- `move_to_sprint(issue_id, sprint_id)` — валидација: тикетот мора да е open
- `backlog(project_id)` — тикети со `SprintID IS NULL`, сортирани по `Rank`
- `burndown(sprint_id, today)` → дневни точки: `remaining` vs `ideal`

### 3.3 Рути

| Метод | Рута | Улога | Опис |
|---|---|---|---|
| GET | `/projects/<id>/backlog` | сите | Backlog листа |
| POST | `/projects/<id>/backlog/reorder` | magacioner+ | Rank промена (drag-drop v2, рачно во MVP) |
| POST | `/projects/<id>/sprints` | magacioner+ | Креирај спринт |
| POST | `/sprints/<id>/start` | magacioner+ | Започни |
| POST | `/sprints/<id>/complete` | magacioner+ | Заврши |
| POST | `/sprints/<id>/move` | magacioner+ | Тикет → спринт |
| GET | `/sprints/<id>` | сите | Детал + burndown |

### 3.4 UI

- `templates_web/backlog.html` — листа со „Додај во спринт" копче
- `templates_web/sprint.html` — тикети спринта + burndown chart (Chart.js,
  веќе се користи на dashboard)
- Board-от во Phase 2 автоматски ги прикажува тикетите од active спринт
  преку филтер `sprint=active`

### 3.5 Story Points

- Колоната `StoryPoints` (Phase 1) — dropdown 1/2/3/5/8/13 (Fibonacci)
- Приказ во картичката на board и backlog
- Вкупно по спринт (kapacitet visibility)

### 3.6 Тестови `tests/test_sprints.py` (7+)

1. Креирање: end ≤ start = одбиено
2. Два active спринта = одбиено
3. `start` → статус active, тикети врзани
4. `complete` → тикети без sprint се враќаат во backlog (не губи)
5. `move_to_sprint` на resolved тикет = одбиено
6. Burndown: точен број по ден
7. `/backlog` 200

**Прифаќање:** спринт-планирање за екипа < 15 мин; burndown ажуриран на секој
resolve.
**Rollback:** исклучи рути; `SprintID` колоната останува (null = backlog).

---

## Phase 4 — Соработка и полирање — 2 недели

### 4.1 @mentions во коментари

- `services/mention_service.py`: `extract(text)` → листа usernames (`@ime`),
  `notify(store, mentions, incident_id)` → push во notifications (F2)
- Автокомплет во comment textarea (постоечки fuzzy autocomplete pattern)
- Тестови: extraction, невалиден username = игнориран, notification креирана

### 4.2 Watchers

- `WATCHER_COLS = ["IncidentID", "UserName", "AddedAt"]`
- `POST /incidents/<id>/watch` + `/unwatch`
- Watcher добива notification при коментар/статус-промена (заедно со assignee)
- Тестови: watch/unwatch toggle, дупликат = еден ред, notification стигнува

### 4.3 Worklog (time logging)

- `WORKLOG_COLS = ["WorklogID", "IncidentID", "UserName", "Minutes", "WorkedDate", "Note"]`
- `POST /incidents/<id>/log` — minutes ≥ 1, WorkedDate ≤ денес
- Приказ: вкупни часови по тикет + по assignee
- **Без invoicing/без billing** — само видливост „колку време оди"

### 4.4 Epic link (parent-child)

- `EpicLink` колона (Phase 1) — dropdown со тикети од тип Epic во истиот проект
- Потипови: „Epic" се додава во default типови (WORKFLOWS["epic"] =
  ["Backlog", "In Progress", "Done"])
- На epic detail: листа на child-тикови со статус-брејкдаун

### 4.5 Version / Release

- `VERSION_COLS = ["VersionID", "ProjectID", "Name", "ReleasedAt", "Status"]`
- Поле `FixVersion` на тикет (dropdown)
- Не е задолжително за MVP — ако екипата не верзува, се игнорира

### 4.6 Тестови (8+)

- mention extraction (3), watcher (3), worklog валидација (2), epic link (2)

**Прифаќање:** @mention → notification за < 1 request; worklog збир по тикет точен.
**Rollback:** секој модул е независен — исклучи поединечно.

---

## Phase 5 — Администрација и извештаи — 2 недели

### 5.1 Project settings UI

- `/projects/<id>/settings` (admin/project lead): rename, lead, archive,
  активирање/деактивирање типови, колони на board (read-only преглед на workflow)
- **Не е drag-drop workflow designer** — тоа е v2

### 5.2 Cross-project dashboard

- `/projects` dashboard: тикети по проект, отворени vs затворени,
  најстари open, breached per project
- Postojeći analytics_service се користи, додаден `by project` dimension

### 5.3 Export / Import project template

- `GET /projects/<id>/export` → JSON (име, типови, workflow-и, label-и)
- `POST /projects/import` → креира проект од JSON (admin)
- Намена: „нов клиент/нов оддел" — клонирај шаблон за < 1 мин

### 5.4 Тестови (5+)

- settings 200/403, export валиден JSON, import креира проект со типови,
  import невалиден JSON = 400, dashboard по проект точен

**Прифаќање:** нов проект од шаблон < 1 мин; dashboard ги покажува сите проекти.
**Rollback:** исклучи рути.

---

## Табела: Фази, траење, зависности

| Фаза | Содржина | Траење | Зависи од | Акумулативно |
|---|---|---|---|---|
| 0 | SPEC F1–F6 (паралелно) | 2 недели | — | — |
| 1 | Проекти + типови + workflows | 2 недели | — | 2 недели |
| 2 | Kanban табла | 2 недели | Phase 1 | 4 недели |
| 3 | Backlog + спринтови + burndown | 2 недели | Phase 1–2 | 6 недели |
| 4 | Mentions, watchers, worklog, epics | 2 недели | Phase 1–3 | 8 недели |
| 5 | Settings, dashboard, template export | 2 недели | Phase 1–4 | 10 недели |

**Вкупно MVP (Phase 1–3): ~6 недели** — проекти + табла + спринтови.
**Целосно (Phase 1–5): ~10 недели.**

---

## Што НЕ правиме (блокирачка листа за овој план)

1. **Нема drag-drop workflow designer** — hardcoded workflows по тип.
2. **Нема JQL parser** — постоечки филтер-бар + fuzzy search е доволно.
3. **Нема microservices / event sourcing** — монолитот останува (ADR-02).
4. **Нема WebSockets** — page refresh + in-app notification (F2) е доволно.
5. **Нема plugin marketplace** — ако треба extension, кôд во `services/`.
6. **Нема Time-tracking invoicing** — worklog е видливост, не billing.
7. **Нема Scrum metrics над burndown** — velocity v2, не MVP.
8. **Нема per-project permission schemes** — глобалните улоги
   (admin/magacioner/citac) + project lead е доволно за SMB.

---

## Ризици

| Ризик | Одговор |
|---|---|
| Scope creep кон целосен Jira | Блокирачката листа; секоја нова идеја → Backlog |
| Миграција крши постоечки тикети | Default ProjectID/TypeID, idempotent ensure, тест |
| Board перформанси при многу тикети | Пагинација + филтер по default; 500+ не е SMB |
| Статуси на workflow ≠ постоечки `Incident.Status` | WORKFLOWS ги користи истите вредности (`open`/`in-progress`/`resolved`) 1:1; транзиција-тестови |
| Фази се блокираат една друга | Phase 0 паралелно; Phase 4+5 не го блокираат core |

---

## Definition of Done (секоја фаза)

- `pytest tests/` зелен (постоечките + новите тестови)
- Нов код покриен со тест ≥ 90%
- CHANGELOG запис со suite-бројка
- README врска ако има нова страница
- Без emoji во UI, без inline-скрипти без nonce, CSRF на секој POST
- Rollback-чекор документиран (< 15 мин)
