"""First-party alpha utility events contain no prompts or health payloads."""
from datetime import datetime
from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import Base


class AlphaEvent(Base):
    __tablename__ = 'alpha_events'
    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    event: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default='now()')
    metadata_json: Mapped[dict] = mapped_column(JSONB, default=dict)
    __table_args__ = (Index('idx_alpha_events_time_event', 'created_at', 'event'),
                      Index('idx_alpha_events_user_time', 'user_id', 'created_at'))
