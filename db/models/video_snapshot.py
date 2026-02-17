import uuid
from sqlalchemy import String, TIMESTAMP, Integer, Float, BigInteger, Date, ForeignKey, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import date


class VideoSnapshot(Base):
    __tablename__ = "video_snapshots"
    __table_args__ = (
        Index("idx_video_channel_id", "channel_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"))
    video_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str | None] = mapped_column(String)
    views: Mapped[int] = mapped_column(BigInteger)
    likes: Mapped[int] = mapped_column(Integer)
    comments: Mapped[int] = mapped_column(Integer)
    engagement_rate: Mapped[float] = mapped_column(Float)
    published_at: Mapped[str | None] = mapped_column(TIMESTAMP)
    snapshot_date: Mapped[date] = mapped_column(Date)
