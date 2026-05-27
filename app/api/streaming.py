import json
import time
from typing import AsyncGenerator, Optional


async def stream_from_result(
    result: str,
    completion_id: str,
    model_name: str,
) -> AsyncGenerator[str, None]:
    """Stream a pre-computed (already PII-masked) result as SSE chunks."""
    yield _sse(completion_id, model_name, {"role": "assistant", "content": ""})
    yield _sse(completion_id, model_name, {"content": result})
    yield _sse(completion_id, model_name, {}, finish_reason="stop")
    yield "data: [DONE]\n\n"


def _sse(
    completion_id: str,
    model: str,
    delta: dict,
    finish_reason: Optional[str] = None,
) -> str:
    payload = {
        "id": completion_id,
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    return f"data: {json.dumps(payload)}\n\n"
