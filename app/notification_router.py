from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.models import User
from app.notification_service import (
    ensure_preferences,
    register_device,
    unregister_device,
    update_preferences,
)
from app.skill_schemas import (
    DeviceTokenIn,
    DeviceTokenOut,
    NotificationPreferencesOut,
    NotificationPreferencesUpdateIn,
)

router = APIRouter(prefix="/api/v1/notifications", tags=["notifications"])


@router.get("/preferences", response_model=NotificationPreferencesOut)
def preferences(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> NotificationPreferencesOut:
    row = ensure_preferences(db, user)
    db.commit()
    return NotificationPreferencesOut.model_validate(row)


@router.patch("/preferences", response_model=NotificationPreferencesOut)
def save_preferences(
    payload: NotificationPreferencesUpdateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> NotificationPreferencesOut:
    row = update_preferences(db, user, payload.model_dump())
    return NotificationPreferencesOut.model_validate(row)


@router.post("/devices", response_model=DeviceTokenOut, status_code=status.HTTP_201_CREATED)
def create_device(
    payload: DeviceTokenIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DeviceTokenOut:
    try:
        device = register_device(db, user, token=payload.token, platform=payload.platform)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return DeviceTokenOut.model_validate(device)


@router.delete("/devices/{token}", status_code=status.HTTP_204_NO_CONTENT)
def delete_device(
    token: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    try:
        unregister_device(db, user, token)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
