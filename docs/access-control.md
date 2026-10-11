# Internal identities and API access

Keep `security.auth_required=true` for a shared installation. The existing owner
password/session and configuration API keys remain compatible; both have full
administrative permissions. The explicitly configured local mode
(`auth_required=false` with no configuration API keys) remains a trusted,
anonymous administrator workspace. Creating a scoped key does not turn that
local mode into an authenticated deployment.

The auth SQLite database now also stores named service accounts, token hashes,
revocation/expiry, service browser sessions, and actor audit events. It needs no
external database service. Include the auth database in consistent backups. API
tokens have 256 bits of generated secret entropy; only their SHA-256 hashes are
stored. The token is returned once when issued. Existing keys in configuration
are still managed by configuration and are not migrated into the named-key list.

## Roles and scopes

| Role | Permissions |
| --- | --- |
| owner / admin | All scopes (`*`) |
| operator | ASR/TTS and voices read/write; production read/write; model operations; system diagnostics |
| editor | Production read/write; voices read; TTS read/write; model catalog read |
| reviewer | Production read/review; voices, TTS, ASR, and model catalog read |

A service account may have a subset of its role's scopes. A narrowed admin
account does not receive the wildcard or project administrator bypass. Project
membership and review-state checks are additionally enforced by the production
domain. The voice library remains shared within its domain scopes. Standalone
ASR/TTS jobs are visible only to their actor and administrators; legacy jobs
without an actor are administrator-only. Project TTS jobs additionally require
current project membership, even for the actor who originally queued them.
Retry a project job through its batch or a new take to retain production history.

The scopes are `production:read`, `production:write`, `production:review`,
`tts:read`, `tts:write`, `asr:read`, `asr:write`, `voices:read`, `voices:write`,
`models:read`, `models:manage`, `system:read`, `iam:manage`, and `audit:read`.

## Provision and rotate service keys

Use the Administration screen or the following API sequence with an owner
session or administrative API key. `/docs` describes the typed payloads.

1. `POST /api/v1/auth/service-accounts` with
   `{"name":"render-worker","role":"editor","scopes":["tts:read","tts:write","voices:read"]}`.
2. `POST /api/v1/auth/service-accounts/{principal_id}/keys` with
   `{"name":"nightly-integration","expires_at":"2030-01-01T00:00:00Z"}`.
   Expiry is optional; when supplied it must be a future timestamp with timezone.
3. Store the returned `token` in the integration's secret store and pass
   `X-Vassil-API-Key: <token>` or `Authorization: Bearer <token>`.
4. Rotate by issuing a replacement key, updating the integration, then calling
   `DELETE /api/v1/auth/api-keys/{old_key_id}`. Disable an entire principal with
   `POST /api/v1/auth/service-accounts/{principal_id}/disable`.

Key and account listing never return tokens. A disabled account cannot issue
new keys. Expired, revoked, and disabled credentials fail immediately; explicit
invalid keys do not fall back to a browser owner's cookie or anonymous access.
Legacy query-string credentials remain compatible for existing clients;
integrations should use headers so tokens do not appear in URLs.

## Browser sessions and audit

`POST /api/v1/auth/key-login` with `{"api_key":"<token>"}` exchanges a named key
for a separate HttpOnly, SameSite cookie. The cookie remains linked to its key;
revoking the key or disabling its account invalidates existing browser sessions.
Logout revokes the session. Password changes apply to the owner login only.
`GET /api/v1/auth/principal` exposes the active principal and effective scopes.

Mutating HTTP requests record actor ID, action/path, response status, and request
ID. IAM changes also record structured account/key events. Audit records contain
metadata, not request bodies, audio, passwords, or tokens. Administrators can
page through `GET /api/v1/auth/audit?limit=100&offset=0&actor_id=<id>`.
Audit storage is local application history, not a tamper-proof external log.

`X-Request-ID` is echoed in responses and appears in structured HTTP logs,
audit, and job provenance. API errors include `error`, `message`, and
`request_id`; HTTP and validation errors also retain `detail` for older clients.
OpenAPI declares API-key, bearer, and cookie authentication alternatives plus
WAV/ZIP download content types. ASR transcript exports advertise their text,
subtitle, and JSON formats.
