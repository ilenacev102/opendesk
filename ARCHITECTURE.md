# ServiceDesk ARCHITECTURE — техничка вистина

> Статус: v1 (2026-09-28). Проверливо со: `routes/`, `services/`, `tests/`, `config.py`.

## 1. C4-накратко

- **Контекст:** LAN-апликација. Актери: admin, magacioner, citac. Надворешни системи (сите read-only кон нас освен heartbeat): SMTP (испраќање), IMAP (читање), LDAP/AD (читање), Intune Graph (читање), SNMP (читање), OIDC провајдер (автентикација), LibreOffice (PDF).
- **Контејнери:** еден Flask-процес (gunicorn во Docker) + SQLite датотека default / Postgres опција + `documents/` + `backup/` + `logs/`.
- **Компоненти:** `app.py` (ядро: init, auth-гард, stores, services, headers) + `routes/` blueprints (admin, api, catalog, cmdb, files, incidents, inventory, kb, operations, popis, reports, system) + `services/` бизнис-логика + `templates_web/` + `static/`.

## 2. Слоеви и правила

```
HTTP (routes/) → services/ (правила) → stores (db_service/open_store) → SQLite/Postgres
```

- Рутите не содржат SQL и не носат бизнис-одлуки; само валидација на влез, повик на сервис, render/redirect.
- Сервисите не знаат за HTTP; враќаат резултат или фрлаат доменска грешка.
- Шаблоните не носат логика; бои/токени само преку `DESIGN.md` CSS-варијабли.
- Секоја мутација пишува audit-запис (history) во иста трансакција.

## 3. Животен циклус на уред

```
Available ↔ Assigned → Broken → Repair → Repaired → Available
Broken → Unrepairable → Disposed
```

- Замена: `old_condition` одредува одредиште (Available→залиха, Broken→сервис, Disposed→расход).
- Враќање: само вистински сопственик; забрана од `Repair` (мора сервисен тек).
- Расход: блокада ако уредот е задолжен (порака кој е носител).
- Bulk offboarding: повеќе уреди, еден документ.

## 4. Трансакции и конкуренција

- `BEGIN IMMEDIATE` за поврзани мутации (уред + трансакција + историја) со rollback.
- `journal_mode=WAL` + `busy_timeout=5000` на секоја конекција.
- ID-генерација внатре во трансакцијата (`next_id_in` + `max_suffix_con`); имиња на документи со uuid-суфикс.
- Heartbeat-трки: губитникот паѓа на match-тек (IntegrityError-fallback), докажано со 8-нишки тест.

## 5. Складирање и миграции

- `StoreProtocol` + `open_store()` фабрика; SQLite default (`SERVICEDESK_DB`), Postgres преку `SERVICEDESK_DB_URL`.
- Миграции: `ALTER TABLE` за нови колони + partial unique индекси; proverka со `tests/test_migrate_check.py`.
- SQLite→Postgres mover: `services/pg_mover.py` (`move_table`, `move_all`, `verify_all`, dry-run, `MoverError`). Употреба: копирај → верификувај броеви → дури тогаш префрли сообраќај.
- Backup: конзистентни snapshots вклучително WAL; задржување 7 дена локално + надворешна копија (задолжително).

## 6. Auth, API, безбедност

- Сесии (Flask-Login) + улоги `admin/magacioner/citac`; празна users-табела = setup-режим (`/setup`).
- REST v1: sha256 Bearer-токени (`/api-tokens`), 401 JSON (не редирект); `/api/` изземен од CSRF (Bearer, не cookie).
- CSRF: session-токен, `hmac.compare_digest`, hidden `_csrf_token` или `X-CSRF-Token`.
- Headers: CSP nonce-based, `X-Frame-Options: DENY`, `nosniff`, `MAX_CONTENT_LENGTH` 25MB, friendly 500 без истекување.
- Rate-limit: sliding-window; `/login` 30/мин, `/pdf` 30/мин, `/api/v1/*` 120/мин → 429 + `Retry-After`; `memory` default, `file` за workers.
- Прилози: `documents/incidents/<id>/`, `commonpath` traversal-заштита, png/jpg/pdf/log/txt.
- Secrets: само env (`SECRET`, SMTP, LDAP, IMAP, OIDC, INTUNE, SNMP). Никогаш во логови и repo.

## 7. Интеграции (сите недоверливи влезови)

| Интеграција | Насока | Правило |
|---|---|---|
| CSV discovery | влез | normalize + reconcile (new/match/conflict), preview, задолжените недопрени |
| Heartbeat | влез | Bearer magacioner, hostname+serial задолжителни, full reconcile/confirm |
| SNMP sweep | влез | read-only printer OIDs, clean-skip без lib/мрежа |
| Intune Graph | влез | MSAL client-credentials, paginated fetch, ист reconcile/confirm како CSV |
| LDAP/AD | влез | read-only, dry-run, без лозинки, без деактивација на локални корисници |
| IMAP email-to-ticket | влез | read-only poll, рачен trigger, `[I-XXXXXX]` reply-детекција, Message-ID dedupe |
| SMTP notify | излез | `send_email` никогаш не фрла; без SMTP тивко се прескокнува |
| OIDC SSO | auth | JIT `citac`, link-по-email, улогата се чува, локална најава останува |

## 8. ADR-записи (одлуки што не се преиспитуваат тивко)

- ADR-01: SQLite default, Postgres опција — offline LAN пред сè.
- ADR-02: Монолит со blueprints, без микросервиси — еден deploy, еден backup.
- ADR-03: Ниеден bulk-увоз без preview — грешка во увоз е полоша од бавен увоз.
- ADR-04: LDAP read-only засекогаш — директориумот не е наш.
- ADR-05: OIDC наместо SAML — ги покрива Entra ID/Google/Keycloak.
- ADR-06: Bootstrap вендоран локално — офлајн LAN + строг CSP.

## 9. Проверка (како се докажува)

- `python3 -m pytest tests/` — 441 тест (438 passed, 3 skipped).
- Auth-матрица: `tests/test_auth_matrix.py`. CSP: `tests/test_csp.py`. Конкуренција: integrity + heartbeat-flow + popis-concurrency.
- Дизајн-гарда: `tests/test_ui.py` (без emoji, sprite-покриеност).

