import uuid
from sqlalchemy import TIMESTAMP, Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime, date


class WeeklyInsight(Base):
    __tablename__ = "weekly_insights"
    __table_args__ = (
        Index("idx_weekly_channel_id", "channel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"))
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    summary: Mapped[str | None]
    wins: Mapped[dict | None] = mapped_column(JSONB)
    losses: Mapped[dict | None] = mapped_column(JSONB)
    next_actions: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow)
