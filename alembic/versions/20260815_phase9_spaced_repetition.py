"""phase9 spaced repetition

Revision ID: 20260815_phase9
Revises: 20260815_phase8
Create Date: 2026-08-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


revision: str = "20260815_phase9"
down_revision: str | None = "20260815_phase8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("profiles", sa.Column("timezone", sa.String(length=80), server_default="Asia/Ho_Chi_Minh", nullable=False))
    op.add_column("profiles", sa.Column("daily_new_cards_limit", sa.Integer(), server_default="10", nullable=False))
    op.add_column("profiles", sa.Column("daily_review_cards_limit", sa.Integer(), server_default="50", nullable=False))
    op.create_table(
        "review_cards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("card_type", sa.String(length=40), nullable=False),
        sa.Column("content_key", sa.String(length=180), nullable=False),
        sa.Column("vocabulary_id", sa.Integer(), nullable=True),
        sa.Column("grammar_id", sa.String(length=180), nullable=True),
        sa.Column("state", sa.String(length=40), server_default="NEW", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reps", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lapses", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stability", sa.Float(), nullable=True),
        sa.Column("difficulty", sa.Float(), nullable=True),
        sa.Column("interval_days", sa.Float(), server_default="0", nullable=False),
        sa.Column("scheduler_version", sa.String(length=40), server_default="fsrs-5-default", nullable=False),
        sa.Column("content_snapshot", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "(card_type = 'VOCABULARY' AND grammar_id IS NULL) "
            "OR (card_type = 'GRAMMAR' AND grammar_id IS NOT NULL AND vocabulary_id IS NULL)",
            name="ck_review_cards_one_content_ref",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "card_type", "content_key", name="uq_review_cards_user_content"),
    )
    op.create_index("ix_review_cards_user_due", "review_cards", ["user_id", "due_at"])
    op.create_index("ix_review_cards_user_type", "review_cards", ["user_id", "card_type"])
    op.create_index("ix_review_cards_vocabulary", "review_cards", ["vocabulary_id"])
    op.create_index("ix_review_cards_grammar", "review_cards", ["grammar_id"])
    op.create_table(
        "review_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("card_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("rating", sa.String(length=20), nullable=False),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("previous_state", sa.String(length=40), nullable=False),
        sa.Column("new_state", sa.String(length=40), nullable=False),
        sa.Column("previous_due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("new_due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("previous_stability", sa.Float(), nullable=True),
        sa.Column("new_stability", sa.Float(), nullable=True),
        sa.Column("previous_difficulty", sa.Float(), nullable=True),
        sa.Column("new_difficulty", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=40), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.ForeignKeyConstraint(["card_id"], ["review_cards.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "idempotency_key", name="uq_review_history_user_key"),
    )
    op.create_index("ix_review_history_card_reviewed", "review_history", ["card_id", "reviewed_at"])
    op.create_index("ix_review_history_user_reviewed", "review_history", ["user_id", "reviewed_at"])


def downgrade() -> None:
    op.drop_index("ix_review_history_user_reviewed", table_name="review_history")
    op.drop_index("ix_review_history_card_reviewed", table_name="review_history")
    op.drop_table("review_history")
    op.drop_index("ix_review_cards_grammar", table_name="review_cards")
    op.drop_index("ix_review_cards_vocabulary", table_name="review_cards")
    op.drop_index("ix_review_cards_user_type", table_name="review_cards")
    op.drop_index("ix_review_cards_user_due", table_name="review_cards")
    op.drop_table("review_cards")
    op.drop_column("profiles", "daily_review_cards_limit")
    op.drop_column("profiles", "daily_new_cards_limit")
    op.drop_column("profiles", "timezone")
