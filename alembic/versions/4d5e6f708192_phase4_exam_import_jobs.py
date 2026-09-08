"""phase4 exam import jobs

Revision ID: 4d5e6f708192
Revises: 3c4d5e6f7081
"""

from typing import Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4d5e6f708192"
down_revision: Union[str, Sequence[str], None] = "3c4d5e6f7081"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return postgresql.JSONB(astext_type=sa.Text())


def upgrade() -> None:
    op.create_table(
        "exam_import_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False, server_default="UPLOADING"),
        sa.Column("exam_revision_id", sa.Integer(), nullable=False),
        sa.Column("exam_level_id", sa.Integer(), nullable=False),
        sa.Column("exam_name", sa.String(length=180), nullable=False),
        sa.Column("source_hash", sa.String(length=64), nullable=False),
        sa.Column("source_exam_file", sa.String(length=500), nullable=False),
        sa.Column("source_answer_file", sa.String(length=500), nullable=True),
        sa.Column("source_audio_file", sa.String(length=500), nullable=True),
        sa.Column("source_audio_asset_id", sa.Integer(), nullable=True),
        sa.Column("created_exam_id", sa.Integer(), nullable=True),
        sa.Column("created_exam_version_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("warnings", _jsonb(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("errors", _jsonb(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("parsed_document", _jsonb(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exam_revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exam_level_id"], ["exam_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["source_audio_asset_id"], ["audio_assets.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_exam_id"], ["mock_tests.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_exam_version_id"], ["exam_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_hash", "exam_revision_id", "exam_level_id", "exam_name", name="uq_exam_import_jobs_idempotency"),
    )
    op.create_index("ix_exam_import_jobs_status", "exam_import_jobs", ["status"])
    op.create_index("ix_exam_import_jobs_status_updated", "exam_import_jobs", ["status", "updated_at"])
    op.create_index("ix_exam_import_jobs_source_hash", "exam_import_jobs", ["source_hash"])
    op.create_index("ix_exam_import_jobs_exam_revision_id", "exam_import_jobs", ["exam_revision_id"])
    op.create_index("ix_exam_import_jobs_exam_level_id", "exam_import_jobs", ["exam_level_id"])
    op.create_index("ix_exam_import_jobs_source_audio_asset_id", "exam_import_jobs", ["source_audio_asset_id"])
    op.create_index("ix_exam_import_jobs_created_exam_id", "exam_import_jobs", ["created_exam_id"])
    op.create_index("ix_exam_import_jobs_created_exam_version_id", "exam_import_jobs", ["created_exam_version_id"])
    op.create_index("ix_exam_import_jobs_created_by", "exam_import_jobs", ["created_by"])


def downgrade() -> None:
    for name in (
        "ix_exam_import_jobs_created_by",
        "ix_exam_import_jobs_created_exam_version_id",
        "ix_exam_import_jobs_created_exam_id",
        "ix_exam_import_jobs_source_audio_asset_id",
        "ix_exam_import_jobs_exam_level_id",
        "ix_exam_import_jobs_exam_revision_id",
        "ix_exam_import_jobs_source_hash",
        "ix_exam_import_jobs_status_updated",
        "ix_exam_import_jobs_status",
    ):
        op.drop_index(name, table_name="exam_import_jobs")
    op.drop_table("exam_import_jobs")
