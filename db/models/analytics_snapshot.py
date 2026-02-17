import uuid
from sqlalchemy import String, TIMESTAMP, Integer, Float, BigInteger, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime
from typing import Optional


class AnalyticsSnapshot(Base):
    __tablename__ = "analytics_snapshots"
    __table_args__ = (
        Index("idx_snapshots_channel_id", "channel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"))
    period: Mapped[str] = mapped_column(String, nullable=False)
    subscribers: Mapped[int] = mapped_column(Integer)
    views: Mapped[int] = mapped_column(BigInteger)
    avg_ctr: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_watch_time_minutes: Mapped[float] = mapped_column(Float)
    
    # Extended metrics (added for CTR, retention, traffic sources)
    impressions: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    avg_view_percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    traffic_sources: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow)
