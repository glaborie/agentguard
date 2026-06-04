.DEFAULT_GOAL := help
PYTEST        := pytest
COV_FLAGS     := --cov=app --cov=guardrails --cov-report=term-missing

# ── helpers ──────────────────────────────────────────────────────────────────
.PHONY: help
help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Test targets:"
	@awk 'BEGIN {FS = ":.*##"} /^[a-zA-Z_-]+:.*##/ { printf "  %-28s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ── unit tests (no Docker required) ─────────────────────────────────────────
.PHONY: test
test: ## Run all unit tests (excludes integration)
	$(PYTEST) -m "not integration" -v

.PHONY: test-cov
test-cov: ## Run unit tests with coverage report
	$(PYTEST) -m "not integration" $(COV_FLAGS)

# ── integration tests (Docker stack must be running) ─────────────────────────
.PHONY: test-integration
test-integration: ## Run integration tests (requires live Docker stack)
	$(PYTEST) -m integration -v

.PHONY: test-all
test-all: ## Run the full test suite (unit + integration)
	$(PYTEST) -v

.PHONY: test-all-cov
test-all-cov: ## Run full test suite with coverage report
	$(PYTEST) $(COV_FLAGS)

# ── per-module targets ────────────────────────────────────────────────────────
.PHONY: test-agent
test-agent: ## Run agent tests (graph, tools, tool_guard, agent integration)
	$(PYTEST) tests/test_agent_graph.py tests/test_agent_tools.py \
	          tests/test_agent_tool_guard.py tests/test_agent_integration.py -v

.PHONY: test-rag
test-rag: ## Run RAG pipeline tests (chain, ingest)
	$(PYTEST) tests/test_chain.py tests/test_ingest.py -v

.PHONY: test-api
test-api: ## Run API route and service tests
	$(PYTEST) tests/test_api_routes.py tests/test_services.py -v

.PHONY: test-eval
test-eval: ## Run evaluation tests (evaluators, deepeval, regression gate, benchmark)
	$(PYTEST) tests/test_evaluators.py tests/test_deepeval_metrics.py \
	          tests/test_regression_gate.py tests/test_benchmark.py -v

.PHONY: test-guardrails
test-guardrails: ## Run guardrail and semantic cache tests
	$(PYTEST) tests/test_guardrails.py tests/test_semantic_cache.py -v

.PHONY: test-cli
test-cli: ## Run CLI tests
	$(PYTEST) tests/test_cli.py -v

.PHONY: test-config
test-config: ## Run config tests
	$(PYTEST) tests/test_config.py -v

# ── convenience ───────────────────────────────────────────────────────────────
.PHONY: test-fast
test-fast: ## Run unit tests in parallel with minimal output (requires pytest-xdist)
	$(PYTEST) -m "not integration" -q --tb=short -n auto

.PHONY: test-file
test-file: ## Run a single test file:  make test-file FILE=tests/test_chain.py
	$(PYTEST) $(FILE) -v

.PHONY: test-k
test-k: ## Run tests matching a keyword:  make test-k K=retriever
	$(PYTEST) -k "$(K)" -v
