# Имплементациски План: Спринт 6 — ChatOps, Webhooks & Agile Sprint Analytics

Овој план го дефинира **Спринт 6** од Мастер Трансформацискиот План: надградба на Agile аналитиката (Burndown & Velocity графикони), Canned Response Macros за операторите, автоматизирана детекција на дупликати (Triage AI-like Duplicate Detection), и Outgoing Webhook систем за интеграција со Slack/Teams/Mattermost.

---

## 1. Функционалности во Спринт 6

### А. Agile Burndown & Velocity графикони (`/sprints/<id>/analytics`)
- **Проблем сега:** Спринтовите имаат само листа на тикети и едноставен статус, без визуелен приказ на брзината на тимот (Velocity) и преостаната работа (Burndown chart).
- **Решение:**
  - Локален Canvas/SVG генератор на Burndown крива (идеална линија vs. реално завршени Story Points / тикети низ деновите на спринтот).
  - Velocity Chart низ завршените спринтови (Committed vs. Completed Story Points).
  - 100% vanilla JS без надворешни графички библиотеки (Chart.js/D3 CDN), целосно CSP компатибилно.

### Б. Canned Response Macros (Брзи шаблонски одговори при коментари)
- **Проблем сега:** Агентите постојано рачно пишуваат исти одговори (пр. „Испратете скриншот“, „Рестартирајте го уредот“, „Барањето е одобрено и опремата е нарачана“).
- **Решение:**
  - Складиште `macros` (`MacroID`, `Title`, `Category`, `BodyText`).
  - Избирач на шаблони во формата за коментар на инцидент кој инстантно го пополнува текстот со клик.
  - Администрација на шаблони на `/settings/macros`.

### В. Автоматска детекција на дупликати при Triage (Duplicate Detector)
- **Проблем сега:** Повеќе корисници пријавуваат ист дефект (пр. паднат интернет на кат 2), создавајќи хаос во редот на тикети.
- **Решение:**
  - Endpoint `/api/v1/incidents/detect-duplicates?title=...`: пресметува текстуална сличност (Jaccard / Token overlap) со активните инциденти.
  - Приказ на предупредувачки панел: „Пронајдени се 2 слични активни инциденти (INC-0012, INC-0015) — Поврзи како дупликат со 1 клик“.

### Г. Outgoing Webhooks за Slack / Teams / Mattermost
- **Проблем сега:** Критичните инциденти (Priority: Critical) и CAB промените немаат автоматска надворешна нотификација кон тимовите на терен.
- **Решение:**
  - Складиште `webhooks` (`WebhookID`, `Name`, `Url`, `Events`, `Secret`, `Active`).
  - Асинхроно испраќање на JSON payload при настани: `incident.critical_created`, `change.cab_pending`, `problem.resolved`.

---

## 2. Предложени Промени во Кодот

### 2.1 Шеми и складишта
- [MODIFY] services/schemas.py — Дефинирање на `MACRO_COLS` и `WEBHOOK_COLS`.
- [MODIFY] app.py — Отворање на `macros` и `webhooks` складишта.

### 2.2 Нови Рути и Сервиси
- [MODIFY] routes/sprints.py — Рута `/sprints/<id>/analytics`: податоци за Burndown крива и Velocity споредба.
- [NEW] routes/chatops.py — Менаџирање на Macros и Webhooks, dispatch сервис за нотификации.
- [MODIFY] routes/incidents.py — Детекција на дупликати и примена на макроа при коментирање/решавање.

### 2.3 Шаблони и Скрипти
- [NEW] templates_web/sprint_analytics.html — Визуелен Burndown & Velocity преглед.
- [NEW] static/js/burndown.js — Локален Canvas графикон за денови vs. Story Points.

---

## 3. План за Верификација
- Тестови во `tests/test_sprint_analytics.py`, `tests/test_macros.py`, `tests/test_webhooks.py`.
- 100% положени тестови на целокупниот pytest suite.
