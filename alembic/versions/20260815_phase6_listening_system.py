"""phase6 listening system

Revision ID: 20260815_phase6
Revises: 20260815_phase5
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260815_phase6"
down_revision: str | None = "20260815_phase5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audio_assets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("storage_provider", sa.String(length=40), nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("url", sa.String(length=1000), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("format", sa.String(length=20), nullable=True),
        sa.Column("locale", sa.String(length=20), nullable=True),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("mime_type", sa.String(length=120), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("language", sa.String(length=20), nullable=False),
        sa.Column("transcript", sa.Text(), nullable=True),
        sa.Column("pinyin", sa.Text(), nullable=True),
        sa.Column("translation", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_provider", "storage_key", name="uq_audio_storage_key"),
        sa.UniqueConstraint("provider", "storage_key", name="uq_audio_assets_provider_key"),
    )
    op.create_index("ix_audio_assets_status_language", "audio_assets", ["status", "language"])
    op.create_index(op.f("ix_audio_assets_language"), "audio_assets", ["language"])
    op.create_index(op.f("ix_audio_assets_status"), "audio_assets", ["status"])
    op.add_column(
        "answer_attempts",
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("answer_attempts", "metadata")
    op.drop_index(op.f("ix_audio_assets_status"), table_name="audio_assets")
    op.drop_index(op.f("ix_audio_assets_language"), table_name="audio_assets")
    op.drop_index("ix_audio_assets_status_language", table_name="audio_assets")
    op.drop_table("audio_assets")
