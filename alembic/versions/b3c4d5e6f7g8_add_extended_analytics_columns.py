"""Add extended analytics columns for CTR, retention, and traffic sources.

Revision ID: b3c4d5e6f7g8
Revises: a1b2c3d4e5f6
Create Date: 2026-01-22 12:52:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


# revision identifiers, used by Alembic.
revision: str = 'b3c4d5e6f7g8'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add impressions, avg_view_percentage, and traffic_sources columns."""
    # Add impressions column (nullable for backward compatibility)
    op.add_column(
        'analytics_snapshots',
        sa.Column('impressions', sa.BigInteger(), nullable=True)
    )
    
    # Add avg_view_percentage column (nullable for backward compatibility)
    op.add_column(
        'analytics_snapshots',
        sa.Column('avg_view_percentage', sa.Float(), nullable=True)
    )
    
    # Add traffic_sources column as JSONB (nullable for backward compatibility)
    op.add_column(
        'analytics_snapshots',
        sa.Column('traffic_sources', JSONB(), nullable=True)
    )


def downgrade() -> None:
    """Remove the extended analytics columns."""
    op.drop_column('analytics_snapshots', 'traffic_sources')
    op.drop_column('analytics_snapshots', 'avg_view_percentage')
    op.drop_column('analytics_snapshots', 'impressions')
