from __future__ import annotations

# ruff: noqa: B008
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.review_scheduler import ReviewRating
from app.review_service import (
    card_statuses,
    card_to_out,
    due_cards,
    enroll_card,
    history,
    review_card,
    review_summary,
)
from app.skill_schemas import (
    ReviewCardOut,
    ReviewCardStatusOut,
    ReviewDueOut,
    ReviewEnrollIn,
    ReviewHistoryOut,
    ReviewSubmitIn,
    ReviewSubmitOut,
    ReviewSummaryOut,
)

router = APIRouter(prefix="/api/v1/review", tags=["review"])


@router.get("/due", response_model=ReviewDueOut)
def due(
    limit: int | None = Query(default=None, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewDueOut:
    return due_cards(db, user, limit=limit)


@router.post("/cards/{card_id}/review", response_model=ReviewSubmitOut)
def submit_review(
    card_id: int,
    payload: ReviewSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewSubmitOut:
    try:
        card, _history, _duplicate = review_card(
            db,
            user,
            card_id,
            ReviewRating(payload.rating),
            payload.idempotency_key,
            source="MANUAL_REVIEW",
        )
    except ValueError as exc:
        raise HTTPException(status_code=404 if "not found" in str(exc).lower() else 422, detail=str(exc)) from exc
    db.commit()
    db.refresh(card)
    summary = review_summary(db, user)
    return ReviewSubmitOut(
        card=card_to_out(card),
        reviewed_today=summary.reviewed_today,
        next_review_at=summary.next_review_at,
    )


@router.get("/summary", response_model=ReviewSummaryOut)
def summary(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ReviewSummaryOut:
    return review_summary(db, user)


@router.get("/history", response_model=list[ReviewHistoryOut])
def review_history(
    limit: int = Query(default=50, ge=1, le=200),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewHistoryOut]:
    return history(db, user, limit)


@router.post("/cards", response_model=ReviewCardOut, status_code=status.HTTP_201_CREATED)
def create_card(
    payload: ReviewEnrollIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ReviewCardOut:
    try:
        card = enroll_card(
            db,
            user,
            payload.card_type,
            vocabulary_id=payload.vocabulary_id,
            grammar_id=payload.grammar_id,
            content_key=payload.content_key,
            content=payload.content,
            source="MANUAL",
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.commit()
    db.refresh(card)
    return card_to_out(card)


@router.get("/cards", response_model=list[ReviewCardStatusOut])
def cards(
    card_type: str | None = Query(default=None, pattern="^(VOCABULARY|GRAMMAR)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[ReviewCardStatusOut]:
    return card_statuses(db, user, card_type)
