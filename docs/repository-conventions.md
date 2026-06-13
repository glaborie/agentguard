# Repository Conventions

<!-- markdownlint-disable MD013 -->

This document defines naming and location conventions to keep repository structure predictable and reduce documentation drift.

## Compose files

- Canonical pattern: `docker-compose.<purpose>.yml`
- Main stack stays at `docker-compose.yml`
- Infrastructure stack stays at `docker-compose.infra.yml`
- LiteLLM-only stack should use `docker-compose.litellm.yml`
- Backward-compatible legacy alias: `compose-litellm.yml` (do not add new references)

## Documentation structure

- Keep user-facing docs under `docs/`
- Keep deployment docs under `docs/deployment/`
- Keep architecture/evaluation workflow docs in `docs/`
- Avoid duplicating complete guides across root and `docs/`; prefer one canonical page and links to it

## Documentation assets

- Store screenshots and static image assets under `docs/assets/`
- Current screenshot path: `docs/assets/screenshots/`
- Do not store long-lived docs assets in ad hoc root folders

## Naming conventions

- Use lowercase kebab-case for new markdown and YAML files unless ecosystem conventions require otherwise
- Keep script names in snake_case for Python modules
- Use explicit purpose suffixes for config files (`*.config.yml`, `*-config.yml`) when possible

## Cleanup candidates (tracked but not changed here)

- Consolidate overlap between `DEPLOYMENT.md` and `docs/deployment/local.md`
- Decide retention policy for generated benchmark artifacts in `notebooks/`
- Regenerate `FILETREE.md` after structural changes
