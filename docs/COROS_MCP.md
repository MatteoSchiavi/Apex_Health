# COROS over MCP

The COROS connector sends MCP JSON-RPC requests only to an administrator-configured Streamable HTTP MCP server. It does not call COROS OAuth or COROS API URLs. The MCP service must authenticate the account's bearer token and scope its returned data to that account; the application stores each token encrypted on that account's integration row and never falls back to a shared server token.

Configure these backend settings:

| Setting | Meaning |
| --- | --- |
| `COROS_MCP_URL` | Absolute HTTP(S) Streamable HTTP MCP endpoint. |
| `COROS_MCP_ACTIVITY_TOOL` | Exact read-only tool name chosen by the administrator. Empty means disabled. |
| `COROS_MCP_ACTIVITY_ARGS` | JSON object passed to the selected tool, default `{}`. |
| `COROS_MCP_TIMEOUT_SECONDS` | Request timeout, default `30`. |

The account connect flow stores the user's MCP bearer token as `mcp_access_token` in the encrypted COROS integration credentials. The connector initializes an MCP session, calls `tools/list`, checks that the configured activity tool exists and validates its arguments against that tool's advertised input schema, then invokes only that selected tool. It does not expose arbitrary MCP tool calls to the application or user interface.

## Activity result contract

The selected tool must return this MCP `structuredContent` shape:

```json
{
  "activities": [
    {
      "id": "provider-activity-id",
      "start_time": "2026-06-14T08:30:00Z",
      "duration_s": 3600,
      "distance_m": 10000,
      "elevation_gain_m": 120,
      "avg_hr": 145,
      "max_hr": 178,
      "calories": 600,
      "sport_type": "running"
    }
  ]
}
```

Only `id` (or `external_id`), timezone-qualified `start_time`, and positive `duration_s` are required. The other canonical fields are optional. Units are seconds, metres, beats per minute, and kilocalories. The tool must return all activities for the window it is configured to serve; the current contract has no portable paging parameter because server tool argument names are not yet known. Invalid and unrecognized records remain in raw ingestion for review, and a result with no valid canonical activities does not advance the sync checkpoint.

MCP wire behavior follows Streamable HTTP JSON-RPC: initialize with the negotiated protocol version, send `notifications/initialized`, then list and call tools. The implementation accepts JSON and SSE JSON-RPC responses and carries `MCP-Session-Id` between requests.

## Verification status

No specific COROS MCP server URL, repository, tool name, tool schema, or response payload has been supplied or verified. This contract is an application-side interface for configuring a compatible server; it does not claim compatibility with an uninspected provider's MCP service. Verify the real server's advertised tool name, arguments, authentication model, and `structuredContent` against this contract before enabling account connections.
