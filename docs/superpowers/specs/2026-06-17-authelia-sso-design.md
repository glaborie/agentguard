# Authelia SSO — Design

## Goal

Single sign-on portal in front of every Traefik-routed service in AgentGuard's main stack. One login gates openwebui, langfuse, litellm, rag-api, grafana, jaeger, zipkin, loki, and the Traefik dashboard.

## Scope decisions

- **Coverage:** all existing Traefik routers get the ForwardAuth middleware. No service is left open.
- **Auth backend:** file-based (`users_database.yml`, bcrypt-hashed passwords). No LDAP service added.
- **2FA:** disabled. `one_factor` policy only — dev/local stack, not internet-facing.
- **Session store:** existing Redis container (already password-protected via `REDIS_PASSWORD`).
- **Notifier:** filesystem notifier — writes notification emails to a local file, no SMTP.
- **Cookie/portal domain:** `localhost`. Portal served at `auth.localhost`. All protected services are `*.localhost` subdomains already, so a single cookie domain covers them.

## Components

### 1. Authelia service (`docker-compose.yml`)

```yaml
authelia:
  image: authelia/authelia:4
  restart: always
  volumes:
    - ./authelia/configuration.yml:/config/configuration.yml:ro
    - ./authelia/users_database.yml:/config/users_database.yml:ro
    - authelia_data:/config/data
  environment:
    AUTHELIA_JWT_SECRET: ${AUTHELIA_JWT_SECRET}
    AUTHELIA_SESSION_SECRET: ${AUTHELIA_SESSION_SECRET}
    AUTHELIA_STORAGE_ENCRYPTION_KEY: ${AUTHELIA_STORAGE_ENCRYPTION_KEY}
  networks:
    - langfuse
```

New volume `authelia_data` for SQLite storage backend (regulation/registration metadata — not session state, that's Redis).

### 2. Config files

- `authelia/configuration.yml` — checked in. Defines: `access_control` (default deny, `one_factor` policy on `*.localhost`), `session` (Redis backend, `domain: localhost`, cookie name `authelia_session`), `storage` (SQLite local file), `notifier` (filesystem, `/config/data/notification.txt`), `authentication_backend` (file, points at `users_database.yml`).
- `authelia/users_database.yml` — gitignored (real password hashes). `authelia/users_database.yml.example` checked in with a placeholder user and instructions to generate hashes via `docker run authelia/authelia:4 authelia crypto hash generate bcrypt --password 'yourpassword'`.

### 3. Secrets (`.env` / `.env.example`)

Three new vars: `AUTHELIA_JWT_SECRET`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY` (random 32+ char strings, generated once, gitignored in `.env`).

### 4. Traefik wiring (`traefik-routes.yml`)

- New router/service entry for `authelia` itself: `Host(\`auth.localhost\`)` → `http://authelia:9091`.
- New middleware:
  ```yaml
  middlewares:
    authelia:
      forwardAuth:
        address: "http://authelia:9091/api/verify?rd=http://auth.localhost/"
        trustForwardHeader: true
        authResponseHeaders:
          - Remote-User
          - Remote-Groups
          - Remote-Name
          - Remote-Email
  ```
- Every existing router (`openwebui`, `langfuse`, `litellm`, `rag-api`, `grafana`, `jaeger`, `zipkin`, `loki`, `traefik`) gets `middlewares: [authelia]` added.

## Data flow

1. Browser hits e.g. `http://grafana.localhost/` → Traefik router has `authelia` ForwardAuth middleware → Traefik calls `authelia:9091/api/verify`.
2. No session cookie → Authelia returns 302 to `auth.localhost` login portal.
3. User logs in (file backend, bcrypt check, one_factor) → Authelia sets session cookie (domain `localhost`, stored in Redis) → redirects back to original URL.
4. Subsequent requests to any `*.localhost` service carry the cookie → ForwardAuth call succeeds immediately, request proceeds to backend service with `Remote-User` header injected.

## Error handling

- Authelia unreachable → Traefik ForwardAuth fails closed (503), no service reachable without auth — acceptable for this stack since Authelia is a hard dependency once wired in.
- Bad/missing secrets → Authelia container fails health check at startup with clear log error (config validation).

## Testing

- Manual: `docker compose up authelia`, hit `http://openwebui.localhost/` unauthenticated → expect redirect to `auth.localhost`; log in with example user → expect redirect back and access granted.
- Verify Traefik dashboard (`traefik.localhost`) is also gated — easy to forget since it was previously open via `--api.insecure=true`.
- No automated test added — this is infra/compose config, consistent with how Traefik/Jaeger/other infra services in this repo are untested.

## Out of scope

- LDAP, TOTP/2FA, SMTP notifications, per-service authorization rules (groups/roles) beyond default `one_factor` — all noted as possible follow-ups, not built now.
