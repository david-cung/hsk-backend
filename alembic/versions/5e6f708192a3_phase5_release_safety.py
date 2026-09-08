"""phase5 release safety

Revision ID: 5e6f708192a3
Revises: 4d5e6f708192
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5e6f708192a3"
down_revision: Union[str, Sequence[str], None] = "4d5e6f708192"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "uq_exam_attempts_one_active",
        "exam_attempts",
        ["user_id", "exam_id"],
        unique=True,
        postgresql_where=sa.text("status = 'IN_PROGRESS'"),
    )


def downgrade() -> None:
    op.drop_index("uq_exam_attempts_one_active", table_name="exam_attempts")
