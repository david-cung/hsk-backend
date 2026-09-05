"""phase13 gamification events xp streaks achievements notifications

Revision ID: 8d4b2c91e6a0
Revises: 7c3e9a12f4b8
Create Date: 2026-09-02 20:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "8d4b2c91e6a0"
down_revision: Union[str, Sequence[str], None] = "7c3e9a12f4b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "profiles",
        sa.Column("xp_total", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "profiles",
        sa.Column("daily_goal_type", sa.String(length=20), server_default="minutes", nullable=False),
    )
    op.add_column(
        "achievements",
        sa.Column(
            "criteria",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
    )
    op.add_column(
        "achievements",
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
    )

    op.create_table(
        "learning_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_type", "source_key", name="uq_learning_events_idempotency"),
    )
    op.create_index("ix_learning_events_user_id", "learning_events", ["user_id"])
    op.create_index("ix_learning_events_event_type", "learning_events", ["event_type"])
    op.create_index("ix_learning_events_user_created", "learning_events", ["user_id", "created_at"])

    op.create_table(
        "xp_transactions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("source_key", sa.String(length=180), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("xp >= 0", name="ck_xp_transactions_non_negative"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "event_type", "source_key", name="uq_xp_transactions_idempotency"),
    )
    op.create_index("ix_xp_transactions_user_id", "xp_transactions", ["user_id"])
    op.create_index("ix_xp_transactions_event_type", "xp_transactions", ["event_type"])
    op.create_index("ix_xp_transactions_user_created", "xp_transactions", ["user_id", "created_at"])

    op.create_table(
        "user_daily_activity",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("xp", sa.Integer(), server_default="0", nullable=False),
        sa.Column("minutes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("exercises", sa.Integer(), server_default="0", nullable=False),
        sa.Column("lessons", sa.Integer(), server_default="0", nullable=False),
        sa.Column("reviews", sa.Integer(), server_default="0", nullable=False),
        sa.Column("goal_completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "local_date", name="uq_user_daily_activity_day"),
    )
    op.create_index("ix_user_daily_activity_user_id", "user_daily_activity", ["user_id"])
    op.create_index("ix_user_daily_activity_local_date", "user_daily_activity", ["local_date"])
    op.create_index("ix_user_daily_activity_user_date", "user_daily_activity", ["user_id", "local_date"])

    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=20), server_default="local", nullable=False),
        sa.Column("active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token", name="uq_device_tokens_token"),
    )
    op.create_index("ix_device_tokens_user_id", "device_tokens", ["user_id"])

    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("daily_reminder", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("streak_reminder", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("srs_reminder", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("exam_reminder", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("achievement_notification", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )

    op.create_table(
        "notification_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("title", sa.String(length=180), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "kind", "local_date", name="uq_notification_logs_dedupe"),
    )
    op.create_index("ix_notification_logs_user_id", "notification_logs", ["user_id"])
    op.create_index("ix_notification_logs_kind", "notification_logs", ["kind"])


def downgrade() -> None:
    op.drop_index("ix_notification_logs_kind", table_name="notification_logs")
    op.drop_index("ix_notification_logs_user_id", table_name="notification_logs")
    op.drop_table("notification_logs")
    op.drop_table("notification_preferences")
    op.drop_index("ix_device_tokens_user_id", table_name="device_tokens")
    op.drop_table("device_tokens")
    op.drop_index("ix_user_daily_activity_user_date", table_name="user_daily_activity")
    op.drop_index("ix_user_daily_activity_local_date", table_name="user_daily_activity")
    op.drop_index("ix_user_daily_activity_user_id", table_name="user_daily_activity")
    op.drop_table("user_daily_activity")
    op.drop_index("ix_xp_transactions_user_created", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_event_type", table_name="xp_transactions")
    op.drop_index("ix_xp_transactions_user_id", table_name="xp_transactions")
    op.drop_table("xp_transactions")
    op.drop_index("ix_learning_events_user_created", table_name="learning_events")
    op.drop_index("ix_learning_events_event_type", table_name="learning_events")
    op.drop_index("ix_learning_events_user_id", table_name="learning_events")
    op.drop_table("learning_events")
    op.drop_column("achievements", "sort_order")
    op.drop_column("achievements", "criteria")
    op.drop_column("profiles", "daily_goal_type")
    op.drop_column("profiles", "xp_total")
