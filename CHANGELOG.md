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

## Фаза SSO — најава преку OIDC

- **Кориснички шеми**: `USER_COLS` + `Email`/`OIDCSubject` (auto-migrate) +
  `AuthService.create_sso_user()` со празен hash — SSO-корисниците не можат
  локално да се најават.
- **OIDC сервис**: `services/oidc_service.py` (env config, authorize-URL,
  callback-verify преку injectable factory, claim-мапирање со username-
  fallback, `OidcError`, без secrets во логови) + `Authlib==1.6.12` pin.
- **Рути**: `GET /login/sso` (302 кон провајдер) + `GET /login/sso/callback`
  (JIT `citac`, link-по-email, улогата се чува) + SSO-копче на login; локалната
  најава недопрена. Без SAML (OIDC ги покрива Entra ID/Google/Keycloak).
- **Тестови**: sso-schemas, oidc (fake client, без мрежа), sso-ui (mocked flow,
  role-preserved, unconfigured-redirect).

## Фаза Discovery Pro — уредите сами се пријавуваат

- **Heartbeat API**: `POST /api/v1/discovery/heartbeat` (Bearer magacioner,
  JSON-валидација hostname+serial → 400, 401 без токен, 429 со Retry-After;
  full reconcile/confirm flow со verdict во одговор).
- **Агенти**: `agents/heartbeat.sh` (Linux: sysfs/dmidecode/machine-id) +
  `agents/heartbeat.ps1` (Windows: WMI) — само env-конфиг, dry-run режим,
  exit-кодови 0/1/2; cron/Task Scheduler упатство во `agents/README.md`.
- **Race-поправка**: конкурентни heartbeat-и за ист сериски беа 500
  (`UNIQUE constraint failed`) — сега губитникот паѓа на match-тек
  (IntegrityError-fallback), докажано со 8-нишки тест.
- **SNMP sweep**: `services/snmp_service.py` (read-only printer OIDs,
  injectable factory, clean-skip без lib/мрежа, community никогаш во логови).
- **Intune sync**: `services/intune_service.py` (MSAL client-credentials преку
  env, paginated fetch, injectable client) + preview/confirm UI во `/import`
  (re-reconcile при confirm, споделен preview-блок).
- **Тестови**: heartbeat (5), agents (6), heartbeat-flow (2, вкл. concurrency),
  snmp (4), intune (4), intune-ui (3); pg parity и понатаму skip без сервер.

## Фаза Analytics — контролна табла со бројки

- **Метрики**: `services/analytics_service.py` (8 чисти функции без I/O:
  devices_by, warranty_buckets 30/60/90, costs_by, incidents_by, breach_counts,
  mttr_hours, aging_buckets, license_expiry; празни/невалидни влезови → нули).
- **Dashboard**: incident-doughnut + warranty-прогноза + трошоци-табела +
  MTTR/breach бројачи врз постоечката страница (вендоран Chart.js + tojson,
  старите картички недопрени).
- **Месечен извештај**: `summary_email()` + `POST /reports/monthly-summary`
  (рачен trigger, citac-403, friendly flash без admin-email).
- **Тестови**: analytics (8), dashboard-ext (2), monthly (4).
- **Вкупно во suite**: 323 теста (67 фајлови).

## Документациска усогласеност (2026-09-28)

- `README.md`: бројка 151 → 323, env-табела проширена со DB/LDAP/OIDC/IMAP/
  SMTP/RATELIMIT/ADMIN/TEMPLATES (целосен список: `.env.example`), scan-патека
  исправена на `/popis/<pid>/scan`, rate-limit напомената усогласена со
  `SECURITY.md` (memory per-process + file за workers).
- `requirements.txt`: отстранет дупликат `qrcode>=7.0`, `msal` пиниран на
  `==1.39.0` (опционален, само за жив Intune sync).
- Познато WIP (завршено): `tests/test_pg_mover.py` (5 теста) + нов `services/pg_mover.py`
  (`MoverError`, `move_table`, `move_all`, `verify_all`, dry-run, без парцијални
  записи при грешка) — suite зелен: 320 passed, 3 skipped (вкупно 323).

## MS-1 — Offboarding листа (read-only)

- `services/offboarding_service.py`: чисти `departed_ids` + `flagged_devices`
  (без I/O); `GET /offboarding/flagged` во `routes/operations.py` со
  `offboarding_flagged.html` (breadcrumb + табела, без записи).
- Тестови: `tests/test_offboarding_flag.py` (3 service + 1 route).
  Suite: 324 passed, 3 skipped.

## MS-2 — Невратено: ескалација (идемпотентна)

- `services/offboarding_service.py`: `days_since` + `overdue` (чисти) +
  `escalate` (еден `OFF_ESC` audit, втор повик не дуплира).
- `POST /offboarding/escalate` (`@require admin/magacioner`, citac → 403) +
  колона „Последна промена" и копче „Ескалирај" на flagged-страницата.
- Научено: новите логини го прелија shared `/login` rate-limit (30/мин) и го
  срушија `test_sso_ui` во полн suite — route-тестовите сега викаат
  `ratelimit.reset()` (конвенција од `test_hardening`).
- Тестови: `tests/test_offboarding_overdue.py` (3 + 1).
  Suite: 328 passed, 3 skipped.

## MS-3 — Транзит-валидација (чиста, без рути)

- `services/transit_service.py`: `TRANSITIONS` + `can_move` + `allowed`,
  втемелени во validators/repair-FLOW (`Assigned→Disposed` и
  `Repair→Available` забранети, `InTransit` round-trip дозволен).
- Не е врзан за рути — rollback е бришење на фајлот.
- Тестови: `tests/test_transit.py` (4).

## MS-4 — Транзит со историја (chain-of-custody)

- `services/schemas.py`: `TRANSIT_COLS` (TransitID/DateTime/AssetID/FromLoc/ToLoc/ByUser).
- `services/transit_service.py`: `TransitService.ship` (→ InTransit + локација,
  валидирано преку `can_move`) + `receive` (→ Assigned ако има носител, инаку
  Available); секое движење = transit-запис + history во една трансакција.
- `POST /transit/ship` + `POST /transit/receive` (`@require admin/magacioner`) +
  транзит-картичка на device-страница („Испрати"/„Прими").
- Тестови: `tests/test_transit_flow.py` (3 + 1).
  Suite: 336 passed, 3 skipped.

## MS-5 — HR-intake за onboarding

- `services/schemas.py`: `ONBOARD_COLS` (RequestID/FullName/Position/StartDate/
  Package/RequestedBy).
- `services/onboard_service.py`: `validate` (старт ≥ +2 дена, пакет мора да
  постои) + `submit` (RequestID `OB…`, дупликат одбиен, `ONBOARD_CREATE` audit).
- `GET+POST /onboard` во `routes/catalog.py` со преглед пред запис
  (preview → confirm) + `onboard.html`.
- Тестови: `tests/test_onboard.py` (4 + 1 route).
  Suite: 341 passed, 3 skipped.

## MS-6 — Ревизор-извоз на еден клик

- `services/audit_export.py`: чист `export_changes` (филтер [од, до] +
  мапирање when/who/what/why, сортиран).
- `GET /reports/audit-export?from=&to=` (`@require admin/magacioner`,
  CSV со injection-guard, лош опсег → 400).
- Поправен мој bug: `history.records()` → `history.store.records()`
  (докажан од route-тестот пред merge).
- Тестови: `tests/test_audit_export.py` (3 + 1 route).
  Suite: 345 passed, 3 skipped.

## MS-7 — SLA без гејминг (reopen + pause-гејт)

- Наод: немаше reopen-тек ни `INC_REOPEN` — MS-7 го додаде, не само броење.
- `services/sla_service.py`: `PAUSE_REASONS` (3) + `pause_allowed`.
- `services/incident_service.py`: `resolved→open` со `INC_REOPEN` audit,
  `ClosedAt` се брише; `reopen_count` + `first_response_at`.
- Detail-страница: „Прв одговор" (respond) одвоено од „Рок" (resolve) +
  „Реотворен N пати" + копче „Реотвори" (постоечки transition-endpoint).
- Тестови: `tests/test_sla_pause.py` (4).
  Suite: 349 passed, 3 skipped.

## MS-8 — CSAT оцена 1–5

- `services/schemas.py`: колона `Satisfaction` (auto-migrate).
- `services/incident_service.py`: `rate` (само resolved, 1–5, `INC_RATE`
  audit) + чист `csat_average`.
- `POST /incidents/<iid>/rate` (`@require`) + оцена и форма на detail-страница.
- Месечниот извештај доби CSAT-линија (само кога има оценки; старите
  тестови недопрени). Schema-тестот ажуриран со новата колона.
- Тестови: `tests/test_csat.py` (3).
  Suite: 352 passed, 3 skipped.

## MS-9 — Audit-датум и кампања недостасувачи

- `services/schemas.py`: колона `NextAuditDate` (auto-migrate).
- `services/popis_service.py`: `mark_scanned` (+30 дена) + `missing`
  (само докажани истечени; без датум никогаш не е missing).
- `GET /popis/missing` + `popis_missing.html`; скенерот
  (`/popis/<pid>/found`) автоматски ја поместува штампата.
- Тестови: `tests/test_audit_date.py` (3 + 1 route).
  Suite: 356 passed, 3 skipped.

## S1/S2 — Тврдост: CI, RUNBOOK, workers-профил

- `.github/workflows/tests.yml`: проширен со `ruff check` и secret-scan job
  (без `.env`/клучеви во repo).
- `RUNBOOK.md` (нов): deploy, rollback <15 мин, restore SQLite (WAL-безбеден
  backup API + 7 дена ретенција) и Postgres (`pg_dump`), secret-ротација,
  табела за дијагностика.
- `docker-compose.yml`: `servicedesk-workers` профил (gunicorn `-w 4`,
  порт 5001, `SERVICEDESK_RATELIMIT=file` врз споделен `data/` volume).

## Backlog — LDAP preview, observability, QR bulk-print

- `scripts/ldap_preview.py` (нов): fetch + reconcile, никогаш `sync()`;
  exit 2 без конфигурација; cron-пример во docstring. Наод: dry-run
  неповредливоста веќе ја покрива `test_dry_run_writes_nothing`.
- Observability: `X-Request-ID` на секој одговор (валиден влезен се ехува,
  ѓубре се заменува); `uuid` веќе беше импортиран.
- QR bulk-print: верификувано како готово — `/labels` со филтри
  (статус/тип/локација) + print-копче, покриено со `test_qr.py` и
  `test_auth_matrix.py` (13 passed).
- Тестови: `tests/test_request_id.py` (3) + `tests/test_ldap_preview.py` (3).
  Suite: 362 passed, 3 skipped (вкупно 365, 78 фајлови).

## F1 — Моја работа табла

- `services/mywork_service.py` (нов, чист): `collect` + `days_left`.
  Пронајден bug при интеграција: `breach()` бара date-објект — нормализирано.
- `GET /my-work` + `mywork.html` (4 картички).
- Тестови: `tests/test_mywork.py` (3 + 1 route).

## F2 — In-app известувања (ѕвонче)

- `services/schemas.py`: `NOTIF_COLS`; `services/notify_center.py` (нов):
  `push`/`unread`/`mark_read`/`validate_kind`.
- `app.py`: `notifications` store + `unread_count` context-processor;
  `base.html` ѕвонче; `GET /notifications` + `POST /notifications/read`.
- Емитери (3): incident-escalate → assignee, transit-ship → носител,
  onboard-confirm → RequestedBy (празен username = без запис, никогаш грешка).
- Тестови: `tests/test_notify_center.py` (4 + 1 route со badge).

## F3 — Breach-прогноза

- `services/sla_service.py`: `will_breach` (garbage → False) + `forecast`
  (не-resolved во прозорец, сортирани по DueDate).
- `digest_email(..., forecast_rows=None)` — опциона секција „Ќе пробијат
  наскоро:"; стари повици недопрени.
- `notify_digest` пресметува `forecast(…, 2)` и го проследува.
- Тестови: `tests/test_forecast.py` (4).

## SPEC-FEATURES-2 — план за 6 нови функционалности

- `SPEC-FEATURES-2.md` (нов, неимплементиран): F1 Моја работа табла,
  F2 In-app известувања (ѕвонче), F3 Breach-прогноза, F4 Резервации
  календар + конфликти, F5 KB оценки + рангирање, F6 Договорни опомени +
  трошоци. Редослед: F1 → F2 → F3 → F6 → F4 → F5 (F3 пред F6 — заеднички
  digest; F5 последен — најголем). Секој со точни фајлови/функции/тестови/
  прифаќање/rollback + заеднички DoD.

## Jira Lite Phase 1 — Проекти и типови тикети

- `services/project_service.py` (нов): `create_project` (нормализација на
  клуч 2–6 ASCII, дупликат-заштита, аудит `PRJ_CREATE`), `default_project`
  (автоматски „IT ServiceDesk" со клуч `IT`), `ensure_defaults` (4
  стандартни типови, идемпотентен backfill на стари тикети без проект),
  `validate_type`, `workflow_columns` (сите текови →
  `open/in-progress/resolved` — 1:1 со постојните статуси, без миграција).
- `routes/projects.py` (нов): листа со бројачи, детали со статистика и
  типови, креирај/архивирај/додај тип — записи под `@require("admin")`;
  `app.py` store `projects` + `issue_types`; навигациски линк „Проекти".
- `services/schemas.py`: `PROJECT_COLS`, `ISSUE_TYPE_COLS`, проширен
  `INCIDENT_COLS` (`ProjectID`, `TypeID`, `EpicLink`, `StoryPoints`,
  `SprintID`, `Rank`) + ажуриран schema-lock; `db_service.py`: unique
  индекси за двата нови клуча.
- Тестови: `tests/test_projects.py` (7 unit + 3 route).

## F4 — Резервации: календар + сервис за конфликти

- `services/reservation_service.py` (нов): чисти `overlaps` (допир на
  граници = конфликт, garbage → `ValueError`), `conflicts` (само `active`),
  `create` (одбива преклоп со `ValidationError`); POST `/reservations`
  сега минува низ `create()` наместо инлајн-проверката.
- `GET /reservations/calendar?week=` — неделен grid (7 дена × уреди, денес
  означен, невалиден `week` → тековна недела), `reservations_calendar.html`
  (нов) и копче „Неделен календар" од листата.
- Тестови: `tests/test_reserv_calendar.py` (6).

## F5 — KB оценки и рангирање

- `services/schemas.py`: `KB_RATING_COLS`; `services/kb_rating.py` (нов):
  `vote` (1–5, upsert по напис+корисник), `average`, `ranked` (оценети
  прво по просек, неоценети после, стабилно).
- `routes/kb.py`: `POST /kb/<id>/rate` (`@require("admin","magacioner")`),
  деталот прикажува просек + форма, листата сортирана преку `ranked`;
  `app.py` store `kb_ratings`.
- Тестови: `tests/test_kb_rating.py` (4 unit + 2 route).
- Suite: 397 passed, 0 failed, 3 skipped (вкупно 400).

## Jira Lite Phase 2 — Kanban табла

- `services/board_service.py` (нов): чисти `columns_for`, `group_issues`
  (непознат статус паѓа во првата колона, без губење), `apply_filters`
  (assignee/тип/приоритет), `board_payload` (JSON-ready за шаблон).
- `routes/boards.py` (нов): `GET /projects/<pid>/board` (филтери, `mine=1`,
  `sprint=active` — само тикети од активниот спринт), `GET /my-board`
  (сите проекти, assignee=јас); blueprint-от е регистриран во `app.py`.
- `templates_web/board.html` (нов): read-only CSS-grid по колони со
  бројачи и empty-state; картичката води на `/incidents/<id>`.
- Тестови: `tests/test_board.py` (8).

## Jira Lite Phase 3 — Backlog и спринтови

- `services/schemas.py`: `SPRINT_COLS` (`planned|active|completed`);
  `app.py` store `sprints` + blueprint `routes/sprints.py`.
- `services/sprint_service.py` (нов): `create` (end > start, еден active
  спринт по проект), `start`, `complete` (останатите назад во Backlog, без
  губење), `move_to_sprint` (само open тикети), `backlog` (SprintID NULL
  по `Rank`), `burndown` (remaining vs ideal по ден).
- `routes/sprints.py` (нов): 8 рути — backlog листа, reorder, points
  (Fibonacci dropdown), креирај/започни/заврши спринт, тикет → спринт,
  детал со burndown.
- `templates_web/backlog.html` и `templates_web/sprint.html` (нови;
  burndown преку Chart.js); таблата филтрира по активен спринт.
- Тестови: `tests/test_sprints.py` (8).

## Jira Lite Phase 4a — Сервиси за соработка

- `services/mention_service.py` (нов): `extract` (граници на интерпункција,
  без дупликати, невалидни usernames игнорирани), `notify`
  (`Kind="mention"`).
- `services/watcher_service.py` (нов): `watch`/`unwatch` (toggle, еден ред
  при дупликат), `list_watchers`, `notify_watchers`.
- `services/worklog_service.py` (нов): `log` (мин ≥ 1, WorkedDate ≤ денес,
  `ValidationError` при прекршување), `total_minutes`,
  `minutes_by_assignee`.
- `services/schemas.py`: `WATCHER_COLS`, `WORKLOG_COLS`, `VERSION_COLS`;
  `app.py` store-ови `notifications`, `watchers`, `worklogs`, `versions`.
- Тестови: `tests/test_collab.py` (8).

## Jira Lite Phase 4b — Рути и UI за соработка

- `routes/incidents.py`: `_can_act` (admin/magacioner), `_collab_ctx`
  (watchers, збир работно време, верзии на проектот, корисници за
  @mention), `_notify_collab` (прво mention-и `Kind="mention"`, потоа
  assignee+watchers `Kind="incident"`, без дупликати); POST
  `/incidents/<id>/watch`, `/unwatch`, `/log`, `/fixversion` (верзија мора
  да припаѓа на истиот проект); емитери во коментар и транзиција на статус.
- `templates_web/incident.html`: редови „Поени" и „FixVersion" (dropdown
  за admin/magacioner), toggle за следење, „Работно време" (збир по
  тикет + форма), @mention автокомплет (nonce-скрипта).
- `services/project_service.py`: `WORKFLOWS["epic"]`
  (`Backlog/In Progress/Done`) + тип `Epic` во default типови;
  `INCIDENT_COLS` += `FixVersion` (авто-ALTER, без миграција).
- Тестови: `tests/test_collab_routes.py` (8).

## Jira Lite Phase 5 — Администрација и извештаи

- `routes/projects.py`: `GET/POST /projects/<pid>/settings` (име, lead,
  архивирање, типови), `POST .../types/<tid>/toggle`, `GET .../export`
  (JSON шаблон), `POST /projects/import` (клонирање проект од JSON);
  `templates_web/project_settings.html` (нов).
- `/projects` листа прикажува бројки по проект преку
  `analytics_service.by_project`.
- Тестови: `tests/test_project_admin.py` (8).
- Suite: 437 passed, 0 failed, 3 skipped (вкупно 440).

## Jira Lite Подобрувања и Оптимизации (2026-10-30)

- **Асинхрон SMTP dispatch (`services/notify_service.py`)**: `send_email_async`
  преку `ThreadPoolExecutor(max_workers=2)` за моментален HTTP одговор при
  задолжување, враќање и нотификации без блокирање на корисничкиот интерфејс.
- **Интерактивен Drag & Drop (`templates_web/board.html`)**: Нативен HTML5
  Drag & Drop на Канбан таблата со автоматска AJAX транзиција кон
  `/incidents/transition` и зачувување на строг CSP nonce.
- **Развојна околина**: Додаден `requirements-dev.txt` (`pytest`, `ruff`),
  а `start.sh` сега автоматски ја користи локалната `.venv` виртуелна околина.
- **Тест верификација**: 438 passed, 0 failed, 3 skipped (вкупно 441).

## Sprint 5 — CMDB Topology Graph и Impact Analysis (2026-11-11)

- **Интерактивна топологија (`routes/cmdb.py`, `templates_web/cmdb_topology.html`)**:
  визуелен граф на зависности меѓу CI (уреди, employees, rack-ови, експлицитни
  врски) со коренска точка `?root=` и филтер по тип `?type=`.
- **Graph API**: `GET /api/v1/cmdb/graph` (nodes + edges JSON) и
  `GET /api/v1/cmdb/impact/<asset_id>` — Blast Radius калкулатор (BFS
  надолно/нагоре) за процентели од уреди, rack-ови и rack items на кои
  влијае дефект на даден CI.
- **Релации**: `GET/POST /cmdb/relations/new` и `POST /cmdb/relations/delete`
  (SourceID/TargetID/RelationType во нова `cmdb_relations` табела, авто-ALTER).
- **UI анимациони систем**: `static/css/motion.css` (360 реда) +
  `static/js/motion.js` (251 реда) — spotlight glow по курсор, click ripples,
  alert progress bars, kinetic drag feedback; spring easings преку CSS токени,
  со почитување на `prefers-reduced-motion`. Board DnD мигриран на новите
  `.is-dragging`/`.drag-active` класи.
- **Тестови**: `tests/test_cmdb_topology.py` (5: graph API, blast radius,
  relations CRUD, topologiја, isolation).
- **Lint политика**: додаден `ruff.toml` — заклучен на pre-0.17 default
  (E4/E7/E9+F) со документирано WHY; `app.py` E402 per-file ignore (намерен
  init-редослед). CI сега инсталира pinned `requirements-dev.txt` наместо
  floating `ruff` (ruff 0.17 прошири default правила → 77 нови advisory
  грешки во стар код).
- **Suite: 465 passed, 0 failed, 3 skipped (вкупно 468).**

## Sprint 6 — ChatOps, Webhooks & Agile Sprint Analytics (2026-11-12)

- **Sprint Analytics (`routes/sprints.py`, `templates_web/sprint_analytics.html`,
  `static/js/burndown.js`)**: нова страница `/sprints/<sid>/analytics` —
  Burndown крива (идеал vs. реални преостанати Story Points) и Velocity
  графикон (Committed vs. Completed) низ завршени спринтови;
  `sprint_service.velocity()` пресметува поени по завршен спринт,
  сортирани по EndDate; vanilla canvas рендер без Chart.js (CSP-safe),
  dark/light освестен, DPR-скейлиран.
- **Canned Response Macros (`routes/chatops.py`, `services/macro_service.py`,
  `templates_web/macros.html`)**: складиште `macros` (MACRO_COLS), админ
  страница `/settings/macros` (админ само), JSON API `GET /api/v1/macros`
  за најавени корисници; избирач во формата за коментар на инцидент што
  инстантно го пополнува текстот.
- **Duplicate Detection (`services/duplicate_service.py`)**: Jaccard
  сличност по токени (кирилица+латиница); `GET
  /api/v1/incidents/detect-duplicates?title=&exclude=`; предупредувачки
  панел на страната на инцидент со 1-клик „Поврзи како дупликат“ (повторно
  го користи POST /incidents/link); debounced JS детектор на формата за
  нов инцидент; веќе-линкувани и resolved инциденти не се сугерираат.
- **Outgoing Webhooks (`services/webhook_service.py`,
  `templates_web/webhooks.html`)**: складиште `webhooks` (WEBHOOK_COLS),
  админ страница `/settings/webhooks` со toggle/delete; асинхроно
  испраќање преку ThreadPoolExecutor со HMAC-SHA256 потпис (`X-Signature`);
  настани: `incident.critical_created` (критичен инцидент — во системот
  тоа е приоритет `urgent`), `change.cab_pending` (нова промена поднесена
  до CAB), `problem.resolved` (решен проблем со каскаден број); доставата е
  fire-and-forget — неуспехот се логира, никад не крева исклучок.
- **Бугфикс (review)**: испорака на webhook при креирање на критичен
  инцидент била тивка — dispatch го добивал погрешен store и условот
  проверувал непостоечки приоритет `critical`; сега се испорачува на
  `urgent`, а wiring-от за сите три настани е покриен со тестови.
  URL валидација на webhook цели е зацврстена (urlparse: scheme+host,
  без whitespace); дупликат-детекторот на формата повеќе не гради HTML
  преку innerHTML (DOM API — без XSS); „Поврзи како дупликат“ копчињата
  се скриени за `citac` улога; burndown/velocity графиконите реагираат
  веднаш на рачна промена на темата (`sd-theme` настан).
- **Тестови**: `test_sprint_analytics.py` (9), `test_macros.py` (10),
  `test_duplicate_detection.py` (14), `test_webhooks.py` (18).
- **Suite: 516 passed, 0 failed, 3 skipped (вкупно 519).**

## Набљудување (observability) — 2026-11-16

- **JSON access-лог (`services/observability.py`, `app.py`)**: по едно барање
  една JSON линија (`ts`, `request_id`, `method`, `route`, `status`,
  `duration_ms`, `role`) во `logs/app.log` (10 MB × 5) и на stdout; без query
  string, headers, тела, имиња и IP. `/health` и `/static/*` се изоставени.
- **Корелација**: 500-страницата го прикажува `request_id` од хедерот, а
  пристапната линија ја носи истата вредност и `exc` со трагата — еден запис
  по барање, без дупликат `log.exception`.
- **Панел (`/system/observability`, admin)**: 5xx/429 по рута, p95 (проценка
  од хистограм), последни 100 бавни/паднати барања; бројачите се по процес.
- **CLI (`scripts/log_report.py`)**: агрегација низ workers/рестарти, вклучно
  `--log -` од `docker compose logs`; чист излез при лош `--since`/фајл.
- **Тестови**: `test_observability.py` (17), `test_observability_cli.py` (6);
  auth-матрицата го покрива панелот.
- **Suite: 539 passed, 0 failed, 3 skipped (вкупно 542).**

## P1 — транзакциски интегритет (2026-11-19)

Секоја мутација во опфатот е атомична и остава audit ред.

- **`store_transaction(*stores)`** (`services/db_service.py`): една
  backend-aware трансакција за SQLite и Postgres; одбива мешање на бази или
  различни DSN-и; `fallback_path` за legacy повикувачи. Мигрирани
  `IncidentService`, `CommentService`, `PopisService`, `project_service`.
  PG режимот повеќе не отвора SQLite конекција врз PgStore.
- **Нови store методи**: `update_where_all`, `delete_where_all` (SQLite + PG) —
  targeted замена за read-modify-write врз цела табела.
- **Спринтови**: `create/start/complete/move_to_sprint` во една трансакција со
  `SPRINT_CREATE|START|COMPLETE`, `INC_SPRINT_ADD|REMOVE`; ранг и поени
  преселени од рутите во `set_rank`/`set_points` (`INC_RANK`, `INC_POINTS`).
- **Каталог**: лиценцни седишта (`SeatsUsed` + seat ред + audit) во една
  трансакција; материјали, договори, барања, резервации и полиња повеќе не
  прават `replace_all`; одлуките `REQ_DECIDE`/`RES_CANCEL` се аудитирани.
- **KB оценки**: `vote` прави targeted upsert на еден ред (`KB_RATE`), без
  губење гласови при паралелни гласања.
- **Auth и токени**: сите мутации во трансакција со audit
  (`USER_CREATE|SSO_CREATE|ROLE|ACTIVATE|DEACTIVATE|PASS|SSO_LINK`,
  `TOKEN_CREATE|REVOKE`); лозинка и хеш никогаш не влегуваат во историја.
- **Попис**: `preview_finish` (read-only) → документ → еден `finish` со
  `POPIS_CLOSE` + `POPIS_MISSING`; `POPIS_START|SCAN` и `AUDIT_SCAN` се
  аудитирани; пад при генерирање документ го остава пописот `OPEN`.
- **Останати**: `onboard.submit`, `project_template.import_project`,
  `watcher_service.watch/unwatch`, `notify_center.push/mark_read` атомични;
  ID-ата одат низ `next_id_in`.
- **Уникатни индекси** за сите 36 табели (композитни за `field_values`,
  `kb_ratings`, `watchers`, `kb_links`); legacy дупликати не го блокираат
  стартувањето (лог + прескокнат индекс). `scripts/check_duplicate_ids.py`
  е read-only проверка пред миграција.
- **Guard тестови**: `test_store_transaction.py`, `test_sprint_tx.py`,
  `test_catalog_tx.py`, `test_auth_tx.py`, `test_popis_tx.py`,
  `test_atomic_secondary.py`, `test_identity_indexes.py`,
  `test_transaction_guards.py` (забрана за `replace_all` во доменски код и за
  `history.log` без `con` во трансакција).
- **Suite: 600 passed, 4 skipped**, ruff clean.

## P2 — безбедносна хигиена (2026-11-20)

- **CSRF за API**: `services/csrf.py` го дели `should_enforce(path,
  authorization)`; session-cookie `POST /api/*` бара токен (403 без него),
  `Authorization: Bearer …` останува exempt за машина-клиенти.
- **TLS преку env**: `config.tls_enabled()` / `SERVICEDESK_TLS=1` вклучува
  `SESSION_COOKIE_SECURE` и `Strict-Transport-Security`
  (`max-age=31536000; includeSubDomains`); default останува LAN-безбеден.
- **Стриктен CSP за стилови**: Google Fonts е отстранет; Inter/Sora woff2
  подмножества се вендорвани во `static/fonts/` (`scripts/vendor_fonts.py`,
  `static/css/fonts.css`). CSP е `style-src 'self' 'nonce-…'`, `font-src
  'self'`; сите inline `style=` атрибути се заменети со класи во
  `static/css/app.css`, а динамичните ширини/висини одат во nonce-заштитен
  `<style>` блок (`racks.html`, `licenses.html`).
- **Rate-limit граници**: `_rate_bucket` бара точен префикс или
  `prefix + "/"`, па `/api/v1foo` и `/loginx` повеќе не паѓаат во туѓа корпа.
- **Тајни споредби**: потврдено `hmac.compare_digest` во CSRF и API-токени,
  werkzeug хешеви за лозинки; додаден guard-тест против `==` врз тајни.
- **Auth-matrix**: 10 blueprints (chatops, sprints, itsm, maintenance, racks,
  cmdb, popis, portal, system, boards) × admin/magacioner/citac/anon, плус
  `tests/test_chatops.py` (макроа CRUD, `/api/v1/macros`, admin-only).
- **Одлука за мртви модули**: `finance.py` вратен во употреба — CSV извозот
  на уреди сега содржи пресметана `BookValue` колона
  (`test_reports_book_value.py`). `snmp_service.py` добива оперативен
  read-only влез `scripts/snmp_sweep.py` (`test_snmp_cli.py`); без `pysnmp`
  излегува со код 2 и јасна порака, без записи во база.
- **Схема документација**: `AGENTS.md` поправен — миграциите се во
  `services/db_service.py` / `services/pg_store.py`, не во `app.py`;
  service-сопствените `*_COLS` се преселени во `services/schemas.py` и
  ре-експортирани (`test_schema_columns.py`).
- **Suite: 631 passed, 4 skipped**, ruff clean.

## P3 — Портал: детаљ на тикет (2026-11-23)

- **Детал `/portal/ticket/<iid>`**: сопственикот гледа наслов, статус,
  приоритет, рок, техничар, thread од јавни коментари и прилози. Туѓ тикет →
  403, непостоечки → 404, анонимен → најава. Сопственост = `EmployeeID` на
  тикетот наспроти поврзаниот вработен или корисничкото име
  (`services/portal_service.py`).
- **Коментари**: `POST /portal/ticket/<iid>/comment` пишува во `comments` и
  аудитот со `PORTAL_COMMENT`; празен или предолг коментар се одбива;
  лимит 10/мин по корисник (429).
- **CSAT**: `POST /portal/ticket/<iid>/rate` (1–5), истите правила како staff
  CSAT (`resolved` само), но исклучиво сопственик; аудит `INC_RATE`.
- **Reopen**: `POST /portal/ticket/<iid>/reopen` само за `resolved`, еднаш на
  7 дена, статус → `open`, аудит `INC_REOPEN` и нотификација до assignee.
- **Мои тикети `/portal/tickets`**: филтер по статус, пагинација 10/страна,
  бројачи по статус и празна состојба.
- **Прилози**: `/portal/ticket/<iid>/attach/<name>` со истата traversal
  заштита, но со проверка на сопственост (staff рутата не се користи).
- **Тестови**: `test_portal_service.py` (ownership, reopen прозорец,
  пагинација, traversal), `test_portal_tickets.py` (сопственик vs туѓ 403,
  rate-limit, CSAT само на решен, reopen лимит, цел тек пријава → коментар →
  решавање → оценка → reopen); auth-матрицата покрива портал-тикет рутите.
- **Suite: 646 passed, 4 skipped**, ruff clean.

## P4 — Портал: идентитет и мобилност (2026-11-23)

- **ADR-07**: корисничките сметки ги креира администратор; нема
  саморегистрација ниту покани по e-mail, освен ако партнерот експлицитно
  побара (`ARCHITECTURE.md` §8).
- **Врзување корисник↔вработен**: citac без Employee ред гледа јасна порака
  на порталот со линк `/employees`; admin/magacioner не добиваат предупредување
  (нивните сметки по дизајн немаат вработен).
- **Известувања во порталот**: панел со badge, листа и „Прочитај“/„Прочитај
  сите“ (`POST /portal/notifications/read`); без нова страница.
- **Мобилен pass**: sticky CTA на `/portal`, скриени секундарни колони во
  табелите под 576/768px, `text-break` за долги наслови, auth-shell CSS за
  најава/сетуп (една колона под 768px, без хоризонтален скрол).
- **Доказ**: Playwright на 390×844 — `scrollWidth == innerWidth` за `/login`,
  `/portal`, `/portal/ticket/<iid>` и `/portal/tickets`; screenshot-и
  `docs/screenshots/p4-{login,portal,ticket,tickets}-390.png`.
- **Тестови**: `test_portal_mobile.py` (6) — мобилни маркери, CSS правила,
  mapping порака само за citac, notification read (едно/сите).
- **Suite: 652 passed, 4 skipped**, ruff clean.

## Стартување

```bash
bash start.sh             # стартува со .venv и отвора порта 5000
python3 -m pytest tests/  # целосен suite (652 passed, 4 skipped)
```

