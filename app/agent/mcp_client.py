"""GitHub MCP tool loader for the AgentGuard agent.

Connects to the github-mcp sidecar via streamable HTTP (GITHUB_MCP_URL).
Host usage: set GITHUB_MCP_URL=http://localhost:8091/mcp in .env.
Docker usage: default http://github-mcp:8080/mcp resolves via bridge network.
"""

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


async def load_github_mcp_tools() -> list:
    """Return GitHub MCP tools, or empty list if token/package not configured."""
    token = settings.github_personal_access_token
    if not token:
        logger.info("GITHUB_PERSONAL_ACCESS_TOKEN not set — GitHub MCP tools disabled")
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning("langchain-mcp-adapters not installed — GitHub MCP tools disabled")
        return []

    mcp_url = settings.github_mcp_url
    if mcp_url:
        config = {
            "github": {
                "transport": "streamable_http",
                "url": mcp_url,
                "headers": {"Authorization": f"Bearer {token}"},
            }
        }
        logger.info("GitHub MCP: connecting via streamable_http to %s", mcp_url)
    else:
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
        client = MultiServerMCPClient(config)
        tools = await client.get_tools()
        logger.info("GitHub MCP tools loaded: %s", [t.name for t in tools])
        return tools
    except Exception as exc:
        logger.error("GitHub MCP client failed: %s", exc)
        return []
