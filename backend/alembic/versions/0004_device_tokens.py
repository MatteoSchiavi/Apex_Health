"""device_tokens — per-user bearer credentials for the Connect IQ watch
(MASTER_SPEC §23 Phase 10; the table itself is a documented judgment call —
the §6.4 schema predates the watch app and has no device-presentable
credential type).

Hashed like sessions (peppered SHA-256 of the raw token via
app/core/security.hash_session_token), so a database leak yields no usable
watch credentials. Soft revocation keeps mint/last-used history.

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-11
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE device_tokens (
            id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            user_id       BIGINT NOT NULL REFERENCES users(id),
            name          TEXT NOT NULL DEFAULT 'watch',
            token_hash    TEXT NOT NULL UNIQUE,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_used_at  TIMESTAMPTZ,
            revoked_at    TIMESTAMPTZ
        );
    """)


def downgrade() -> None:
    op.execute("DROP TABLE device_tokens;")
