"""Pre-execution guardrail for agent tool calls.

validate_tool_call() is called before ToolNode dispatches each tool.
Raises ToolCallBlockedError on policy violation; callers convert to ToolMessage.
"""

import re

_TOOL_ALLOWLIST = frozenset({
    "search_docs",
    "list_traces",
    "get_trace_detail",
    "score_response",
    "get_dataset_summary",
})

# Dynamically extended at runtime when MCP tools are loaded
_MCP_TOOL_ALLOWLIST: set[str] = set()


def register_mcp_tools(tool_names: list[str]) -> None:
    """Register MCP tool names so the guard allows them through."""
    _MCP_TOOL_ALLOWLIST.update(tool_names)

_LIST_TRACES_MAX_LIMIT = 50

# Injection patterns scoped to search queries — subset of PromptInjectionGuard patterns
# that are meaningful when embedded in a retrieval query string.
_QUERY_INJECTION_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"ignore (?:all |any )?(?:previous|prior|above) (?:instructions|prompts|rules)",
        r"disregard (?:all |any )?(?:previous|prior|above)",
        r"forget (?:all |any )?(?:previous|prior|your)",
        r"(?:give|show|reveal|print|display|output|repeat|tell)\b.*\b(?:system\s*prompt|instructions|rules)",
        r"\bsystem\s*prompt\b",
        r"\byour\s+(?:instructions|rules|guidelines|directives|constraints|configuration|prompt)\b",
        r"jailbreak",
        r"do anything now",
        r"developer mode",
        r"(?-i:DAN)\b",
    ]
]


class ToolCallBlockedError(Exception):
    """Raised when a tool call violates the pre-execution policy."""


def validate_tool_call(tool_name: str, tool_args: dict) -> None:
    """Validate a pending tool call before execution.

    Raises ToolCallBlockedError if the call violates policy.
    All legitimate AgentGuard tool calls pass through unchanged.
    """
    if tool_name not in _TOOL_ALLOWLIST and tool_name not in _MCP_TOOL_ALLOWLIST:
        raise ToolCallBlockedError(
            f"Tool '{tool_name}' is not in allowlist. "
            f"Allowed tools: {sorted(_TOOL_ALLOWLIST | _MCP_TOOL_ALLOWLIST)}"
        )

    if tool_name == "search_docs":
        _validate_search_docs(tool_args)

    if tool_name == "list_traces":
        _validate_list_traces(tool_args)


def _validate_search_docs(tool_args: dict) -> None:
    query = tool_args.get("query", "")
    if not isinstance(query, str):
        return
    for pattern in _QUERY_INJECTION_PATTERNS:
        match = pattern.search(query)
        if match:
            raise ToolCallBlockedError(
                f"search_docs blocked: injection pattern detected in query: '{match.group()}'"
            )


def _validate_list_traces(tool_args: dict) -> None:
    limit = tool_args.get("limit", 10)
    if limit is None:
        return
    if not isinstance(limit, int):
        raise ToolCallBlockedError(
            f"list_traces blocked: limit must be an integer, got {type(limit).__name__}"
        )
    if limit < 0 or limit > _LIST_TRACES_MAX_LIMIT:
        raise ToolCallBlockedError(
            f"list_traces blocked: limit {limit} out of range [0, {_LIST_TRACES_MAX_LIMIT}]"
        )
