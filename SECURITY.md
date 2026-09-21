# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| main (current) | :white_check_mark: |

## Reporting a Vulnerability

Пријавете преку **GitHub Security Advisories** (Private vulnerability reporting)
на репозиториумот — не отворајте јавен issue за безбедносен проблем.

## Known posture (прочитајте пред deploy)

- Автентикација: Flask-Login сесии + улоги `admin`/`magacioner`/`citac`
  (`/users` е само за admin). Празна `users` табела = setup-режим (отворено
  додека не се креира првиот администратор преку `/setup`); штом има
  корисник, сè освен `/login`, `/setup`, `/health` и static бара најава.
  REST API v1 користи Bearer-токени (`/api-tokens`, sha256-хеш, отповикливи).
- Docker deploy бара `SERVICEDESK_SECRET`; локален install генерира приватен key
  во `.servicedesk_secret` со дозволи само за тековниот корисник.
- HTTP-хардининг: security headers (CSP без CDN освен Google Fonts,
  `X-Frame-Options: DENY`, `nosniff`), `MAX_CONTENT_LENGTH` 5MB, friendly 500
  без истекување детали, RotatingFileHandler за логови.
- `/doc` и `/pdf` рутите се заштитени од path traversal (`commonpath` проверка).
- Заштита од злоупотреба: in-memory rate-limit (по IP, sliding-window) на
  `/login` (30/мин), `/pdf` (30/мин), `/api/v1/*` (120/мин) со 429 +
  `Retry-After`; POST барањата со туѓ `Origin`/`Referer` се одбиваат (403);
  import прифаќа само `.csv`. Нема CSRF-токени и rate-limitот е по процес
  (не се дели меѓу gunicorn- workers) — изложувајте на доверлива мрежа
  (VPN/LAN + firewall) додека не се затвори и ова.
- Дневните SQLite backups се конзистентни snapshots. Чувајте и надворешна копија
  од `backup/`, бидејќи локалното задржување е седум дена.
