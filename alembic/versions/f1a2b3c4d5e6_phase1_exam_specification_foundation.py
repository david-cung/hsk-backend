"""phase1 exam specification foundation

Revision ID: f1a2b3c4d5e6
Revises: d9f02a4c6b31
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "d9f02a4c6b31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _jsonb():
    return postgresql.JSONB(astext_type=sa.Text())


def _status_enum():
    return postgresql.ENUM("draft", "published", "archived", name="content_status", create_type=False)


def upgrade() -> None:
    op.create_table(
        "exam_standards",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _status_enum(), nullable=False, server_default="published"),
        sa.Column("metadata", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code", name="uq_exam_standards_code"),
    )
    op.create_index("ix_exam_standards_code", "exam_standards", ["code"])
    op.create_index("ix_exam_standards_status", "exam_standards", ["status"])

    op.create_table(
        "exam_specifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("standard_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _status_enum(), nullable=False, server_default="published"),
        sa.Column("metadata", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["standard_id"], ["exam_standards.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("standard_id", "code", name="uq_exam_specs_standard_code"),
    )
    op.create_index("ix_exam_specifications_standard_id", "exam_specifications", ["standard_id"])
    op.create_index("ix_exam_specifications_status", "exam_specifications", ["status"])

    op.create_table(
        "exam_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("specification_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", _status_enum(), nullable=False, server_default="published"),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("metadata", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["specification_id"], ["exam_specifications.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("specification_id", "code", name="uq_exam_revisions_spec_code"),
    )
    op.create_index("ix_exam_revisions_specification_id", "exam_revisions", ["specification_id"])
    op.create_index("ix_exam_revisions_status", "exam_revisions", ["status"])
    op.create_index("ix_exam_revisions_is_default", "exam_revisions", ["is_default"])
    op.create_index("ix_exam_revisions_spec_status", "exam_revisions", ["specification_id", "status"])

    op.create_table(
        "exam_levels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("level_number", sa.Integer(), nullable=True),
        sa.Column("display_name", sa.String(180), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", _status_enum(), nullable=False, server_default="published"),
        sa.Column("metadata", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("level_number IS NULL OR level_number > 0", name="ck_exam_levels_number_positive"),
        sa.ForeignKeyConstraint(["revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "code", name="uq_exam_levels_revision_code"),
        sa.UniqueConstraint("revision_id", "level_number", name="uq_exam_levels_revision_number"),
    )
    op.create_index("ix_exam_levels_revision_id", "exam_levels", ["revision_id"])
    op.create_index("ix_exam_levels_status", "exam_levels", ["status"])

    op.create_table(
        "scoring_policies",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("revision_id", sa.Integer(), nullable=True),
        sa.Column("code", sa.String(80), nullable=False),
        sa.Column("name", sa.String(180), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("policy_type", sa.String(80), nullable=False),
        sa.Column("configuration", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", _status_enum(), nullable=False, server_default="published"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("revision_id", "code", "version", name="uq_scoring_policies_identity"),
    )
    op.create_index("ix_scoring_policies_revision_id", "scoring_policies", ["revision_id"])
    op.create_index("ix_scoring_policies_status", "scoring_policies", ["status"])

    op.create_table(
        "content_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("content_type", sa.String(60), nullable=False),
        sa.Column("content_id", sa.Integer(), nullable=False),
        sa.Column("exam_level_id", sa.Integer(), nullable=False),
        sa.Column("introduced_in_revision_id", sa.Integer(), nullable=True),
        sa.Column("retired_in_revision_id", sa.Integer(), nullable=True),
        sa.Column("metadata", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["exam_level_id"], ["exam_levels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["introduced_in_revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["retired_in_revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("content_type", "content_id", "exam_level_id", name="uq_content_membership_level"),
    )
    op.create_index("ix_content_memberships_content_type", "content_memberships", ["content_type"])
    op.create_index("ix_content_memberships_content_id", "content_memberships", ["content_id"])
    op.create_index("ix_content_memberships_exam_level_id", "content_memberships", ["exam_level_id"])
    op.create_index("ix_content_memberships_introduced_in_revision_id", "content_memberships", ["introduced_in_revision_id"])
    op.create_index("ix_content_memberships_retired_in_revision_id", "content_memberships", ["retired_in_revision_id"])
    op.create_index("ix_content_memberships_level_type", "content_memberships", ["exam_level_id", "content_type"])

    op.create_table(
        "user_learning_targets",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("exam_revision_id", sa.Integer(), nullable=False),
        sa.Column("exam_level_id", sa.Integer(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("metadata", _jsonb(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["exam_revision_id"], ["exam_revisions.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["exam_level_id"], ["exam_levels.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "exam_revision_id", "exam_level_id", name="uq_user_learning_target"),
    )
    op.create_index("ix_user_learning_targets_user_id", "user_learning_targets", ["user_id"])
    op.create_index("ix_user_learning_targets_exam_revision_id", "user_learning_targets", ["exam_revision_id"])
    op.create_index("ix_user_learning_targets_exam_level_id", "user_learning_targets", ["exam_level_id"])
    op.create_index("ix_user_learning_targets_is_primary", "user_learning_targets", ["is_primary"])
    op.create_index("ix_user_learning_targets_user_primary", "user_learning_targets", ["user_id", "is_primary"])

    op.add_column("hsk_levels", sa.Column("exam_level_id", sa.Integer(), nullable=True))
    op.create_index("ix_hsk_levels_exam_level_id", "hsk_levels", ["exam_level_id"])
    op.create_foreign_key("fk_hsk_levels_exam_level_id", "hsk_levels", "exam_levels", ["exam_level_id"], ["id"], ondelete="RESTRICT")
    op.add_column("mock_tests", sa.Column("exam_revision_id", sa.Integer(), nullable=True))
    op.add_column("mock_tests", sa.Column("exam_level_id", sa.Integer(), nullable=True))
    op.add_column("mock_tests", sa.Column("scoring_policy_id", sa.Integer(), nullable=True))
    op.add_column("mock_tests", sa.Column("blueprint_schema_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_mock_tests_exam_revision_id", "mock_tests", ["exam_revision_id"])
    op.create_index("ix_mock_tests_exam_level_id", "mock_tests", ["exam_level_id"])
    op.create_index("ix_mock_tests_scoring_policy_id", "mock_tests", ["scoring_policy_id"])
    op.create_foreign_key("fk_mock_tests_exam_revision_id", "mock_tests", "exam_revisions", ["exam_revision_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_mock_tests_exam_level_id", "mock_tests", "exam_levels", ["exam_level_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_mock_tests_scoring_policy_id", "mock_tests", "scoring_policies", ["scoring_policy_id"], ["id"], ondelete="RESTRICT")
    op.add_column("exam_attempts", sa.Column("exam_revision_id", sa.Integer(), nullable=True))
    op.add_column("exam_attempts", sa.Column("exam_level_id", sa.Integer(), nullable=True))
    op.add_column("exam_attempts", sa.Column("scoring_policy_id", sa.Integer(), nullable=True))
    op.add_column("exam_attempts", sa.Column("blueprint_schema_version", sa.Integer(), nullable=False, server_default="1"))
    op.create_index("ix_exam_attempts_exam_revision_id", "exam_attempts", ["exam_revision_id"])
    op.create_index("ix_exam_attempts_exam_level_id", "exam_attempts", ["exam_level_id"])
    op.create_index("ix_exam_attempts_scoring_policy_id", "exam_attempts", ["scoring_policy_id"])
    op.create_foreign_key("fk_exam_attempts_exam_revision_id", "exam_attempts", "exam_revisions", ["exam_revision_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_exam_attempts_exam_level_id", "exam_attempts", "exam_levels", ["exam_level_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_exam_attempts_scoring_policy_id", "exam_attempts", "scoring_policies", ["scoring_policy_id"], ["id"], ondelete="RESTRICT")
    op.alter_column("mock_tests", "hsk_level", existing_type=sa.Integer(), nullable=True)

    conn = op.get_bind()
    conn.execute(sa.text("""
        INSERT INTO exam_standards (code, name, description)
        VALUES ('HSK', 'HSK', 'Chinese proficiency examination standard')
        ON CONFLICT (code) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO exam_specifications (standard_id, code, name, description)
        SELECT id, 'HSK_LEGACY', 'Legacy HSK curriculum',
               'Compatibility specification for content created before specification-aware exams.'
        FROM exam_standards WHERE code = 'HSK'
        ON CONFLICT (standard_id, code) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO exam_revisions (specification_id, code, version, name, description, is_default)
        SELECT id, 'CURRENT_LEGACY_HSK_CONTENT', '1', 'Current legacy HSK content',
               'Initial compatibility revision. It must not be presented as an official HSK 2.x or 3.x scoring specification.', true
        FROM exam_specifications WHERE code = 'HSK_LEGACY'
        ON CONFLICT (specification_id, code) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO exam_levels (revision_id, code, level_number, display_name, description, sort_order)
        SELECT r.id, 'LEGACY_HSK_' || h.level_number, h.level_number, h.title, h.description, h.display_order
        FROM exam_revisions r CROSS JOIN hsk_levels h
        WHERE r.code = 'CURRENT_LEGACY_HSK_CONTENT'
        ON CONFLICT (revision_id, code) DO NOTHING
    """))
    conn.execute(sa.text("""
        UPDATE hsk_levels h SET exam_level_id = el.id
        FROM exam_levels el JOIN exam_revisions r ON r.id = el.revision_id
        WHERE r.code = 'CURRENT_LEGACY_HSK_CONTENT' AND el.level_number = h.level_number
    """))
    conn.execute(sa.text("""
        INSERT INTO scoring_policies (revision_id, code, name, version, policy_type, configuration)
        SELECT r.id, 'GENERIC_PRACTICE', 'Generic practice scoring', '1', 'generic_practice',
               '{"passing_percentage": 60, "score_label": "Estimated Practice Score", "official": false}'::jsonb
        FROM exam_revisions r WHERE r.code = 'CURRENT_LEGACY_HSK_CONTENT'
        ON CONFLICT (revision_id, code, version) DO NOTHING
    """))
    conn.execute(sa.text("""
        UPDATE mock_tests mt SET exam_revision_id = r.id, exam_level_id = el.id, scoring_policy_id = sp.id
        FROM exam_revisions r, exam_levels el, scoring_policies sp
        WHERE r.code = 'CURRENT_LEGACY_HSK_CONTENT'
          AND el.revision_id = r.id AND el.level_number = mt.hsk_level
          AND sp.revision_id = r.id AND sp.code = 'GENERIC_PRACTICE' AND sp.version = '1'
    """))
    conn.execute(sa.text("""
        UPDATE exam_attempts ea SET exam_revision_id = mt.exam_revision_id,
            exam_level_id = mt.exam_level_id, scoring_policy_id = mt.scoring_policy_id
        FROM mock_tests mt WHERE mt.id = ea.exam_id
    """))
    conn.execute(sa.text("""
        INSERT INTO user_learning_targets (user_id, exam_revision_id, exam_level_id, is_primary, metadata)
        SELECT p.user_id, r.id, el.id, true, '{"source":"profile_compatibility"}'::jsonb
        FROM profiles p JOIN exam_revisions r ON r.code = 'CURRENT_LEGACY_HSK_CONTENT'
        JOIN exam_levels el ON el.revision_id = r.id AND el.level_number = p.target_hsk_level
        ON CONFLICT (user_id, exam_revision_id, exam_level_id) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO content_memberships (content_type, content_id, exam_level_id, introduced_in_revision_id, metadata)
        SELECT 'lesson', l.id, h.exam_level_id, r.id, '{"source":"legacy_hsk_content"}'::jsonb
        FROM lessons l JOIN hsk_levels h ON h.id = l.hsk_level_id
        JOIN exam_revisions r ON r.code = 'CURRENT_LEGACY_HSK_CONTENT'
        WHERE h.exam_level_id IS NOT NULL
        ON CONFLICT (content_type, content_id, exam_level_id) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO content_memberships (content_type, content_id, exam_level_id, introduced_in_revision_id, metadata)
        SELECT 'vocabulary', v.id, h.exam_level_id, r.id, '{"source":"legacy_hsk_content"}'::jsonb
        FROM vocabulary v JOIN hsk_levels h ON h.id = v.hsk_level_id
        JOIN exam_revisions r ON r.code = 'CURRENT_LEGACY_HSK_CONTENT'
        WHERE h.exam_level_id IS NOT NULL
        ON CONFLICT (content_type, content_id, exam_level_id) DO NOTHING
    """))
    conn.execute(sa.text("""
        INSERT INTO content_memberships (content_type, content_id, exam_level_id, introduced_in_revision_id, metadata)
        SELECT 'grammar', g.id, h.exam_level_id, r.id, '{"source":"legacy_hsk_content"}'::jsonb
        FROM grammar_points g JOIN hsk_levels h ON h.id = g.hsk_level_id
        JOIN exam_revisions r ON r.code = 'CURRENT_LEGACY_HSK_CONTENT'
        WHERE h.exam_level_id IS NOT NULL
        ON CONFLICT (content_type, content_id, exam_level_id) DO NOTHING
    """))


def downgrade() -> None:
    op.alter_column("mock_tests", "hsk_level", existing_type=sa.Integer(), nullable=False)
    for name, table in (
        ("fk_exam_attempts_scoring_policy_id", "exam_attempts"),
        ("fk_exam_attempts_exam_level_id", "exam_attempts"),
        ("fk_exam_attempts_exam_revision_id", "exam_attempts"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    for column in ("blueprint_schema_version", "scoring_policy_id", "exam_level_id", "exam_revision_id"):
        op.drop_column("exam_attempts", column)
    for name, table in (
        ("fk_mock_tests_scoring_policy_id", "mock_tests"),
        ("fk_mock_tests_exam_level_id", "mock_tests"),
        ("fk_mock_tests_exam_revision_id", "mock_tests"),
    ):
        op.drop_constraint(name, table, type_="foreignkey")
    for column in ("blueprint_schema_version", "scoring_policy_id", "exam_level_id", "exam_revision_id"):
        op.drop_column("mock_tests", column)
    op.drop_constraint("fk_hsk_levels_exam_level_id", "hsk_levels", type_="foreignkey")
    op.drop_column("hsk_levels", "exam_level_id")
    for table in ("user_learning_targets", "content_memberships", "scoring_policies", "exam_levels", "exam_revisions", "exam_specifications", "exam_standards"):
        op.drop_table(table)
