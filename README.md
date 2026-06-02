# AgentGuard

**AgentGuard is a self-hosted AI reliability platform for RAG and agentic applications.**

It helps teams detect, evaluate, and prevent costly AI incidents before they become customer-visible.

[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![CI](https://github.com/glaborie/agentguard/actions/workflows/ci.yml/badge.svg)](https://github.com/glaborie/agentguard/actions/workflows/ci.yml)
[![Regression Gate](https://github.com/glaborie/agentguard/actions/workflows/regression-gate.yml/badge.svg)](https://github.com/glaborie/agentguard/actions/workflows/regression-gate.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](https://www.python.org/downloads/)
[![Last Commit](https://img.shields.io/github/last-commit/glaborie/agentguard)](https://github.com/glaborie/agentguard/commits/main)

## Why AgentGuard

AI applications can fail in expensive ways:
- hallucinated pricing or policy answers
- unsafe or misleading outputs
- PII leakage
- regressions after prompt, model, retrieval, or tool changes

AgentGuard provides a control layer for observing, protecting, and evaluating those systems.

## What it does

- **Observability** — traces, retrieval, latency, model behavior, and tool usage
- **Protection** — prompt injection blocking and PII masking
- **Evaluation** — golden datasets, benchmarks, regression checks, and scoring
- **Support for RAG and agents** — works across both retrieval pipelines and agentic workflows

## Architecture at a glance

```mermaid
flowchart LR
    APP[Your AI Application<br/>RAG or Agent]
    AG[AgentGuard Control Layer]
    LLM[LLMs / Model Gateway]
    DATA[Knowledge, Tools, Actions]
    SAFE[Protection]
    OBS[Observability]
    EVAL[Evaluation]

    APP --> AG
    AG --> LLM
    AG --> DATA
    AG --> SAFE
    AG --> OBS
    AG --> EVAL
```

For the full system view, see [Architecture](docs/architecture.md).

## Who it’s for

- AI engineers building RAG or agentic systems
- platform teams standardizing AI reliability
- technical product owners responsible for release confidence
- teams handling sensitive, regulated, or business-critical workflows

## Quick Start

```bash
cp .env.example .env
docker compose up -d
docker compose exec ollama ollama pull nomic-embed-text
pip install -r requirements.txt
python -m app.main ingest
python -m app.main query "Does the Starter plan include SAML SSO?"
```

Open:
- Open WebUI: `http://localhost:3001`
- Langfuse: `http://localhost:3000`

## Documentation

- [Roadmap](docs/ROADMAP.md)
- [Architecture](docs/architecture.md)
- [Local deployment](docs/deployment/local.md)
- [Evaluation](docs/evaluation.md)
- [Agent workflow](docs/agent-workflow.md)
- [TODO / SOTA gaps](TODO.md)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Security

See [SECURITY.md](SECURITY.md).

## License

Licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE).
