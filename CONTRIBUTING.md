# Contributing to AgentGuard

Thanks for your interest in contributing to AgentGuard.

AgentGuard is a self-hosted AI reliability platform for RAG and agentic applications, with a focus on observability, protection, evaluation, and operational confidence. We welcome contributions that improve the platform’s reliability, usability, developer experience, and production readiness.

## How to contribute

There are many ways to contribute:

- report bugs
- suggest features or product improvements
- improve documentation
- add or improve tests
- fix issues
- propose architecture or developer-experience improvements

If you are unsure whether a change is a good fit, open an issue first to discuss it.

## Before you start

Please:

- search existing issues and pull requests before opening a new one
- keep changes focused and scoped
- prefer incremental pull requests over very large ones
- include tests when changing behavior
- update documentation when introducing user-visible changes

## Development setup

### Prerequisites

To run AgentGuard locally, you typically need:

- Docker with Compose v2
- Python 3.13+
- approximately 15 GB RAM allocated to Docker
- optional: NVIDIA GPU and drivers for Ollama GPU acceleration

### Initial setup

```bash
cp .env.example .env
docker compose up -d
pip install -r requirements.txt
python -m app.main ingest
```

### Useful commands

Run the unit test suite:

```bash
pytest -m "not integration"
```

Run integration tests:

```bash
pytest -m integration
```

Run the full test suite:

```bash
pytest -v
```

Start the platform locally:

```bash
docker compose up -d
```

Test the RAG flow:

```bash
python -m app.main query "Does the Starter plan include SAML SSO?"
```

Test the agentic flow:

```bash
python -m app.main agent "How is my RAG system performing?"
```

## Contribution guidelines

### Code quality

Please aim for contributions that are:

- clear and maintainable
- well-scoped
- tested
- consistent with the existing project structure and naming
- documented when behavior changes

### Tests

If your change affects behavior, add or update tests whenever practical.

Examples:
- bug fix -> add a regression test
- new feature -> add happy-path and failure-path coverage
- refactor -> preserve or improve existing coverage

Prefer fast unit tests unless the change specifically requires integration coverage.

### Documentation

Please update relevant documentation when changing:

- setup steps
- CLI behavior
- API behavior
- configuration
- architecture or workflow expectations
- guardrails, evaluations, or telemetry behavior

### Pull requests

When submitting a pull request:

- explain the problem being solved
- describe the approach taken
- keep the PR focused on a single concern where possible
- link related issues if applicable
- call out any tradeoffs or follow-up work
- include screenshots or logs when UI or operational behavior changes

A good PR makes it easy to answer:
- what changed?
- why did it change?
- how was it tested?
- what should reviewers pay attention to?

## Areas where contributions are especially welcome

Contributions are especially valuable in areas such as:

- documentation and onboarding
- cloud deployment support
- evaluation workflows and benchmark tooling
- observability improvements
- guardrails and protection policies
- developer experience and local setup
- test coverage and CI reliability
- integrations with adjacent AI tooling

## Reporting bugs

When reporting a bug, please include as much of the following as possible:

- what you expected to happen
- what actually happened
- steps to reproduce
- environment details
- relevant logs, traces, screenshots, or error messages
- whether the issue is reproducible

## Suggesting features

Feature suggestions are welcome. Please describe:

- the user problem
- why it matters
- the proposed behavior
- any relevant alternatives considered
- whether the request is product, platform, or developer-experience related

## Security issues

Please do not report security vulnerabilities in public issues.

If you discover a vulnerability, please contact the maintainer privately through an appropriate responsible-disclosure channel.

## Licensing

By contributing to this repository, you agree that your contributions will be licensed under the Apache License, Version 2.0.

## Code of conduct

Please be respectful, constructive, and collaborative in all interactions.

## Maintainer discretion

To keep the project coherent and maintainable, maintainers may decline contributions that do not align with the project roadmap, architecture, or quality bar. Discussion is always welcome before substantial work begins.

Thank you for helping improve AgentGuard.
