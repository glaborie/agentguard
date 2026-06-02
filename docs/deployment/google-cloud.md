# Deploying AgentGuard on Google Cloud

This guide covers a production-grade deployment of AgentGuard on GCP using
Cloud Run for stateless services and managed infrastructure for stateful ones.

## Architecture overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Google Cloud                             │
│                                                                 │
│  Cloud Run (stateless)        Managed services (stateful)       │
│  ─────────────────────        ───────────────────────────────   │
│  agentguard-api               Cloud SQL (PostgreSQL 17)         │
│  agentguard-worker            Memorystore (Redis 7)             │
│  litellm                      Cloud Storage (MinIO replacement) │
│  langfuse-web                 Qdrant VM  ← GCE e2-standard-4   │
│  langfuse-worker              ClickHouse VM ← GCE e2-standard-4 │
│  otel-collector               Artifact Registry (images)        │
│                                                                 │
│  VPC: agentguard-vpc          Secret Manager (all secrets)      │
│  Subnet: 10.0.0.0/24          Cloud Logging (replaces Dozzle)   │
└─────────────────────────────────────────────────────────────────┘
```

### Service mapping

| Local (docker-compose) | GCP equivalent | Notes |
|---|---|---|
| agentguard-api | Cloud Run | Stateless FastAPI |
| agentguard-worker | Cloud Run (min-instances=1) | Needs persistent polling |
| litellm | Cloud Run | Stateless proxy |
| langfuse-web | Cloud Run | Stateless web |
| langfuse-worker | Cloud Run (min-instances=1) | BullMQ consumer |
| postgres | Cloud SQL (PostgreSQL 17) | Managed, HA |
| redis | Memorystore (Redis 7) | Managed, HA |
| minio | Cloud Storage + S3-compat API | GCS bucket |
| qdrant | GCE VM (e2-standard-4, 50 GB SSD) | No managed GCP option |
| clickhouse | GCE VM (e2-standard-4, 100 GB SSD) | Langfuse analytics store |
| ollama | Skip — use OpenRouter or Vertex AI | GPU VMs are expensive |
| otel-collector | Cloud Run | Stateless collector |
| portainer / dozzle | Skip — use Cloud Logging + GKE console | |
| jaeger | Skip or replace with Cloud Trace | |
| open-webui | Optional Cloud Run deployment | |

## Prerequisites

```bash
# Install and authenticate
gcloud auth login
gcloud auth configure-docker us-central1-docker.pkg.dev

# Set project and region
export PROJECT_ID=your-project-id
export REGION=us-central1
export ZONE=us-central1-a

gcloud config set project $PROJECT_ID
gcloud config set compute/region $REGION
```

Enable required APIs:

```bash
gcloud services enable \
  run.googleapis.com \
  sql-component.googleapis.com \
  sqladmin.googleapis.com \
  redis.googleapis.com \
  compute.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com \
  storage.googleapis.com \
  cloudtrace.googleapis.com \
  logging.googleapis.com
```

## Step 1 — VPC and networking

```bash
gcloud compute networks create agentguard-vpc --subnet-mode=custom

gcloud compute networks subnets create agentguard-subnet \
  --network=agentguard-vpc \
  --range=10.0.0.0/24 \
  --region=$REGION

# Allow internal traffic
gcloud compute firewall-rules create agentguard-internal \
  --network=agentguard-vpc \
  --allow=tcp,udp,icmp \
  --source-ranges=10.0.0.0/24

# Serverless VPC connector (Cloud Run → VPC)
gcloud compute networks vpc-access connectors create agentguard-connector \
  --network=agentguard-vpc \
  --region=$REGION \
  --range=10.8.0.0/28
```

## Step 2 — Managed stateful services

### Cloud SQL (PostgreSQL)

```bash
gcloud sql instances create agentguard-pg \
  --database-version=POSTGRES_17 \
  --tier=db-g1-small \
  --region=$REGION \
  --network=agentguard-vpc \
  --no-assign-ip

gcloud sql databases create langfuse --instance=agentguard-pg
gcloud sql databases create litellm  --instance=agentguard-pg

# Create users
gcloud sql users create langfuse --instance=agentguard-pg --password=$(openssl rand -hex 16)
gcloud sql users create litellm  --instance=agentguard-pg --password=$(openssl rand -hex 16)
```

### Memorystore (Redis)

```bash
gcloud redis instances create agentguard-redis \
  --size=1 \
  --region=$REGION \
  --network=agentguard-vpc \
  --redis-version=redis_7_0 \
  --auth-enabled
```

### Cloud Storage (replaces MinIO)

```bash
gcloud storage buckets create gs://${PROJECT_ID}-langfuse \
  --location=$REGION \
  --uniform-bucket-level-access

# Service account for Langfuse to access GCS
gcloud iam service-accounts create langfuse-gcs \
  --display-name="Langfuse GCS access"

gcloud storage buckets add-iam-policy-binding gs://${PROJECT_ID}-langfuse \
  --member=serviceAccount:langfuse-gcs@${PROJECT_ID}.iam.gserviceaccount.com \
  --role=roles/storage.objectAdmin
```

> **Note:** Langfuse expects an S3-compatible API. Use the GCS S3-interop endpoint:
> `https://storage.googleapis.com` with HMAC keys as `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`.
> Generate HMAC keys in the GCS console under *Settings → Interoperability*.

## Step 3 — Stateful VMs (Qdrant and ClickHouse)

Qdrant and ClickHouse have no GCP managed equivalents — they run on GCE VMs with
persistent SSD disks attached.

### Qdrant VM

```bash
gcloud compute instances create agentguard-qdrant \
  --zone=$ZONE \
  --machine-type=e2-standard-4 \
  --network=agentguard-vpc \
  --subnet=agentguard-subnet \
  --no-address \
  --boot-disk-size=50GB \
  --boot-disk-type=pd-ssd \
  --metadata=startup-script='#!/bin/bash
    apt-get update -q
    curl -fsSL https://qdrant.tech/installation.sh | bash
    systemctl enable qdrant --now'
```

Qdrant listens on port `6333` (HTTP). Cloud Run services reach it via the VPC connector
at the VM's internal IP (`10.0.0.x:6333`).

### ClickHouse VM

```bash
gcloud compute instances create agentguard-clickhouse \
  --zone=$ZONE \
  --machine-type=e2-standard-4 \
  --network=agentguard-vpc \
  --subnet=agentguard-subnet \
  --no-address \
  --boot-disk-size=100GB \
  --boot-disk-type=pd-ssd \
  --metadata=startup-script='#!/bin/bash
    apt-get update -q
    apt-get install -y clickhouse-server clickhouse-client
    systemctl enable clickhouse-server --now'
```

## Step 4 — Artifact Registry and image build

```bash
gcloud artifacts repositories create agentguard \
  --repository-format=docker \
  --location=$REGION

# Build and push AgentGuard API image
docker build -t ${REGION}-docker.pkg.dev/${PROJECT_ID}/agentguard/api:latest .
docker push ${REGION}-docker.pkg.dev/${PROJECT_ID}/agentguard/api:latest
```

## Step 5 — Secret Manager

Store all secrets before deploying Cloud Run services:

```bash
# Helper: create or update a secret
_secret() { echo -n "$2" | gcloud secrets create "$1" --data-file=- 2>/dev/null \
            || echo -n "$2" | gcloud secrets versions add "$1" --data-file=-; }

_secret LANGFUSE_SECRET_KEY      "$(openssl rand -hex 32)"
_secret LANGFUSE_SALT            "$(openssl rand -hex 32)"
_secret LANGFUSE_NEXTAUTH_SECRET "$(openssl rand -hex 32)"
_secret LITELLM_MASTER_KEY       "sk-litellm-$(openssl rand -hex 16)"
_secret OPENROUTER_API_KEY       "your-openrouter-key"
_secret POSTGRES_PASSWORD_LANGFUSE "$(openssl rand -hex 16)"
_secret POSTGRES_PASSWORD_LITELLM  "$(openssl rand -hex 16)"
_secret REDIS_PASSWORD           "$(openssl rand -hex 16)"
```

## Step 6 — Cloud Run deployments

### Service account

```bash
gcloud iam service-accounts create agentguard-run \
  --display-name="AgentGuard Cloud Run"

# Grant secret access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:agentguard-run@${PROJECT_ID}.iam.gserviceaccount.com \
  --role=roles/secretmanager.secretAccessor

# Grant Cloud SQL access
gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member=serviceAccount:agentguard-run@${PROJECT_ID}.iam.gserviceaccount.com \
  --role=roles/cloudsql.client
```

### LiteLLM proxy

```bash
gcloud run deploy litellm \
  --image=ghcr.io/berriai/litellm:main-v1.82.3 \
  --region=$REGION \
  --service-account=agentguard-run@${PROJECT_ID}.iam.gserviceaccount.com \
  --vpc-connector=agentguard-connector \
  --vpc-egress=private-ranges-only \
  --min-instances=1 \
  --cpu=2 --memory=2Gi \
  --port=4000 \
  --no-allow-unauthenticated \
  --set-env-vars="DATABASE_URL=postgresql://litellm:<pass>@<cloudsql-ip>:5432/litellm" \
  --set-secrets="LITELLM_MASTER_KEY=LITELLM_MASTER_KEY:latest,OPENROUTER_API_KEY=OPENROUTER_API_KEY:latest"
```

### AgentGuard API

```bash
gcloud run deploy agentguard-api \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/agentguard/api:latest \
  --region=$REGION \
  --service-account=agentguard-run@${PROJECT_ID}.iam.gserviceaccount.com \
  --vpc-connector=agentguard-connector \
  --vpc-egress=private-ranges-only \
  --min-instances=1 \
  --cpu=2 --memory=2Gi \
  --port=8000 \
  --allow-unauthenticated \
  --set-env-vars="\
LITELLM_BASE_URL=https://<litellm-cloud-run-url>,\
QDRANT_HOST=10.0.0.x,\
QDRANT_PORT=6333,\
LANGFUSE_HOST=https://<langfuse-cloud-run-url>" \
  --set-secrets="\
LANGFUSE_PUBLIC_KEY=LANGFUSE_PUBLIC_KEY:latest,\
LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest"
```

### AgentGuard worker

```bash
gcloud run deploy agentguard-worker \
  --image=${REGION}-docker.pkg.dev/${PROJECT_ID}/agentguard/api:latest \
  --command="python,-m,scripts.worker" \
  --region=$REGION \
  --service-account=agentguard-run@${PROJECT_ID}.iam.gserviceaccount.com \
  --vpc-connector=agentguard-connector \
  --vpc-egress=all-traffic \
  --min-instances=1 \
  --cpu=1 --memory=1Gi \
  --no-allow-unauthenticated \
  --set-env-vars=LANGFUSE_HOST=https://<langfuse-cloud-run-url> \
  --set-secrets="LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest"
```

### Langfuse web

```bash
gcloud run deploy langfuse-web \
  --image=docker.io/langfuse/langfuse:3.174.1 \
  --region=$REGION \
  --service-account=agentguard-run@${PROJECT_ID}.iam.gserviceaccount.com \
  --vpc-connector=agentguard-connector \
  --min-instances=1 \
  --cpu=2 --memory=2Gi \
  --port=3000 \
  --allow-unauthenticated \
  --set-env-vars="\
DATABASE_URL=postgresql://langfuse:<pass>@<cloudsql-ip>:5432/langfuse,\
CLICKHOUSE_URL=http://10.0.0.y:8123,\
LANGFUSE_S3_EVENT_UPLOAD_BUCKET=${PROJECT_ID}-langfuse,\
LANGFUSE_S3_MEDIA_UPLOAD_BUCKET=${PROJECT_ID}-langfuse,\
LANGFUSE_S3_ENDPOINT=https://storage.googleapis.com,\
REDIS_HOST=<memorystore-ip>,\
REDIS_PORT=6379,\
NEXTAUTH_URL=https://<langfuse-cloud-run-url>" \
  --set-secrets="\
LANGFUSE_SECRET_KEY=LANGFUSE_SECRET_KEY:latest,\
SALT=LANGFUSE_SALT:latest,\
NEXTAUTH_SECRET=LANGFUSE_NEXTAUTH_SECRET:latest,\
REDIS_AUTH=REDIS_PASSWORD:latest"
```

## Step 7 — OTel Collector

```bash
gcloud run deploy otel-collector \
  --image=otel/opentelemetry-collector-contrib:0.114.0 \
  --region=$REGION \
  --vpc-connector=agentguard-connector \
  --min-instances=1 \
  --cpu=1 --memory=512Mi \
  --no-allow-unauthenticated
```

Mount `otel-collector-config.yaml` via a Cloud Storage bucket or build it into a custom image.
Point the `otlp` exporter at Langfuse's Cloud Run URL instead of `localhost:3000`.

## Step 8 — DNS and load balancing (optional)

For a custom domain (`agentguard.example.com`), map it to the `agentguard-api` Cloud Run service:

```bash
gcloud run domain-mappings create \
  --service=agentguard-api \
  --domain=agentguard.example.com \
  --region=$REGION
```

Cloud Run provisions a managed TLS certificate automatically.

## Cost estimate (us-central1, light load)

| Service | Spec | Est. monthly |
|---|---|---|
| Cloud SQL (PostgreSQL) | db-g1-small | ~$25 |
| Memorystore (Redis) | 1 GB basic | ~$35 |
| Qdrant GCE VM | e2-standard-4 + 50 GB SSD | ~$130 |
| ClickHouse GCE VM | e2-standard-4 + 100 GB SSD | ~$145 |
| Cloud Run (all services) | ~10 req/min avg | ~$20–50 |
| Cloud Storage | 10 GB + egress | ~$5 |
| **Total** | | **~$360–390/mo** |

> Scale down Qdrant and ClickHouse VMs to `e2-medium` for dev/staging (~$60 less/mo).

## Migrating from local docker-compose

1. `ingest` to populate Qdrant: `python -m app.main ingest` pointed at the new `QDRANT_HOST`
2. Run `python -m scripts.seed_langfuse_prompt` to register the RAG prompt in the cloud Langfuse instance
3. Run `python -m scripts.seed_benchmark_dataset` to seed datasets

## Upgrading to GKE (optional)

Use GKE Autopilot when you need:
- Qdrant with replicated volumes (`PersistentVolumeClaim` + ReadWriteMany via Filestore)
- ClickHouse cluster mode
- Horizontal pod autoscaling on AgentGuard API
- GitOps with ArgoCD or Flux

A minimal GKE Autopilot cluster:

```bash
gcloud container clusters create-auto agentguard \
  --region=$REGION \
  --network=agentguard-vpc \
  --subnetwork=agentguard-subnet
```

Helm charts for Qdrant (`qdrant/qdrant`) and ClickHouse (`clickhouse/clickhouse`) are
available and drop into GKE with minimal configuration changes.
