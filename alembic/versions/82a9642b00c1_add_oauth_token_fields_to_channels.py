"""Add OAuth token fields to channels

Revision ID: 82a9642b00c1
Revises: 018d02f230de
Create Date: 2026-01-16 21:37:57.060823

NOTE: This migration has been squashed into the initial schema (52ed405e2963).
      OAuth token fields, indexes, and unique constraints are now created in
      the initial migration. This file is kept as a no-op to preserve the
      Alembic revision chain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '82a9642b00c1'
down_revision: Union[str, Sequence[str], None] = '018d02f230de'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op — squashed into initial schema."""
    pass


def downgrade() -> None:
    """No-op — squashed into initial schema."""
    pass
