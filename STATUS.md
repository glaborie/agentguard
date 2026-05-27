# Status

AgentGuard currently has no open TODO items.

## Completed Work

### Infrastructure

- Added health checks to `docker-compose.yml`
- Added container observability with Portainer and Dozzle
- Added CPU and memory resource limits for all services
- Added log rotation limits
- Set the correct timezone for containers

### API and Security

- Added LiteLLM guardrails for prompt injection and PII masking
- Made CORS configurable via settings and environment variables
- Introduced stricter Pydantic typing for API request models

### CLI

- Removed or consistently wired `--session` / `--user` across CLI commands

### Testing and Tooling

- Added test suite coverage
- Fixed stale Langfuse v4 API usage in `experiments.py`

### Documentation and Examples

- Added a sample Jupyter notebook showcasing the functionality

### Agent

- Implemented an agentic application
- Reduced technical debt in the agentic application

## Next Steps

No active work is currently tracked in this file.
