"""align schema with models

Revision ID: 018d02f230de
Revises: 52ed405e2963
Create Date: 2026-01-04 15:40:21.717733

NOTE: This migration has been squashed into the initial schema (52ed405e2963).
      All indexes and JSONB column types are now created in the initial migration.
      This file is kept as a no-op to preserve the Alembic revision chain.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '018d02f230de'
down_revision: Union[str, Sequence[str], None] = '52ed405e2963'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """No-op — squashed into initial schema."""
    pass


def downgrade() -> None:
    """No-op — squashed into initial schema."""
    pass
