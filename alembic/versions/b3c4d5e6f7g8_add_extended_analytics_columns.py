"""Add extended analytics columns for CTR, retention, and traffic sources.

Revision ID: b3c4d5e6f7g8
Revises: a1b2c3d4e5f6
Create Date: 2026-01-22 12:52:00.000000

NOTE: This migration has been squashed into the initial schema (52ed405e2963).
      The impressions, avg_view_percentage, and traffic_sources columns are now
      created in the initial migration. This file is kept as a no-op to preserve
      the Alembic revision chain.
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
    """No-op — squashed into initial schema."""
    pass


def downgrade() -> None:
    """No-op — squashed into initial schema."""
    pass
