from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.specification_schemas import (
    ExamLevelOut,
    ExamRevisionOut,
    ExamSpecificationOut,
    ExamStandardOut,
)
from app.specification_service import (
    get_revision,
    get_specification,
    list_levels,
    list_revisions,
    list_specifications,
    list_standards,
)

router = APIRouter(tags=["exam-metadata"])


@router.get("/api/v1/exam-standards", response_model=list[ExamStandardOut])
def standards(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ExamStandardOut]:
    return list_standards(db)


@router.get("/api/v1/exam-specifications", response_model=list[ExamSpecificationOut])
def specifications(
    standard_id: int | None = Query(default=None, ge=1),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExamSpecificationOut]:
    return list_specifications(db, standard_id)


@router.get("/api/v1/exam-specifications/{specification_id}", response_model=ExamSpecificationOut)
def specification(specification_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamSpecificationOut:
    return get_specification(db, specification_id)


@router.get("/api/v1/exam-revisions", response_model=list[ExamRevisionOut])
def revisions(
    specification_id: int | None = Query(default=None, ge=1),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ExamRevisionOut]:
    return list_revisions(db, specification_id)


@router.get("/api/v1/exam-revisions/{revision_id}", response_model=ExamRevisionOut)
def revision(revision_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ExamRevisionOut:
    return get_revision(db, revision_id)


@router.get("/api/v1/exam-revisions/{revision_id}/levels", response_model=list[ExamLevelOut])
def levels(revision_id: int, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ExamLevelOut]:
    return list_levels(db, revision_id)
