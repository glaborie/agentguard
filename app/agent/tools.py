"""Agent tools for the AgentGuard ReAct agent."""

import json
from datetime import datetime

from langchain_core.tools import tool

from app.eval.evaluators import (
    contains_no_hallucination_markers,
    has_source_citation,
    is_within_length,
)
from app.rag.chain import format_docs, get_retriever
from app.tracing import get_langfuse_client
from app.utils import truncate as _truncate


@tool
def search_docs(query: str) -> str:
    """Search the NorthstarCRM knowledge base.

    Use this for questions about NorthstarCRM products, pricing, plans,
    policies, sales processes, integrations, and support topics.

    Args:
        query: The search query describing what you want to find.
    """
    retriever = get_retriever(k=6)
    docs = retriever.invoke(query)
    if not docs:
        return "No relevant documents found for that query."
    return format_docs(docs)


@tool
def list_traces(limit: int = 10) -> str:
    """List recent traces from Langfuse.

    Use this to see recent system activity — what questions were asked,
    how long they took, and when they happened.

    Args:
        limit: Number of traces to return (default 10, max 50).
    """
    limit = min(max(1, limit), 50)
    client = get_langfuse_client()
    # Fetch a larger batch so filtering system calls doesn't shrink the result below limit
    fetch_size = min(limit * 4, 100)
    response = client.api.trace.list(limit=fetch_size)
    traces = response.data

    if not traces:
        return "No traces found."

    lines = []
    for t in traces:
        if len(lines) >= limit:
            break
        input_str = str(t.input or "")
        # Skip Open WebUI internal system calls (same filter as online eval worker)
        if input_str.startswith("### Task:"):
            continue
        trace_id = t.id or "unknown"
        ts = t.timestamp.strftime("%Y-%m-%d %H:%M") if isinstance(t.timestamp, datetime) else str(t.timestamp or "")
        input_preview = _truncate(input_str, 80)
        output_preview = _truncate(str(t.output or ""), 80)
        # t.latency from the list endpoint equals (now - createdAt) for unclosed traces,
        # not execution time. Cap at 120s to avoid surfacing stale-trace ages as durations.
        latency = f"{t.latency:.1f}s" if t.latency is not None and t.latency <= 120 else "n/a"
        lines.append(
            f"- [{trace_id}] {ts} | latency: {latency}\n"
            f"  input:  {input_preview}\n"
            f"  output: {output_preview}"
        )

    if not lines:
        return "No user traces found (only internal system calls in this window)."
    return f"Found {len(lines)} recent trace(s):\n\n" + "\n".join(lines)


@tool
def get_trace_detail(trace_id: str) -> str:
    """Get full details for a specific trace by ID.

    Use this after list_traces to drill into a specific trace and see
    its observation tree, token usage, and scores.

    Args:
        trace_id: The trace ID (or prefix) from list_traces output.
    """
    client = get_langfuse_client()
    try:
        trace = client.api.trace.get(trace_id)
    except Exception as e:
        return f"Error fetching trace {trace_id}: {e}"

    lines = [
        f"Trace: {trace.id}",
        f"Name: {trace.name or 'unnamed'}",
        f"Timestamp: {trace.timestamp}",
        f"Latency: {trace.latency:.1f}s" if trace.latency else "Latency: n/a",
        f"Input: {_truncate(str(trace.input or ''), 200)}",
        f"Output: {_truncate(str(trace.output or ''), 200)}",
    ]

    if trace.scores:
        lines.append("\nScores:")
        for s in trace.scores:
            lines.append(f"  - {s.name}: {s.value}")

    observations = trace.observations or []
    if observations:
        lines.append(f"\nObservations ({len(observations)}):")
        for obs in observations:
            obs_type = obs.type or "span"
            obs_name = obs.name or "unnamed"
            obs_latency = f"{obs.latency:.1f}s" if obs.latency else "n/a"
            model = obs.model or ""
            tokens = ""
            if obs.usage:
                tokens = f" | tokens: {obs.usage.input or 0} in / {obs.usage.output or 0} out"
            lines.append(f"  [{obs_type}] {obs_name} ({obs_latency}){' | model: ' + model if model else ''}{tokens}")

    return "\n".join(lines)


@tool
def score_response(response_text: str) -> str:
    """Run code-based quality evaluators on a response string.

    Checks for source citations, response length, and hallucination markers.
    Use this to quickly assess the quality of any AI-generated text.

    Args:
        response_text: The text to evaluate.
    """
    scores = {
        "has_source_citation": has_source_citation(response_text),
        "is_within_length": is_within_length(response_text),
        "no_hallucination_markers": contains_no_hallucination_markers(response_text),
    }
    passed = sum(1 for v in scores.values() if v)
    total = len(scores)
    result = {
        "summary": f"{passed}/{total} checks passed",
        "scores": scores,
    }
    return json.dumps(result, indent=2)


@tool
def get_dataset_summary(dataset_name: str = "") -> str:
    """List available Langfuse datasets, or show items from a specific dataset.

    Use this to review what evaluation datasets exist and what test cases
    they contain.

    Args:
        dataset_name: If provided, show items from this dataset. If empty, list all datasets.
    """
    client = get_langfuse_client()

    if not dataset_name:
        try:
            response = client.api.datasets.list()
            datasets = response.data
        except Exception as e:
            return f"Error fetching datasets: {e}"

        if not datasets:
            return "No datasets found. Create one in the Langfuse UI or via the API."

        lines = ["Available datasets:\n"]
        for ds in datasets:
            lines.append(f"- {ds.name} (items: {ds.items_count if hasattr(ds, 'items_count') else 'unknown'})")
        return "\n".join(lines)

    try:
        dataset = client.get_dataset(dataset_name)
    except Exception as e:
        return f"Error fetching dataset '{dataset_name}': {e}"

    items = dataset.items or []
    if not items:
        return f"Dataset '{dataset_name}' exists but has no items."

    lines = [f"Dataset '{dataset_name}' — {len(items)} item(s):\n"]
    for i, item in enumerate(items[:10]):
        input_text = _truncate(str(item.input or {}), 100)
        expected = _truncate(str(item.expected_output or ""), 100)
        lines.append(f"  {i+1}. input: {input_text}")
        if expected:
            lines.append(f"     expected: {expected}")
    if len(items) > 10:
        lines.append(f"  ... and {len(items) - 10} more items")
    return "\n".join(lines)


ALL_TOOLS = [search_docs, list_traces, get_trace_detail, score_response, get_dataset_summary]
