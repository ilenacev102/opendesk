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
  `X-Frame-Options: DENY`, `nosniff`), `MAX_CONTENT_LENGTH` 25MB, friendly 500
  без истекување детали, RotatingFileHandler за логови.
- `/doc` и `/pdf` рутите се заштитени од path traversal (`commonpath` проверка).
- Заштита од злоупотреба: rate-limit (sliding-window) на
  `/login` (30/мин), `/pdf` (30/мин), `/api/v1/*` (120/мин) со 429 +
  `Retry-After`; backend `memory` default или споделен `file`
  (`SERVICEDESK_RATELIMIT`, `SERVICEDESK_RATELIMIT_FILE`) за повеќе workers.
  POST барањата со туѓ `Origin`/`Referer` се одбиваат (403);
  import прифаќа само `.csv`.
- CSRF: session-токен на секој cookie-authenticated POST (hidden поле
  `_csrf_token` или header `X-CSRF-Token`, `hmac.compare_digest` споредба);
  патеките под `/api/` се изземени (Bearer, не cookie). Може да се исклучи со
  `SERVICEDESK_CSRF=0` (на пример во тест-рези).
- Останато: со `memory` rate-limit backend-от е по процес — за повеќе
  workers користете `file` режим. И натаму изложувајте на доверлива мрежа
  (VPN/LAN + firewall); не е наменето директно на интернет.
- LDAP/AD sync е read-only (никогаш не пишува во директориумот, не чува
  лозинки, не ги деактивира локалните корисници); bind-лозинката е само во
  env (`SERVICEDESK_LDAP_PASSWORD`), синхронизацијата е рачна admin-акција
  (`/users/sync`) со dry-run преглед.
- Postgres-опцијата (`SERVICEDESK_DB_URL`) ја користи истата TEXT-шема и
  partial unique индекси; SQLite останува default за offline LAN.
- PWA скенерот (`/popis/<pid>/scan`) бара камера-дозвола во прелистувачот;
  скенираните кодови се праќаат само на истиот сервер (нема трета страна).
- Email-to-ticket е read-only IMAP poll со рачен trigger (нема daemon);
  лозинката е само во env (`SERVICEDESK_IMAP_PASSWORD`), прилозите од mail
  не се преземаат (само наслов/текст), дупликатите се дедуплицираат по
  Message-ID.
- SSO најавата е OIDC (Entra ID / Google / Keycloak) со Authlib: client secret
  е само во env (`SERVICEDESK_OIDC_CLIENT_SECRET`) и никогаш не влегува во
  логови; callback е `http://127.0.0.1:5000/login/sso/callback` (регистрирајте
  го точно тој URI кај провајдерот); првиот login креира `citac`, улогите не
  се пребришуваат од IdP; локалната најава останува достапна како fallback.
- Прилозите на инциденти се чуваат под `documents/incidents/<id>/` со
  traversal-заштита (`commonpath`) и дозволени екстензии
  (png, jpg, pdf, log, txt); лимит 25MB.
- Дневните SQLite backups се конзистентни snapshots. Чувајте и надворешна копија
  од `backup/`, бидејќи локалното задржување е седум дена.
