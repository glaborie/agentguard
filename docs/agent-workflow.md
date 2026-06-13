# Agent workflow

<!-- markdownlint-disable MD013 MD060 -->

Beyond simple RAG, AgentGuard includes a LangGraph-powered agentic workflow that reasons about which tools to use.

## Available tools

| Tool | What it does |
|---|---|
| `search_docs` | Search the Qdrant knowledge base |
| `list_traces` | List recent Langfuse traces (ID, latency, input/output preview) |
| `get_trace_detail` | Drill into a specific trace with full observation tree |
| `score_response` | Run code-based evaluators on any text |
| `get_dataset_summary` | List datasets or inspect dataset items |

## Example usage

The agent can answer complex questions that require multiple tool calls.

```bash
python -m app.main agent "How is my RAG system performing?"
python -m app.main agent "What were my slowest queries?"
python -m app.main agent-chat --session demo
```

In practice, this lets the system combine document search, trace inspection, response scoring, and dataset inspection in a single workflow.

## Tool-call guardrails

Every tool call passes through `app/agent/tool_guard.py` before execution. The guard enforces:

- **Allowlist** — only the 5 registered tools above can be called; any other tool name is blocked.
- **Injection check on `search_docs`** — queries are scanned for 10 injection patterns (subset of the LiteLLM `PromptInjectionGuard`) before the retriever runs.
- **Bounds check on `list_traces`** — `limit` must be an integer between 0 and 50.

Blocked calls return a `ToolMessage` error so the agent can reason about the refusal rather than crashing. The guard has 23 dedicated unit tests in `tests/test_agent_tool_guard.py`.
