"""phase2 canonical question bank

Revision ID: 2a3b4c5d6e7f
Revises: f1a2b3c4d5e6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "2a3b4c5d6e7f"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return postgresql.JSONB(astext_type=sa.Text())


def _status_enum():
    return postgresql.ENUM("draft", "published", "archived", name="content_status", create_type=False)


def upgrade() -> None:
    op.create_table(
        "question_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", _status_enum(), nullable=False, server_default="draft"),
        sa.Column("question_type", sa.String(40), nullable=False),
        sa.Column("skill", sa.String(40), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("instruction", sa.Text(), nullable=True),
        sa.Column("correct_answer", sa.Text(), nullable=False, server_default=""),
        sa.Column("explanation", sa.Text(), nullable=True),
        sa.Column("difficulty", sa.Integer(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reference_type", sa.String(40), nullable=True),
        sa.Column("reference_id", sa.String(120), nullable=True),
        sa.Column("metadata", _jsonb(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_question_versions_number_positive"),
        sa.CheckConstraint("points > 0", name="ck_question_versions_points"),
        sa.CheckConstraint("length(trim(prompt)) > 0", name="ck_question_versions_prompt_not_empty"),
        sa.ForeignKeyConstraint(["question_id"], ["questions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_id", "version_number", name="uq_question_versions_number"),
    )
    op.create_index("ix_question_versions_question_id", "question_versions", ["question_id"])
    op.create_index("ix_question_versions_status", "question_versions", ["status"])
    op.create_index("ix_question_versions_question_status", "question_versions", ["question_id", "status"])

    op.create_table(
        "question_options",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("question_version_id", sa.Integer(), nullable=False),
        sa.Column("option_group", sa.String(40), nullable=False, server_default="options"),
        sa.Column("option_id", sa.String(120), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("translations", _jsonb(), nullable=True),
        sa.Column("is_correct", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("question_version_id", "option_group", "option_id", name="uq_question_options_identity"),
    )
    op.create_index("ix_question_options_question_version_id", "question_options", ["question_version_id"])
    op.create_index("ix_question_options_version_group", "question_options", ["question_version_id", "option_group"])

    op.add_column("questions", sa.Column("current_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_questions_current_version_id", "questions", ["current_version_id"])
    op.create_foreign_key(
        "fk_questions_current_version_id",
        "questions",
        "question_versions",
        ["current_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("practice_sessions", sa.Column("question_version_ids", _jsonb(), nullable=True))
    op.add_column("question_attempts", sa.Column("question_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_question_attempts_question_version_id", "question_attempts", ["question_version_id"])
    op.create_foreign_key(
        "fk_question_attempts_question_version_id",
        "question_attempts",
        "question_versions",
        ["question_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.add_column("mock_tests", sa.Column("question_version_ids", _jsonb(), nullable=False, server_default=sa.text("'[]'::jsonb")))
    op.add_column("exam_question_results", sa.Column("question_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_exam_question_results_question_version_id", "exam_question_results", ["question_version_id"])
    op.create_foreign_key(
        "fk_exam_question_results_question_version_id",
        "exam_question_results",
        "question_versions",
        ["question_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    op.execute(
        sa.text(
            """
            INSERT INTO question_versions (
                question_id, version_number, status, question_type, skill, prompt, instruction,
                correct_answer, explanation, difficulty, points, configuration,
                reference_type, reference_id, metadata, published_at
            )
            SELECT q.id, 1, q.status, q.question_type, e.skill, q.prompt, q.instruction,
                   q.correct_answer, q.explanation, q.difficulty, q.points,
                   COALESCE(q.configuration, '{}'::jsonb),
                   q.reference_type, q.reference_id, q.metadata,
                   CASE WHEN q.status = 'published' THEN COALESCE(q.updated_at, now()) ELSE NULL END
            FROM questions q
            LEFT JOIN exercises e ON e.id = q.exercise_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE questions q
            SET current_version_id = qv.id
            FROM question_versions qv
            WHERE qv.question_id = q.id AND qv.version_number = 1
              AND q.status = 'published'
            """
        )
    )
    op.execute(
        sa.text(
            """
            INSERT INTO question_options (
                question_version_id, option_group, option_id, text, translations, is_correct, sort_order
            )
            SELECT qv.id, 'options', option->>'id', option->>'text', option->'translations',
                   (option->>'id') IN (
                       SELECT jsonb_array_elements_text(qv.configuration->'correct_option_ids')
                   ), ordinality - 1
            FROM question_versions qv
            CROSS JOIN LATERAL jsonb_array_elements(qv.configuration->'options') WITH ORDINALITY AS items(option, ordinality)
            WHERE jsonb_typeof(qv.configuration->'options') = 'array'
              AND option->>'id' IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE practice_sessions ps
            SET question_version_ids = COALESCE((
                SELECT jsonb_agg(qv.id ORDER BY ids.ordinality)
                FROM jsonb_array_elements_text(ps.question_ids) WITH ORDINALITY AS ids(question_id, ordinality)
                JOIN questions q ON q.id = ids.question_id::integer
                JOIN question_versions qv ON qv.id = q.current_version_id
            ), '[]'::jsonb)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE question_attempts qa
            SET question_version_id = q.current_version_id
            FROM questions q
            WHERE q.id = qa.question_id
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE mock_tests mt
            SET question_version_ids = COALESCE((
                SELECT jsonb_agg(q.current_version_id ORDER BY q.id)
                FROM questions q
                JOIN lessons l ON l.id = q.lesson_id
                JOIN hsk_levels hl ON hl.id = l.hsk_level_id
                WHERE q.current_version_id IS NOT NULL
                  AND hl.level_number = mt.hsk_level
            ), '[]'::jsonb)
            WHERE mt.hsk_level IS NOT NULL
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE exam_question_results eqr
            SET question_version_id = q.current_version_id
            FROM questions q
            WHERE q.id = eqr.question_id
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_exam_question_results_question_version_id", "exam_question_results", type_="foreignkey")
    op.drop_index("ix_exam_question_results_question_version_id", table_name="exam_question_results")
    op.drop_column("exam_question_results", "question_version_id")
    op.drop_column("mock_tests", "question_version_ids")
    op.drop_constraint("fk_question_attempts_question_version_id", "question_attempts", type_="foreignkey")
    op.drop_index("ix_question_attempts_question_version_id", table_name="question_attempts")
    op.drop_column("question_attempts", "question_version_id")
    op.drop_column("practice_sessions", "question_version_ids")
    op.drop_constraint("fk_questions_current_version_id", "questions", type_="foreignkey")
    op.drop_index("ix_questions_current_version_id", table_name="questions")
    op.drop_column("questions", "current_version_id")
    op.drop_index("ix_question_options_version_group", table_name="question_options")
    op.drop_index("ix_question_options_question_version_id", table_name="question_options")
    op.drop_table("question_options")
    op.drop_index("ix_question_versions_question_status", table_name="question_versions")
    op.drop_index("ix_question_versions_status", table_name="question_versions")
    op.drop_index("ix_question_versions_question_id", table_name="question_versions")
    op.drop_table("question_versions")
