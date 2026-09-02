"""phase10 mock exam system

Revision ID: 20260815_phase10
Revises: 20260815_phase9
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260815_phase10"
down_revision: str | None = "20260815_phase9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("mock_tests", sa.Column("description", sa.Text(), nullable=True))
    op.add_column("mock_tests", sa.Column("exam_type", sa.String(length=40), server_default="MOCK", nullable=False))
    op.add_column("mock_tests", sa.Column("status", sa.String(length=40), server_default="PUBLISHED", nullable=False))
    op.add_column("mock_tests", sa.Column("version", sa.Integer(), server_default="1", nullable=False))
    op.add_column("mock_tests", sa.Column("blueprint", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("mock_tests", sa.Column("scoring_config", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False))
    op.add_column("mock_tests", sa.Column("instructions", sa.Text(), nullable=True))
    op.add_column("mock_tests", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("mock_tests", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "exam_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("exam_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), server_default="IN_PROGRESS", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("percentage", sa.Float(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=True),
        sa.Column("random_seed", sa.Integer(), nullable=False),
        sa.Column("current_section", sa.String(length=40), nullable=True),
        sa.Column("question_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("section_results", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("result_summary", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["exam_id"], ["mock_tests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_exam_attempts_user_status", "exam_attempts", ["user_id", "status"])
    op.create_index("ix_exam_attempts_user_created", "exam_attempts", ["user_id", "created_at"])
    op.create_index("ix_exam_attempts_exam_user", "exam_attempts", ["exam_id", "user_id"])
    op.create_table(
        "exam_question_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_attempt_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("answer", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("correct", sa.Boolean(), nullable=True),
        sa.Column("points", sa.Float(), server_default="0", nullable=False),
        sa.Column("max_points", sa.Float(), server_default="1", nullable=False),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["exam_attempt_id"], ["exam_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_attempt_id", "question_id", name="uq_exam_question_results_attempt_question"),
    )
    op.create_index("ix_exam_question_results_attempt", "exam_question_results", ["exam_attempt_id"])
    op.create_index("ix_exam_question_results_question", "exam_question_results", ["question_id"])


def downgrade() -> None:
    op.drop_index("ix_exam_question_results_question", table_name="exam_question_results")
    op.drop_index("ix_exam_question_results_attempt", table_name="exam_question_results")
    op.drop_table("exam_question_results")
    op.drop_index("ix_exam_attempts_exam_user", table_name="exam_attempts")
    op.drop_index("ix_exam_attempts_user_created", table_name="exam_attempts")
    op.drop_index("ix_exam_attempts_user_status", table_name="exam_attempts")
    op.drop_table("exam_attempts")
    op.drop_column("mock_tests", "archived_at")
    op.drop_column("mock_tests", "published_at")
    op.drop_column("mock_tests", "instructions")
    op.drop_column("mock_tests", "scoring_config")
    op.drop_column("mock_tests", "blueprint")
    op.drop_column("mock_tests", "version")
    op.drop_column("mock_tests", "status")
    op.drop_column("mock_tests", "exam_type")
    op.drop_column("mock_tests", "description")
