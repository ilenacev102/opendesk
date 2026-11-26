# ServiceDesk ROADMAP — спринтови со излези

> Статус: v1.1 (2026-11-20). Секој спринт завршува со демо + метрика. Без демо — не е завршен.
> Активниот програм е `docs/superpowers/plans/2026-11-19-platform-program-5-months.md`;
> P1 (транзакциски интегритет), P2 (безбедносна хигиена), P3 (портал-тикет) и
> P4 (портал-идентитет и мобилност) се затворени.

## Definition of Done (важи за сè)

- Тестови зелени (`pytest`), нов код покриен со тест.
- Документирано (README/CHANGELOG или соодветен .md).
- Rollback-план: како се враќа назад за < 15 мин.
- Без secrets во repo, без emoji во UI, без inline-скрипт без nonce.

## S1 — Хигиена и зелен CI (недела 1)

**Цел:** секој merge е безбеден.
- `pg_mover` завршен (готово: 5 теста, suite 362+3).
- CI: pytest + ruff + secret-scan на секој push; блокира merge при црвено.
- `requirements.txt` замрзнат (gotovo: msal==1.39.0, без дупликати).
- Излез: зелен CI-badge + доказ `pytest -q`.

## S2 — Тврдост (недела 2)

**Цел:** убиј процес сред работа — податоците преживуваат.
- Backup restore-проба: snapshot → бриши DB → restore → `pytest` брза проверка. Runbook во `SECURITY.md` или нов `RUNBOOK.md`.
- Load-проба: 50 конкурентни heartbeat-и + 8-нишки ID-тест; p95 на `/devices` < 300ms при 500 уреди.
- Rate-limit `file`-режим документиран со compose-пример за 2 workers.
- Излез: restore-лог + load-бројки.

## S3 — Попис и discovery (недела 3–4)

**Цел:** попис за еден ден.
- PWA скенер: теренска проба 200 уреди/час; offline ред без губење.
- Discovery: CSV + Intune + heartbeat + SNMP низ ист reconcile/confirm; метрика: 0 прегазени задолжени уреди.
- CMDB `/cmdb/<id>` комплетен и empty-state безбеден.
- Излез: записник од реален попис + import-извештај.

## S4 — Ticketing и автоматизација (недела 5–6)

**Цел:** ниту еден тикет не тоне.
- SLA работни часови Пон–Пет 08–16 + празници; ескалација со priority-bump, без assignee-steal.
- Email-to-ticket: IMAP preview/confirm, Message-ID dedupe; KB-врски + „Реши од напис".
- Месечен mail-извештај на копче; digest со breached-секција.
- Излез: MTTR-бројка + breach-листа пред/по спринт.

## Топ-6 Reddit болки (практично, без научна фантастика)

1. **Auto offboarding-flag + невратено.** Проблем: „$30k изгубени уреди", враќањето е manual follow-up. Решение: дневен преглед „заминати со опрема" + ескалација по N дена + еден клик потсетник. Метрика: 0 уреди кај заминати >7 дена.
2. **Транзит/следење (chain-of-custody).** Проблем: заглавено во транзит, погрешна адреса, преселба без пријава. Решение: состојби `InTransit` + локациска историја (од→до→кој→кога) + „прими" копче. Метрика: 0 уреди без локација >24ч.
3. **HR-intake за onboarding.** Проблем: IT дознава последен. Решение: формулар „нов вработен" со рок X дена пред старт + пакет-шаблон по позиција. Без HR-пријава нема акаунт на време — пишано правило. Метрика: 100% спремни на ден 1.
4. **Ревизор-извоз на еден клик.** Проблем: ревизори бараат доказ, не способност. Решение: извоз (CSV/PDF) на промени, одобрувања, пристапи, одлуки по период + retention-политика. Метрика: ревизија поминува за <1 ден подготовка.
5. **SLA без гејминг.** Проблем: `On Hold` злоупотреба, затвори-отвори нов тикет. Решение: respond vs resolve SLA одвоено, строги pause-правила, reopen-бројач, CSAT-оценка по затворен тикет. Метрика: reopen <5%, CSAT >4/5.
6. **Аудит-датум + налепници.** Проблем: пописот умира без дисциплина. Решение: `next_audit_date` (+30 дена) по уред + кампања „недостасувачи" + задолжителни баркод-налепници на сè. Метрика: 100% скенирани во квартал.

## Микро-спринтови MS-1..MS-9 (секој <2ч работа за модел)

> Правило: еден микро-спринт = еден мал диф. Редоследот е задолжителен. Секој има точни фајлови, точни тестови и мерливо прифаќање.

### MS-1 — Offboarding листа (само читање, без записи)
- Цел: страница „заминати со опрема" што само чита.
- Чекори:
  1. `services/offboarding_service.py`: `flagged_devices(employees, devices, departed_ids)` — чиста функција, без I/O, враќа листа dict.
  2. `routes/operations.py`: GET `/offboarding/flagged` (magacioner+) што ја повикува функцијата и рендерира постоечки table-шаблон.
  3. `tests/test_offboarding_flag.py`: 3 теста — празно, еден заминат со 2 уреди, заминат без уреди.
- Прифаќање: рутата враќа 200, citac добива 403, тестовите зелени.
- Rollback: избриши рута + сервис (ништо не пишува).

### MS-2 — Невратено: потсетник + ескалација
- Цел: N дена невратено → видливо + ескалирано, идемпотентно.
- Чекори:
  1. `services/offboarding_service.py`: `overdue(days, today)` + `escalate(device_id)` што пишува еден `ESC_FLAG` audit (втор повик не дуплира).
  2. `routes/operations.py`: POST `/offboarding/escalate` со CSRF, само magacioner+.
  3. `tests/test_offboarding_overdue.py`: 3 теста — под праг, над праг, двојна ескалација = 1 audit.
- Прифаќање: метрика „0 уреди кај заминати >7 дена" видлива на страницата.
- Rollback: исклучи POST-рута (листата од MS-1 останува).

### MS-3 — Транзит состојби (валидација)
- Цел: `InTransit` како првокласна состојба со забранети премини.
- Чекори:
  1. `services/transit_service.py`: `TRANSITIONS = {Available: [InTransit], InTransit: [Available, Assigned], ...}` + `can_move(frm, to)`.
  2. `tests/test_transit.py`: 4 теста — дозволено, забрането (Assigned→Disposed, Repair→Available), непозната состојба, round-trip.
- Прифаќање: ниту една постоечка транзиција не се крши (`pytest tests/test_phases.py` зелен).
- Rollback: избриши сервис (не е врзан за рути).

### MS-4 — Локациска историја + „прими" копче
- Цел: од→до→кој→кога за секој транзит.
- Чекори:
  1. `services/schemas.py`: `TRANSIT_COLS = [TransitID, AssetID, FromLoc, ToLoc, ByUser, At]` (TEXT-шема како останатите).
  2. `services/transit_service.py`: `ship(asset, to_loc, by)` + `receive(asset, by)` — двете во трансакција со history-запис.
  3. `routes/operations.py`: POST `/transit/ship` + POST `/transit/receive` (CSRF).
  4. `tests/test_transit_flow.py`: 3 теста — ship→receive, receive без ship = грешка, историјата расте за 2.
- Прифаќање: 0 уреди без локација >24ч проверливо со query.
- Rollback: исклучи 2-те POST-рути.

### MS-5 — HR-intake формулар (валидација, без автоматика)
- Цел: „нов вработен" со рок X дена, без daemon.
- Чекори:
  1. `services/schemas.py`: `ONBOARD_COLS = [RequestID, FullName, Position, StartDate, Package, RequestedBy]`.
  2. `services/onboard_service.py`: `validate(req)` — StartDate мора ≥ today+2 дена, Package мора да постои.
  3. `routes/catalog.py`: GET+POST `/onboard` (magacioner+), preview пред запис.
  4. `tests/test_onboard.py`: 4 теста — валидно, StartDate утре = одбиено, непознат пакет = одбиено, дупликат RequestID = одбиено.
- Прифаќање: правилото „без HR-пријава нема акаунт на време" е напишано на страницата.
- Rollback: избриши рута (податоците остануваат).

### MS-6 — Ревизор-извоз (CSV, еден клик)
- Цел: доказ за ревизор без рачно собирање.
- Чекори:
  1. `services/audit_export.py`: `export_changes(history, frm, to)` — чиста функција, враќа редови (who/when/what/why).
  2. `routes/reports.py`: GET `/reports/audit-export?from=&to=` → CSV download (admin/magacioner).
  3. `tests/test_audit_export.py`: 3 теста — празен период, еден период со 2 записи, неуреден опсег = 400.
- Прифаќање: ревизор добива фајл за <1 мин; подготовка <1 ден.
- Rollback: избриши рута (сервисот е чист).

### MS-7 — SLA pause-правила + reopen-бројач
- Цел: крај на гејминг со `On Hold`.
- Чекори:
  1. `services/sla_service.py`: `pause_allowed(reason)` — само 3 дозволени причини, сè друго = одбиено.
  2. `services/incident_service.py`: `reopen_count(incident_id)` од history (`INC_REOPEN`).
  3. `tests/test_sla_pause.py`: 4 теста — дозволен pause, недозволен pause, reopen брои 2, затвори-отвори-нов не го ресетира бројачот.
- Прифаќање: respond vs resolve SLA прикажани одвоено на detail-страница.
- Rollback: врати ги двете функции (мала диф).

### MS-8 — CSAT оцена (една колона, еден endpoint)
- Цел: задоволство по затворен тикет.
- Чекори:
  1. `services/schemas.py`: додај `Satisfaction` колона во `INCIDENT_COLS` (auto-migrate како `LinkedTo`).
  2. `routes/incidents.py`: POST `/incidents/<id>/rate` (1–5, само затворени тикети).
  3. `tests/test_csat.py`: 3 теста — валидна оцена, оцена на отворен = 403/400, оцена 6 = 400.
- Прифаќање: просек CSAT видлив во digest; цел >4/5.
- Rollback: исклучи рута (колоната останува празна).

### MS-9 — `next_audit_date` + кампања недостасувачи
- Цел: пописна дисциплина без лов на луѓе.
- Чекори:
  1. `services/schemas.py`: `NextAuditDate` колона во `DEV_COLS` (auto-migrate).
  2. `services/popis_service.py`: `mark_scanned(asset)` поставува +30 дена; `missing(today)` враќа истечени.
  3. `routes/popis.py`: GET `/popis/missing` листа.
  4. `tests/test_audit_date.py`: 3 теста — скенирано = +30д, истечено се појавува, идно не се појавува.
- Прифаќање: 100% скенирани квартално мерливо со еден query.
- Rollback: исклучи рута (колоната останува).

## Backlog (по S4, по вредност)

1. Auto offboarding-flag + транзит-следење (болки 1+2).
2. HR-intake + ревизор-извоз (болки 3+4).
3. SLA anti-gaming + CSAT (болка 5).
4. Postgres-како-примарен со mover-runbook (dry-run → verify → cutover).
5. Gunicorn multi-worker compose-профил + споделен rate-limit file.
6. QR-налепници v2: bulk-print + `next_audit_date` (болка 6).
7. LDAP закажан sync (сè уште со preview, никогаш daemon-запис).
8. ~~Observability: JSON-логови + корелациски ID + табла 5xx/429 по рута~~
   — готово (2026-11-16): JSON access-лог, `request_id` корелација до
   500-страницата, `/system/observability` (admin), `scripts/log_report.py`;
   доказ `tests/test_observability.py` + `tests/test_observability_cli.py`.

## Ризици и одговори

| Ризик | Одговор |
|---|---|
| Увоз прегазува вистина | preview задолжителен, задолжените недопрени |
| Secret истекува | ротација преку env, revoke на токени, audit |
| Backup не работи кога треба | restore-проба неделно, надворешна копија |
| Scope-creep | VISION „не правиме" е блокирачка листа |
