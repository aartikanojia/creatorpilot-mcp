"""Seed test user for development

Revision ID: a1b2c3d4e5f6
Revises: 82a9642b00c1
Create Date: 2026-01-20 22:21:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '82a9642b00c1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Test user ID used by the frontend for development
TEST_USER_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    """Seed test user for development environment."""
    # Insert test user if not exists (using raw SQL for upsert)
    op.execute(
        sa.text("""
            INSERT INTO users (id, email, name, plan, created_at)
            VALUES (
                :user_id,
                'test@contexthub.dev',
                'Test User',
                'free',
                NOW()
            )
            ON CONFLICT (id) DO NOTHING
        """).bindparams(user_id=TEST_USER_ID)
    )


def downgrade() -> None:
    """Remove test user."""
    op.execute(
        sa.text("""
            DELETE FROM users WHERE id = :user_id
        """).bindparams(user_id=TEST_USER_ID)
    )
