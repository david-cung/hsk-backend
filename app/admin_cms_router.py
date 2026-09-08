from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.orm import Session

from app.admin_cms_service import (
    audit_logs,
    change_status,
    dashboard,
    export_entity,
    global_search,
    import_preview,
    validate_entity,
)
from app.auth import require_admin
from app.database import get_db
from app.models import User
from app.skill_schemas import (
    AdminAuditListOut,
    AdminDashboardOut,
    AdminImportPreviewIn,
    AdminImportPreviewOut,
    AdminSearchOut,
    AdminStatusChangeIn,
    AdminValidationOut,
)

router = APIRouter(prefix="/api/v1/admin/cms", tags=["admin-cms"])


@router.get("/dashboard", response_model=AdminDashboardOut)
def admin_dashboard(
    _: User = Depends(require_admin), db: Session = Depends(get_db)
) -> AdminDashboardOut:
    return AdminDashboardOut.model_validate(dashboard(db))


@router.get("/search", response_model=AdminSearchOut)
def admin_search(
    query: str | None = Query(default=None, min_length=1, max_length=160),
    content_type: str | None = Query(default=None, max_length=60),
    status: str | None = Query(default=None, pattern="^(draft|published|archived|READY|ARCHIVED)$"),
    hsk_level: int | None = Query(default=None, ge=1, le=6),
    exam_revision_id: int | None = Query(default=None, ge=1),
    exam_level_id: int | None = Query(default=None, ge=1),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    sort: str = Query(default="updated", pattern="^(created|updated|title|order|hsk_level)$"),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminSearchOut:
    return AdminSearchOut.model_validate(
        global_search(
            db,
            query=query,
            content_type=content_type,
            status_filter=status.lower() if status else None,
            hsk_level=hsk_level,
            exam_revision_id=exam_revision_id,
            exam_level_id=exam_level_id,
            page=page,
            page_size=page_size,
            sort=sort,
        )
    )


@router.get("/validate/{entity_type}/{entity_id}", response_model=AdminValidationOut)
def admin_validate(
    entity_type: str,
    entity_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminValidationOut:
    return AdminValidationOut.model_validate(validate_entity(db, entity_type, entity_id))


@router.post("/publish/{entity_type}/{entity_id}", response_model=AdminValidationOut)
def admin_publish(
    entity_type: str,
    entity_id: int,
    payload: AdminStatusChangeIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminValidationOut:
    return AdminValidationOut.model_validate(
        change_status(
            db,
            admin,
            entity_type=entity_type,
            entity_id=entity_id,
            next_status="published",
            expected_updated_at=payload.expected_updated_at,
        )
    )


@router.post("/archive/{entity_type}/{entity_id}", response_model=AdminValidationOut)
def admin_archive(
    entity_type: str,
    entity_id: int,
    payload: AdminStatusChangeIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminValidationOut:
    return AdminValidationOut.model_validate(
        change_status(
            db,
            admin,
            entity_type=entity_type,
            entity_id=entity_id,
            next_status="archived",
            expected_updated_at=payload.expected_updated_at,
        )
    )


@router.post("/imports/preview", response_model=AdminImportPreviewOut)
def admin_import_preview(
    payload: AdminImportPreviewIn,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminImportPreviewOut:
    return AdminImportPreviewOut.model_validate(
        import_preview(db, payload.entity_type, payload.source_format, payload.data)
    )


@router.get("/export/{entity_type}")
def admin_export(
    entity_type: str,
    format: str = Query(default="json", pattern="^(json|csv)$"),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    media_type, filename, body = export_entity(db, admin, entity_type, format)
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/audit", response_model=AdminAuditListOut)
def admin_audit(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    action: str | None = Query(default=None, max_length=40),
    entity_type: str | None = Query(default=None, max_length=60),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminAuditListOut:
    return AdminAuditListOut.model_validate(
        audit_logs(db, limit=limit, offset=offset, action=action, entity_type=entity_type)
    )
