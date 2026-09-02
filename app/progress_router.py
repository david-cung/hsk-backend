from __future__ import annotations

# ruff: noqa: B008
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.progress_service import (
    course_progress,
    daily_activity,
    hsk_progress,
    lesson_progress,
    summary,
)
from app.schemas import (
    CourseProgressOut,
    DailyActivityOut,
    HskProgressOut,
    LessonProgressAnalyticsOut,
    ProgressSummaryOut,
    SkillPerformanceOut,
)

router = APIRouter(prefix="/api/v1/progress", tags=["progress"])


@router.get("/summary", response_model=ProgressSummaryOut)
def progress_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProgressSummaryOut:
    payload = summary(db, user)
    db.commit()
    return payload


@router.get("/hsk/{level}", response_model=HskProgressOut)
def progress_hsk(
    level: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> HskProgressOut:
    try:
        return hsk_progress(db, user, level)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/courses/{course_id}", response_model=CourseProgressOut)
def progress_course(
    course_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CourseProgressOut:
    try:
        return course_progress(db, user, course_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/lessons/{lesson_id}", response_model=LessonProgressAnalyticsOut)
def progress_lesson(
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonProgressAnalyticsOut:
    try:
        return lesson_progress(db, user, lesson_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/skills", response_model=list[SkillPerformanceOut])
def progress_skills(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SkillPerformanceOut]:
    return summary(db, user).skill_overview


@router.get("/activity", response_model=list[DailyActivityOut])
def progress_activity(
    days: int = 30,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DailyActivityOut]:
    clamped_days = max(1, min(days, 90))
    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=clamped_days - 1)
    return daily_activity(db, user.id, start_date, end_date)
