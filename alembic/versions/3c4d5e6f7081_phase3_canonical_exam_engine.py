"""phase3 canonical exam engine

Revision ID: 3c4d5e6f7081
Revises: 2b3c4d5e6f70
"""

import json
from typing import Any, Sequence, Union

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "3c4d5e6f7081"
down_revision: Union[str, Sequence[str], None] = "2b3c4d5e6f70"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return postgresql.JSONB(astext_type=sa.Text())


def _status_enum():
    return postgresql.ENUM("draft", "published", "archived", name="content_status", create_type=False)


def _status(value: str | None) -> str:
    return str(value or "draft").lower()


def _sections(blueprint: Any) -> list[dict[str, Any]]:
    if not isinstance(blueprint, dict):
        return []
    rows = blueprint.get("sections")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def upgrade() -> None:
    op.create_table(
        "exam_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_id", sa.Integer(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", _status_enum(), nullable=False, server_default="draft"),
        sa.Column("exam_revision_id", sa.Integer(), nullable=True),
        sa.Column("exam_level_id", sa.Integer(), nullable=True),
        sa.Column("scoring_policy_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("duration_seconds", sa.Integer(), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("blueprint_schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("configuration", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("metadata", _jsonb(), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("version_number > 0", name="ck_exam_versions_number_positive"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_exam_versions_duration_positive"),
        sa.ForeignKeyConstraint(["exam_id"], ["mock_tests.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exam_revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exam_level_id"], ["exam_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scoring_policy_id"], ["scoring_policies.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_id", "version_number", name="uq_exam_versions_number"),
    )
    op.create_index("ix_exam_versions_exam_id", "exam_versions", ["exam_id"])
    op.create_index("ix_exam_versions_status", "exam_versions", ["status"])
    op.create_index("ix_exam_versions_exam_status", "exam_versions", ["exam_id", "status"])
    op.create_index("ix_exam_versions_exam_revision_id", "exam_versions", ["exam_revision_id"])
    op.create_index("ix_exam_versions_exam_level_id", "exam_versions", ["exam_level_id"])
    op.create_index("ix_exam_versions_scoring_policy_id", "exam_versions", ["scoring_policy_id"])

    op.create_table(
        "exam_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_version_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("skill", sa.String(40), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_seconds", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("configuration", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_exam_sections_order_nonnegative"),
        sa.CheckConstraint("duration_seconds >= 0", name="ck_exam_sections_duration_nonnegative"),
        sa.ForeignKeyConstraint(["exam_version_id"], ["exam_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_version_id", "code", name="uq_exam_sections_code"),
        sa.UniqueConstraint("exam_version_id", "sort_order", name="uq_exam_sections_order"),
    )
    op.create_index("ix_exam_sections_exam_version_id", "exam_sections", ["exam_version_id"])
    op.create_index("ix_exam_sections_skill", "exam_sections", ["skill"])

    op.create_table(
        "exam_parts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_section_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(80), nullable=True),
        sa.Column("title", sa.String(180), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("configuration", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("sort_order >= 0", name="ck_exam_parts_order_nonnegative"),
        sa.ForeignKeyConstraint(["exam_section_id"], ["exam_sections.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_section_id", "sort_order", name="uq_exam_parts_order"),
    )
    op.create_index("ix_exam_parts_exam_section_id", "exam_parts", ["exam_section_id"])

    op.create_table(
        "exam_questions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("exam_part_id", sa.Integer(), nullable=False),
        sa.Column("question_version_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("points", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("required", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("configuration", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["exam_part_id"], ["exam_parts.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_version_id"], ["question_versions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exam_part_id", "sort_order", name="uq_exam_questions_order"),
        sa.CheckConstraint("sort_order >= 0", name="ck_exam_questions_order_nonnegative"),
        sa.CheckConstraint("points > 0", name="ck_exam_questions_points"),
    )
    op.create_index("ix_exam_questions_exam_part_id", "exam_questions", ["exam_part_id"])
    op.create_index("ix_exam_questions_question_version_id", "exam_questions", ["question_version_id"])

    op.add_column("exam_attempts", sa.Column("exam_version_id", sa.Integer(), nullable=True))
    op.create_index("ix_exam_attempts_exam_version_id", "exam_attempts", ["exam_version_id"])
    op.create_foreign_key(
        "fk_exam_attempts_exam_version_id",
        "exam_attempts",
        "exam_versions",
        ["exam_version_id"],
        ["id"],
        ondelete="RESTRICT",
    )

    conn = op.get_bind()
    exams = conn.execute(
        sa.text(
            """
            SELECT id, title, description, hsk_level, exam_revision_id, exam_level_id,
                   scoring_policy_id, duration_minutes, status, blueprint,
                   question_count, question_version_ids, blueprint_schema_version, scoring_config, instructions
            FROM mock_tests
            """
        )
    ).mappings().all()
    for exam in exams:
        existing = conn.execute(
            sa.text("SELECT id FROM exam_versions WHERE exam_id = :exam_id AND version_number = :version"),
            {"exam_id": exam["id"], "version": int(exam.get("version") or 1)},
        ).scalar()
        if existing:
            continue
        version_number = 1
        status = _status(exam["status"])
        version_id = conn.execute(
            sa.text(
                """
                INSERT INTO exam_versions (
                    exam_id, version_number, status, exam_revision_id, exam_level_id,
                    scoring_policy_id, title, description, duration_seconds, instructions,
                    blueprint_schema_version, configuration, published_at
                ) VALUES (
                    :exam_id, :version_number, :status, :revision_id, :level_id,
                    :scoring_id, :title, :description, :duration_seconds, :instructions,
                    :schema_version, CAST(:configuration AS JSONB),
                    CASE WHEN CAST(:status AS content_status) = 'published' THEN COALESCE(:published_at, now()) ELSE NULL END
                ) RETURNING id
                """
            ),
            {
                "exam_id": exam["id"],
                "version_number": version_number,
                "status": status,
                "revision_id": exam["exam_revision_id"],
                "level_id": exam["exam_level_id"],
                "scoring_id": exam["scoring_policy_id"],
                "title": exam["title"],
                "description": exam["description"],
                "duration_seconds": max(int(exam["duration_minutes"] or 1) * 60, 1),
                "instructions": exam["instructions"],
                "schema_version": int(exam["blueprint_schema_version"] or 1),
                "configuration": json.dumps(exam["blueprint"] or {}),
                "published_at": None,
            },
        ).scalar_one()

        blueprint = exam["blueprint"] or {}
        sections = _sections(blueprint)
        if not sections:
            sections = [{"type": "VOCABULARY", "title": "Vocabulary", "question_count": int(exam["question_count"] or 0), "duration_minutes": int(exam["duration_minutes"] or 1)}]
        qv_ids = [int(item) for item in (exam["question_version_ids"] or []) if str(item).isdigit()]
        qv_rows = conn.execute(
            sa.text(
                "SELECT id, points, skill, question_type "
                "FROM question_versions WHERE id = ANY(CAST(:ids AS INTEGER[]))"
            ),
            {"ids": qv_ids or [0]},
        ).mappings().all()
        qv_by_id = {int(row["id"]): row for row in qv_rows}
        used: set[int] = set()
        for section_index, section in enumerate(sections):
            code = str(section.get("type") or f"SECTION_{section_index + 1}").upper()
            section_id = conn.execute(
                sa.text(
                    """
                    INSERT INTO exam_sections (
                        exam_version_id, code, title, skill, sort_order, duration_seconds,
                        instructions, configuration
                    ) VALUES (:version_id, :code, :title, :skill, :sort_order, :duration_seconds, :instructions, CAST(:configuration AS JSONB))
                    RETURNING id
                    """
                ),
                {
                    "version_id": version_id,
                    "code": code,
                    "title": str(section.get("title") or code.title()),
                    "skill": code.lower(),
                    "sort_order": section_index,
                    "duration_seconds": max(int(section.get("duration_minutes") or 0) * 60, 0),
                    "instructions": section.get("instructions"),
                    "configuration": json.dumps(section),
                },
            ).scalar_one()
            part_id = conn.execute(
                sa.text(
                    """
                    INSERT INTO exam_parts (exam_section_id, code, title, instructions, sort_order, configuration)
                    VALUES (:section_id, :code, :title, :instructions, 0, CAST(:configuration AS JSONB))
                    RETURNING id
                    """
                ),
                {
                    "section_id": section_id,
                    "code": f"{code}_1",
                    "title": "Part 1",
                    "instructions": section.get("instructions"),
                    "configuration": json.dumps({}),
                },
            ).scalar_one()
            matching = [
                qv_by_id[qv_id]
                for qv_id in qv_ids
                if qv_id in qv_by_id
                and qv_id not in used
                and (str(qv_by_id[qv_id]["skill"] or "").lower() == code.lower() or section_index == 0)
            ]
            for question_index, qv in enumerate(matching):
                used.add(int(qv["id"]))
                conn.execute(
                    sa.text(
                        """
                        INSERT INTO exam_questions (exam_part_id, question_version_id, sort_order, points, required, configuration)
                        VALUES (:part_id, :question_version_id, :sort_order, :points, true, '{}'::jsonb)
                        """
                    ),
                    {
                        "part_id": part_id,
                        "question_version_id": int(qv["id"]),
                        "sort_order": question_index,
                        "points": max(int(qv["points"] or 1), 1),
                    },
                )

    conn.execute(
        sa.text(
            """
            UPDATE exam_attempts ea
            SET exam_version_id = ev.id
            FROM exam_versions ev
            WHERE ev.exam_id = ea.exam_id AND ev.version_number = ea.exam_version
            """
        )
    )


def downgrade() -> None:
    op.drop_constraint("fk_exam_attempts_exam_version_id", "exam_attempts", type_="foreignkey")
    op.drop_index("ix_exam_attempts_exam_version_id", table_name="exam_attempts")
    op.drop_column("exam_attempts", "exam_version_id")
    op.drop_index("ix_exam_questions_question_version_id", table_name="exam_questions")
    op.drop_index("ix_exam_questions_exam_part_id", table_name="exam_questions")
    op.drop_table("exam_questions")
    op.drop_index("ix_exam_parts_exam_section_id", table_name="exam_parts")
    op.drop_table("exam_parts")
    op.drop_index("ix_exam_sections_skill", table_name="exam_sections")
    op.drop_index("ix_exam_sections_exam_version_id", table_name="exam_sections")
    op.drop_table("exam_sections")
    op.drop_index("ix_exam_versions_scoring_policy_id", table_name="exam_versions")
    op.drop_index("ix_exam_versions_exam_level_id", table_name="exam_versions")
    op.drop_index("ix_exam_versions_exam_revision_id", table_name="exam_versions")
    op.drop_index("ix_exam_versions_exam_status", table_name="exam_versions")
    op.drop_index("ix_exam_versions_status", table_name="exam_versions")
    op.drop_index("ix_exam_versions_exam_id", table_name="exam_versions")
    op.drop_table("exam_versions")
