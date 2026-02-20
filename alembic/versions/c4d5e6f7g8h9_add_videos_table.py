"""Add videos table for persistent video metadata.

Revision ID: c4d5e6f7g8h9
Revises: b3c4d5e6f7g8
Create Date: 2026-02-19 22:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "c4d5e6f7g8h9"
down_revision: Union[str, None] = "b3c4d5e6f7g8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "videos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "channel_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("channels.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("youtube_video_id", sa.String(255), nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("published_at", sa.TIMESTAMP, nullable=True),
        sa.Column("thumbnail_url", sa.Text, nullable=True),
        sa.Column("duration_seconds", sa.Integer, nullable=True),
        sa.Column("view_count", sa.BigInteger, nullable=True),
        sa.Column("like_count", sa.BigInteger, nullable=True),
        sa.Column("comment_count", sa.BigInteger, nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP,
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP,
            server_default=sa.func.now(),
            nullable=False,
        ),
    )

    # Indexes
    op.create_index("idx_videos_channel_id", "videos", ["channel_id"])
    op.create_index("idx_videos_youtube_video_id", "videos", ["youtube_video_id"])

    # Composite unique constraint
    op.create_unique_constraint(
        "uq_videos_channel_video",
        "videos",
        ["channel_id", "youtube_video_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_videos_channel_video", "videos", type_="unique")
    op.drop_index("idx_videos_youtube_video_id", table_name="videos")
    op.drop_index("idx_videos_channel_id", table_name="videos")
    op.drop_table("videos")
