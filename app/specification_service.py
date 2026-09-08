from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import (
    ContentMembership,
    ExamLevel,
    ExamRevision,
    ExamSpecification,
    ExamStandard,
    ScoringPolicy,
    User,
    UserLearningTarget,
)
from app.specification_schemas import (
    ExamLevelOut,
    ExamRevisionOut,
    ExamSpecificationOut,
    ExamStandardOut,
    ScoringPolicyOut,
)


def _value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def standard_out(row: ExamStandard) -> ExamStandardOut:
    return ExamStandardOut(
        id=row.id, code=row.code, name=row.name, description=row.description,
        status=_value(row.status), metadata=row.metadata_json or {},
    )


def specification_out(row: ExamSpecification) -> ExamSpecificationOut:
    return ExamSpecificationOut(
        id=row.id, standard_id=row.standard_id, standard_code=row.standard.code,
        code=row.code, name=row.name, description=row.description,
        status=_value(row.status), metadata=row.metadata_json or {},
    )


def revision_out(row: ExamRevision) -> ExamRevisionOut:
    return ExamRevisionOut(
        id=row.id, specification_id=row.specification_id,
        specification_code=row.specification.code, code=row.code, version=row.version,
        name=row.name, description=row.description, status=_value(row.status),
        is_default=row.is_default, metadata=row.metadata_json or {},
    )


def level_out(row: ExamLevel) -> ExamLevelOut:
    return ExamLevelOut(
        id=row.id, revision_id=row.revision_id, revision_code=row.revision.code,
        code=row.code, level_number=row.level_number, display_name=row.display_name,
        description=row.description, sort_order=row.sort_order, status=_value(row.status),
        metadata=row.metadata_json or {},
    )


def scoring_policy_out(row: ScoringPolicy) -> ScoringPolicyOut:
    return ScoringPolicyOut(
        id=row.id, revision_id=row.revision_id, code=row.code, name=row.name,
        version=row.version, policy_type=row.policy_type,
        configuration=row.configuration or {}, status=_value(row.status),
    )


def list_standards(db: Session) -> list[ExamStandardOut]:
    return [standard_out(row) for row in db.scalars(select(ExamStandard).order_by(ExamStandard.id)).all()]


def list_specifications(db: Session, standard_id: int | None = None) -> list[ExamSpecificationOut]:
    stmt = select(ExamSpecification).join(ExamStandard)
    if standard_id is not None:
        stmt = stmt.where(ExamSpecification.standard_id == standard_id)
    return [specification_out(row) for row in db.scalars(stmt.order_by(ExamSpecification.id)).all()]


def get_specification(db: Session, specification_id: int) -> ExamSpecificationOut:
    row = db.get(ExamSpecification, specification_id)
    if not row:
        raise HTTPException(status_code=404, detail="Exam specification not found")
    return specification_out(row)


def list_revisions(db: Session, specification_id: int | None = None) -> list[ExamRevisionOut]:
    stmt = select(ExamRevision).join(ExamSpecification)
    if specification_id is not None:
        stmt = stmt.where(ExamRevision.specification_id == specification_id)
    return [revision_out(row) for row in db.scalars(stmt.order_by(ExamRevision.is_default.desc(), ExamRevision.id)).all()]


def get_revision(db: Session, revision_id: int) -> ExamRevisionOut:
    row = db.get(ExamRevision, revision_id)
    if not row:
        raise HTTPException(status_code=404, detail="Exam revision not found")
    return revision_out(row)


def list_levels(db: Session, revision_id: int) -> list[ExamLevelOut]:
    if not db.get(ExamRevision, revision_id):
        raise HTTPException(status_code=404, detail="Exam revision not found")
    rows = db.scalars(
        select(ExamLevel).where(ExamLevel.revision_id == revision_id).order_by(ExamLevel.sort_order, ExamLevel.id)
    ).all()
    return [level_out(row) for row in rows]


def validate_revision_level(db: Session, revision_id: int, level_id: int) -> ExamLevel:
    level = db.get(ExamLevel, level_id)
    if not level or level.revision_id != revision_id:
        raise HTTPException(status_code=422, detail="Exam level does not belong to the selected revision")
    return level


def upsert_learning_target(db: Session, user: User, revision_id: int, level_id: int) -> UserLearningTarget:
    validate_revision_level(db, revision_id, level_id)
    db.execute(
        update(UserLearningTarget)
        .where(UserLearningTarget.user_id == user.id)
        .values(is_primary=False)
    )
    target = db.scalar(
        select(UserLearningTarget).where(
            UserLearningTarget.user_id == user.id,
            UserLearningTarget.exam_revision_id == revision_id,
            UserLearningTarget.exam_level_id == level_id,
        )
    )
    if target is None:
        target = UserLearningTarget(
            user_id=user.id, exam_revision_id=revision_id, exam_level_id=level_id, is_primary=True
        )
        db.add(target)
    else:
        target.is_primary = True
    db.flush()
    return target


def create_content_membership(
    db: Session,
    *,
    content_type: str,
    content_id: int,
    exam_level_id: int,
    introduced_in_revision_id: int | None = None,
    metadata: dict[str, Any] | None = None,
) -> ContentMembership:
    level = db.get(ExamLevel, exam_level_id)
    if not level:
        raise HTTPException(status_code=422, detail="Exam level does not exist")
    if introduced_in_revision_id is not None and introduced_in_revision_id != level.revision_id:
        raise HTTPException(status_code=422, detail="Membership revision does not match exam level")
    row = ContentMembership(
        content_type=content_type, content_id=content_id, exam_level_id=exam_level_id,
        introduced_in_revision_id=introduced_in_revision_id or level.revision_id,
        metadata_json=metadata or {},
    )
    db.add(row)
    db.flush()
    return row
