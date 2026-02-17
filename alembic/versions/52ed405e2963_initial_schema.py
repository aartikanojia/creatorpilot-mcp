"""initial schema

Revision ID: 52ed405e2963
Revises: 
Create Date: 2026-01-04 15:30:42.394106

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '52ed405e2963'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables from scratch — safe for fresh production deployment."""

    # ── users ──────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=True),
        sa.Column('plan', sa.String(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
        sa.UniqueConstraint('email', name=op.f('uq_users_email')),
    )

    # ── channels ───────────────────────────────────────────────────────
    op.create_table(
        'channels',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('youtube_channel_id', sa.String(255), nullable=False),
        sa.Column('channel_name', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True,
                  server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_channels')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name=op.f('fk_channels_user_id_users'),
                                ondelete='CASCADE'),
        sa.UniqueConstraint('user_id', 'youtube_channel_id',
                            name='uq_user_youtube_channel'),
    )
    op.create_index('idx_channels_user_id', 'channels', ['user_id'])
    op.create_index('idx_channels_youtube_id', 'channels', ['youtube_channel_id'])

    # ── analytics_snapshots ────────────────────────────────────────────
    op.create_table(
        'analytics_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('period', sa.String(), nullable=False),
        sa.Column('subscribers', sa.Integer(), nullable=True),
        sa.Column('views', sa.BigInteger(), nullable=True),
        sa.Column('avg_ctr', sa.Float(), nullable=True),
        sa.Column('avg_watch_time_minutes', sa.Float(), nullable=True),
        sa.Column('impressions', sa.BigInteger(), nullable=True),
        sa.Column('avg_view_percentage', sa.Float(), nullable=True),
        sa.Column('traffic_sources', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_analytics_snapshots')),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'],
                                name=op.f('fk_analytics_snapshots_channel_id_channels'),
                                ondelete='CASCADE'),
    )
    op.create_index('idx_snapshots_channel_id', 'analytics_snapshots', ['channel_id'])

    # ── chat_sessions ──────────────────────────────────────────────────
    op.create_table(
        'chat_sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('user_message', sa.Text(), nullable=False),
        sa.Column('assistant_response', sa.Text(), nullable=True),
        sa.Column('tools_used', postgresql.JSONB(), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_chat_sessions')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'],
                                name=op.f('fk_chat_sessions_user_id_users'),
                                ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'],
                                name=op.f('fk_chat_sessions_channel_id_channels'),
                                ondelete='SET NULL'),
    )
    op.create_index('idx_chat_user_id', 'chat_sessions', ['user_id'])

    # ── video_snapshots ────────────────────────────────────────────────
    op.create_table(
        'video_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('video_id', sa.String(), nullable=False),
        sa.Column('title', sa.String(), nullable=True),
        sa.Column('views', sa.BigInteger(), nullable=True),
        sa.Column('likes', sa.Integer(), nullable=True),
        sa.Column('comments', sa.Integer(), nullable=True),
        sa.Column('engagement_rate', sa.Float(), nullable=True),
        sa.Column('published_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('snapshot_date', sa.Date(), nullable=True),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_video_snapshots')),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'],
                                name=op.f('fk_video_snapshots_channel_id_channels'),
                                ondelete='CASCADE'),
    )
    op.create_index('idx_video_channel_id', 'video_snapshots', ['channel_id'])

    # ── weekly_insights ────────────────────────────────────────────────
    op.create_table(
        'weekly_insights',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text('gen_random_uuid()')),
        sa.Column('channel_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('week_start', sa.Date(), nullable=False),
        sa.Column('summary', sa.String(), nullable=True),
        sa.Column('wins', postgresql.JSONB(), nullable=True),
        sa.Column('losses', postgresql.JSONB(), nullable=True),
        sa.Column('next_actions', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=True,
                  server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_weekly_insights')),
        sa.ForeignKeyConstraint(['channel_id'], ['channels.id'],
                                name=op.f('fk_weekly_insights_channel_id_channels'),
                                ondelete='CASCADE'),
    )
    op.create_index('idx_weekly_channel_id', 'weekly_insights', ['channel_id'])


def downgrade() -> None:
    """Drop all tables in reverse dependency order."""
    op.drop_table('weekly_insights')
    op.drop_table('video_snapshots')
    op.drop_table('chat_sessions')
    op.drop_table('analytics_snapshots')
    op.drop_table('channels')
    op.drop_table('users')
