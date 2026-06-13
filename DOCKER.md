# Docker Scout

## Scan a specific image
docker compose -f docker-compose.infra.yml --profile tools run --rm scout cves grafana/grafana:11.1.0

## Scan a locally-built image
docker compose -f docker-compose.infra.yml --profile tools run --rm scout cves local://langfuse_poc-rag-api

The local:// prefix tells Scout to read from the Docker daemon instead of pulling from a registry.