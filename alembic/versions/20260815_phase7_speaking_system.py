"""phase7 speaking system

Revision ID: 20260815_phase7
Revises: 20260815_phase6
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260815_phase7"
down_revision: str | None = "20260815_phase6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("lesson_progress", sa.Column("speaking_attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "lesson_progress",
        sa.Column("speaking_acceptable_attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("lesson_progress", sa.Column("pronunciation_score_avg", sa.Float(), nullable=True))
    op.add_column("lesson_progress", sa.Column("last_speaking_practice", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "speech_recordings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("extension", sa.String(length=20), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("upload_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_provider", "storage_key", name="uq_speech_recordings_storage_key"),
    )
    op.create_index("ix_speech_recordings_user_status", "speech_recordings", ["user_id", "status"])
    op.create_index("ix_speech_recordings_expires_at", "speech_recordings", ["expires_at"])
    op.create_index(op.f("ix_speech_recordings_user_id"), "speech_recordings", ["user_id"])
    op.create_index(op.f("ix_speech_recordings_language"), "speech_recordings", ["language"])
    op.create_index(op.f("ix_speech_recordings_status"), "speech_recordings", ["status"])
    op.create_table(
        "speaking_attempts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("practice_session_id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("answer_attempt_id", sa.Integer(), nullable=False),
        sa.Column("recording_id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("provider_model_version", sa.String(length=120), nullable=True),
        sa.Column("recognized_text", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("pronunciation_score", sa.Float(), nullable=True),
        sa.Column("accuracy_score", sa.Float(), nullable=True),
        sa.Column("fluency_score", sa.Float(), nullable=True),
        sa.Column("completeness_score", sa.Float(), nullable=True),
        sa.Column("word_feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("tone_feedback", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("feedback_label", sa.String(length=80), nullable=True),
        sa.Column("processing_status", sa.String(length=40), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["answer_attempt_id"], ["answer_attempts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["practice_session_id"], ["practice_sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["recording_id"], ["speech_recordings.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("answer_attempt_id", name="uq_speaking_attempts_answer_attempt"),
    )
    op.create_index("ix_speaking_attempts_user_status", "speaking_attempts", ["user_id", "processing_status"])
    op.create_index("ix_speaking_attempts_session_question", "speaking_attempts", ["practice_session_id", "question_id"])
    op.create_index(op.f("ix_speaking_attempts_answer_attempt_id"), "speaking_attempts", ["answer_attempt_id"])
    op.create_index(op.f("ix_speaking_attempts_practice_session_id"), "speaking_attempts", ["practice_session_id"])
    op.create_index(op.f("ix_speaking_attempts_question_id"), "speaking_attempts", ["question_id"])
    op.create_index(op.f("ix_speaking_attempts_recording_id"), "speaking_attempts", ["recording_id"])
    op.create_index(op.f("ix_speaking_attempts_user_id"), "speaking_attempts", ["user_id"])
    op.create_index(op.f("ix_speaking_attempts_processing_status"), "speaking_attempts", ["processing_status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_speaking_attempts_processing_status"), table_name="speaking_attempts")
    op.drop_index(op.f("ix_speaking_attempts_user_id"), table_name="speaking_attempts")
    op.drop_index(op.f("ix_speaking_attempts_recording_id"), table_name="speaking_attempts")
    op.drop_index(op.f("ix_speaking_attempts_question_id"), table_name="speaking_attempts")
    op.drop_index(op.f("ix_speaking_attempts_practice_session_id"), table_name="speaking_attempts")
    op.drop_index(op.f("ix_speaking_attempts_answer_attempt_id"), table_name="speaking_attempts")
    op.drop_index("ix_speaking_attempts_session_question", table_name="speaking_attempts")
    op.drop_index("ix_speaking_attempts_user_status", table_name="speaking_attempts")
    op.drop_table("speaking_attempts")
    op.drop_index(op.f("ix_speech_recordings_status"), table_name="speech_recordings")
    op.drop_index(op.f("ix_speech_recordings_language"), table_name="speech_recordings")
    op.drop_index(op.f("ix_speech_recordings_user_id"), table_name="speech_recordings")
    op.drop_index("ix_speech_recordings_expires_at", table_name="speech_recordings")
    op.drop_index("ix_speech_recordings_user_status", table_name="speech_recordings")
    op.drop_table("speech_recordings")
    for column in (
        "last_speaking_practice",
        "pronunciation_score_avg",
        "speaking_acceptable_attempts",
        "speaking_attempts",
    ):
        op.drop_column("lesson_progress", column)
