import uuid
from sqlalchemy import String, Text, TIMESTAMP, ForeignKey, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from db.base import Base
from datetime import datetime


class Channel(Base):
    """SQLAlchemy model for YouTube channel connections.
    
    Stores OAuth tokens and channel information for connected YouTube accounts.
    MCP is the single source of truth for this data.
    """
    
    __tablename__ = "channels"
    __table_args__ = (
        Index("idx_channels_user_id", "user_id"),
        Index("idx_channels_youtube_id", "youtube_channel_id"),
        UniqueConstraint("user_id", "youtube_channel_id", name="uq_user_youtube_channel"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"))
    youtube_channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_name: Mapped[str | None] = mapped_column(String(255))
    
    # OAuth tokens (stored securely - consider encryption in production)
    access_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP, default=datetime.utcnow, onupdate=datetime.utcnow)

