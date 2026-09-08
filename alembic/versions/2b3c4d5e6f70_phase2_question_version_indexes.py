"""phase2 question version indexes

Revision ID: 2b3c4d5e6f70
Revises: 2a3b4c5d6e7f
"""

from typing import Sequence, Union

from alembic import op

revision: str = "2b3c4d5e6f70"
down_revision: Union[str, Sequence[str], None] = "2a3b4c5d6e7f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_question_versions_skill", "question_versions", ["skill"])
    op.create_index("ix_question_versions_difficulty", "question_versions", ["difficulty"])
    op.create_index("ix_question_versions_reference_type", "question_versions", ["reference_type"])
    op.create_index("ix_question_versions_reference_id", "question_versions", ["reference_id"])


def downgrade() -> None:
    op.drop_index("ix_question_versions_reference_id", table_name="question_versions")
    op.drop_index("ix_question_versions_reference_type", table_name="question_versions")
    op.drop_index("ix_question_versions_difficulty", table_name="question_versions")
    op.drop_index("ix_question_versions_skill", table_name="question_versions")
