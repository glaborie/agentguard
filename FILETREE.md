# Project Filetree

_Auto-maintained by `/filetree:update`. Each entry carries a content hash; mismatched hashes indicate stale summaries._

## (root)/

- `.dockerignore` — Excludes credentials, development artifacts, documentation, and runtime configs from Docker build context. <!--hash:13eae0d0-->
- `.env.example` — Template environment variables for Langfuse, LiteLLM, Qdrant, OpenTelemetry, guardrails, and cloud integrations. <!--hash:7dbf4102-->
- `.gitattributes` — Enforces LF line endings across all text files and marks binary files for consistent version control. <!--hash:ba7ed9ad-->
- `.gitignore` — Git ignore file excluding Python artifacts, environment variables, data docs, test state files, and local caches <!--hash:c7e03718-->
- `CLAUDE.md` — Project architecture guide covering LiteLLM proxy, LangChain RAG, LangGraph agent, Langfuse tracing, OpenTelemetry pipeline, and all CLI commands <!--hash:54102f9a-->
- `CONTRIBUTING.md` — Contribution guidelines covering development setup, code quality, testing, documentation, PR workflow, and prioritized contribution areas <!--hash:2ca6144f-->
- `DEPLOYMENT.md` — Root deployment entrypoint linking to canonical local/cloud deployment docs and compose naming conventions <!--hash:66e2501c-->
- `DOCKER.md` — Docker Scout commands for scanning images for CVEs using docker-compose with tools profile <!--hash:1794dcbb-->
- `Dockerfile.api` — Multi-stage Docker image for rag-api service using Python 3.11-slim with dependency wheels and health checks <!--hash:fbf199ac-->
- `Dockerfile.litellm` — LiteLLM proxy image extending berriai base with qdrant-client and OpenInference instrumentation <!--hash:dd566ded-->
- `Dockerfile.ollama` — Ollama image with nomic-embed-text embedding model pre-pulled at build time for instant availability <!--hash:7cf0224f-->
- `Dockerfile.worker` — Multi-stage worker service image containing polling scripts for feedback sync, online eval, and dataset building <!--hash:de620a0d-->
- `LICENSE` — Apache License 2.0 full terms granting worldwide copyright and patent licenses for derivative works <!--hash:49cea315-->
- `Makefile` — Test target aliases for unit, integration, module-specific, and parallel test execution with coverage reporting <!--hash:d9014444-->
- `NOTICE` — Copyright notice attributing AgentGuard to Guillaume Laborie <!--hash:222201ef-->
- `README.md` — Project overview describing AgentGuard as self-hosted AI reliability platform with observability, protection, evaluation, and red-teaming <!--hash:7dce56f1-->
- `SECURITY.md` — Security policy covering vulnerability reporting via private disclosure, scope definition, response process, and user best practices <!--hash:1425099c-->
- `SETUP_POSTMORTEM.md` — Post-mortem documenting Docker setup challenges on Windows (port exclusion, service networking, database requirements, credential management) <!--hash:087168b8-->
- `SHOWCASE.md` — Manual testing scenarios for RAG (plans, features, policies) and guardrails with Langfuse trace inspection instructions <!--hash:dd7d5102-->
- `TODO.md` — SOTA gaps and technical debt backlog with implemented items (#1-9) covering semantic detection, CI/CD, toxicity, red-teaming <!--hash:cf65523e-->
- `VALIDATION.md` — End-to-end validation guide covering ingestion, retrieval, tracing, and troubleshooting across Docker stack. <!--hash:cbca5062-->
- `compose-litellm.yml` — Legacy compatibility alias for the LiteLLM-only compose file. Prefer `docker-compose.litellm.yml` for new references. <!--hash:9786e9d1-->
- `docker-compose.litellm.yml` — LiteLLM-only compose file (canonical naming) with config mount and guardrails module. <!--hash:9786e9d1-->
- `docker-compose.infra.yml` — Compose anchors and Jaeger/OTel collector service definitions for tracing infrastructure. <!--hash:5c82b657-->
- `docker-compose.yml` — Main Compose stack defining Langfuse, Postgres, Redis, Qdrant, MinIO, and OpenObserve services. <!--hash:6ba8607c-->
- `litellm_config.yaml` — LiteLLM proxy configuration: model routing (Ollama/OpenRouter), callbacks (Langfuse/Arize/semantic cache/Prometheus), three guardrails, user headers. <!--hash:cb251a21-->
- `loki-config.yml` — Loki log aggregation server config with TSDB backend, filesystem storage, query caching, and alertmanager integration. <!--hash:f62cc893-->
- `minimax.sh` — Bash script routing Claude SDK to OpenRouter MiniMax models via ANTHROPIC_BASE_URL and model tier mapping environment variables. <!--hash:f78a2f76-->
- `otel-collector-config.yaml` — OpenTelemetry collector config routing OTLP traces to Jaeger, Langfuse, and OpenObserve exporters. <!--hash:449d4576-->
- `prometheus.yml` — Prometheus scrape config targeting LiteLLM, OTel collector, and RAG API metrics with remote write. <!--hash:8f219709-->
- `promptfooconfig.yaml` — Red teaming configuration for promptfoo testing RAG chatbot against 30+ attack plugins and strategies. <!--hash:85a94c68-->
- `promtail-config.yml` — Promtail log scraper pipeline shipping Docker container logs to Loki and OpenObserve via relabeling. <!--hash:f65cd857-->
- `pyproject.toml` — Poetry project config with Python 3.13 requirement, pytest markers for integration tests, coverage. <!--hash:702dc293-->
- `redteam.yaml` — Red team attack configuration defining purpose, plugins, strategies, and test counts (large YAML file). <!--hash:e9f518be-->
- `requirements.txt` — Python dependencies: langfuse, langchain, qdrant, fastapi, deepeval, opentelemetry, pydantic. <!--hash:d172f0fc-->
- `runtime_config.json` — JSON runtime config enabling guardrails, semantic cache, tracing, hybrid search with threshold weights. <!--hash:49e7fc3e-->
- `skills-lock.json` — Skills dependency lock file; records source, version, computed hash for all registered skills <!--hash:e24933ca-->
- `traefik-routes.yml` — Traefik reverse proxy routing configuration mapping localhost hostnames to Docker services (OpenWebUI, Langfuse, LiteLLM, Jaeger, etc). <!--hash:eb16d6f2-->

## .claude/

- `agentguard-files.md` — Inventory of infrastructure, application, CLI, API, RAG, agent, eval, and script files with role descriptions and architecture notes. <!--hash:a57d7c97-->
- `settings.json` — Claude Code harness configuration; permits Python testing and Slack integration. <!--hash:8292cbd7-->

## .claude/skills/arize-admin/

- `SKILL.md` — Manages Arize users, organizations, spaces, projects, roles, API keys via ax CLI for enterprise access control workflows. <!--hash:27935368-->

## .claude/skills/arize-admin/references/

- `REFERENCE.md` — Enterprise workflow examples: onboarding teams, SAML/SSO role mappings, offboarding, restricting projects, service keys. <!--hash:73cda6f2-->
- `ax-profiles.md` — Troubleshooting guide for ax CLI authentication; fixing misconfigured profiles and creating new ones. <!--hash:27b01a5b-->
- `ax-setup.md` — Installation and version troubleshooting for ax CLI on macOS, Linux, and Windows. <!--hash:86eda5a2-->

## .claude/skills/arize-ai-provider-integration/

- `SKILL.md` — Creates and manages Arize AI integrations storing LLM provider credentials for evaluators and features. <!--hash:0ee895a8-->

## .claude/skills/arize-ai-provider-integration/references/

- `ax-profiles.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-profiles.md <!--hash:27b01a5b-->
- `ax-setup.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-setup.md <!--hash:86eda5a2-->

## .claude/skills/arize-annotation/

- `SKILL.md` — Creates annotation configs and queues; applies human labels to spans and experiments via Python SDK. <!--hash:7edbd62b-->

## .claude/skills/arize-annotation/references/

- `ax-profiles.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-profiles.md <!--hash:27b01a5b-->
- `ax-setup.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-setup.md <!--hash:86eda5a2-->

## .claude/skills/arize-compliance-audit/

- `SKILL.md` — Audits AI agents for EU AI Act, GDPR, NIST AI RMF, Colorado Act, HIPAA, and ISO 42001 compliance. <!--hash:1290a947-->

## .claude/skills/arize-compliance-audit/references/

- `compliance-checklist-template.md` — Template checklist covering governance, data protection, bias, monitoring, and supply chain compliance controls. <!--hash:03f05f6a-->
- `eu-ai-act-gpai.md` — Developer reference for EU AI Act risk tiers and high-risk system requirements for hiring, credit, healthcare. <!--hash:65e8bf9b-->
- `iso-42001.md` — ISO 42001 AI management system standard mapped to code-auditable clauses and control requirements. <!--hash:aa4e159c-->
- `us-ai-compliance.md` — US AI compliance developer reference covering NIST AI RMF, Colorado AI Act, NYC Local Law 144, and HIPAA frameworks <!--hash:86e256c6-->

## .claude/skills/arize-dataset/

- `SKILL.md` — Creates, manages, queries, and exports Arize datasets for evaluation and experimentation via ax CLI. <!--hash:97e9ee37-->

## .claude/skills/arize-dataset/references/

- `ax-profiles.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-profiles.md <!--hash:27b01a5b-->
- `ax-setup.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-setup.md <!--hash:86eda5a2-->

## .claude/skills/arize-evaluator/

- `SKILL.md` — LLM-as-judge and code evaluator workflows on Arize; creates evaluators, runs evaluations, manages tasks. <!--hash:d063fcaf-->

## .claude/skills/arize-evaluator/references/

- `ax-profiles.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-profiles.md <!--hash:27b01a5b-->
- `ax-setup.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-setup.md <!--hash:86eda5a2-->

## .claude/skills/arize-experiment/

- `SKILL.md` — Creates, runs, and analyzes Arize experiments comparing model performance on datasets via ax CLI. <!--hash:10db6d0c-->

## .claude/skills/arize-experiment/references/

- `ax-profiles.md` — symlink → /mnt/h/Training/AI_Engineering/Langfuse/Langfuse_POC/.claude/skills/arize-admin/references/ax-profiles.md <!--hash:27b01a5b-->
- `ax-setup.md` — Troubleshooting guide for ax CLI installation, versioning, and certificate issues; reference when ax commands fail. <!--hash:86eda5a2-->

## .claude/skills/arize-instrumentation/

- `SKILL.md` — Two-phase agent-assisted flow for adding Arize AX tracing to Python, TypeScript, Go, and Java LLM apps from scratch. <!--hash:0dfcd294-->

## .claude/skills/arize-instrumentation/references/

- `ax-profiles.md` — Reference for creating, updating, and validating ax profiles; resolves authentication errors and API key setup. <!--hash:c08551d8-->
- `integration-routing.md` — Maps detected language, LLM provider, and framework signals to correct Arize integration documentation and links. <!--hash:9435eb32-->
- `manual-spans.md` — Guide for adding manual CHAIN and TOOL spans to trace tool execution and agent loops; provides code patterns. <!--hash:13e609fa-->
- `tracing-assistant-mcp.md` — Reference for enabling Arize AX Tracing Assistant MCP server in Cursor IDE for instrumentation guidance. <!--hash:7befd283-->

## .claude/skills/arize-link/

- `SKILL.md` — Generates deep links to Arize UI for traces, spans, sessions, datasets, queues, and evaluators. <!--hash:44d9f470-->

## .claude/skills/arize-link/references/

- `EXAMPLES.md` — URL template examples for linking to Arize traces, spans, sessions, datasets, and labeling queues. <!--hash:32d6a00e-->

## .claude/skills/arize-prompt-optimization/

- `SKILL.md` — Optimizes LLM prompts using production trace data, evaluations, annotations, and ax CLI; extracts performance signals. <!--hash:94723f86-->

## .claude/skills/arize-prompt-optimization/references/

- `ax-profiles.md` — Reference for creating, updating, and validating ax profiles; resolves authentication errors and API key setup. <!--hash:27b01a5b-->
- `ax-setup.md` — Troubleshooting guide for ax CLI installation, versioning, and certificate issues; reference when ax commands fail. <!--hash:86eda5a2-->

## .claude/skills/arize-prompts/

- `SKILL.md` — Creates, versions, labels, and manages LLM prompts in Prompt Hub with templates, variables, and production labels. <!--hash:fdd8f099-->

## .claude/skills/arize-prompts/references/

- `ax-profiles.md` — Reference for creating, updating, and validating ax profiles; resolves authentication errors and API key setup. <!--hash:27b01a5b-->
- `ax-setup.md` — Troubleshooting guide for ax CLI installation, versioning, and certificate issues; reference when ax commands fail. <!--hash:8075e5fa-->
- `cli-prompts.md` — CLI flag reference tables for ax prompts commands: create, create-version, label, list, get, update, delete. <!--hash:835c2aae-->

## .claude/skills/arize-trace/

- `SKILL.md` — Downloads, exports, and inspects existing Arize traces, spans, and sessions using ax CLI for debugging and analysis. <!--hash:b908c72b-->

## .claude/skills/arize-trace/references/

- `ax-profiles.md` — Reference for creating, updating, and validating ax profiles; resolves authentication errors and API key setup. <!--hash:27b01a5b-->
- `ax-setup.md` — Troubleshooting guide for ax CLI installation, versioning, and certificate issues; reference when ax commands fail. <!--hash:86eda5a2-->

## .github/

- `CODEOWNERS` — Assigns code review ownership to @glaborie for all repository files and directories. <!--hash:8f73ac8c-->
- `pull_request_template.md` — GitHub PR template with sections for summary, problem, change type, testing approach, documentation, risks, and reviewer notes <!--hash:fbd324be-->

## .github/ISSUE_TEMPLATE/

- `bug_report.md` — Template for reporting reproducible bugs with summary, steps, environment, impact, and diagnostic logs. <!--hash:1b7831e9-->
- `config.yml` — Disables blank issues; routes security vulnerabilities and contributions to dedicated channels. <!--hash:53669f97-->
- `feature_request.md` — Template for proposing features with problem statement, solution, alternatives, beneficiaries, and impact. <!--hash:06921fbe-->

## .github/workflows/

- `bandit.yml` — GitHub Action runs Bandit security linter on Python code weekly and on push/PR to main branch <!--hash:5efc546b-->
- `ci.yml` — GitHub Actions pipeline for linting with flake8 and running unit tests with coverage on main branch <!--hash:46880535-->
- `regression-gate.yml` — GitHub Actions workflow runs quality regression checks on golden dataset via smoke-test and full modes <!--hash:429fcd92-->

## .sota/

- `last-scan.json` — SOTA scan results comparing AgentGuard against 10 peer platforms on AI control capabilities (93% coverage) <!--hash:9bca9506-->
- `rubric.ai-application-control-platform.json` — SOTA rubric defining 19 table-stakes and edge-tier capabilities for AI application control platforms <!--hash:3f6acb0b-->

## app/

- `__init__.py` — Empty module marker for app package. <!--hash:e69de29b-->
- `config.py` — Re-exports all core config settings for backward-compatible import paths across codebase <!--hash:1bdc947d-->
- `main.py` — Entry point delegating to CLI app. <!--hash:a4324d07-->
- `telemetry.py` — Re-export from app.core.telemetry for backward compatibility. <!--hash:85fbe367-->
- `tracing.py` — Re-export from app.core.tracing for backward compatibility. <!--hash:0f620f6c-->
- `utils.py` — Utility helpers for text truncation and trace output normalization. <!--hash:734e71bd-->

## app/agent/

- `__init__.py` — Empty module marker for agent subpackage. <!--hash:e69de29b-->
- `graph.py` — LangGraph ReAct agent with guarded tool execution, message state, and multi-turn memory via checkpointer. <!--hash:f71e8ccd-->
- `mcp_client.py` — GitHub MCP tool loader supporting both streamable HTTP and stdio transports with token-based auth. <!--hash:63653b2d-->
- `prompts.py` — System prompt for AgentGuard ReAct agent describing tools, guidelines, and response behavior. <!--hash:371f7025-->
- `service.py` — Agent service layer wrapping graph execution with Langfuse session/user propagation and chat sessions. <!--hash:93d23f8c-->
- `tool_guard.py` — Pre-execution guardrail blocking disallowed tools and injection-shaped queries to search_docs and list_traces. <!--hash:e7b39829-->
- `tools.py` — ReAct agent tools: search_docs, list_traces, get_trace_detail, score_response, get_dataset_summary. <!--hash:2916be3b-->

## app/api/

- `__init__.py` — Re-exports FastAPI app instance for uvicorn server startup. <!--hash:1450607c-->
- `app.py` — FastAPI application factory with CORS, BM25 warmup, OpenTelemetry instrumentation, and route inclusion. <!--hash:c7f64846-->
- `schemas.py` — Pydantic request schemas for chat completions with message, stream, and Open WebUI metadata fields. <!--hash:783442e1-->
- `streaming.py` — Converts pre-computed results to OpenAI-compatible server-sent-events (SSE) streaming chunks <!--hash:2773a848-->

## app/api/routes/

- `__init__.py` — Re-exports API route modules for inclusion in application. <!--hash:b0ce51e5-->
- `chat.py` — Chat completions endpoint supporting streaming and non-streaming responses with guardrails and tracing. <!--hash:098db8a6-->
- `config.py` — Feature flag control panel dashboard and REST API for runtime guardrail, search, and model toggles. <!--hash:edeacf89-->
- `health.py` — Health check endpoint reporting status of Docker services and dependencies. <!--hash:9f46de98-->
- `models.py` — Model listing endpoint returning available LLM models from LiteLLM configuration. <!--hash:2b3df72f-->
- `retrieval.py` — Retrieval debugging API supporting vector-only, BM25, and hybrid search with scoring comparison. <!--hash:02af7342-->
- `webhook.py` — Open WebUI feedback webhook endpoint converting thumbs-up/down to Langfuse user_feedback scores. <!--hash:b3b2c153-->

## app/api/services/

- `__init__.py` — Empty module marker for API services subpackage. <!--hash:e69de29b-->
- `agent_llm.py` — Agent invocation service handling ReAct execution, guardrail error detection, and completion ID generation. <!--hash:cb01c0cc-->
- `chat_service.py` — Chat orchestrator routing requests to agent, RAG, or direct LLM modes with OTel span annotation. <!--hash:468c5650-->
- `direct_llm.py` — Direct LLM call service bypassing RAG, with error handling and guardrail violation detection. <!--hash:f7f5d536-->
- `feedback_service.py` — Open WebUI feedback webhook handler parsing ratings and pushing user_feedback scores to Langfuse. <!--hash:a68eed53-->
- `guardrail_scoring.py` — Detects guardrail blocks and pushes Langfuse scores and traces for visibility in observability dashboard <!--hash:92716f67-->
- `health_service.py` — Probes backing services (LiteLLM, Langfuse, Qdrant) and returns health status with cached results <!--hash:eaa2b645-->
- `models_service.py` — Returns OpenAI-compatible model list for chat completions endpoint with AgentGuard model variants <!--hash:3ae29a9a-->
- `rag_llm.py` — Invokes RAG chain with error handling, guardrail detection, PII scoring, and completion ID tracking <!--hash:75fd5988-->

## app/cli/

- `__init__.py` — Exposes main CLI entry point for command-line interface <!--hash:7feeefa8-->
- `app.py` — Argument parser and CLI dispatcher; loads env, registers subcommands, and routes to handlers <!--hash:0c2b700b-->
- `common.py` — Shared CLI utilities for flushing buffered Langfuse spans before process exit <!--hash:5a07e9b1-->

## app/cli/commands/

- `__init__.py` — Re-exports public CLI command modules for cross-module imports <!--hash:0afb8f9a-->
- `agent.py` — CLI commands for single-shot ReAct agent questions and interactive multi-turn agent chat with memory <!--hash:71ced864-->
- `benchmark.py` — CLI command to run NorthstarCRM benchmark suite with mode selection and multi-mode comparison <!--hash:cf15baee-->
- `dataset.py` — CLI command to seed RAG evaluation dataset in Langfuse from external dataset script <!--hash:567e0522-->
- `drift.py` — CLI command to detect quality metric regressions from Langfuse score history over time windows <!--hash:8df3f5b7-->
- `evaluate.py` — CLI commands for running DeepEval metrics on datasets and continuous online evaluation worker <!--hash:8dcb8777-->
- `experiment.py` — CLI command to run multi-model comparison experiments against datasets with metric reporting <!--hash:d28095c7-->
- `ingest.py` — CLI command to ingest documents into Qdrant vector store with configurable chunk parameters <!--hash:bd095fb2-->
- `query.py` — CLI commands for single RAG question and interactive multi-turn RAG chat with session tracking <!--hash:12247ad1-->
- `red_team.py` — CLI command to probe guardrails with auto-generated adversarial prompts for security testing <!--hash:b9294720-->
- `regression.py` — CLI command implementing quality gate; runs golden dataset and fails if metrics below thresholds <!--hash:68104f3c-->
- `retrieval_debug.py` — CLI command inspects and compares vector, hybrid, and BM25 retrievers with ranking and score analysis <!--hash:9eb28ff7-->

## app/core/

- `__init__.py` — Empty module marker for app/core package <!--hash:e69de29b-->
- `config.py` — Pydantic Settings singleton managing environment configuration for all external services and defaults <!--hash:e1c188d8-->
- `feature_flags.py` — Runtime feature flag management; reads/writes runtime_config.json for guardrails and observability toggles <!--hash:10240cda-->
- `ids.py` — Generates short request IDs and OpenAI-compatible completion IDs for tracing and correlation <!--hash:0e9953df-->
- `logging.py` — Centralised logging helpers providing get_logger() and configure_logging() utilities. <!--hash:c673373c-->
- `telemetry.py` — OpenTelemetry SDK bootstrap; auto-instruments FastAPI and httpx for distributed tracing. <!--hash:64b41856-->
- `tracing.py` — Langfuse SDK client and CallbackHandler; returns real handler or no-op stub based on feature flag. <!--hash:daf796e4-->

## app/eval/

- `__init__.py` — Empty module initializer. <!--hash:e69de29b-->
- `benchmark.py` — Benchmark runner evaluating RAG pipeline against test items across five metrics in three modes. <!--hash:3e8e4cfd-->
- `deepeval_metrics.py` — DeepEval metric wrappers with LiteLLM proxy routing for judge LLM calls; factory registry. <!--hash:bcb4dcf1-->
- `deepeval_runner.py` — DeepEval evaluation orchestrator; runs metrics on dataset items and pushes scores to Langfuse. <!--hash:b4d07e30-->
- `drift.py` — Quality drift detection comparing consecutive time windows; pure function with Langfuse fetch helper. <!--hash:7408125e-->
- `evaluators.py` — Code-based and LLM-as-judge evaluation functions; checks citations, length, hallucination markers. <!--hash:e085acb3-->
- `experiments.py` — Multi-model experiment runner; compares models on dataset, pushes DeepEval scores to Langfuse. <!--hash:f43d5440-->
- `service.py` — Evaluation service facade; wires evaluate(), experiment(), and regression_gate() to backend functions. <!--hash:06f1c268-->

## app/rag/

- `__init__.py` — Empty module initializer. <!--hash:e69de29b-->
- `bm25_index.py` — In-memory BM25 index built from Qdrant corpus with disk cache and atomic persist. <!--hash:13c00147-->
- `chain.py` — RAG pipeline building retriever, LLM, and LangChain LCEL chain; includes Langfuse prompt fetch and scoring. <!--hash:acd1bb30-->
- `hybrid_retriever.py` — Ensemble retriever combining vector and BM25 via RRF; emits OTel span attributes for hybrid mode. <!--hash:d78c0594-->
- `ingest.py` — Document ingestion pipeline loading markdown and JSONL corpus files, chunking, embedding, and storing in Qdrant. <!--hash:38304e16-->
- `service.py` — RAG service facade wrapping ingestion, queries, and chain building with Langfuse attribute propagation. <!--hash:1a7ad116-->

## config/openwebui/

- `chat_id_injection.json` — Open WebUI filter function injecting chat_id, message_id, user context into RAG request body. <!--hash:979a5deb-->

## docs/

- `ROADMAP.md` — Product roadmap and strategic priorities for AgentGuard: protection strengthening, release workflows, deployment, and contributor onboarding. <!--hash:2980d75e-->
- `agent-workflow.md` — ReAct agent with five tools: document search, trace listing, trace details, response scoring, and dataset inspection with guardrails. <!--hash:d41d8039-->
- `agentguard.html` — Static HTML landing page showcasing AgentGuard features, use cases, quick-start deployment instructions, and project information. <!--hash:6cb985db-->
- `architecture.md` — System design overview including component diagram, message flow, platform services, project structure, and continuous improvement loop. <!--hash:83130828-->
- `evaluation.md` — Evaluation framework with golden datasets, LLM-based quality metrics, benchmark suite, and quality drift monitoring for regression detection. <!--hash:ce92a76e-->
- `index.html` — Interactive HTML landing page with Tailwind CSS styling, feature tabs, use cases, quick-start code block, and GitHub links. <!--hash:d5bf8ff8-->
- `screenshots.md` — Documentation page showing Langfuse tracing UI views with session-level visibility and detailed trace inspection examples. <!--hash:44bbea78-->

## docs/deployment/

- `google-cloud.md` — Production GCP deployment guide covering VPC setup, Cloud SQL/Redis/Storage, GCE VMs for Qdrant/ClickHouse, Cloud Run services, and cost estimates. <!--hash:b7181918-->
- `local.md` — Local development setup guide covering Docker prerequisites, quick-start steps, model routing via LiteLLM, and Windows-specific port configuration. <!--hash:99d400c9-->

## docs/superpowers/

- `performance-audit.md` — One-off performance audit identifying bottlenecks in benchmarking serial execution, semantic cache overhead, async/sync boundaries, and backend polling. <!--hash:01258721-->

## docs/superpowers/plans/

- `2026-06-03-semantic-cache.md` — Semantic cache implementation plan with nine tasks: test scaffolding, helpers, get/set paths, activation, config updates, integration tests. <!--hash:93f929c9-->
- `2026-06-06-agent-openwebui.md` — Agent integration plan exposing LangGraph ReAct as agentguard-agent model in Open WebUI with four tasks: model registry, service, routing, verification. <!--hash:6cdc2e78-->

## docs/superpowers/specs/

- `2026-06-03-semantic-cache-design.md` — Semantic cache architecture spec using Qdrant vectors + Redis responses with cosine similarity threshold, TTL, and error resilience. <!--hash:c40cd175-->
- `2026-06-06-agent-openwebui-design.md` — Design spec for wiring LangGraph agent into Open WebUI: adds agentguard-agent model, session management via thread_id, error handling. <!--hash:ad8191ef-->

## grafana/provisioning/dashboards/

- `agentguard.json` — Grafana dashboard JSON with Loki data source panels monitoring semantic cache hits/misses and system performance metrics. <!--hash:5faaa858-->
- `dashboards.yml` — Grafana provisioning config declaring AgentGuard folder and file-based dashboard loader from /etc/grafana/provisioning/dashboards. <!--hash:3ef45072-->

## grafana/provisioning/datasources/

- `datasources.yml` — Grafana datasources config registering Loki and Prometheus backends for observability visualization and alerting. <!--hash:9942bcc6-->

## guardrails/

- `custom_guardrails.py` — LiteLLM custom guardrails: PromptInjectionGuard (regex + optional LLM-judge), PIIMaskingGuard (redacts PII), runtime config hot-reload. <!--hash:2efb5eba-->
- `semantic_cache.py` — QdrantSemanticCache implementation using Qdrant vectors + Redis responses; embedding via Ollama nomic-embed-text with 0.85 similarity threshold. <!--hash:e2d4147f-->

## mock_corpus/

- `README.md` — Describes NorthstarCRM synthetic B2B SaaS corpus structure: company, products, sales process, policies, FAQs. <!--hash:2bab44b8-->

## mock_corpus/01_company/

- `about.md` — NorthstarCRM fictional company profile: B2B SaaS for mid-market support/sales workflows with target personas and value proposition. <!--hash:9a9c0c5b-->
- `glossary.md` — Enterprise sales and operations terminology glossary: AE, SDR, MSA, DPA, SSO, SLA, POC, Deal Desk. <!--hash:36f50487-->
- `target-customers.md` — NorthstarCRM ideal customer profile (100–2,000 employees) and poor-fit segments (email-only, on-prem, month-to-month requirements). <!--hash:75e961ae-->

## mock_corpus/02_products/

- `feature-matrix.md` — NorthstarCRM product tiers (Starter/Business/Enterprise) feature comparison including automation, integrations, SSO, and audit capabilities. <!--hash:4813d78e-->
- `implementation-options.md` — Implementation service tiers (Starter, Business, Enterprise) with onboarding timelines and support levels <!--hash:d1cd4a2e-->
- `integrations.md` — Supported platform integrations (Salesforce, HubSpot, Slack, Teams, Zendesk) by plan tier <!--hash:1e5c0242-->
- `plans-and-pricing.md` — Complete pricing for Starter/Business/Enterprise plans with seat counts, features, support, and SLA details <!--hash:344a56af-->
- `product-overview.md` — NorthstarCRM product capabilities, core modules, feature scope, and competitive positioning vs alternatives <!--hash:7c2bf492-->

## mock_corpus/03_sales_process/

- `demo-booking-process.md` — Rules for scheduling sales demos by customer segment (Starter trial vs Business/Enterprise qualification) <!--hash:616d788b-->
- `legal-review-process.md` — Legal review requirements, timelines, and approval process for custom terms and customer paper <!--hash:3eccb3ab-->
- `procurement-process.md` — Procurement workflow stages including commercial, security, legal, PO, and onboarding handoff phases <!--hash:22776d05-->
- `proposal-process.md` — Proposal prerequisites and outputs including pricing, scope, implementation, and onboarding assumptions <!--hash:f45d2215-->
- `qualification-rules.md` — Lead qualification criteria for Business/Enterprise sales (user count, pain point, integrations, timeline) <!--hash:e4b69da2-->
- `renewal-and-expansion.md` — Renewal process, expansion types (seats, upgrades, add-ons), and pricing considerations for existing customers <!--hash:7735a94c-->

## mock_corpus/04_policies/

- `approval-matrix.md` — Authorization matrix defining who approves discounts, SLAs, custom terms, and non-standard requests <!--hash:1bd86700-->
- `confidentiality-policy.md` — Confidential information restrictions (margins, pricing formulas, roadmap) and proper disclosure handling <!--hash:1ba9f5d7-->
- `data-handling-policy.md` — Data collection and retention principles with no residency promises unless contractually documented <!--hash:90b35228-->
- `discount-policy.md` — Discount approval tiers, restrictions, and rules for annual contracts with new vs expansion customer distinctions <!--hash:8a3b04b4-->
- `refund-and-cancellation-policy.md` — Cancellation rules: monthly Starter plans cancellable, annual contracts non-refundable unless agreed <!--hash:7c86da32-->
- `security-and-compliance-policy.md` — Security control availability by plan, compliance posture, TPRM process, and data handling commitments <!--hash:ec18b7b3-->
- `sla-policy.md` — Standard SLAs for Starter/Business/Enterprise with uptime, response times, and custom SLA approval requirements <!--hash:1db3546f-->

## mock_corpus/05_support/

- `billing-faq.md` — FAQs covering payment options (monthly/annual), discount availability, and billing terms <!--hash:35e0ac71-->
- `general-sales-faq.md` — Sales FAQs on demos, trials, quotes, pricing matches, discounts, upgrades, and POC arrangements <!--hash:e44b4960-->
- `onboarding-faq.md` — Onboarding implementation timelines and support levels by plan (2-4 weeks Business, 4-8 weeks Enterprise) <!--hash:4e20e035-->
- `security-faq.md` — Security-related FAQs on questionnaires, advanced controls, and custom commitment review requirements <!--hash:7a0746fa-->
- `technical-faq.md` — Technical FAQs covering integrations, SSO, audit logs, SLAs, data retention, and deployment options <!--hash:a72243d7-->

## mock_corpus/06_conversations/

- `escalation-examples.jsonl` — Conversational examples demonstrating proper escalation handling for security and legal review scenarios <!--hash:9bb55568-->
- `lead-qualification-examples.jsonl` — Conversational examples showing lead qualification assessment based on user count and feature needs <!--hash:c833aec7-->
- `objection-handling.jsonl` — Conversational examples for handling pricing, feature gap, and timeline objections with escalation guidance <!--hash:d7ba9880-->
- `quote-request-examples.jsonl` — JSONL dataset with conversational quote request examples mapping customer intent to escalation rules. <!--hash:1fa6a4e5-->

## mock_corpus/07_benchmark/

- `benchmark_questions.jsonl` — JSONL benchmark questions for NorthstarCRM RAG pipeline with expected facts and escalation labels. <!--hash:331974be-->
- `edge_cases.jsonl` — JSONL edge case questions testing competitor pricing, custom plans, and policy exceptions. <!--hash:ad607a2d-->
- `expected_answers.jsonl` — JSONL ideal responses for benchmark questions grounded in NorthstarCRM policies and product details. <!--hash:d831d3f4-->
- `retrieval_labels.jsonl` — JSONL gold documents mapping benchmark questions to relevant source files for retrieval evaluation. <!--hash:16a8f39d-->

## notebooks/

- `benchmark.ipynb` — Jupyter notebook evaluating RAG pipeline across three modes (full, no-guardrails, direct) with metric visualization. <!--hash:2921584d-->
- `benchmark_full.txt` — Text snapshot of benchmark notebook execution output showing health checks and result summaries. <!--hash:f079bbb2-->
- `benchmark_results_20260528_103913.csv` — CSV export of benchmark results with per-item scores across retrieval, policy, escalation, and helpfulness. <!--hash:279d9245-->
- `quality_drift.ipynb` — Jupyter notebook monitoring metric trends via Langfuse, detecting regressions with synthetic data fallback. <!--hash:0843a7eb-->
- `validation.ipynb` — End-to-end validation notebook verifying services, ingestion, retrieval, guardrails, tracing, and tests. <!--hash:08c5bb26-->

## openobserve/

- `import_dashboards.sh` — Bash script importing AgentGuard dashboards into OpenObserve API via authenticated HTTP POST. <!--hash:9012f3df-->
- `setup_alerts.sh` — Bash script creating OpenObserve alerts for error spikes, LLM latency, guardrail blocks, and logs. <!--hash:a0182b04-->

## openobserve/dashboards/

- `agentguard_llm.json` — OpenObserve dashboard JSON defining LLM observability panels: request rate, latency, guardrail blocks. <!--hash:ef3f32e0-->

## postman/

- `AgentGuard.postman_collection.json` — Postman API collection with base URL variables for testing RAG API, chat, and webhook endpoints. <!--hash:a2a0e9b0-->

## postman/specs/

- `openapi.yaml` — OpenAPI 3.0 specification documenting AgentGuard RAG API endpoints, schemas, and security requirements. <!--hash:c30ca106-->

## scripts/

- `build_dataset.py` — Python script building Langfuse dataset from user-rated RAG traces with dry-run and reset modes. <!--hash:842b8264-->
- `compare_retrieval.py` — Benchmarks vector vs hybrid retrieval (BM25+RRF) on gold labels; measures hit-rate without LLM calls <!--hash:6370ffa1-->
- `demo_prospect_chat.py` — Playwright demo simulating B2B sales conversation with RAG chatbot in Open WebUI; headed/headless modes <!--hash:10d89d01-->
- `init_litellm.py` — Idempotent LiteLLM bootstrap; registers models, budget, team, key, and guardrails in database <!--hash:f9c9a20a-->
- `ollama_entrypoint.sh` — Starts Ollama server and pre-loads models via CLI to ensure residency before first request <!--hash:326ab581-->
- `online_eval_worker.py` — Polls Langfuse for new RAG traces; runs code-based evaluators and posts scores back continuously <!--hash:5507c4fd-->
- `openwebui_langfuse_filter.py` — Open WebUI filter function injecting chat_id, message_id, user context into request body for session linking <!--hash:d2bbb8fc-->
- `red_team.py` — Generates adversarial prompts and probes guardrail stack (prompt injection, jailbreak, PII, system prompt leak) <!--hash:134abc5b-->
- `regression_gate.py` — Evaluates Langfuse dataset with DeepEval; exits non-zero if metric averages fall below thresholds <!--hash:2d46ba9f-->
- `run_benchmark_experiment.py` — Runs multi-model experiments against northstar-rag/safety datasets using Langfuse SDK run_experiment API <!--hash:871839d9-->
- `seed_benchmark_dataset.py` — Seeds northstar-rag (18 items) and northstar-safety (11 items) datasets from JSONL corpus files <!--hash:5fdfe8d9-->
- `seed_dataset.py` — Seeds rag-eval-v1 dataset in Langfuse with 5 Langfuse documentation Q&A pairs for DeepEval <!--hash:a15ee545-->
- `seed_langfuse_prompt.py` — Registers RAG system prompt in Langfuse Prompt Registry; idempotent with --force to create new version <!--hash:a9b51bbe-->
- `seed_score_configs.py` — Creates Langfuse score configs for online eval, user feedback, guardrail events; returns name→id mapping <!--hash:199750d4-->
- `sync_feedback.py` — Syncs Open WebUI thumbs-up/down ratings to Langfuse as user_feedback scores; polls every N seconds <!--hash:c34a038c-->
- `utils.py` — Shared HTTP timeout, Langfuse pagination constants, Basic auth encoding, state file serialization helpers <!--hash:01082a47-->
- `warmup_ollama.py` — Pre-loads Ollama models into memory at container start with long timeout for slow Windows Docker disks <!--hash:486d2989-->
- `worker.py` — Combined daemon running online_eval_worker, sync_feedback, build_dataset threads on configurable intervals <!--hash:bacde774-->

## tests/

- `CLAUDE.md` — Test instructions; directs to update Makefile when adding or modifying test targets <!--hash:09c1eda6-->
- `README.md` — Test guide with inventory of 12 test files, Docker dependency info, integration test auto-skip behavior <!--hash:4564fbd6-->
- `__init__.py` — Empty marker file making tests directory a Python package <!--hash:e69de29b-->
- `conftest.py` — Shared pytest fixtures; auto-skips integration tests if Docker stack at localhost:4000 unreachable <!--hash:7f665c2e-->
- `test_agent_graph.py` — Unit tests for LangGraph agent structure, routing, node presence, tool binding to LLM <!--hash:7eabb7b5-->
- `test_agent_integration.py` — E2E integration tests for ReAct agent (requires Docker); validates Q&A, model override, callbacks <!--hash:09282658-->
- `test_agent_llm.py` — Unit tests for agent model registry, service call interface, tuple return values <!--hash:3da372d2-->
- `test_agent_tool_guard.py` — Unit tests for pre-execution validation of agent tool calls, blocking forbidden tools and injection attempts. <!--hash:4bad985e-->
- `test_agent_tools.py` — Tests for agent tools (search_docs, list_traces, get_trace_detail, score_response, get_dataset_summary) with mocked Langfuse client. <!--hash:d39cbd04-->
- `test_api_routes.py` — FastAPI route tests for /health, /v1/models, /webhook, /v1/chat/completions endpoints with mocked services. <!--hash:b01edde2-->
- `test_benchmark.py` — Unit tests for NorthstarCRM benchmark loader, evaluators (retrieval, factual coverage, escalation), and CLI wiring. <!--hash:62a5227c-->
- `test_bm25_index.py` — Unit tests for BM25 retriever cache build/load, invalidation, atomicity, and Qdrant scroll pagination. <!--hash:737b06ad-->
- `test_bm25_warmup.py` — Tests for BM25 FastAPI lifespan startup, skipping when disabled or on errors like unreachable Qdrant. <!--hash:d666139e-->
- `test_chain.py` — Tests for RAG chain document formatting and system prompt, with integration tests for end-to-end queries. <!--hash:2a0e4447-->
- `test_cli.py` — CLI smoke tests for command parser recognition, missing-command exit, and dispatcher function wiring. <!--hash:0e307a7c-->
- `test_config.py` — Tests for Settings defaults and environment variable overrides for Langfuse, LiteLLM, and Qdrant config. <!--hash:44f82d8b-->
- `test_deepeval_metrics.py` — Tests for DeepEval metric factories, LiteLLMModel wrapper, and metric configuration without LLM calls. <!--hash:93655603-->
- `test_drift.py` — Unit tests for check_drift() quality regression detection across 7-day windows with threshold overrides. <!--hash:8ee89050-->
- `test_evaluators.py` — Tests for code-based evaluators: source citation detection, length bounds, hallucination markers, JSON validation. <!--hash:aff26198-->
- `test_experiments.py` — Tests for cost aggregation and token tracking across multiple models and experimental runs. <!--hash:52264663-->
- `test_guardrails.py` — Tests for custom LiteLLM guardrails: prompt injection blocking, semantic jailbreak detection, toxicity filtering, PII masking. <!--hash:4898afc8-->
- `test_hybrid_retriever.py` — Tests for hybrid vector+BM25 retriever with RRF ranking, deduplication, and OpenTelemetry span attribution. <!--hash:53eef594-->
- `test_ingest.py` — Tests for document ingestion: chunking, markdown/JSONL loading, corpus traversal, metadata preservation. <!--hash:c79875cb-->
- `test_integration.py` — Integration tests verifying full Docker stack health and LiteLLM guardrails end-to-end (requires running services). <!--hash:09cc4b72-->
- `test_red_team.py` — Unit tests for red team adversarial probe variants, attack summary aggregation, and LiteLLM proxy blocking. <!--hash:24a90db6-->
- `test_regression_gate.py` — Unit tests for regression detection: threshold checking, metric passing/failing, and CI gate reporting. <!--hash:bf438883-->
- `test_semantic_cache.py` — Tests for semantic cache (Qdrant + Redis): message embedding, similarity hits, TTL expiry, cache write/read flow. <!--hash:657a95e7-->
- `test_services.py` — Service-layer unit tests for direct_llm, rag_llm, health aggregation, webhook normalization, and ID generation. <!--hash:a2ce7b77-->

## tmp/

- `check_logs.sh` — Bash script that lists Docker container logs by size in descending order using du and sort. <!--hash:ebbe58e7-->
