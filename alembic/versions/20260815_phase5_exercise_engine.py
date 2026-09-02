"""phase5 exercise engine

Revision ID: 20260815_phase5
Revises:
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260815_phase5"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_table(
        "exercise_sets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("skill", sa.String(length=40), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("lesson_id", "slug", name="uq_exercise_sets_lesson_slug"),
    )
    op.create_index("ix_exercise_sets_lesson_active", "exercise_sets", ["lesson_id", "is_archived"])
    op.create_index(op.f("ix_exercise_sets_lesson_id"), "exercise_sets", ["lesson_id"])
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exercise_set_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("exercise_type", sa.String(length=40), nullable=False),
        sa.Column("skill", sa.String(length=40), nullable=True),
        sa.Column("source_type", sa.String(length=40), nullable=True),
        sa.Column("source_id", sa.String(length=120), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["exercise_set_id"], ["exercise_sets.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exercise_set_id", "slug", name="uq_exercises_set_slug"),
    )
    op.create_index("ix_exercises_set_active", "exercises", ["exercise_set_id", "is_archived"])
    op.create_index(op.f("ix_exercises_exercise_set_id"), "exercises", ["exercise_set_id"])
    op.create_index(op.f("ix_exercises_lesson_id"), "exercises", ["lesson_id"])
    op.add_column("questions", sa.Column("exercise_id", sa.Integer(), nullable=True))
    op.add_column("questions", sa.Column("instruction", sa.Text(), nullable=True))
    op.add_column("questions", sa.Column("difficulty", sa.Integer(), server_default="1", nullable=False))
    op.add_column("questions", sa.Column("points", sa.Integer(), server_default="1", nullable=False))
    op.add_column("questions", sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False))
    op.add_column("questions", sa.Column("reference_type", sa.String(length=40), nullable=True))
    op.add_column("questions", sa.Column("reference_id", sa.String(length=120), nullable=True))
    op.add_column("questions", sa.Column("is_archived", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_foreign_key(None, "questions", "exercises", ["exercise_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_questions_exercise_order", "questions", ["exercise_id", "sort_order"])
    op.create_table(
        "answer_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("option_id", sa.String(length=80), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "option_id", name="uq_answer_options_question_option"),
    )
    op.create_table(
        "practice_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("lesson_id", sa.Integer(), nullable=True),
        sa.Column("exercise_set_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("question_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_questions", sa.Integer(), nullable=False),
        sa.Column("answered_questions", sa.Integer(), nullable=False),
        sa.Column("correct_answers", sa.Integer(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["exercise_set_id"], ["exercise_sets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["lesson_id"], ["lessons.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "answer_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("practice_session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("submitted_answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("normalized_answer", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_correct", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("time_spent_seconds", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(length=120), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["practice_session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("practice_session_id", "idempotency_key", name="uq_answer_attempts_session_key"),
    )


def downgrade() -> None:
    op.drop_table("answer_attempts")
    op.drop_table("practice_sessions")
    op.drop_table("answer_options")
    op.drop_index("ix_questions_exercise_order", table_name="questions")
    for column in ("is_archived", "reference_id", "reference_type", "config", "points", "difficulty", "instruction", "exercise_id"):
        op.drop_column("questions", column)
    op.drop_table("exercises")
    op.drop_table("exercise_sets")
    op.drop_column("users", "is_admin")
