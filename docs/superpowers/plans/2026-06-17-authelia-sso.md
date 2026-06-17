# Authelia SSO Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Authelia as a ForwardAuth SSO portal in front of every Traefik-routed service in the main stack (`docker-compose.yml` + `traefik-routes.yml`).

**Architecture:** Authelia runs as a new container on the `langfuse` network, file-based user backend, session store in the existing Redis container, SQLite for its own storage backend, filesystem notifier. Traefik gets a `forwardAuth` middleware pointed at Authelia's `/api/verify` endpoint, attached to every existing router.

**Tech Stack:** `authelia/authelia:4` Docker image, existing Redis 7 container, existing Traefik v3.7.5.

## Global Constraints

- Cookie/session domain: `localhost` (every protected service is a `*.localhost` subdomain).
- Portal hostname: `auth.localhost`.
- Policy: `one_factor` only — no TOTP/2FA.
- Auth backend: file (`authelia/users_database.yml`), bcrypt hashes.
- `authelia/users_database.yml` is gitignored (real secrets); `authelia/users_database.yml.example` is checked in.
- Notifier: filesystem, writes to `/config/data/notification.txt` inside the container.
- New env vars `AUTHELIA_JWT_SECRET`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY` go in `.env` (gitignored) and `.env.example` (placeholder values, checked in).
- Authelia image pinned to `authelia/authelia:4.37.5` — newer 4.38+ images reject `session.domain: localhost` at startup (validation requires a period or IP in the domain; bare `localhost` fails). 4.37.5 is the last release accepting it, needed to keep every existing `*.localhost` route unchanged. Found during Task 2 implementation; documented here for anyone re-deriving the plan.
- Spec: `docs/superpowers/specs/2026-06-17-authelia-sso-design.md`

---

### Task 1: Authelia config files + secrets

**Files:**
- Create: `authelia/configuration.yml`
- Create: `authelia/users_database.yml.example`
- Modify: `.gitignore` — add `authelia/users_database.yml`
- Modify: `.env.example` — add 3 new vars
- Create: `.env` entries (local only, not committed) — same 3 vars with real generated values

**Interfaces:**
- Produces: `authelia/configuration.yml` referencing `users_database.yml` and Redis host `redis`/port `6379` (no password inline — Redis password supplied at container-start time in Task 2 via the `AUTHELIA_SESSION_REDIS_PASSWORD` env var, which Authelia auto-maps onto `session.redis.password` per its documented `AUTHELIA_<dotted.path>` env-mapping convention). Keeps the real secret out of the checked-in YAML.

- [ ] **Step 1: Create `authelia/configuration.yml`**

```yaml
theme: light

server:
  host: 0.0.0.0
  port: 9091

log:
  level: info

totp:
  disable: true

authentication_backend:
  file:
    path: /config/users_database.yml
    password:
      algorithm: bcrypt
      bcrypt:
        cost: 12

access_control:
  default_policy: one_factor

session:
  name: authelia_session
  domain: localhost
  same_site: lax
  expiration: 1h
  inactivity: 15m
  redis:
    host: redis
    port: 6379

storage:
  local:
    path: /config/data/db.sqlite3

notifier:
  filesystem:
    filename: /config/data/notification.txt
```

- [ ] **Step 2: Create `authelia/users_database.yml.example`**

```yaml
# Copy to authelia/users_database.yml and replace the hash.
# Generate a hash with:
#   docker run --rm authelia/authelia:4 authelia crypto hash generate bcrypt --password 'yourpassword'
users:
  admin:
    displayname: "Admin"
    password: "$2a$12$REPLACE_WITH_GENERATED_HASH"
    email: admin@localhost
    groups:
      - admins
```

- [ ] **Step 3: Add gitignore entry**

In `.gitignore`, add a new line under the existing `.env` line:

```
authelia/users_database.yml
```

- [ ] **Step 4: Add secrets to `.env.example`**

Append to `.env.example`:

```
# Authelia SSO
AUTHELIA_JWT_SECRET=changeme_jwt_secret_min_32_chars
AUTHELIA_SESSION_SECRET=changeme_session_secret_min_32_chars
AUTHELIA_STORAGE_ENCRYPTION_KEY=changeme_storage_key_min_32_chars
```

- [ ] **Step 5: Generate real secrets into local `.env`**

Run (do not commit output anywhere — `.env` is gitignored):

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(32))"
```

Run it 3 times, append to `.env`:

```
AUTHELIA_JWT_SECRET=<output1>
AUTHELIA_SESSION_SECRET=<output2>
AUTHELIA_STORAGE_ENCRYPTION_KEY=<output3>
```

- [ ] **Step 6: Create real `users_database.yml` for local testing**

```bash
docker run --rm authelia/authelia:4 authelia crypto hash generate bcrypt --password 'testpassword123'
```

Copy `authelia/users_database.yml.example` to `authelia/users_database.yml`, paste the generated hash in place of the placeholder.

- [ ] **Step 7: Verify gitignore works**

```bash
git status --porcelain authelia/
```

Expected: only `authelia/configuration.yml` and `authelia/users_database.yml.example` show as untracked (new files); `authelia/users_database.yml` must NOT appear.

- [ ] **Step 8: Commit**

```bash
git add authelia/configuration.yml authelia/users_database.yml.example .gitignore .env.example
git commit -m "feat(sso): add Authelia config and secrets scaffolding"
```

---

### Task 2: Authelia service in docker-compose.yml

**Files:**
- Modify: `docker-compose.yml` — add `authelia` service after `traefik` (around line 608), add `authelia_data` volume

**Interfaces:**
- Consumes: `authelia/configuration.yml`, `authelia/users_database.yml` from Task 1; `${AUTHELIA_JWT_SECRET}`, `${AUTHELIA_SESSION_SECRET}`, `${AUTHELIA_STORAGE_ENCRYPTION_KEY}`, `${REDIS_PASSWORD}` from `.env`
- Produces: container reachable at `http://authelia:9091` on the `langfuse` network for Task 3 to wire into Traefik

- [ ] **Step 1: Add the service block**

In `docker-compose.yml`, insert after the `traefik` service block (after line 608, before the blank line preceding `volumes:`):

```yaml
  authelia:
    image: authelia/authelia:4.37.5
    restart: always
    logging: *default-logging
    volumes:
      - ./authelia/configuration.yml:/config/configuration.yml:ro
      - ./authelia/users_database.yml:/config/users_database.yml:ro
      - authelia_data:/config/data
    environment:
      TZ: UTC
      AUTHELIA_JWT_SECRET: ${AUTHELIA_JWT_SECRET}
      AUTHELIA_SESSION_SECRET: ${AUTHELIA_SESSION_SECRET}
      AUTHELIA_SESSION_REDIS_PASSWORD: ${REDIS_PASSWORD}
      AUTHELIA_STORAGE_ENCRYPTION_KEY: ${AUTHELIA_STORAGE_ENCRYPTION_KEY}
    healthcheck:
      test: ["CMD", "wget", "--no-verbose", "--tries=1", "--spider", "http://localhost:9091/api/health"]
      interval: 10s
      timeout: 5s
      retries: 6
      start_period: 10s
    depends_on:
      redis:
        condition: service_healthy
    networks:
      - langfuse
```

- [ ] **Step 2: Add the volume**

In the top-level `volumes:` section (around line 610-619), add:

```yaml
  authelia_data:
```

- [ ] **Step 3: Validate compose file**

```bash
docker compose config --quiet
```

Expected: no output, exit code 0.

- [ ] **Step 4: Start Authelia alone and check health**

```bash
docker compose up -d authelia
docker compose ps authelia
```

Expected: `STATUS` column shows `healthy` within ~30s. If it shows `unhealthy` or restarting, run `docker compose logs authelia` and fix config before proceeding.

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml
git commit -m "feat(sso): add Authelia service to main stack"
```

---

### Task 3: Traefik ForwardAuth wiring

**Files:**
- Modify: `traefik-routes.yml` — add `authelia` router/service, add `authelia` middleware, attach middleware to all 9 existing routers

**Interfaces:**
- Consumes: `http://authelia:9091` from Task 2
- Produces: every `*.localhost` route gated behind Authelia login

- [x] **Step 1: Add the `authelia` router and service**

In `traefik-routes.yml`, under `http.routers`, add:

```yaml
    authelia:
      rule: "Host(`auth.localhost`)"
      service: authelia
      entryPoints: [web]
```

Under `http.services`, add:

```yaml
    authelia:
      loadBalancer:
        servers:
          - url: "http://authelia:9091"
```

- [x] **Step 2: Add the `authelia` forwardAuth middleware**

Add a new top-level key under `http:` (sibling of `routers` and `services`):

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

- [x] **Step 3: Attach the middleware to all 9 existing routers**

For each of `openwebui`, `langfuse`, `litellm`, `rag-api`, `grafana`, `jaeger`, `zipkin`, `loki`, `traefik` under `http.routers`, add a `middlewares` key. Example for `openwebui`:

```yaml
    openwebui:
      rule: "Host(`openwebui.localhost`)"
      service: openwebui
      entryPoints: [web]
      middlewares: [authelia]
```

Repeat the same `middlewares: [authelia]` line for the other 8 routers (`langfuse`, `litellm`, `rag-api`, `grafana`, `jaeger`, `zipkin`, `loki`, `traefik`). Do NOT add it to the new `authelia` router itself — that would create a redirect loop.

- [x] **Step 4: Reload Traefik and verify config loaded without error**

```bash
docker compose up -d --force-recreate traefik
docker compose logs traefik --tail=60
```

Note: `docker compose restart traefik` failed in this WSL2 environment with a Docker
Desktop bind-mount error unmounting `/etc/traefik/routes.yml` (known WSL2 bind-mount
flakiness, unrelated to the routes config). `docker compose up -d --force-recreate traefik`
worked around it. Verified: no `error` level log lines about `routes.yml` or middleware
parsing — only informational `maxResponseBodySize not configured` warnings for the new
`authelia@file` ForwardAuth middleware on all 9 routers.

- [x] **Step 5: Verify gating end-to-end**

```bash
curl -s -o /dev/null -w "%{http_code}\n" --resolve auth.localhost:80:127.0.0.1 http://auth.localhost/
curl -s -i --resolve openwebui.localhost:80:127.0.0.1 http://openwebui.localhost/
```

Actual: `auth.localhost` → `200`. All 9 gated routers (`openwebui`, `langfuse`, `litellm`,
`rag-api`, `grafana`, `jaeger`, `zipkin`, `loki`, `traefik`) → `401 Unauthorized` from
Authelia's `/api/verify`, confirming the request never reaches the upstream service.
Deviates from the plan's expected `302` — Authelia 4.37.5's `/api/verify` returns `401`
for this request shape rather than redirecting; this is still correct, secure gating
behavior (access denied pre-auth). A real browser (Step 6) is expected to receive the
`302` redirect to `auth.localhost` since it negotiates `Accept: text/html` differently
than curl's default and Authelia's redirect logic is browser-navigation-aware.

- [ ] **Step 6: Manual browser login check**

Open `http://openwebui.localhost/` in a browser. Expect redirect to Authelia login at `auth.localhost`. Log in with `admin` / `testpassword123` (from Task 1 Step 6). Expect redirect back to `openwebui.localhost` with the app loading. Then open `http://grafana.localhost/` in the same browser — expect it to load without a second login (session cookie shared across `*.localhost`).

**Not verifiable from this non-interactive shell session — requires a human with a browser. Flagging for manual follow-up.**

- [x] **Step 7: Commit**

```bash
git add traefik-routes.yml
git commit -m "feat(sso): gate all Traefik routes behind Authelia ForwardAuth"
```

Committed as `6ee2f29`.

---

### Task 4: Documentation

**Files:**
- Modify: `CLAUDE.md` — add an "Authelia SSO" subsection under "Architecture decisions"

**Interfaces:**
- Consumes: nothing new
- Produces: documented operational knowledge (how to add users, where secrets live) for future sessions

- [ ] **Step 1: Add architecture-decisions entry**

In `CLAUDE.md`, after the existing `**OpenObserve observability.**` paragraph (end of the Architecture decisions section), add:

```markdown
**Authelia SSO.** `authelia` service (image `authelia/authelia:4`) gates every Traefik route via ForwardAuth — `traefik-routes.yml` defines an `authelia` middleware (`forwardAuth` → `http://authelia:9091/api/verify`) attached to all 9 routers. File-based auth backend (`authelia/users_database.yml`, gitignored — copy from `authelia/users_database.yml.example` and generate bcrypt hashes via `docker run --rm authelia/authelia:4 authelia crypto hash generate bcrypt --password 'x'`). `one_factor` only, no TOTP. Session store is the existing Redis container (`AUTHELIA_SESSION_REDIS_PASSWORD` env var maps to Authelia's `session.redis.password` config key via its auto env-mapping convention); session cookie domain `localhost` covers all `*.localhost` services with one login. Portal at `http://auth.localhost/`. Notifier writes to a local file (`/config/data/notification.txt` in container) — no SMTP configured. Secrets (`AUTHELIA_JWT_SECRET`, `AUTHELIA_SESSION_SECRET`, `AUTHELIA_STORAGE_ENCRYPTION_KEY`) live in `.env` only.
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: document Authelia SSO architecture"
```
