from __future__ import annotations

import hashlib
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import require_admin
from app.database import get_db
from app.exam_import_service import (
    ALLOWED_ANSWER_EXTENSIONS,
    ALLOWED_AUDIO_EXTENSIONS,
    ALLOWED_EXAM_EXTENSIONS,
    create_job,
    existing_job,
    job_out,
    new_storage_name,
    retry_job,
    run_import,
    source_hash,
    validate_audio_bytes,
    validate_upload_metadata,
    write_upload,
)
from app.models import ExamImportJob, User
from app.skill_schemas import ExamImportJobOut

router = APIRouter(prefix="/api/v1/admin/exam-imports", tags=["admin-exam-imports"])


@router.post("", response_model=ExamImportJobOut, status_code=status.HTTP_202_ACCEPTED)
async def create_import(
    background_tasks: BackgroundTasks,
    exam_name: str = Form(..., min_length=1, max_length=180),
    exam_revision_id: int = Form(..., ge=1),
    exam_level_id: int = Form(..., ge=1),
    exam_pdf: UploadFile = File(...),
    answer_file: UploadFile | None = File(default=None),
    listening_audio: UploadFile | None = File(default=None),
    force_new: bool = Form(default=False),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExamImportJobOut:
    exam_suffix = validate_upload_metadata(exam_pdf.filename, exam_pdf.content_type, ALLOWED_EXAM_EXTENSIONS)
    exam_bytes = await exam_pdf.read(settings_max_bytes(db) + 1)
    if len(exam_bytes) > settings_max_bytes(db):
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    digest = source_hash(exam_bytes)
    duplicate = existing_job(db, digest, exam_revision_id, exam_level_id, exam_name.strip()[:180])
    if duplicate and not force_new:
        return ExamImportJobOut.model_validate(job_out(duplicate))
    if duplicate and force_new:
        digest = hashlib.sha256(exam_bytes + uuid4().bytes).hexdigest()

    answer_path: str | None = None
    audio_path: str | None = None
    exam_path = new_storage_name(exam_suffix)
    write_upload(exam_path, exam_bytes, settings_max_bytes(db))
    if answer_file is not None:
        suffix = validate_upload_metadata(answer_file.filename, answer_file.content_type, ALLOWED_ANSWER_EXTENSIONS)
        answer_bytes = await answer_file.read(settings_max_bytes(db) + 1)
        answer_path = new_storage_name(suffix)
        write_upload(answer_path, answer_bytes, settings_max_bytes(db))
    if listening_audio is not None:
        suffix = validate_upload_metadata(listening_audio.filename, listening_audio.content_type, ALLOWED_AUDIO_EXTENSIONS)
        audio_bytes = await listening_audio.read(settings_max_bytes(db) + 1)
        validate_audio_bytes(audio_bytes, suffix)
        audio_path = new_storage_name(suffix)
        write_upload(audio_path, audio_bytes, settings_max_bytes(db))
    job = create_job(
        db,
        admin,
        exam_name=exam_name,
        revision_id=exam_revision_id,
        level_id=exam_level_id,
        source_exam_file=exam_path,
        source_answer_file=answer_path,
        source_audio_file=audio_path,
        digest=digest,
    )
    background_tasks.add_task(run_import, job.id)
    return ExamImportJobOut.model_validate(job_out(job))


@router.get("", response_model=list[ExamImportJobOut])
def list_imports(
    status_filter: str | None = Query(default=None, alias="status", max_length=40),
    limit: int = Query(default=50, ge=1, le=100),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[ExamImportJobOut]:
    stmt = select(ExamImportJob)
    if status_filter:
        stmt = stmt.where(ExamImportJob.status == status_filter.upper())
    rows = db.scalars(stmt.order_by(ExamImportJob.updated_at.desc(), ExamImportJob.id.desc()).limit(limit)).all()
    return [ExamImportJobOut.model_validate(job_out(row)) for row in rows]


@router.get("/{job_id}", response_model=ExamImportJobOut)
def get_import(job_id: int, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> ExamImportJobOut:
    job = db.get(ExamImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Exam import job not found")
    return ExamImportJobOut.model_validate(job_out(job))


@router.post("/{job_id}/retry", response_model=ExamImportJobOut, status_code=status.HTTP_202_ACCEPTED)
def retry_import(job_id: int, background_tasks: BackgroundTasks, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> ExamImportJobOut:
    job = db.get(ExamImportJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Exam import job not found")
    retry_job(db, job)
    background_tasks.add_task(run_import, job.id)
    return ExamImportJobOut.model_validate(job_out(job))


def settings_max_bytes(_db: Session) -> int:
    from app.config import settings

    return settings.exam_import_max_bytes
