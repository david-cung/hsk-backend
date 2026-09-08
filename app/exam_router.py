from __future__ import annotations

# ruff: noqa: B008
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.exam_builder_service import (
    apply_document,
    clone_version,
    create_exam,
    list_admin_exams,
    load_version,
    validate_version,
    version_out,
)
from app.exam_service import (
    attempt_history,
    exam_detail,
    list_exams,
    result_for_attempt,
    resume_attempt,
    save_answer,
    start_exam,
    validate_exam_content,
)
from app.exam_service import (
    submit_attempt as submit_attempt_service,
)
from app.models import ContentStatus, MockTest, User
from app.skill_schemas import (
    AdminExamDocumentIn,
    AdminExamIn,
    AdminExamListOut,
    AdminExamVersionOut,
    ExamAnswerIn,
    ExamAttemptHistoryOut,
    ExamAttemptOut,
    ExamDetailOut,
    ExamListOut,
    ExamResultOut,
    ExamValidationOut,
)
from app.specification_schemas import normalize_blueprint
from app.specification_service import validate_revision_level

router = APIRouter(tags=["exams"])
admin_router = APIRouter(prefix="/api/v1/admin/exams", tags=["admin-exams"])
builder_router = APIRouter(prefix="/api/v1/admin/exam-builder", tags=["admin-exam-builder"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@router.get("/api/v1/exams", response_model=list[ExamListOut])
def exams(
    hsk_level: int | None = Query(default=None, ge=1, le=6),
    exam_revision_id: int | None = Query(default=None, ge=1),
    exam_level_id: int | None = Query(default=None, ge=1),
    published: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExamListOut]:
    return list_exams(db, user, hsk_level, published, exam_revision_id, exam_level_id)


@router.get("/api/v1/exams/{exam_id}", response_model=ExamDetailOut)
def exam(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamDetailOut:
    return exam_detail(db, user, exam_id)


@router.post("/api/v1/exams/{exam_id}/start", response_model=ExamAttemptOut, status_code=status.HTTP_201_CREATED)
def start(exam_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamAttemptOut:
    payload = start_exam(db, user, exam_id)
    db.commit()
    return payload


@router.get("/api/v1/exam-attempts", response_model=list[ExamAttemptHistoryOut])
def attempts(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExamAttemptHistoryOut]:
    return attempt_history(db, user, limit, offset)


@router.get("/api/v1/exam-attempts/{attempt_id}", response_model=ExamAttemptOut)
def attempt(attempt_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamAttemptOut:
    payload = resume_attempt(db, user, attempt_id)
    db.commit()
    return payload


@router.put("/api/v1/exam-attempts/{attempt_id}/answers/{question_id}", response_model=ExamAttemptOut)
def answer(
    attempt_id: int,
    question_id: int,
    payload: ExamAnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ExamAttemptOut:
    result = save_answer(db, user, attempt_id, question_id, payload.answer)
    db.commit()
    return result


@router.post("/api/v1/exam-attempts/{attempt_id}/submit", response_model=ExamResultOut)
def submit(attempt_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamResultOut:
    result = submit_attempt_service(db, user, attempt_id)
    db.commit()
    return result


@router.get("/api/v1/exam-attempts/{attempt_id}/result", response_model=ExamResultOut)
def result(attempt_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamResultOut:
    payload = result_for_attempt(db, user, attempt_id)
    db.commit()
    return payload


@admin_router.post("", response_model=ExamDetailOut, status_code=status.HTTP_201_CREATED)
def admin_create_exam(payload: AdminExamIn, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> ExamDetailOut:
    exam = MockTest(
        title=payload.title,
        description=payload.description,
        hsk_level=payload.hsk_level,
        exam_revision_id=payload.exam_revision_id,
        exam_level_id=payload.exam_level_id,
        scoring_policy_id=payload.scoring_policy_id,
        duration_minutes=payload.duration_minutes,
        question_count=payload.question_count,
        exam_type="MOCK",
        status=payload.status,
        version=1,
        blueprint=normalize_blueprint(
            {
                "schema_version": 1,
                "revision_id": payload.exam_revision_id,
                "sections": [section.model_dump() for section in payload.sections],
                "allow_previous_section": True,
            },
            revision_id=payload.exam_revision_id,
        ),
        blueprint_schema_version=1,
        scoring_config=payload.scoring_config or {"score_label": "Estimated Practice Score", "passing_percentage": 60},
        instructions=payload.instructions,
        published_at=datetime.now(UTC) if payload.status == "PUBLISHED" else None,
    )
    db.add(exam)
    db.flush()
    if exam.exam_revision_id and exam.exam_level_id:
        validate_revision_level(db, exam.exam_revision_id, exam.exam_level_id)
    if exam.status == "PUBLISHED":
        validate_exam_content(db, exam)
    db.commit()
    return exam_detail(db, _admin, exam.id)


@admin_router.get("", response_model=AdminExamListOut)
def admin_list_exams(
    query: str | None = Query(default=None, max_length=160),
    exam_revision_id: int | None = Query(default=None, ge=1),
    exam_level_id: int | None = Query(default=None, ge=1),
    status_filter: str | None = Query(default=None, alias="status", pattern="^(draft|published|archived)$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExamListOut:
    return list_admin_exams(
        db, status=status_filter, revision_id=exam_revision_id, level_id=exam_level_id,
        query=query, page=page, page_size=page_size,
    )


@admin_router.patch("/{exam_id}", response_model=ExamDetailOut)
def admin_update_exam(
    exam_id: int,
    payload: AdminExamIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExamDetailOut:
    exam = db.get(MockTest, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    if exam.status == "PUBLISHED":
        raise HTTPException(status_code=409, detail="Published exams are immutable; create a new version")
    exam.title = payload.title
    exam.description = payload.description
    exam.hsk_level = payload.hsk_level
    exam.exam_revision_id = payload.exam_revision_id
    exam.exam_level_id = payload.exam_level_id
    exam.scoring_policy_id = payload.scoring_policy_id
    exam.duration_minutes = payload.duration_minutes
    exam.question_count = payload.question_count
    exam.blueprint = normalize_blueprint(
        {
            "schema_version": 1,
            "revision_id": payload.exam_revision_id,
            "sections": [section.model_dump() for section in payload.sections],
            "allow_previous_section": True,
        },
        revision_id=payload.exam_revision_id,
    )
    exam.blueprint_schema_version = 1
    exam.scoring_config = payload.scoring_config or exam.scoring_config
    exam.instructions = payload.instructions
    exam.status = payload.status
    exam.version += 1
    if exam.status == "PUBLISHED":
        validate_exam_content(db, exam)
        exam.published_at = datetime.now(UTC)
    db.commit()
    return exam_detail(db, _admin, exam.id)


@admin_router.post("/{exam_id}/publish", response_model=ExamDetailOut)
def admin_publish_exam(exam_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> ExamDetailOut:
    exam = db.get(MockTest, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    validate_exam_content(db, exam)
    exam.status = "PUBLISHED"
    exam.published_at = datetime.now(UTC)
    db.commit()
    return exam_detail(db, _admin, exam.id)


@admin_router.post("/{exam_id}/archive", response_model=ExamDetailOut)
def admin_archive_exam(exam_id: int, _admin: User = Depends(require_admin), db: Session = Depends(get_db)) -> ExamDetailOut:
    exam = db.get(MockTest, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    exam.status = "ARCHIVED"
    exam.archived_at = datetime.now(UTC)
    db.commit()
    return exam_detail(db, _admin, exam.id)


@builder_router.post("", response_model=AdminExamVersionOut, status_code=status.HTTP_201_CREATED)
def builder_create(
    payload: AdminExamDocumentIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExamVersionOut:
    version = create_exam(db, payload)
    db.commit()
    return version_out(load_version(db, version.id))


@builder_router.get("/{version_id}", response_model=AdminExamVersionOut)
def builder_get(version_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminExamVersionOut:
    return version_out(load_version(db, version_id))


@builder_router.patch("/{version_id}", response_model=AdminExamVersionOut)
def builder_update(
    version_id: int,
    payload: AdminExamDocumentIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExamVersionOut:
    version = load_version(db, version_id)
    apply_document(db, version, payload)
    db.commit()
    return version_out(load_version(db, version.id))


@builder_router.post("/{version_id}/clone", response_model=AdminExamVersionOut, status_code=status.HTTP_201_CREATED)
def builder_clone(version_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminExamVersionOut:
    version = load_version(db, version_id)
    cloned = clone_version(db, version)
    db.commit()
    return version_out(load_version(db, cloned.id))


@builder_router.post("/{version_id}/validate", response_model=ExamValidationOut)
def builder_validate(version_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> ExamValidationOut:
    return validate_version(db, load_version(db, version_id))


@builder_router.get("/{version_id}/preview", response_model=AdminExamVersionOut)
def builder_preview(version_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminExamVersionOut:
    return version_out(load_version(db, version_id))


@builder_router.post("/{version_id}/publish", response_model=AdminExamVersionOut)
def builder_publish(version_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminExamVersionOut:
    version = load_version(db, version_id)
    validation = validate_version(db, version)
    if not validation.valid:
        raise HTTPException(status_code=422, detail=validation.model_dump())
    version.status = ContentStatus.PUBLISHED
    version.published_at = datetime.now(UTC)
    exam = db.get(MockTest, version.exam_id)
    if exam:
        exam.status = "PUBLISHED"
        exam.version = version.version_number
        exam.title = version.title
        exam.description = version.description
        exam.exam_revision_id = version.exam_revision_id
        exam.exam_level_id = version.exam_level_id
        exam.scoring_policy_id = version.scoring_policy_id
        exam.duration_minutes = max(1, (version.duration_seconds + 59) // 60)
        exam.question_count = sum(len(part.questions) for section in version.sections for part in section.parts)
        exam.instructions = version.instructions
        exam.published_at = version.published_at
    db.commit()
    return version_out(load_version(db, version.id))


@builder_router.post("/{version_id}/archive", response_model=AdminExamVersionOut)
def builder_archive(version_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> AdminExamVersionOut:
    version = load_version(db, version_id)
    version.status = ContentStatus.ARCHIVED
    db.commit()
    return version_out(load_version(db, version.id))
