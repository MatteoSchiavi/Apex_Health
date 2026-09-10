"""AI-layer models (MASTER_SPEC §6.4, Phase 5): ai_reports, token_usage,
agent_tool_calls, embeddings.

Mapped in Phase 5 — the tables themselves exist since migration 0001
(all 45 §6.4 tables), so no DDL migration is needed; this is the same
"tables first, ORM mapping when the owning phase lands" convention as
gear (Phase 4).

agent_tool_calls.session_id is nullable by design (§6.4 comment): the
scheduled report generation reuses the same query functions (§8.2) and
logs there too — NULL means "not a chat-originated call".
"""

from datetime import date, datetime
from decimal import Decimal

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Date, DateTime, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class AiReport(Base):
    __tablename__ = "ai_reports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_type: Mapped[str] = mapped_column(Text, nullable=False)  # daily|weekly|monthly
    period_start: Mapped[date] = mapped_column(Date, nullable=False)
    period_end: Mapped[date] = mapped_column(Date, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
    content_md: Mapped[str] = mapped_column(Text, nullable=False)
    model_used: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # NULL for templated (non-LLM) daily summaries
    source_feature_ids: Mapped[list[str] | None] = mapped_column(
        ARRAY(Text), nullable=True
    )  # §6.4: audit list of metric-name/date identifiers, NOT a FK


class TokenUsage(Base):
    __tablename__ = "token_usage"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    call_type: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)  # free|cheap|powerful
    model: Mapped[str] = mapped_column(Text, nullable=False)
    tokens_in: Mapped[int | None] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cached_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_estimate_usd: Mapped[Decimal | None] = mapped_column(Numeric, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class AgentToolCall(Base):
    __tablename__ = "agent_tool_calls"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    session_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True
    )  # NULL = scheduled/report-originated (§8.2)
    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    input_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    output_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )


class Embedding(Base):
    __tablename__ = "embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_table: Mapped[str] = mapped_column(Text, nullable=False)
    source_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    embedding: Mapped[list | None] = mapped_column(
        Vector(1536), nullable=True
    )  # pinned to text-embedding-3-small — §6.2
    content_snippet: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default="now()"
    )
