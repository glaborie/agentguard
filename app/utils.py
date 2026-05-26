def truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def extract_trace_output(trace) -> str | None:
    """Normalise a Langfuse trace's output field to a plain string."""
    raw = trace.output
    if raw is None:
        return None
    if isinstance(raw, str):
        return raw
    if isinstance(raw, dict):
        return raw.get("output") or raw.get("text") or str(raw)
    return str(raw)
