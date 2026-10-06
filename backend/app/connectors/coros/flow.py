"""The legacy COROS OAuth flow is disabled; users connect with an MCP token."""

class OAuthFlowError(Exception):
    """Raised when a client attempts the retired COROS OAuth flow."""


def flow_settings_ready() -> bool:
    return False


async def create_pending_authorization(redis, user):
    del redis, user
    raise OAuthFlowError("COROS OAuth is disabled; connect through the configured MCP server")


async def complete_authorization(session, redis, *, code: str, state: str) -> dict:
    del session, redis, code, state
    raise OAuthFlowError("COROS OAuth is disabled; connect through the configured MCP server")
