from __future__ import annotations

from math import ceil
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import delete, exists, func, or_, select
from sqlalchemy.orm import Session, aliased, joinedload

from app.auth import require_admin
from app.database import get_db
from app.models import (
    ContentMembership,
    ContentStatus,
    ExamLevel,
    ExamRevision,
    ExamSpecification,
    Exercise,
    Question,
    QuestionVersion,
    User,
)
from app.practice_engine import canonical_exercise_type, validate_question_configuration
from app.question_service import (
    create_version,
    ensure_current_version,
    legacy_answer_from_configuration,
    publish_version,
)
from app.schemas import (
    QuestionBankCreate,
    QuestionBankItemOut,
    QuestionBankListOut,
    QuestionBankUpdate,
)
from app.specification_service import validate_revision_level

router = APIRouter(prefix="/api/v1/admin/question-bank", tags=["admin-question-bank"])


def _latest_version(db: Session, question: Question) -> QuestionVersion:
    if question.current_version_id:
        version = db.get(QuestionVersion, question.current_version_id)
        if version is not None:
            return version
    versions = sorted(question.versions, key=lambda item: (item.version_number, item.id), reverse=True)
    if versions:
        return versions[0]
    return ensure_current_version(db, question)


def _membership(db: Session, question_id: int) -> tuple[ContentMembership | None, ExamLevel | None, ExamRevision | None, ExamSpecification | None]:
    row = db.execute(
        select(ContentMembership, ExamLevel, ExamRevision, ExamSpecification)
        .join(ExamLevel, ExamLevel.id == ContentMembership.exam_level_id)
        .join(ExamRevision, ExamRevision.id == ExamLevel.revision_id)
        .join(ExamSpecification, ExamSpecification.id == ExamRevision.specification_id)
        .where(ContentMembership.content_type == "question", ContentMembership.content_id == question_id)
        .order_by(ContentMembership.id)
    ).first()
    if row is None:
        return None, None, None, None
    membership, level, revision, specification = row
    return membership, level, revision, specification


def _item(db: Session, question: Question, version: QuestionVersion | None = None) -> QuestionBankItemOut:
    version = version or _latest_version(db, question)
    membership, level, revision, specification = _membership(db, question.id)
    return QuestionBankItemOut(
        id=question.id,
        question_version_id=version.id,
        version_number=version.version_number,
        exercise_id=question.exercise_id,
        lesson_id=question.lesson_id,
        external_id=question.external_id,
        question_type=version.question_type,
        prompt=version.prompt,
        instruction=version.instruction,
        explanation=version.explanation,
        difficulty=version.difficulty,
        points=version.points,
        order=question.sort_order,
        configuration=version.configuration,
        status=str(version.status.value if hasattr(version.status, "value") else version.status),
        metadata=version.metadata_json,
        exam_revision_id=revision.id if revision else None,
        exam_level_id=level.id if level else None,
        specification_id=specification.id if specification else None,
        skill=version.skill,
    )


def _membership_exists(question_id: Any, exam_level_id: int | None = None, exam_revision_id: int | None = None, specification_id: int | None = None):
    membership_query = select(ContentMembership.id).join(ExamLevel, ExamLevel.id == ContentMembership.exam_level_id).join(ExamRevision, ExamRevision.id == ExamLevel.revision_id).join(ExamSpecification, ExamSpecification.id == ExamRevision.specification_id).where(
        ContentMembership.content_type == "question",
        ContentMembership.content_id == question_id,
    )
    if exam_level_id is not None:
        membership_query = membership_query.where(ContentMembership.exam_level_id == exam_level_id)
    if exam_revision_id is not None:
        membership_query = membership_query.where(ExamLevel.revision_id == exam_revision_id)
    if specification_id is not None:
        membership_query = membership_query.where(ExamRevision.specification_id == specification_id)
    return exists(membership_query)


def _query(
    *,
    query: str | None,
    exam_level_id: int | None,
    exam_revision_id: int | None,
    specification_id: int | None,
    skill: str | None,
    question_type: str | None,
    status_filter: str | None,
):
    latest_version = aliased(QuestionVersion)
    latest_version_id = (
        select(QuestionVersion.id)
        .where(QuestionVersion.question_id == Question.id)
        .order_by(QuestionVersion.version_number.desc(), QuestionVersion.id.desc())
        .limit(1)
        .correlate(Question)
        .scalar_subquery()
    )
    stmt = (
        select(Question)
        .outerjoin(latest_version, latest_version.id == latest_version_id)
        .join(Exercise, Exercise.id == Question.exercise_id, isouter=True)
        .options(joinedload(Question.versions))
    )
    if query:
        pattern = f"%{query.strip()}%"
        stmt = stmt.where(or_(Question.external_id.ilike(pattern), latest_version.prompt.ilike(pattern)))
    if skill:
        stmt = stmt.where(or_(latest_version.skill == skill, Exercise.skill == skill))
    if question_type:
        stmt = stmt.where(latest_version.question_type == question_type)
    if status_filter:
        stmt = stmt.where(latest_version.status == status_filter)
    if any(item is not None for item in (exam_level_id, exam_revision_id, specification_id)):
        stmt = stmt.where(_membership_exists(Question.id, exam_level_id, exam_revision_id, specification_id))
    return stmt.order_by(Question.updated_at.desc(), Question.id.desc())


def _status(value: Any) -> ContentStatus:
    try:
        return ContentStatus(value)
    except ValueError:
        raise HTTPException(status_code=422, detail=f"Unsupported question status: {value}") from None


@router.get("", response_model=QuestionBankListOut)
def list_question_bank(
    query: str | None = Query(default=None, max_length=160),
    specification_id: int | None = Query(default=None, ge=1),
    exam_revision_id: int | None = Query(default=None, ge=1),
    exam_level_id: int | None = Query(default=None, ge=1),
    skill: str | None = Query(default=None, max_length=40),
    question_type: str | None = Query(default=None, max_length=40),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(draft|published|archived)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QuestionBankListOut:
    stmt = _query(
        query=query,
        exam_level_id=exam_level_id,
        exam_revision_id=exam_revision_id,
        specification_id=specification_id,
        skill=skill,
        question_type=question_type,
        status_filter=status_filter,
    )
    total = int(db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0)
    rows = db.scalars(stmt.offset((page - 1) * page_size).limit(page_size)).unique().all()
    return QuestionBankListOut(
        items=[_item(db, row) for row in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=ceil(total / page_size) if total else 0,
    )


def _validated_values(question_type: str, configuration: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    normalized_type = canonical_exercise_type(question_type).value
    normalized_config = validate_question_configuration(normalized_type, configuration).model_dump()
    return normalized_type, normalized_config


@router.post("", response_model=QuestionBankItemOut, status_code=status.HTTP_201_CREATED)
def create_question_bank_item(
    payload: QuestionBankCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QuestionBankItemOut:
    validate_revision_level(db, payload.exam_revision_id, payload.exam_level_id)
    exercise = db.get(Exercise, payload.exercise_id)
    if exercise is None or exercise.exercise_set.lesson_id != payload.lesson_id:
        raise HTTPException(status_code=422, detail="Exercise does not belong to lesson")
    question_type, configuration = _validated_values(payload.question_type, payload.configuration)
    question = Question(
        lesson_id=payload.lesson_id,
        exercise_id=payload.exercise_id,
        external_id=payload.external_id,
        question_type=question_type,
        prompt=payload.prompt.strip(),
        instruction=payload.instruction,
        correct_answer=legacy_answer_from_configuration(configuration),
        explanation=payload.explanation,
        difficulty=payload.difficulty,
        points=payload.points,
        configuration=configuration,
        sort_order=payload.order,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    db.add(question)
    db.flush()
    version = create_version(
        db,
        question,
        status=payload.status,
        values={"question_type": question_type, "configuration": configuration, "skill": payload.skill},
    )
    db.add(
        ContentMembership(
            content_type="question",
            content_id=question.id,
            exam_level_id=payload.exam_level_id,
            introduced_in_revision_id=payload.exam_revision_id,
        )
    )
    db.commit()
    db.refresh(question)
    return _item(db, question, version)


def _question_or_404(db: Session, question_id: int) -> Question:
    question = db.scalar(select(Question).where(Question.id == question_id).options(joinedload(Question.versions)))
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.get("/{question_id}", response_model=QuestionBankItemOut)
def get_question_bank_item(
    question_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QuestionBankItemOut:
    question = _question_or_404(db, question_id)
    return _item(db, question)


@router.patch("/{question_id}", response_model=QuestionBankItemOut)
def update_question_bank_item(
    question_id: int,
    payload: QuestionBankUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QuestionBankItemOut:
    question = _question_or_404(db, question_id)
    current = _latest_version(db, question)
    updates = payload.model_dump(exclude_unset=True)
    question_type, configuration = _validated_values(
        updates.get("question_type", current.question_type),
        updates.get("configuration", current.configuration),
    )
    effective_revision = updates.get("exam_revision_id")
    effective_level = updates.get("exam_level_id")
    if (effective_revision is None) != (effective_level is None):
        raise HTTPException(status_code=422, detail="Both exam revision and exam level are required")
    if effective_revision is not None and effective_level is not None:
        validate_revision_level(db, effective_revision, effective_level)
        db.execute(delete(ContentMembership).where(ContentMembership.content_type == "question", ContentMembership.content_id == question.id))
        db.add(ContentMembership(content_type="question", content_id=question.id, exam_level_id=effective_level, introduced_in_revision_id=effective_revision))
    version_values = {
        "question_type": question_type,
        "prompt": updates.get("prompt", current.prompt),
        "instruction": updates.get("instruction", current.instruction),
        "correct_answer": legacy_answer_from_configuration(configuration),
        "explanation": updates.get("explanation", current.explanation),
        "difficulty": updates.get("difficulty", current.difficulty),
        "points": updates.get("points", current.points),
        "configuration": configuration,
        "metadata_json": updates.get("metadata", current.metadata_json),
        "skill": updates.get("skill", current.skill),
    }
    version_status = _status(updates.get("status", current.status))
    version = create_version(db, question, status=version_status, values=version_values)
    question.sort_order = updates.get("order", question.sort_order)
    if version_status != ContentStatus.PUBLISHED:
        question.status = version_status
    db.commit()
    db.refresh(question)
    return _item(db, question, version)


@router.post("/{question_id}/publish", response_model=QuestionBankItemOut)
def publish_question_bank_item(
    question_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QuestionBankItemOut:
    question = _question_or_404(db, question_id)
    version = _latest_version(db, question)
    publish_version(db, question, version)
    db.commit()
    db.refresh(question)
    return _item(db, question, version)


@router.post("/{question_id}/archive", response_model=QuestionBankItemOut)
def archive_question_bank_item(
    question_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> QuestionBankItemOut:
    question = _question_or_404(db, question_id)
    version = _latest_version(db, question)
    version.status = ContentStatus.ARCHIVED
    question.status = ContentStatus.ARCHIVED
    question.is_archived = True
    db.commit()
    db.refresh(question)
    return _item(db, question, version)
