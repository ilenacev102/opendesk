# SPEC-FEATURES-2 — 6 нови функционалности (полн spec)

> Статус: имплементирано (F1–F6). Редослед: F1 → F2 → F3 → F6 → F4 → F5
> (F3 пред F6 — двете го допираат digest; F5 последен — најголем).
> Секој feature се имплементира по MS-шемата: сервис → рута → шаблон → тестови → suite зелен.

## F1 — Моја работа табла (`GET /my-work`)

- **Цел:** магационерот отвора една страница и гледа сè што гори кај него.
- **Фајлови:**
  - `services/mywork_service.py` (нов, чист): `collect(assignee, employee_id, incidents, devices, history, today=None)` враќа dict `{my_open, breached, due_soon_2d, my_devices, pending_receives, escalated_mine}`. `due_soon` = DueDate во [today, today+2], не-resolved. `pending_receives` = InTransit уреди чија Location е моја локација? (по EmployeeID нема локација — затоа: InTransit уреди задолжени кај моите вработени? поедноставно: сите InTransit + моите Assigned). Дефинитивно: `my_devices` = EmployeeID==мој? магационерот нема свои уреди — затоа `my_open`/`breached`/`due_soon` по Assignee==јас, `my_devices` = уреди што сум ги задолжил последен (history ASSIGN со PerformedBy==јас, лимит 20), `pending_receives` = сите InTransit.
  - `routes/system.py`: `GET /my-work` (најавен, сите улоги — секој гледа свое).
  - `templates_web/mywork.html` (нов): 4 картички со броеви + листи, без нови икони.
- **Тестови** `tests/test_mywork.py` (3 + 1): празно (сè нули), еден assignee со breach + due-soon, route 200 со „Моја работа".
- **Прифаќање:** страницата одговара <300ms при 500 уреди; citac гледа само свои тикети (нема туѓи имиња).
- **Rollback:** избриши рута + сервис (ништо не пишува).

## F2 — In-app известувања (ѕвонче)

- **Цел:** ниту еден настан не чека mail — ѕвончето во `base.html` покажува непрочитани.
- **Фајлови:**
  - `services/schemas.py`: `NOTIF_COLS = [NotifID, UserName, Kind, RefID, Text, Created, ReadAt]`.
  - `services/notify_center.py` (нов): `push(store, username, kind, ref_id, text)` (ReadAt=""), `unread(store, username)` (листа, најнови прво), `mark_read(store, username, notif_id="")` (еден или сите), сите со `stamp()`.
  - `app.py`: `notifications = open_store(DB_PATH, "notifications", None, NOTIF_COLS)` + context-processor `unread_count` за најавен корисник (0 за анонимен).
  - `templates_web/base.html`: ѕвонче со бројка (постоечка `#i-bell` ако ја има во sprite, инаку текст „Известувања (N)") + `templates_web/notifications.html` листа со „Прочитано" копчиња.
  - `routes/system.py`: `GET /notifications`, `POST /notifications/read` (сопствени, секој најавен).
  - Емитери (точно 3, сите постоечки POST рути): `incident_escalate` → assignee; `offboarding_escalate` → admin-улога? (нема список admin-и при рака — затоа: PerformedBy? не. Решение: `PerformedBy` на последната ASSIGN-трансакција? прекомплицирано. Дефинитивно: offboarding-ескалацијата известува **носителот-менаџер? нема**. Затоа емитери: (1) incident escalate → assignee, (2) transit ship → EmployeeID на уредот (носителот), (3) transit receive → PerformedBy на ship-от? (нема. Затоа: (3) onboard confirm → RequestedBy). Сите со fallback: празен username = без запис, никогаш грешка.
- **Тестови** `tests/test_notify_center.py` (4 + 1): push/unread, mark_read еден, mark_read сите, празен username не пишува, route 200 + badge.
- **Прифаќање:** ескалација → ѕвончето на assignee расте за 1 во ист request; click „Прочитано" → 0.
- **Rollback:** исклучи емитери (3 реда); табелата останува празна.

## F3 — Breach-прогноза (+ авто-кандидати)

- **Цел:** „ќе пробие за 2 дена" видливо пред да пробие.
- **Фајлови:**
  - `services/sla_service.py`: `will_breach(due, within_days, today=None)` чист (garbage → False) + `forecast(incidents, days=2, today=None)` вратена сортирана по DueDate (само не-resolved).
  - `services/notify_service.py`: `digest_email(..., forecast_rows=None)` — опционален параметар, постоечките повици недопрени; нова секција „Ќе пробијат скоро:".
  - `routes/reports.py::notify_digest`: пресметај `forecast(inc_records, 2)` и проследи.
- **Тестови** `tests/test_forecast.py` (4): garbage/празно → False/празно; 2 од 5 во прозорец сортирани; digest без forecast = стар body (backward compat); digest со forecast ја има секцијата.
- **Прифаќање:** digest-mailот ја содржи секцијата; MTTR/breach броеви непроменети.
- **Rollback:** врати 2 функции (мала диф). Имплементирај ПРЕД F6 (и двете го допираат digest).

## F4 — Резервации календар + конфликти

- **Цел:** двојна резервација невозможна; неделата видлива на еден поглед.
- **Фајлови:**
  - `services/reservation_service.py` (нов): чист `overlaps(a_from, a_to, b_from, b_to)` (ISO-датуми, garbage → ValueError) + `conflicts(existing, asset_id, frm, to)` (само Status=="active"? провери ги вистинските статуси во `catalog.py` при имплементација — ако се различни, прилагоди) + `create(store, ...)` што одбива конфликт со ValidationError.
  - `routes/catalog.py`: `GET /reservations/calendar?week=` (неделен grid: денови × уреди/локации, read-only) + врзи `create()` во постоечкиот POST (без нова рута за запис).
  - `templates_web/reservations_calendar.html` (нов): табела 7 дена, денес означен.
- **Тестови** `tests/test_reserv_calendar.py` (4 + 1): допир на граници (to==from → конфликт), без преклоп → ок, garbage датум → ValueError, create одбива дупликат, route 200 со тековна недела.
- **Прифаќање:** двоен клик „резервирај" ист термин → еден успева, вториот добива порака (конкурентност преку постоечки трансакции ако ги има, инаку serialize преку service-check + тест со 2 нишки како доказ).
- **Rollback:** исклучи calendar-рута; `create()` останува како stricter валидација (или врати).

## F5 — KB надградба (оценки + рангирање)

- **Цел:** најдобрите написи излегуваат први; лош напис се гледа по оцена.
- **Наод:** „Реши од напис" ВЕЌЕ постои (`incident_resolve_kb`) — не се гради, се верификува + тестира.
- **Фајлови:**
  - `services/schemas.py`: `KB_RATING_COLS = [ArticleID, UserName, Score]` (нова табела — еден корисник еден глас, upsert).
  - `services/kb_rating.py` (нов): `vote(store, article_id, username, score)` (1–5, upsert по ArticleID+UserName, празен username → ValidationError), `average(store, article_id)` → float|None, `ranked(articles, store)` (со просек прво, без оценка после, стабилно).
  - `routes/kb.py`? (провери го името на blueprint при имплементација): `POST /kb/<id>/rate` (`@require`, 1–5) + detail прикажува просек + форма; листата сортирана преку `ranked`.
- **Тестови** `tests/test_kb_rating.py` (4 + 1): upsert ја менува оцената (1 ред), просек 4.5, `ranked` редослед, 6 → ValidationError, route 302 + запишано.
- **Прифаќање:** напис со 5 оценки излегува пред неоценет; resolve-од-напис тече непроменето (постоечки тестови зелени).
- **Rollback:** исклучи rate-рута (табелата останува).

## F6 — Договорни опомени + трошоци по оддел

- **Цел:** ниеден договор/лиценца не истекува тивко; трошоците се видливи по оддел.
- **Фајлови:**
  - `services/notify_service.py`: чист `contracts_expiring(rows, days=30)` (поле `ValidUntil`, garbage се прескокнува — ист образец како `warranty_expiring`) + `licenses_expiring(rows, days=30)` (поле `ExpiryDate`).
  - `digest_email(..., contract_rows=None, license_rows=None)` — опционални параметри, стари повици недопрени; две нови секции.
  - `routes/reports.py::notify_digest`: пресметај и проследи; месечниот извештај (`summary_email` + stats) добива `contracts_30` бројка (опционален клуч, стари тестови недопрени — образец од CSAT).
  - Трошоци по оддел: `analytics.costs_by` постои (по Location) — провери при имплементација дали има Department-верзија; ако нема, чист `costs_by_dept(devices, employees)` во `analytics_service.py` + еден ред во summary-stats.
- **Тестови** `tests/test_contract_remind.py` (4): garbage се прескокнува, 30-дневен прозорец точен, digest без нови клучеви = стар body, digest со нив = нови секции.
- **Прифаќање:** договор што истекува за 10 дена е во digest; SaaS-претплатите се внесуваат како договори (документирано во README-табелата? ако не — додај 1 ред).
- **Rollback:** врати digest-повикот (мала диф). Имплементирај ПО F3.

## Заеднички Definition of Done (секој feature)

- Тестови зелени + нови тестови по spec; `rl.reset()` во секој route-тест со login.
- Без emoji/икони надвор од sprite; без inline-скрипти; CSRF на секој POST.
- CHANGELOG запис со suite-бројка; README-врска ако има нова страница.
