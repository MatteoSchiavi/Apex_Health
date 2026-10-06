"""Small Streamable HTTP MCP client used by the COROS connector.

COROS access is delegated to an explicitly configured MCP server.  This
module speaks MCP JSON-RPC only; it has no knowledge of COROS HTTP endpoints
or OAuth.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

import httpx

MCP_PROTOCOL_VERSION = "2025-11-25"
SUPPORTED_PROTOCOL_VERSIONS = frozenset(
    {"2025-03-26", "2025-06-18", "2025-11-25"}
)
_ACCEPT = "application/json, text/event-stream"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024
MAX_TOOL_LIST_PAGES = 100
MAX_TOOL_ROWS = 10_000


class MCPError(Exception):
    """MCP endpoint, protocol, or tool invocation failure."""


@dataclass(frozen=True)
class MCPTool:
    name: str
    description: str | None
    input_schema: dict[str, Any]


class StreamableHTTPMCPClient:
    """A one-session MCP Streamable HTTP client.

    `transport` is injectable for tests.  Redirects are disabled so a bearer
    token cannot be forwarded to a different host.
    """

    def __init__(
        self,
        endpoint: str,
        *,
        bearer_token: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise MCPError("MCP endpoint must be an absolute HTTP or HTTPS URL")
        if parsed.username or parsed.password:
            raise MCPError("MCP endpoint must not contain embedded credentials")
        self.endpoint = endpoint
        self.bearer_token = bearer_token
        self.timeout = timeout
        self.transport = transport
        self.session_id: str | None = None
        self.protocol_version: str | None = None
        self._next_id = 1
        self._initialized = False

    async def initialize(self) -> dict[str, Any]:
        if self._initialized:
            return {}
        result = await self._rpc(
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "apex-health-coros", "version": "1.0"},
            },
            include_session=False,
            include_protocol=False,
        )
        if not isinstance(result, dict):
            raise MCPError("MCP initialize returned an invalid result")
        negotiated = result.get("protocolVersion")
        if not isinstance(negotiated, str):
            raise MCPError("MCP initialize did not return a protocol version")
        if negotiated not in SUPPORTED_PROTOCOL_VERSIONS:
            raise MCPError("MCP server negotiated an unsupported protocol version")
        self.protocol_version = negotiated
        self._initialized = True
        await self._notify("notifications/initialized")
        return result

    async def list_tools(self) -> list[MCPTool]:
        await self.initialize()
        rows: list[Any] = []
        cursor: str | None = None
        seen_cursors: set[str] = set()
        pages = 0
        while True:
            pages += 1
            if pages > MAX_TOOL_LIST_PAGES:
                raise MCPError("MCP tools/list exceeded the page limit")
            params = {"cursor": cursor} if cursor is not None else {}
            result = await self._rpc("tools/list", params)
            page_rows = result.get("tools") if isinstance(result, dict) else None
            if not isinstance(page_rows, list):
                raise MCPError("MCP tools/list returned an invalid result")
            rows.extend(page_rows)
            if len(rows) > MAX_TOOL_ROWS:
                raise MCPError("MCP tools/list exceeded the tool limit")
            next_cursor = result.get("nextCursor")
            if not next_cursor:
                break
            if not isinstance(next_cursor, str) or next_cursor in seen_cursors:
                raise MCPError("MCP tools/list returned an invalid pagination cursor")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        tools: list[MCPTool] = []
        for row in rows:
            if not isinstance(row, dict) or not isinstance(row.get("name"), str):
                continue
            schema = row.get("inputSchema")
            if not isinstance(schema, dict):
                raise MCPError(f"MCP tool {row['name']!r} has no input schema")
            tools.append(
                MCPTool(
                    name=row["name"],
                    description=row.get("description") if isinstance(row.get("description"), str) else None,
                    input_schema=schema,
                )
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if not name or not isinstance(arguments, dict):
            raise MCPError("MCP tool name and object arguments are required")
        tools = await self.list_tools()
        tool = next((item for item in tools if item.name == name), None)
        if tool is None:
            raise MCPError(f"Selected MCP tool {name!r} is not offered by the server")
        _validate_arguments(tool.input_schema, arguments, name)
        result = await self._rpc("tools/call", {"name": name, "arguments": arguments})
        if not isinstance(result, dict):
            raise MCPError(f"MCP tool {name!r} returned an invalid result")
        if result.get("isError"):
            raise MCPError(f"MCP tool {name!r} reported an error")
        return result

    async def _notify(self, method: str) -> None:
        headers = self._headers()
        if self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        if self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport, follow_redirects=False
            ) as client:
                async with client.stream(
                    "POST",
                    self.endpoint,
                    headers=headers,
                    json={"jsonrpc": "2.0", "method": method},
                ) as response:
                    if response.status_code not in {200, 202, 204}:
                        raise MCPError(f"MCP notification returned HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            raise MCPError("MCP notification transport request failed") from exc

    async def _rpc(
        self,
        method: str,
        params: dict[str, Any],
        *,
        include_session: bool = True,
        include_protocol: bool = True,
    ) -> Any:
        request_id = self._next_id
        self._next_id += 1
        headers = self._headers()
        if include_session and self.session_id:
            headers["MCP-Session-Id"] = self.session_id
        if include_protocol and self.protocol_version:
            headers["MCP-Protocol-Version"] = self.protocol_version
        body = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, transport=self.transport, follow_redirects=False
            ) as client:
                async with client.stream(
                    "POST", self.endpoint, headers=headers, json=body
                ) as response:
                    if response.status_code >= 400:
                        raise MCPError(f"MCP {method} returned HTTP {response.status_code}")
                    session_id = response.headers.get("MCP-Session-Id")
                    if session_id:
                        self.session_id = session_id
                    payload = await _read_rpc_response(response, request_id)
        except httpx.HTTPError as exc:
            # Do not include upstream exception text: some servers echo bearer
            # tokens or account data into response/transport diagnostics.
            raise MCPError(f"MCP {method} transport request failed") from exc
        if not isinstance(payload, dict) or payload.get("id") != request_id:
            raise MCPError(f"MCP {method} returned an invalid JSON-RPC response")
        if "error" in payload:
            raise MCPError(f"MCP {method} returned a JSON-RPC error")
        if "result" not in payload:
            raise MCPError(f"MCP {method} response is missing a result")
        return payload["result"]

    def _headers(self) -> dict[str, str]:
        headers = {"Accept": _ACCEPT, "Content-Type": "application/json"}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return headers


async def _read_rpc_response(response: httpx.Response, request_id: int) -> Any:
    """Read bounded JSON or return as soon as the matching SSE event arrives."""
    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    length = response.headers.get("content-length")
    if length:
        try:
            if int(length) > MAX_RESPONSE_BYTES:
                raise MCPError("MCP response exceeded the size limit")
        except ValueError:
            pass

    if content_type in {"application/json", ""}:
        buffer = bytearray()
        async for chunk in response.aiter_bytes():
            buffer.extend(chunk)
            if len(buffer) > MAX_RESPONSE_BYTES:
                raise MCPError("MCP response exceeded the size limit")
        try:
            return json.loads(buffer)
        except (ValueError, UnicodeDecodeError) as exc:
            raise MCPError("MCP endpoint returned invalid JSON") from exc

    if content_type != "text/event-stream":
        raise MCPError("MCP endpoint returned an unsupported content type")

    total = 0
    pending = bytearray()
    data_lines: list[str] = []
    async for chunk in response.aiter_bytes():
        total += len(chunk)
        if total > MAX_RESPONSE_BYTES:
            raise MCPError("MCP response exceeded the size limit")
        pending.extend(chunk)
        while True:
            newline = pending.find(b"\n")
            if newline < 0:
                break
            raw_line = bytes(pending[:newline])
            del pending[: newline + 1]
            if raw_line.endswith(b"\r"):
                raw_line = raw_line[:-1]
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise MCPError("MCP event stream contained invalid UTF-8") from exc
            if line == "":
                if data_lines:
                    payload = _parse_sse_data(data_lines)
                    data_lines.clear()
                    if isinstance(payload, dict) and payload.get("id") == request_id:
                        return payload
                continue
            if line.startswith("data:"):
                data_lines.append(line[5:].lstrip(" "))
    raise MCPError("MCP event stream ended before the matching response")


def _parse_sse_data(lines: list[str]) -> Any:
    try:
        return json.loads("\n".join(lines))
    except ValueError:
        return None


def _validate_arguments(schema: dict[str, Any], arguments: dict[str, Any], tool_name: str) -> None:
    """Validate the JSON Schema subset relevant to MCP tool arguments."""
    if schema.get("type") not in (None, "object"):
        raise MCPError(f"MCP tool {tool_name!r} does not accept an object schema")
    properties = schema.get("properties")
    properties = properties if isinstance(properties, dict) else {}
    required = schema.get("required")
    required = required if isinstance(required, list) else []
    missing = [key for key in required if isinstance(key, str) and key not in arguments]
    if missing:
        raise MCPError(f"MCP tool {tool_name!r} requires arguments: {', '.join(missing)}")
    if schema.get("additionalProperties") is False:
        unknown = sorted(set(arguments) - set(properties))
        if unknown:
            raise MCPError(f"MCP tool {tool_name!r} does not accept: {', '.join(unknown)}")
    for key, value in arguments.items():
        property_schema = properties.get(key)
        if not isinstance(property_schema, dict):
            continue
        expected = property_schema.get("type")
        if expected == "string" and not isinstance(value, str):
            raise MCPError(f"MCP tool argument {key!r} must be a string")
        if expected == "integer" and (not isinstance(value, int) or isinstance(value, bool)):
            raise MCPError(f"MCP tool argument {key!r} must be an integer")
        if expected == "number" and (not isinstance(value, (int, float)) or isinstance(value, bool)):
            raise MCPError(f"MCP tool argument {key!r} must be numeric")
        if expected == "boolean" and not isinstance(value, bool):
            raise MCPError(f"MCP tool argument {key!r} must be a boolean")
        if expected == "array" and not isinstance(value, list):
            raise MCPError(f"MCP tool argument {key!r} must be an array")
        if expected == "object" and not isinstance(value, dict):
            raise MCPError(f"MCP tool argument {key!r} must be an object")
