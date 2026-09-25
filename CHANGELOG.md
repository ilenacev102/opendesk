# ServiceDesk — детален преглед на измените

Локална Flask-апликација за евиденција на ИТ опрема: задолжување, раздолжување
(поединечно и групно offboarding), замена, сервис, расход, пакети опрема,
попис, историја/ревизија, документи (DOCX/PDF) и извештаи. Складирање: SQLite
со CSV-компатибилен слој (`services/db_service.py`).

## Фаза 1 — логички исправки и интегритет на податоци

- **Замена (`ReplacementService.confirm`)**: нов параметар `old_condition`
  (`Available` → залиха, `Broken` → сервис, `Disposed` → расход); валидација
  дека стариот уред е задолжен кај вработениот, а новиот е слободен.
- **Враќање (`validators.require_returnable`)**: проверка на вистински
  сопственик (`dev.EmployeeID == emp_id`); забрана за враќање од статус
  `Repair` (мора низ сервисен тек).
- **Расход (`DisposalService.confirm/confirm_many`)**: блокада на расход на
  задолжен уред преку `require_disposable`, со порака кој е носителот.
- **Сервис (`RepairService`)**: тек `Broken → Repair → Repaired → Available`;
  `mark_unrepairable` носи директно во расход; `advance(..., return_to_emp=True)`
  го враќа поправениот уред кај истиот вработен.
- **Групно раздолжување (`ReturnService.confirm_many`)**: offboarding на повеќе
  уреди одеднаш со еден документ.
- **Трансакции (`db_service.db_transaction`)**: поврзани мутации (уред + трансакција
  + историја) во една `BEGIN IMMEDIATE` трансакција со автоматски rollback.

## Фаза 2 — UI/UX, пагинација, филтри, offboarding, мобилност

- `/devices`: филтер-бар (статус, тип, локација, текст), пагинација
  (прва/претходна/броеви/следна/последна), бројач „прикажани X–Y од Z",
  избор на ставки по страница, зачувување на филтрите при листење.
- `/history`: пагинација + бројач + избор на ставки по страница.
- `/return`: табови „Поединечно" и „Групен поврат (Offboarding)" — избор на
  вработен ја листа сите негови уреди со чекбоксови и [✓ Сите].
- `/replace`: селектор за состојба на стариот уред.
- Сите табели во `.table-responsive`; подобрен контраст на статус-беџовите во
  светла и темна тема.

## Целосен редизајн — дизајн-систем „Ops Console" (`DESIGN.md`)

- Токени: еден син акцент, неутрални површини, семантички бои само за статус;
  типографија Sora (наслови/бројки) + Inter (текст).
- SVG sprite (`templates_web/_icons.html`, 18 икони) ги замени сите 38 emoji-икони.
- Модерна леплива навигација со активни состојби, skip-link, `<main>` landmark,
  SVG theme-toggle со persist во localStorage.
- Табла: икона-картички за брзи акции, рамни stat-картички со икона-chip,
  theme-aware Chart.js графикони; детал на уред со hero-картичка.
- SEO: автоматски наслови по страница, meta description, Open Graph тагови,
  `theme-color`, `robots: noindex, nofollow` (интерна алатка — намерно надвор од
  пребарувачи).

## P0 — интегритет под конкуренција (докажани дефекти, поправени со TDD)

- **Дупли TransactionID при паралелни операции** (докажано: 8 нишки → 7× ист ID):
  ID-ата сега се коваат *внатре* во трансакцијата (`next_id_in` + `max_suffix_con`);
  имињата на документи користат uuid-суфикс. Покриено со конкурентен тест.
- **SQLite pragmas**: `journal_mode=WAL` + `busy_timeout=5000` на секоја конекција.
- **Friendly 500**: `@app.errorhandler(500)` логира traceback со референца и
  рендерира `500.html` без истекување на детали.

## Откриени и поправени дефекти (хипотеза → runtime доказ)

- `/popis` немаше листа на започнати пописи (недостапни по напуштање на страната)
  → додадена листа со „Продолжи"/„Записник", отворените први.
- `/dispose` фрлаше JS грешка (`DevicePicker` бараше `closest("form")`, а input-от е
  надвор од формата) → опционален `formEl` параметар + null-guardови; страницата
  предава својата форма експлицитно.
- CSP-headerот ги блокираше CDN-врските (Bootstrap/фонтови) → Bootstrap 5.3.3
  вендоран локално (`static/css`, `static/js`); CSP whitelist само за Google Fonts.
- API v1 враќаше 401 во setup-режим додека UI беше отворен → `_require_api_roles`
  го почитува setup-режимот; regression-тест.
- CSP (`script-src 'self'`) ги блокираше сите inline-скрипти (бројачи, графикони,
  autocomplete-инити) → nonce-based CSP: уникатен nonce по response + nonce на
  14-те inline `<script>` во 12 шаблони; `tests/test_csp.py` го заклучува.
- Секое задолжување/враќање излегуваше со незаменето `«ИМЕ_ПРЕЗИМЕ»` →
  додадено во двете `fill_zadolzenie*` мапирања; `tests/test_documents.py`.
- Читач (`citac`) можеше да запишува преку web-рутите (мутациите немаа
  `@roles_required`) → централна заштита: citac + POST → 403 во `enforce_auth`;
  `tests/test_auth_matrix.py` ја заклучува целата auth-матрица.

## Фаза А — платформа: auth, API, нотификации

- **А.1 автентикација + улоги** (`services/auth_service.py`, `tests/test_auth.py`, 8):
  PBKDF2-хеширани лозинки, улоги `admin`/`magacioner`/`citac`, first-run setup
  (`/setup` → `/login` → `/logout`, `/users`), env-bootstrap за Docker,
  `before_request` гард + `roles_required`. Постоечките 29 теста останаа зелени.
- **А.2 REST API v1** (`services/api_token_service.py`, `tests/test_api.py`, 5+1):
  sha256-токени, Bearer `request_loader`, 401 JSON (не редирект) за v1,
  `devices`, `devices/<id>`, `employees`, `checkout`, `checkin`, `history`,
  `/api-tokens` admin-страница.
- **А.3 SMTP нотификации** (`services/notify_service.py`, `tests/test_notify.py`, 8):
  `send_email` никогаш не фрла, mail при задолжување/раздолжување (single+bulk),
  `/notify-digest` за гаранции, SMTP-променливи во `.env.example`.

## Фаза Б — вредност за магационер

- **Б.1 QR-налепници** (`services/qr_service.py`, `tests/test_qr.py`, 8):
  `/qr/<id>` PNG од меморија (404 за непостоечки/небезбеден ID), `/labels`
  со филтри и печатење, QR на device-страница, `qrcode`/`pillow` декларирани.
- **Б.2 амортизација** (`services/finance.py`, `tests/test_finance.py`, 7):
  `PurchasePrice` + `Supplier` колони (авто-миграција преку `ALTER TABLE`),
  линеарна `book_value()` (4 год.), приказ + CSV-export; import толерира стари
  CSV-иња без новите колони (`OPTIONAL_DEV_COLS`, докажано со тест).
- **Б.3а потпис при прием** (`services/signature.py`, `tests/test_signature.py`, 8):
  canvas (mouse+touch, празен = без потпис), PNG ≤200KB под
  `documents/signatures/`, `SignaturePath` колона, вметнување во DOCX
  (докажано: `word/media/*.png` во zip).
- **Б.3б потрошен материјал** (`tests/test_consumables.py`, 5): табела, внес,
  издавање со проверка на залиха (`CONSUME` во историја), „Ниска залиха" беџ.

## Фаза В — евиденција

- **В.1 лиценци** (`tests/test_licenses.py`, 5): седишта со горна/дона граница
  (`LIC_ASSIGN`/`LIC_REVOKE`), „Истекува" беџ (30 дена).
- **В.2 custom полиња** (`tests/test_fields.py`, 4): дефиниции (`/fields`) +
  вредности по уред, inline-уредување на device-страница, каскадно бришење.

## Фаза Г — договори, резервации, барања

- **Договори** (`tests/test_contracts.py`, 3): CRUD + „Истекува" беџ.
- **Резервации** (`tests/test_reservations.py`, 4): заштита од преклопување
  на датуми по уред, откажување (cancel, не бришење).
- **Барања** (`tests/test_requests.py`, 3): intake (`open`) + одлука
  (`approved`/`rejected`, само admin/magacioner).

## Дизајн-додатоци (фази Б–Г)

- Потпис-pad стилови + `.touch-none` (поправено скршено цртање на телефон).
- Print-CSS за QR-налепници (без nav/форми, `break-inside: avoid`,
  точни бои); темна варијанта за warning-редови. Документирано во `DESIGN.md` §5.
- Bootstrap 5.3.3 вендоран локално (офлајн LAN + строг CSP).

## Фаза Д — документација + хигиена

- `SECURITY.md` и `README.md`: отстранета застарената тврдба „нема автентикација";
  posture-секцијата ја опишува вистинската состојба (улоги, Bearer, CSP, лимити)
  со чесно наведени пропусти.
- `CHANGELOG.md`: комплетиран со фазите А–Г.
- `requirements.txt`: отстранет дупликат, сите верзии пинирани (`==`) и
  проверени против инсталираното.

## Фаза Е — hardening

- `services/ratelimit.py`: sliding-window лимитер (in-memory, по процес).
- `security_checks` before_request пред auth: `/login` 30/мин, `/pdf` 30/мин,
  `/api/v1/*` 120/мин → 429 + `Retry-After`; туѓ `Origin`/`Referer` на POST → 403.
- Import прифаќа само `.csv`. Покриено со `tests/test_hardening.py` (7):
  вклучувајќи abuse-тест (40 брзи логини → 429).

## Фаза З — CSRF-заштита

- `services/csrf.py`: session-токен (`secrets.token_urlsafe`, 32B) во
  `session["_csrf_token"]`; споредба со `hmac.compare_digest`; токенот се
  вади од hidden поле `_csrf_token` или header `X-CSRF-Token`.
- `csrf_protect` `before_request` (по `enforce_auth`): секој POST без валиден
  токен → 403; патеките под `/api/` се изземени (Bearer, не cookie auth).
  Контекст-процесор `inject_csrf_token` го изложува токенот на сите шаблони.
- 37 POST-форми во 24 шаблони добија hidden `_csrf_token` поле.
- Конфиг: `SERVICEDESK_CSRF` (default `1`; `tests/conftest.py` става `0` за
  suite-от, `tests/test_csrf.py` го вклучува per-test). 7 нови теста.

## Фаза Ж — тест-изолација

- `SERVICEDESK_DB` env-override во `app.py` + `tests/conftest.py` што ги врзува
  сите app-stores кон tmp-база. Доказ: mtime на `data/` идентичен пред/по suite;
  `tests/test_isolation.py` го заклучува однесувањето.

## Фаза 3 — blueprints (app.py 2414 → 436)

- Сите рути исечени од `app.py` во `routes/`: `admin` (auth, users, api-tokens),
  `api` (REST v1 + autocomplete), `catalog` (consumables, licenses, contracts,
  reservations, requests, fields), `files` (qr, labels, doc, pdf), `inventory`
  (employees, devices, departments, locations), `operations` (assign, return,
  replace, repair, quick-return, dispose, packages), `popis`, `reports`
  (reports, import, notify-digest), `system` (dashboard, search, history, health).
- Во `app.py` останаа само јадрото (init, auth-гард, stores, services,
  `ID_PREFIX`, `warranty_days`/`warranty_level`, errorhandler) и регистрацијата
  на blueprints. `ID_PREFIX` намерно остана во `app.py` — го увезува и
  `routes/api.py`. Бизнис-логиката е недопрена (ист suite, проширен).
- Security-заклучувања: `SESSION_COOKIE_HTTPONLY` + `SAMESITE=Lax`;
  regression-тестови за blueprint auth-матрица, cookie flags и doc/pdf traversal.

## Тестови (151: сè TDD или route-проверено со извршување)

- `tests/test_phases.py` (10): замена, сопственост, Repair-блокада, расход-блокада,
  bulk offboarding, сервис-тек, филтри/пагинација на рути.
- `tests/test_integrity.py` (9): конкурентни ID-а, pragmas, friendly 500,
  попис-листа, попис-сервис тек, пакети, dispose-picker врска.
- `tests/test_ui.py` (6): забрана за emoji, sprite-покриеност, shell-маркери,
  dashboard-маркери, render-проверка на рути.
- Фази А–Г: auth (8), api (6), notify (8), qr (8), finance (7), signature (8),
  consumables (5), licenses (5), fields (4), contracts (3), reservations (4),
  requests (3).
- Фази Д–Ж: hardening (7), isolation (2).

## Фаза Enterprise — доближување до светските платформи

- **Discovery увоз**: `services/discovery_service.py` (normalize + reconcile
  new/match/conflict + transactional confirm; задолжените уреди никогаш не се
  допираат) + dry-run preview во `/import` со `DISCOVERY_IMPORT` summary во audit.
- **Инциденти**: `services/incident_service.py` (open → in-progress → resolved,
  приоритети, рокови) + `/incidents` листа/детал/креирање/транзиција со филтри
  и пагинација; SLA breach-беџ „пробиен рок" + breached-секција во digest.
- **PWA скенер**: `/popis/<pid>/scan` (камера преку BarcodeDetector +
  getUserMedia, offline ред во localStorage) + JSON endpoint
  `/popis/<pid>/found` (CSRF преку `X-CSRF-Token` header).
- **CMDB преглед**: `/cmdb/<asset_id>` (уред + сопственик + лиценци +
  договори + резервации + барања + инциденти, empty-state безбеден).
- **LDAP/AD**: read-only sync (`sAMAccountName` мапирање, dry-run, без лозинки
  во repo) + `/users/sync` admin UI со преглед пред потврда.
- **Складирање**: `StoreProtocol` апстракција + `open_store()` фабрика;
  Postgres-опција преку `SERVICEDESK_DB_URL` (SQLite останува default);
  shared rate-limit (`memory`/`file`) + upload-лимит 25MB.
- **Тестови (221 passed, 3 skipped)**: enterprise +27 (schemas, discovery,
  import-ui, incidents, incidents-ui, sla, scan, history-wire, ldap, ldap-ui,
  store-base, pg-option, ratelimit-shared, cmdb, migrate-check); pg parity
  се прескокнува чисто без жив сервер.

## Фаза Ticketing Pro — длабочина на тикетинг

- **SLA engine**: `services/sla_service.py` (работни часови Пон–Пет 08–16,
  прескокнување викенди/празници, нивоа ok/warning/breached) + seed-политики
  по приоритет.
- **Ескалација**: `services/escalation_service.py` (priority-bump до urgent,
  идемпотентен преку `ESC_ESCALATE` audit, без assignee-steal) + копче на
  detail + ескалирани-секција во digest.
- **Коментари**: `services/comment_service.py` + activity thread на detail
  (автор/датум, XSS-escape) + `INC_COMMENT` audit.
- **Прилози**: `documents/incidents/<id>/` со traversal-заштита
  (`commonpath`), дозволени png/jpg/pdf/log/txt, лимит 25MB.
- **База на знаење**: `routes/kb.py` CRUD + пребарување + `kb_links` врски +
  „Реши од напис" (ClosedAt + `[KB:ID]` референца).
- **Email-to-ticket**: `services/mail_ingest.py` (IMAP read-only, reply-
  детекција `[I-XXXXXX]`, Message-ID dedupe преку history+batch, сè во
  трансакција) + `/incidents/inbox` preview/confirm; само рачен trigger.
- **Дупликати**: `LinkedTo` поле + link/unlink + приказ + `INC_LINK` audit.
- **Тестови (260 passed, 3 skipped)**: ticketing-pro +39 (schemas, sla-engine,
  escalation, comments, attachments, kb-ui, kb-links, mail-ingest,
  duplicates); pg parity и понатаму skip без сервер.

## Стартување

```bash
python3 app.py            # http://127.0.0.1:5000 (или SERVICEDESK_PORT)
python3 -m pytest tests/  # целосен suite
```
