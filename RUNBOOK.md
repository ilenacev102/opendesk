# ServiceDesk RUNBOOK — deploy, rollback, restore

> Проверливо со: `Dockerfile`, `docker-compose.yml`, `utils/helpers.py::backup_all`, `config.py`.

## 1. Deploy (Docker)

```bash
export SERVICEDESK_SECRET="$(openssl rand -hex 32)"
docker compose up -d --build
curl -sf http://127.0.0.1:5000/health  # {"status":"ok"}
```

- Портата е врзана за `127.0.0.1:5000` по default (`SERVICEDESK_BIND`).
- Без `SERVICEDESK_SECRET` контејнерот одбива старт (`SERVICEDESK_REQUIRE_SECRET=1`).
- Postgres-профил: `SERVICEDESK_PG_PASSWORD=... docker compose --profile pg up -d`,
  потоа `SERVICEDESK_DB_URL=postgresql://...` и миграција преку `pg_mover`
  (dry-run → verify → cutover, види `ARCHITECTURE.md`).
- Workers-профил (3+ workers): `docker compose --profile workers up -d`
  (споделен `file` rate-limit преку истиот `data/` volume).

## 2. Rollback (< 15 мин)

Build-от е од извор (`build: .`), податоците се во volumes:

```bash
docker compose down
git log --oneline -3            # најди последна добра ревизија
git checkout <добра-ревизија>
docker compose up -d --build
curl -sf http://127.0.0.1:5000/health
```

Податоците (`data/`, `documents/`, `backup/`) не се чепкаат — rollback-от
менува само код. Миграциите се адитивни колони (`ALTER TABLE`), па стар код
работи и со нова база.

## 3. Backup / restore

- `backup_all()` пишува дневни snapshots во `backup/YYYY-MM-DD/` при секој
  запис (`BACKUP_ON_WRITE=1`); SQLite се копира преку backup API
  (WAL-безбедно, не обичен `cp`); ретенција 7 дена.
- Надворешна копија (задолжителна): `rsync -a backup/ user@nas:/srv/sd-backup/`.

Restore (SQLite):

```bash
docker compose down            # или ./stop.sh за локален режим
ls backup/                     # избери датум
cp backup/<датум>/servicedesk.db data/servicedesk.db
docker compose up -d
curl -sf http://127.0.0.1:5000/health
python3 -m pytest tests/test_migrate_check.py -q   # брза проверка
```

Restore (Postgres-профил):

```bash
docker compose --profile pg exec db pg_dump -U servicedesk servicedesk > /srv/sd-backup/dump.sql   # backup
cat /srv/sd-backup/dump.sql | docker compose --profile pg exec -T db psql -U servicedesk servicedesk  # restore
```

Restore-проба: неделно на тест-машина — snapshot → бриши → restore →
`/health` + брз pytest. Лог од пробата се чува.

## 4. Secret-ротација

- Flask secret (`.servicedesk_secret` локално / `SERVICEDESK_SECRET` во Docker):
  ротирај со рестарт; сите сесии се одјавуваат (очекувано).
- API-токени: revoke преку `/api-tokens`, издај нови.
- SMTP/LDAP/IMAP/OIDC лозинки: смени во env, рестарт, провери `/health`
  и еден рачен trigger (digest-preview, users-sync-preview).

## 5. Кога нешто не работи

| Симптом | Прво провери |
|---|---|
| 500 на сè | `logs/` + `docker compose logs --tail 50` |
| 429 насекаде | `SERVICEDESK_RATELIMIT` режим; `file` за повеќе workers |
| Заклучена SQLite | само еден writer; WAL + `busy_timeout=5000` се default |
| Празна база по рестарт | дали `data/` е монтиран volume, не ефемерен слој |
