# Setup Post-Mortem: AgentGuard Docker Stack

## Overview

Getting 9 Docker services (Langfuse v3, LiteLLM, Ollama, Qdrant, PostgreSQL, ClickHouse, Redis, MinIO) to work together on Windows 11 took several rounds of debugging. This document captures every issue encountered and how it was resolved, for anyone attempting a similar self-hosted AI observability stack.

## Issues Encountered

### 1. Windows Port Exclusion Ranges (Redis)

**Symptom:** Redis container failed to bind on port 6379.

**Root cause:** Windows 11 reserves dynamic port ranges for Hyper-V and WSL. The reserved ranges shift unpredictably and can include common service ports like 6379. You can view them with:

```cmd
netsh interface ipv4 show excludedportrange protocol=tcp
```

**Fix:** Remap the host port. Container-internal port stays default:

```yaml
redis:
  ports:
    - "6300:6379"   # host:container
```

**Lesson:** On Windows with Hyper-V/WSL enabled, never assume standard ports are available. Check exclusion ranges first and pick host ports outside them. Container-to-container communication is unaffected since it uses Docker's internal network.

---

### 2. MinIO Endpoint Confusion (Internal vs External)

**Symptom:** Langfuse media uploads failed silently.

**Root cause:** The S3 media upload endpoint was set to `http://localhost:9090` (the host-mapped port). But Langfuse-web runs inside Docker and needs to reach MinIO via the internal Docker network.

**Fix:** All inter-service URLs must use container names and internal ports:

```yaml
LANGFUSE_S3_MEDIA_UPLOAD_ENDPOINT: http://minio:9000    # internal
# NOT: http://localhost:9090                              # host-only
```

**Lesson:** Any URL in a `docker-compose.yml` environment variable that one container uses to talk to another must use `container_name:internal_port`. `localhost` URLs only work for host-to-container access.

---

### 3. LiteLLM Requires a Database (`main-latest` image)

**Symptom:** Every request to LiteLLM returned:
```json
{"error": {"message": "No connected db.", "type": "no_db_connection"}}
```

**Root cause:** The `ghcr.io/berriai/litellm:main-latest` image is the full proxy edition that mandates a PostgreSQL database for API key management, spend tracking, and rate limiting. There is no config flag that fully disables this — `STORE_MODEL_IN_DB=false` and `DISABLE_SPEND_LOGS=true` are insufficient.

**Fix:** Give LiteLLM its own database. We reused the existing Postgres instance with a separate database:

```yaml
litellm:
  image: ghcr.io/berriai/litellm:main-latest
  environment:
    DATABASE_URL: postgresql://postgres:${POSTGRES_PASSWORD:-postgres}@postgres:5432/litellm
```

The `litellm` database must be created first (Prisma migrations run automatically on boot):

```bash
docker compose exec postgres psql -U postgres -c "CREATE DATABASE litellm;"
```

**Lesson:** LiteLLM's `main-latest` tag is the database-backed enterprise proxy. There is no lightweight "config-only" image in current releases. Budget ~30 seconds for Prisma migrations on each container start.

---

### 4. LiteLLM Master Key Not Recognized After DB Migration

**Symptom:** After connecting the database, health checks returned:
```json
{"error": {"message": "Invalid proxy server token passed", "type": "token_not_found_in_db"}}
```

**Root cause:** When a database is connected, LiteLLM validates the master key against a token table. On first boot, it registers the key from config. But if the config used an environment variable reference (`${LITELLM_MASTER_KEY:-sk-litellm-dev-key}`), the token hash stored in the DB could mismatch on subsequent boots due to variable resolution differences.

**Fix:** Use a literal string in `litellm_config.yaml`, not an env var reference:

```yaml
general_settings:
  master_key: sk-litellm-dev-key     # literal, not ${LITELLM_MASTER_KEY}
```

If the DB already has a stale token, drop and recreate it:

```bash
docker compose stop litellm
docker compose exec postgres psql -U postgres -c "DROP DATABASE litellm;"
docker compose exec postgres psql -U postgres -c "CREATE DATABASE litellm;"
docker compose up -d litellm
```

**Lesson:** With DB-backed LiteLLM, the master key is a one-time registration. Changing it later requires wiping the token table or the entire database. Keep it as a literal in the config file to avoid resolution surprises.

---

### 5. LiteLLM Health Endpoint Requires Authentication

**Symptom:** `curl http://localhost:4000/health` returned 401 Unauthorized.

**Root cause:** Unlike many proxies, LiteLLM's `/health` endpoint requires the master key in the Authorization header.

**Fix:** Always include the auth header:

```bash
curl -H "Authorization: Bearer sk-litellm-dev-key" http://localhost:4000/health
```

**Lesson:** Don't add a Docker healthcheck for LiteLLM using a bare `curl /health` — it will always fail. Either use `/health/liveliness` (which may not require auth in some versions) or include the bearer token in the healthcheck command.

---

### 6. Ollama `encoding_format: base64` Not Supported

**Symptom:** Embedding calls through LiteLLM failed with:
```
Setting {'encoding_format': 'base64'} is not supported by ollama
```

**Root cause:** LangChain's `OpenAIEmbeddings` sends `encoding_format: base64` by default (an OpenAI-specific optimization). Ollama doesn't support this parameter and LiteLLM's strict mode rejects it.

**Fix:** Add `drop_params: true` to the LiteLLM config:

```yaml
litellm_settings:
  drop_params: true
```

This tells LiteLLM to silently strip parameters that the backend provider doesn't support, rather than rejecting the request.

**Lesson:** When using LiteLLM as a proxy between OpenAI-compatible clients and non-OpenAI backends (Ollama, vLLM, etc.), always enable `drop_params`. The OpenAI SDK and LangChain send parameters that only OpenAI supports.

---

### 7. Ollama Models Must Be Pulled Manually

**Symptom:** LiteLLM health check showed all Ollama models as "not found."

**Root cause:** The Ollama Docker image starts with zero models. Unlike the standalone Ollama install, there's no model persistence across `docker compose down` unless a volume is mounted (which we do have, but the initial pull is still needed).

**Fix:** After first `docker compose up`:

```bash
docker compose exec ollama ollama pull llama3.2
docker compose exec ollama ollama pull nomic-embed-text
```

The `ollama_data` volume persists models across restarts. They only need to be pulled once unless the volume is deleted.

**Lesson:** Consider adding an init container or startup script that auto-pulls required models. For now, document the manual step clearly.

---

### 8. Langfuse Python SDK v4 Breaking Changes

**Symptom:** `from langfuse.callback import CallbackHandler` raised `ModuleNotFoundError`.

**Root cause:** Langfuse SDK v4 (4.6.x) restructured the module layout. The callback handler moved from `langfuse.callback` to `langfuse.langchain`.

Additionally, the `CallbackHandler` constructor signature changed dramatically:
- v2/v3: `CallbackHandler(public_key=..., secret_key=..., host=..., session_id=..., user_id=...)`
- v4: `CallbackHandler(public_key=..., trace_context=...)` — requires a pre-initialized `Langfuse` client singleton

**Fix:**

```python
# Initialize client at module level (registers with internal registry)
from langfuse import Langfuse
_langfuse = Langfuse(
    public_key=settings.langfuse_public_key,
    secret_key=settings.langfuse_secret_key,
    base_url=settings.langfuse_base_url,
)

# Handler looks up client by public_key from registry
from langfuse.langchain import CallbackHandler
handler = CallbackHandler(public_key=settings.langfuse_public_key)
```

**Lesson:** Pin major versions in `requirements.txt` (`langfuse>=2.0,<5.0`) or expect breaking changes. The v4 SDK moved to OpenTelemetry-based tracing internally, which changed the entire callback interface.

---

### 9. MinIO S3 Credentials Not Passed to Langfuse

**Symptom:** Python SDK reported `Transient error Internal Server Error encountered while exporting span batch`. Langfuse-web logs showed `Failed to upload JSON to S3` and `Could not load credentials from any providers`.

**Root cause:** The docker-compose configured `LANGFUSE_S3_EVENT_UPLOAD_BUCKET`, `_ENDPOINT`, `_REGION`, etc., but omitted the access key credentials (`_ACCESS_KEY_ID` and `_SECRET_ACCESS_KEY`). Without explicit credentials, the AWS SDK inside Langfuse tried instance metadata, environment credentials chain, and config files — all of which fail in a Docker container with no AWS setup.

**Fix:** Add the MinIO credentials to the Langfuse environment block, referencing the same `.env` vars used by the MinIO container:

```yaml
LANGFUSE_S3_EVENT_UPLOAD_ACCESS_KEY_ID: ${MINIO_ROOT_USER}
LANGFUSE_S3_EVENT_UPLOAD_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}
LANGFUSE_S3_MEDIA_UPLOAD_ACCESS_KEY_ID: ${MINIO_ROOT_USER}
LANGFUSE_S3_MEDIA_UPLOAD_SECRET_ACCESS_KEY: ${MINIO_ROOT_PASSWORD}
```

**Lesson:** When configuring S3-compatible storage for Langfuse, the access key and secret are required alongside bucket/endpoint/region. The Langfuse docs show all six env vars together, but it's easy to miss the credentials when copying from examples that assume IAM roles.

---

### 10. MinIO Bucket Not Created on First Boot

**Symptom:** Even with correct credentials, Langfuse S3 uploads failed because the `langfuse` bucket didn't exist.

**Root cause:** MinIO starts with zero buckets. The Langfuse S3 config references a `langfuse` bucket, but nothing creates it.

**Fix:** Added a `minio-init` container that runs after MinIO is healthy and creates the bucket:

```yaml
minio-init:
  image: quay.io/minio/mc:latest
  restart: on-failure
  depends_on:
    minio:
      condition: service_healthy
  entrypoint: >
    /bin/sh -c "
    mc alias set local http://minio:9000 $${MINIO_ROOT_USER} $${MINIO_ROOT_PASSWORD};
    mc mb --ignore-existing local/langfuse;
    "
```

**Lesson:** Always pair MinIO with a bucket init step. The `--ignore-existing` flag makes it idempotent across restarts.

---

### 11. Redis Password Mismatch

**Symptom:** Langfuse worker logs spammed `ERR AUTH <password> called without any password configured for the default user`.

**Root cause:** The `.env` file set `REDIS_PASSWORD=redissecret`, which got loaded into the Langfuse containers via `env_file:`. The Langfuse SDK tried to authenticate with this password, but the Redis container was started without `--requirepass` and had no password configured.

**Fix:** Two changes:
1. Configure Redis to require the password: `--requirepass ${REDIS_PASSWORD:-redissecret}` in the Redis command.
2. Add `REDIS_AUTH: ${REDIS_PASSWORD:-redissecret}` to the Langfuse environment block (the env var Langfuse uses for Redis authentication).

**Lesson:** When using `env_file:` in docker-compose, any `REDIS_PASSWORD` variable gets injected into all containers that reference that file. If a service SDK auto-detects and uses that variable for auth, the actual Redis server must be configured to expect it. Either remove the variable from `.env` or configure Redis to match.

---

## Startup Order Dependencies

The correct dependency chain for this stack:

```
postgres (healthcheck: pg_isready)
  ├── langfuse-web (also needs clickhouse, redis, minio)
  ├── langfuse-worker (same deps as web)
  └── litellm (needs postgres for its own DB)

clickhouse (healthcheck: wget /ping)
  └── langfuse-web, langfuse-worker

redis (healthcheck: redis-cli ping)
  └── langfuse-web, langfuse-worker

minio (healthcheck: curl /minio/health/live)
  ├── langfuse-web, langfuse-worker
  └── minio-init (creates langfuse bucket, runs once)

ollama (no healthcheck, slow to start)
  └── litellm (condition: service_started, not service_healthy)

qdrant (no upstream deps)
```

LiteLLM depends on Ollama with `service_started` (not `service_healthy`) because Ollama has no built-in healthcheck and starts accepting connections before models are loaded.

## Final Working Configuration Summary

| Component | Key Setting | Why |
|---|---|---|
| Redis port | `6300:6379` | Windows port exclusion |
| MinIO endpoints | `http://minio:9000` | Internal Docker networking |
| LiteLLM image | `main-latest` + `DATABASE_URL` | DB is mandatory |
| LiteLLM master key | Literal in YAML, not env var | DB token hash must be stable |
| LiteLLM params | `drop_params: true` | Ollama rejects OpenAI-only params |
| Langfuse SDK | `langfuse.langchain.CallbackHandler` | v4 module path |
| Langfuse client | Module-level singleton | Handler looks up by public_key |
| Ollama models | Manual pull after first boot | No auto-pull in Docker image |
| MinIO S3 credentials | `LANGFUSE_S3_*_ACCESS_KEY_ID/SECRET_ACCESS_KEY` | AWS SDK needs explicit creds in Docker |
| MinIO bucket | `minio-init` container creates `langfuse` bucket | MinIO starts empty, Langfuse expects bucket |
| Redis auth | `--requirepass` + `REDIS_AUTH` in Langfuse env | `env_file` leaks `REDIS_PASSWORD` to all containers |

## Time Spent

Roughly 60% of setup time was spent on LiteLLM alone (database requirement, auth, param compatibility). The remaining issues (port conflicts, SDK changes) were quick to diagnose once the error messages were clear. For future projects, consider whether LiteLLM's proxy features justify the complexity — for a single-backend setup (Ollama only), calling Ollama directly would eliminate an entire service and its database.
