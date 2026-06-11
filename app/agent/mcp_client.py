"""Async context manager that provides GitHub MCP tools via langchain-mcp-adapters.

In Docker: connects to the github-mcp sidecar via SSE (GITHUB_MCP_URL).
On host:   spawns npx subprocess via stdio (requires Node.js).

Usage:
    async with github_mcp_tools() as tools:
        # tools is list[BaseTool] — empty when token not configured
        graph = build_agent(extra_tools=tools)
        result = await graph.ainvoke(...)
"""

import logging
from contextlib import asynccontextmanager

from app.config import settings

logger = logging.getLogger(__name__)


@asynccontextmanager
async def github_mcp_tools():
    """Yield GitHub MCP tools if GITHUB_PERSONAL_ACCESS_TOKEN is configured."""
    token = settings.github_personal_access_token
    if not token:
        logger.info("GITHUB_PERSONAL_ACCESS_TOKEN not set — GitHub MCP tools disabled")
        yield []
        return

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed — GitHub MCP tools disabled")
        yield []
        return

    mcp_url = settings.github_mcp_url
    if mcp_url:
        # Docker mode: connect to github-mcp sidecar via SSE
        config = {
            "github": {
                "transport": "sse",
                "url": mcp_url,
            }
        }
        logger.info("GitHub MCP: connecting via SSE to %s", mcp_url)
    else:
        # Local dev mode: spawn subprocess via stdio (requires Node.js)
        config = {
            "github": {
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-github"],
                "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": token},
                "transport": "stdio",
            }
        }
        logger.info("GitHub MCP: spawning stdio subprocess")

    try:
        async with MultiServerMCPClient(config) as client:
            tools = client.get_tools()
            logger.info("GitHub MCP tools loaded: %s", [t.name for t in tools])
            yield tools
    except Exception as exc:
        logger.error("GitHub MCP client failed: %s", exc)
        yield []
