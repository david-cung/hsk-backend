from __future__ import annotations

# ruff: noqa: B008
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
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
from app.models import MockTest, User
from app.skill_schemas import (
    AdminExamIn,
    ExamAnswerIn,
    ExamAttemptHistoryOut,
    ExamAttemptOut,
    ExamDetailOut,
    ExamListOut,
    ExamResultOut,
)

router = APIRouter(tags=["exams"])
admin_router = APIRouter(prefix="/api/v1/admin/exams", tags=["admin-exams"])


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


@router.get("/api/v1/exams", response_model=list[ExamListOut])
def exams(
    hsk_level: int | None = Query(default=None, ge=1, le=6),
    published: bool = True,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExamListOut]:
    return list_exams(db, user, hsk_level, published)


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
        duration_minutes=payload.duration_minutes,
        question_count=payload.question_count,
        exam_type="MOCK",
        status=payload.status,
        version=1,
        blueprint={"sections": [section.model_dump() for section in payload.sections], "allow_previous_section": True},
        scoring_config=payload.scoring_config or {"score_label": "Estimated Practice Score", "passing_percentage": 60},
        instructions=payload.instructions,
        published_at=datetime.now(UTC) if payload.status == "PUBLISHED" else None,
    )
    db.add(exam)
    db.flush()
    if exam.status == "PUBLISHED":
        validate_exam_content(db, exam)
    db.commit()
    return exam_detail(db, _admin, exam.id)


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
    exam.duration_minutes = payload.duration_minutes
    exam.question_count = payload.question_count
    exam.blueprint = {"sections": [section.model_dump() for section in payload.sections], "allow_previous_section": True}
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
