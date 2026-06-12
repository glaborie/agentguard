# Deployment

Canonical deployment documentation lives in [docs/deployment/local.md](docs/deployment/local.md).

Use this file as a stable root entrypoint, then follow the detailed guide for:

- local prerequisites and startup sequence
- corpus ingestion and prompt seeding
- Open WebUI + Langfuse verification
- ongoing operations and troubleshooting

Related deployment docs:

- local development: [docs/deployment/local.md](docs/deployment/local.md)
- Google Cloud deployment: [docs/deployment/google-cloud.md](docs/deployment/google-cloud.md)
- container security scan notes: [DOCKER.md](DOCKER.md)

## Compose file naming

Preferred compose naming is:

- `docker-compose.yml` (main stack)
- `docker-compose.infra.yml` (observability and infra)
- `docker-compose.litellm.yml` (LiteLLM-only stack)

Legacy compatibility alias retained:

- `compose-litellm.yml`

Naming and location rules are documented in [docs/repository-conventions.md](docs/repository-conventions.md).
