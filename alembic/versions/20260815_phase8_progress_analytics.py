"""phase8 progress analytics

Revision ID: 20260815_phase8
Revises: 20260815_phase7
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260815_phase8"
down_revision: str | None = "20260815_phase7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("longest_streak_days", sa.Integer(), server_default="0", nullable=False))
    op.add_column("profiles", sa.Column("last_active_date", sa.Date(), nullable=True))
    op.create_index("ix_answer_attempts_user_attempted", "answer_attempts", ["user_id", "attempted_at"])
    op.create_index("ix_practice_sessions_user_started", "practice_sessions", ["user_id", "started_at"])
    op.create_index("ix_practice_sessions_user_completed", "practice_sessions", ["user_id", "completed_at"])
    op.create_index("ix_quiz_attempts_user_finished", "quiz_attempts", ["user_id", "finished_at"])
    op.create_index("ix_lesson_progress_user_updated", "lesson_progress", ["user_id", "updated_at"])


def downgrade() -> None:
    op.drop_index("ix_lesson_progress_user_updated", table_name="lesson_progress")
    op.drop_index("ix_quiz_attempts_user_finished", table_name="quiz_attempts")
    op.drop_index("ix_practice_sessions_user_completed", table_name="practice_sessions")
    op.drop_index("ix_practice_sessions_user_started", table_name="practice_sessions")
    op.drop_index("ix_answer_attempts_user_attempted", table_name="answer_attempts")
    op.drop_column("profiles", "last_active_date")
    op.drop_column("profiles", "longest_streak_days")
