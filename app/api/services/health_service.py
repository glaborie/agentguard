import asyncio

import httpx

from app.core.config import settings

_TIMEOUT = 5.0


async def _probe(name: str, url: str, headers: dict | None = None) -> tuple[str, dict]:
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


async def check_all() -> tuple[dict, bool]:
    """Probe all three backing services. Returns (checks_dict, all_ok)."""
    results = await asyncio.gather(
        _probe("litellm", f"{settings.litellm_base_url}/health/liveliness",
               {"Authorization": f"Bearer {settings.litellm_master_key}"}),
        _probe("langfuse", f"{settings.langfuse_base_url}/api/public/health"),
        _probe("qdrant", f"{settings.qdrant_url}/healthz"),
    )
    checks = dict(results)
    all_ok = all(v["status"] == "ok" for v in checks.values())
    return checks, all_ok
