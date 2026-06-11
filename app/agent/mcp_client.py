"""Async context manager that provides GitHub MCP tools via langchain-mcp-adapters.

Usage:
    async with github_mcp_tools() as tools:
        # tools is a list[BaseTool] — empty when token not configured
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

    config = {
        "github": {
            "command": "npx",
            "args": ["-y", "@modelcontextprotocol/server-github"],
            "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": token},
            "transport": "stdio",
        }
    }

    try:
        async with MultiServerMCPClient(config) as client:
            tools = client.get_tools()
            logger.info("GitHub MCP tools loaded: %s", [t.name for t in tools])
            yield tools
    except Exception as exc:
        logger.error("GitHub MCP client failed to start: %s", exc)
        yield []
