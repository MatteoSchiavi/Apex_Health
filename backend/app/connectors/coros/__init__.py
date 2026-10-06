"""COROS connector delegated to an administrator-configured MCP server."""

from app.connectors.coros.client import (
    CorosAuthError,
    CorosClient,
    build_authorize_url,
    build_live_client,
)
from app.connectors.coros.flow import (
    OAuthFlowError,
    complete_authorization,
    create_pending_authorization,
    flow_settings_ready,
)
from app.connectors.coros.sync import run_user_sync_with_coros, sync_user_coros

__all__ = [
    "CorosAuthError",
    "CorosClient",
    "OAuthFlowError",
    "build_authorize_url",
    "build_live_client",
    "complete_authorization",
    "create_pending_authorization",
    "flow_settings_ready",
    "sync_user_coros",
    "run_user_sync_with_coros",
]
