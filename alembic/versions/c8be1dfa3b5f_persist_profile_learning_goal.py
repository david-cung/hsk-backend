"""persist profile learning goal

Revision ID: c8be1dfa3b5f
Revises: bea5d5df6a3e
Create Date: 2026-08-13 22:06:52.409400

"""
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c8be1dfa3b5f'
down_revision: Union[str, Sequence[str], None] = 'bea5d5df6a3e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "profiles",
        sa.Column("learning_goal", sa.String(length=80), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("profiles", "learning_goal")
