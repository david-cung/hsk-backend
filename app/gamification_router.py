from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.gamification_service import (
    daily_snapshot,
    gamification_profile,
    list_achievements,
    update_daily_goal,
    xp_history,
)
from app.models import User
from app.skill_schemas import (
    DailyGoalOut,
    DailyGoalUpdateIn,
    GamificationAchievementOut,
    GamificationProfileOut,
    XPHistoryOut,
)

router = APIRouter(prefix="/api/v1/gamification", tags=["gamification"])


@router.get("/profile", response_model=GamificationProfileOut)
def profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> GamificationProfileOut:
    return GamificationProfileOut.model_validate(gamification_profile(db, user))


@router.get("/achievements", response_model=list[GamificationAchievementOut])
def achievements(
    user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[GamificationAchievementOut]:
    return [GamificationAchievementOut.model_validate(item) for item in list_achievements(db, user)]


@router.get("/history", response_model=XPHistoryOut)
def history(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> XPHistoryOut:
    return XPHistoryOut.model_validate(xp_history(db, user, limit=limit, offset=offset))


@router.get("/daily", response_model=DailyGoalOut)
def daily(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DailyGoalOut:
    return DailyGoalOut.model_validate(daily_snapshot(db, user))


@router.patch("/daily", response_model=DailyGoalOut)
def update_daily(
    payload: DailyGoalUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DailyGoalOut:
    try:
        return DailyGoalOut.model_validate(
            update_daily_goal(db, user, goal_type=payload.goal_type, target=payload.target)
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
