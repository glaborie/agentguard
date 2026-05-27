## Done

### Infrastructure

- [x] Add health checks to `docker-compose.yml`
- [x] Add container observability with Portainer and Dozzle
- [x] Add CPU and memory resource limits for all services
- [x] Add log rotation limits
- [x] Set the correct timezone for containers

### API and Security

- [x] Add LiteLLM guardrails for prompt injection and PII masking
- [x] Make CORS configurable via settings and environment variables
- [x] Introduce stricter Pydantic typing for API request models

### CLI

- [x] Remove or consistently wire `--session` / `--user` across CLI commands

### Testing and Tooling

- [x] Add test suite (82 unit tests, 12 integration tests)
- [x] Fix stale Langfuse v4 API usage in `experiments.py`

### Documentation and Examples

- [x] Add a sample Jupyter notebook showcasing the functionality

### Agent

- [x] Implement an agentic application
- [x] Reduce technical debt in the agentic application

## Next

_No open TODO items right now._
