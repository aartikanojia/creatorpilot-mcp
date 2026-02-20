import uuid
from sqlalchemy import (
    String, Text, TIMESTAMP, BigInteger, Integer,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime


class Video(Base):
    """Persistent video metadata for a YouTube channel.

    Stores video information fetched from the YouTube Data API.
    Used by the video resolver for fuzzy title matching and
    by analytics for video-level context.

    Upserted on every analytics fetch — idempotent via
    (channel_id, youtube_video_id) unique constraint.
    """

    __tablename__ = "videos"
    __table_args__ = (
        Index("idx_videos_channel_id", "channel_id"),
        Index("idx_videos_youtube_video_id", "youtube_video_id"),
        UniqueConstraint(
            "channel_id", "youtube_video_id",
            name="uq_videos_channel_video",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    channel_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("channels.id", ondelete="CASCADE"))
    youtube_video_id: Mapped[str] = mapped_column(
        String(255), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True)
    view_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True)
    like_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True)
    comment_count: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)
