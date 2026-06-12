import asyncio
import time

import httpx

from app.core.config import settings

_TIMEOUT = 5.0
_CACHE_TTL = 20.0  # seconds — prevents probe fan-out on rapid health polls

_cached_checks: dict[str, dict[str, str]] | None = None
_cached_at: float = 0.0


async def _probe(
    name: str, url: str, headers: dict[str, str] | None = None
) -> tuple[str, dict[str, str]]:
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.get(url, headers=headers or {})
            r.raise_for_status()
        return name, {"status": "ok"}
    except httpx.TimeoutException:
        return name, {"status": "error", "error": "timeout"}
    except httpx.HTTPStatusError as e:
        return name, {"status": "error", "error": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return name, {"status": "error", "error": str(e)}


async def check_all() -> tuple[dict[str, dict[str, str]], bool]:
    """Probe all backing services. Results cached for _CACHE_TTL seconds."""
    global _cached_checks, _cached_at
    now = time.monotonic()
    if _cached_checks is not None and _cached_at + _CACHE_TTL > now:
        return _cached_checks, all(v["status"] == "ok" for v in _cached_checks.values())

    results = await asyncio.gather(
        _probe("litellm", f"{settings.litellm_base_url}/health/liveliness",
               {"Authorization": f"Bearer {settings.litellm_master_key}"}),
        _probe("langfuse", f"{settings.langfuse_base_url}/api/public/health"),
        _probe("qdrant", f"{settings.qdrant_url}/healthz"),
    )
    _cached_checks = dict(results)
    _cached_at = now
    return _cached_checks, all(v["status"] == "ok" for v in _cached_checks.values())
