# Security Policy

## Supported Versions

| Version | Supported |
|---|---|
| main (latest release) | :white_check_mark: |

## Reporting a Vulnerability

Please report potential security vulnerabilities privately via **GitHub Security Advisories** (Private vulnerability reporting).
Do not open public GitHub issues for security vulnerabilities.

---

## Security Architecture & Threat Model

OpenDesk is built with defensive defaults for local networks and corporate environments:

- **Authentication & RBAC:**
  - Session-based authentication via Flask-Login with role-based access control (`admin`, `magacioner`, `citac`).
  - Empty database switches to setup mode until the first administrator is registered via `/setup`.
  - REST API v1 utilizes sha256-hashed Bearer tokens (`/api-tokens`), which can be revoked at any time.
- **Secrets Management:**
  - Zero hardcoded secrets. All credentials (OIDC, Intune, LDAP, SMTP, Webhooks) are ingested strictly via environment variables.
  - Deployment with Docker strictly enforces setting `SERVICEDESK_SECRET`. Local installations generate an isolated key in `.servicedesk_secret` with `0600` permissions.
- **HTTP Hardening:**
  - Strict Content Security Policy (CSP) with per-request random nonces.
  - `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`.
  - Max upload limit enforced at 25MB (`MAX_CONTENT_LENGTH`).
- **Path Traversal Protection:**
  - Document and attachment routes strictly validate target file paths using `os.path.commonpath` to prevent directory traversal attacks.
- **Abuse Prevention & Rate Limiting:**
  - Sliding-window rate-limiting on sensitive endpoints (`/login` 30/min, `/pdf` 30/min, `/api/v1/*` 120/min) returning HTTP 429 with `Retry-After`.
  - Configurable between in-memory and shared file mode (`SERVICEDESK_RATELIMIT=file`) for multi-worker deployments.
  - Cross-Origin POST protection rejecting invalid `Origin`/`Referer` headers with HTTP 403.
- **CSRF Defense:**
  - Session-bound anti-CSRF token on all mutating cookie-authenticated requests using timing-attack safe `hmac.compare_digest`.
- **Integrations Security:**
  - **LDAP/Active Directory:** Strictly read-only query engine. Never modifies the remote directory, never persists passwords, and never deactivates local users.
  - **Intune Graph:** Read-only synchronization using MSAL client credentials. Reconciles data through a staging preview without overwriting assigned assets.
  - **OIDC Single Sign-On:** Uses standard Authlib metadata discovery. Default JIT user provisioning grants read-only (`citac`) role, ensuring privilege elevation remains exclusively with local administrators.
