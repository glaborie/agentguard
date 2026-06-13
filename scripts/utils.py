import base64
import json
import logging
from pathlib import Path

from app.config import settings

# Shared HTTP timeout for all outbound calls to local Docker services.
HTTP_TIMEOUT = settings.http_timeout_seconds

# Langfuse API page sizes.
TRACE_PAGE_SIZE = 50
SCORE_PAGE_SIZE = 100

logger = logging.getLogger(__name__)


def langfuse_basic_auth() -> str:
    """Return the Basic auth header value for direct Langfuse REST calls."""
    return base64.b64encode(
        f"{settings.langfuse_public_key}:{settings.langfuse_secret_key}".encode()
    ).decode()


def load_state(state_file: Path) -> set[str]:
    """Load a set of seen IDs from a JSON state file.

    Returns an empty set (and deletes the corrupt file) if the file exists but
    cannot be parsed, so the worker restarts cleanly instead of crashing.
    """
    if not state_file.exists():
        return set()
    try:
        data = json.loads(state_file.read_text())
        if not isinstance(data, list):
            raise ValueError(f"expected list, got {type(data).__name__}")
        return set(data)
    except Exception as exc:
        logger.warning(
            "State file %s is corrupt (%s) — resetting to empty.", state_file, exc
        )
        state_file.unlink(missing_ok=True)
        return set()


def save_state(state_file: Path, seen: set[str]) -> None:
    """Persist a set of seen IDs to a JSON state file."""
    state_file.write_text(json.dumps(sorted(seen)))
