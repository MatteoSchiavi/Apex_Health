import asyncio
import json

import httpx
import pytest

from app.connectors.coros import mcp
from app.connectors.coros.mcp import MCPError, StreamableHTTPMCPClient, _read_rpc_response


@pytest.mark.asyncio
async def test_streamable_http_initializes_lists_and_calls_selected_tool():
    seen = []

    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        seen.append((
            body,
            request.headers.get("authorization"),
            request.headers.get("mcp-session-id"),
            request.headers.get("mcp-protocol-version"),
        ))
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "MCP-Session-Id": "session-1"},
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-06-18"}},
            )
        if body.get("method") == "tools/list":
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {
                        "tools": [
                            {
                                "name": "account_activities",
                                "inputSchema": {
                                    "type": "object",
                                    "properties": {"limit": {"type": "integer"}},
                                    "required": ["limit"],
                                    "additionalProperties": False,
                                },
                            }
                        ]
                    },
                },
            )
        if body.get("method") == "tools/call":
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": body["id"],
                    "result": {"structuredContent": {"activities": []}},
                },
            )
        return httpx.Response(404)

    client = StreamableHTTPMCPClient(
        "https://mcp.example.test/mcp",
        bearer_token="account-token",
        transport=httpx.MockTransport(handle),
    )
    result = await client.call_tool("account_activities", {"limit": 5})

    assert result["structuredContent"] == {"activities": []}
    assert seen[-1][0]["params"] == {"name": "account_activities", "arguments": {"limit": 5}}
    assert all(item[1] == "Bearer account-token" for item in seen)
    assert seen[-1][2] == "session-1"
    assert seen[0][3] is None  # MCP-Protocol-Version is omitted during initialize.
    assert all(item[3] == "2025-06-18" for item in seen[1:])


@pytest.mark.asyncio
async def test_tool_call_rejects_unknown_tool_and_bad_arguments():
    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content) if request.content else {}
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        if body.get("method") == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-03-26"}})
        if body.get("method") == "tools/list":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"tools": [{"name": "read", "inputSchema": {"type": "object", "properties": {"limit": {"type": "integer"}}, "required": ["limit"]}}]}},
            )
        raise AssertionError("tool call should not be sent")

    client = StreamableHTTPMCPClient("https://mcp.example.test/mcp", transport=httpx.MockTransport(handle))
    with pytest.raises(MCPError, match="not offered"):
        await client.call_tool("write", {})
    with pytest.raises(MCPError, match="must be an integer"):
        await client.call_tool("read", {"limit": "many"})


@pytest.mark.asyncio
async def test_streaming_sse_returns_matching_multiline_event_without_waiting_for_eof():
    class PersistentSSE(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b'event: message\ndata: {"jsonrpc":"2.0","id":90,"result":{}}\n\n'
            yield b'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":\n'
            yield b'data: {"tools":[]}}\n\n'
            await asyncio.Future()

    async def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=PersistentSSE(),
        )

    client = StreamableHTTPMCPClient(
        "https://mcp.example.test/mcp", transport=httpx.MockTransport(handle)
    )
    result = await asyncio.wait_for(client._rpc("tools/list", {}), timeout=1)
    assert result == {"tools": []}


@pytest.mark.asyncio
async def test_mcp_json_response_is_bounded(monkeypatch):
    monkeypatch.setattr(mcp, "MAX_RESPONSE_BYTES", 64)

    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={"jsonrpc": "2.0", "id": body["id"], "result": {"large": "x" * 100}},
        )

    client = StreamableHTTPMCPClient(
        "https://mcp.example.test/mcp", transport=httpx.MockTransport(handle)
    )
    with pytest.raises(MCPError, match="size limit"):
        await client._rpc("tools/list", {})


@pytest.mark.asyncio
async def test_tools_list_pagination_is_capped(monkeypatch):
    monkeypatch.setattr(mcp, "MAX_TOOL_LIST_PAGES", 2)
    calls = 0

    async def handle(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        body = json.loads(request.content)
        if body.get("method") == "notifications/initialized":
            return httpx.Response(202)
        if body.get("method") == "initialize":
            return httpx.Response(
                200,
                json={"jsonrpc": "2.0", "id": body["id"], "result": {"protocolVersion": "2025-11-25"}},
            )
        calls += 1
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "result": {"tools": [], "nextCursor": f"cursor-{calls}"},
            },
        )

    client = StreamableHTTPMCPClient(
        "https://mcp.example.test/mcp", transport=httpx.MockTransport(handle)
    )
    with pytest.raises(MCPError, match="page limit"):
        await client.list_tools()
    assert calls == 2


@pytest.mark.asyncio
async def test_server_error_message_is_sanitized():
    async def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "jsonrpc": "2.0",
                "id": body["id"],
                "error": {"code": -32000, "message": "token secret account health data"},
            },
        )

    client = StreamableHTTPMCPClient(
        "https://mcp.example.test/mcp", transport=httpx.MockTransport(handle)
    )
    with pytest.raises(MCPError) as error:
        await client._rpc("tools/list", {})
    assert "secret" not in str(error.value)
    assert "health data" not in str(error.value)


@pytest.mark.asyncio
async def test_transport_exception_message_is_sanitized():
    async def handle(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("token secret account health data")

    client = StreamableHTTPMCPClient(
        "https://mcp.example.test/mcp", transport=httpx.MockTransport(handle)
    )
    with pytest.raises(MCPError) as error:
        await client._rpc("tools/list", {})
    assert "secret" not in str(error.value)
    assert "health data" not in str(error.value)


@pytest.mark.asyncio
async def test_sse_helper_decodes_completed_event():
    response = httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        text='event: message\ndata: {"jsonrpc":"2.0","id":4,"result":\ndata: {"tools":[]}}\n\n',
    )
    assert await _read_rpc_response(response, 4) == {
        "jsonrpc": "2.0", "id": 4, "result": {"tools": []}
    }


def test_endpoint_rejects_embedded_credentials():
    with pytest.raises(MCPError, match="embedded credentials"):
        StreamableHTTPMCPClient("https://user:secret@mcp.example.test/mcp")
