"""COROS data access through a configured MCP server only."""

from __future__ import annotations

import json
from typing import Any

from app.connectors.coros.mcp import MCPError, StreamableHTTPMCPClient
from app.core.config import get_settings

SOURCE = "coros"


class CorosAuthError(Exception):
    """MCP access credentials or server configuration are unavailable."""


def build_live_client(credentials: dict | None) -> "CorosClient":
    if not isinstance(credentials, dict) or not credentials.get("mcp_access_token"):
        raise CorosAuthError("No account-scoped COROS MCP credential is stored")
    settings = get_settings()
    endpoint = getattr(settings, "coros_mcp_url", "")
    if not endpoint:
        raise CorosAuthError("COROS MCP server URL is not configured")
    activity_tool = getattr(settings, "coros_mcp_activity_tool", "")
    if not activity_tool:
        raise CorosAuthError("COROS MCP activity tool is not configured")
    try:
        arguments = json.loads(getattr(settings, "coros_mcp_activity_args", "{}") or "{}")
    except (TypeError, ValueError) as exc:
        raise CorosAuthError("COROS MCP activity arguments are invalid JSON") from exc
    if not isinstance(arguments, dict):
        raise CorosAuthError("COROS MCP activity arguments must be a JSON object")
    try:
        timeout = float(getattr(settings, "coros_mcp_timeout_seconds", 30))
    except (TypeError, ValueError):
        timeout = 30.0
    return CorosClient(
        endpoint,
        bearer_token=str(credentials["mcp_access_token"]),
        activity_tool=activity_tool,
        activity_arguments=arguments,
        timeout=timeout,
    )


class CorosClient:
    """Account-authenticated MCP client for one explicitly selected tool."""

    def __init__(
        self,
        endpoint: str,
        *,
        bearer_token: str,
        activity_tool: str,
        activity_arguments: dict[str, Any],
        timeout: float = 30.0,
    ) -> None:
        self.activity_tool = activity_tool
        self.activity_arguments = activity_arguments
        try:
            self.mcp = StreamableHTTPMCPClient(
                endpoint, bearer_token=bearer_token, timeout=timeout
            )
        except MCPError as exc:
            raise CorosAuthError(str(exc)) from exc

    async def fetch_activities(self) -> dict[str, Any]:
        try:
            return await self.mcp.call_tool(self.activity_tool, self.activity_arguments)
        except MCPError:
            raise


# Legacy OAuth symbols remain import-compatible while the API is migrated.
# They intentionally cannot issue a request to COROS or construct direct URLs.
def build_authorize_url(state: str) -> str:
    del state
    raise CorosAuthError("COROS uses the configured MCP connection flow, not COROS OAuth")


async def exchange(code: str) -> Any:
    del code
    raise CorosAuthError("COROS uses the configured MCP connection flow, not COROS OAuth")
