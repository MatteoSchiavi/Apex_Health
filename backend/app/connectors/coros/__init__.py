"""COROS connector — Open API doc-first shell.

COROS gates API access behind a manual developer-portal application review
(open.coros.com — "apply and wait"), so this ships as a wired-but-inert
shell: config entries, OAuth URL builders, and the sync driver skeleton all
exist; until the owner's application is approved and COROS_CLIENT_ID /
COROS_CLIENT_SECRET are set, `flow_settings_ready()` is False and the UI
shows the connector as "pending provider approval". No fake data paths.

When approved, the collection endpoints (activities list, activity detail
with FIT URLs, daily metrics) slot into the same raw-first -> normalize
pipeline every other connector uses.
"""

from app.connectors.coros.client import CorosAuthError, CorosClient, build_authorize_url
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
    "complete_authorization",
    "create_pending_authorization",
    "flow_settings_ready",
    "sync_user_coros",
    "run_user_sync_with_coros",
]
