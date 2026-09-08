from __future__ import annotations

import hashlib
import logging
import mimetypes
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.exam_import_parser import (
    ParsedExam,
    answer_text_from_file,
    extract_pdf_text,
    match_answers,
    parse_answer_key_text,
    parse_exam_pages,
)
from app.media_storage import get_media_storage
from app.models import (
    AudioAsset,
    ContentMembership,
    ContentStatus,
    Course,
    ExamImportJob,
    ExamLevel,
    ExamPart,
    ExamQuestion,
    ExamRevision,
    ExamSection,
    ExamVersion,
    Exercise,
    ExerciseSet,
    ExerciseType,
    HskLevel,
    Lesson,
    MockTest,
    Question,
    QuestionVersion,
    ScoringPolicy,
    User,
)
from app.practice_engine import validate_question_configuration
from app.question_service import create_version

logger = logging.getLogger("hsk.exam_import")

ALLOWED_EXAM_EXTENSIONS = {".pdf"}
ALLOWED_ANSWER_EXTENSIONS = {".pdf", ".txt", ".csv"}
ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".m4a"}
ALLOWED_AUDIO_MIMES = {"audio/mpeg", "audio/mp3", "audio/mp4", "audio/x-m4a"}


def storage_path(relative_path: str) -> Path:
    root = Path(settings.exam_import_storage_dir).resolve()
    candidate = (root / relative_path).resolve()
    if root != candidate and root not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid import file path")
    return candidate


def validate_upload_metadata(filename: str | None, content_type: str | None, allowed_extensions: set[str]) -> str:
    safe_name = Path(filename or "").name
    suffix = Path(safe_name).suffix.lower()
    if not safe_name or suffix not in allowed_extensions:
        raise HTTPException(status_code=415, detail="Unsupported exam import file type")
    allowed_mimes = {"application/octet-stream"}
    if suffix in ALLOWED_AUDIO_EXTENSIONS:
        allowed_mimes.update(ALLOWED_AUDIO_MIMES)
    elif suffix == ".pdf":
        allowed_mimes.add("application/pdf")
    else:
        allowed_mimes.update({"text/plain", "text/csv"})
    if content_type and content_type not in allowed_mimes:
        raise HTTPException(status_code=415, detail="Unsupported upload MIME type")
    return suffix


def write_upload(relative_path: str, content: bytes, max_bytes: int | None = None) -> None:
    if len(content) > (max_bytes or settings.exam_import_max_bytes):
        raise HTTPException(status_code=413, detail="Uploaded file is too large")
    target = storage_path(relative_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def validate_audio_bytes(content: bytes, suffix: str) -> None:
    if suffix == ".mp3":
        valid = content.startswith(b"ID3") or (len(content) >= 2 and content[0] == 0xFF and content[1] & 0xE0 == 0xE0)
    else:
        valid = len(content) >= 8 and content[4:8] == b"ftyp"
    if not valid:
        raise HTTPException(status_code=422, detail="Uploaded audio does not match a supported audio format")


def new_storage_name(suffix: str) -> str:
    return f"jobs/{uuid4().hex}{suffix}"


def source_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def existing_job(db: Session, digest: str, revision_id: int, level_id: int, exam_name: str) -> ExamImportJob | None:
    return db.scalar(
        select(ExamImportJob).where(
            ExamImportJob.source_hash == digest,
            ExamImportJob.exam_revision_id == revision_id,
            ExamImportJob.exam_level_id == level_id,
            ExamImportJob.exam_name == exam_name,
        ).order_by(ExamImportJob.id.desc())
    )


def create_job(
    db: Session,
    admin: User,
    *,
    exam_name: str,
    revision_id: int,
    level_id: int,
    source_exam_file: str,
    source_answer_file: str | None,
    source_audio_file: str | None,
    digest: str,
) -> ExamImportJob:
    revision = db.get(ExamRevision, revision_id)
    level = db.get(ExamLevel, level_id)
    if revision is None or level is None or level.revision_id != revision.id:
        raise HTTPException(status_code=422, detail="Exam level does not belong to the selected revision")
    job = ExamImportJob(
        status="UPLOADING",
        exam_revision_id=revision_id,
        exam_level_id=level_id,
        exam_name=exam_name.strip()[:180],
        source_hash=digest,
        source_exam_file=source_exam_file,
        source_answer_file=source_answer_file,
        source_audio_file=source_audio_file,
        created_by=admin.id,
        progress=5,
        warnings=[],
        errors=[],
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def job_out(job: ExamImportJob) -> dict[str, Any]:
    parsed = job.parsed_document or {}
    sections = parsed.get("sections") if isinstance(parsed, dict) else []
    questions = [
        question
        for section in sections or []
        for part in section.get("parts", [])
        for question in part.get("questions", [])
    ]
    return {
        "id": job.id,
        "status": job.status,
        "exam_revision_id": job.exam_revision_id,
        "exam_level_id": job.exam_level_id,
        "exam_name": job.exam_name,
        "created_exam_id": job.created_exam_id,
        "created_exam_version_id": job.created_exam_version_id,
        "progress": job.progress,
        "warnings": job.warnings or [],
        "errors": job.errors or [],
        "created_at": job.created_at,
        "updated_at": job.updated_at,
        "summary": {
            "sections": len(sections or []),
            "questions": len(questions),
            "answers_matched": sum(1 for question in questions if question.get("answer")),
            "warnings": len(job.warnings or []),
            "review_required": job.status == "REVIEW_REQUIRED",
        },
        "parsed_document": job.parsed_document,
    }


def run_import(job_id: int) -> None:
    from app.database import SessionLocal

    with SessionLocal() as db:
        job = db.get(ExamImportJob, job_id)
        if job is None:
            return
        try:
            _run_import(db, job)
        except Exception as exc:  # pragma: no cover - final safety net for background execution
            logger.exception("exam_import_failed", extra={"job_id": job_id})
            db.rollback()
            job = db.get(ExamImportJob, job_id)
            if job:
                job.status = "FAILED"
                job.progress = 100
                job.errors = [{"code": "IMPORT_FAILED", "message": str(exc)[:500]}]
                db.commit()


def _run_import(db: Session, job: ExamImportJob) -> None:
    job.status = "EXTRACTING"
    job.progress = 15
    db.commit()
    try:
        extracted = extract_pdf_text(storage_path(job.source_exam_file))
    except ValueError as exc:
        code = str(exc)
        job.status = "REVIEW_REQUIRED" if code == "OCR_REQUIRED" else "FAILED"
        job.progress = 100
        job.errors = [{"code": code}]
        db.commit()
        return

    job.status = "PARSING"
    job.progress = 35
    db.commit()
    try:
        parsed = parse_exam_pages(extracted)
    except ValueError as exc:
        job.status = "FAILED"
        job.progress = 100
        job.errors = [{"code": str(exc)}]
        db.commit()
        return

    warnings = list(parsed.warnings)
    if job.source_answer_file:
        try:
            answer_text = answer_text_from_file(storage_path(job.source_answer_file))
            answers, answer_warnings = parse_answer_key_text(answer_text)
            parsed = match_answers(parsed, answers)
            warnings.extend(answer_warnings)
        except ValueError as exc:
            warnings.append({"code": str(exc) or "ANSWER_KEY_PARSE_FAILED"})
    else:
        warnings.append({"code": "ANSWER_KEY_NOT_PROVIDED"})

    if job.created_exam_version_id:
        warnings.append({"code": "RETRY_REUSED_DRAFT", "exam_version_id": job.created_exam_version_id})
        job.status = "REVIEW_REQUIRED"
        job.progress = 100
        job.warnings = warnings
        job.errors = []
        db.commit()
        return

    job.status = "VALIDATING"
    job.progress = 55
    db.commit()
    audio_asset = _create_audio_asset(db, job)
    warnings.extend(_validate_question_configurations(parsed, audio_asset.id if audio_asset else None))
    created_questions, exam_version = _create_draft_content(db, job, parsed, audio_asset)
    parsed_payload = parsed.model_dump()
    parsed_payload["created_question_ids"] = [item[0].id for item in created_questions]
    parsed_payload["created_question_version_ids"] = [item[1].id for item in created_questions]
    parsed_payload["audio_asset_id"] = audio_asset.id if audio_asset else None
    job.parsed_document = parsed_payload
    job.created_exam_id = exam_version.exam_id
    job.created_exam_version_id = exam_version.id
    job.warnings = warnings + _question_warnings(parsed)
    job.errors = []
    job.progress = 100
    job.status = "REVIEW_REQUIRED" if job.warnings else "COMPLETED"
    db.commit()


def retry_job(db: Session, job: ExamImportJob) -> ExamImportJob:
    if job.status in {"UPLOADING", "EXTRACTING", "PARSING", "VALIDATING"}:
        raise HTTPException(status_code=409, detail="Import is already running")
    job.status = "UPLOADING"
    job.progress = 5
    job.warnings = []
    job.errors = []
    db.commit()
    return job


def _validate_question_configurations(parsed: ParsedExam, audio_asset_id: int | None) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    for section in parsed.sections:
        for part in section.parts:
            for question in part.questions:
                question_type, configuration = _question_payload(question, audio_asset_id if section.code == "LISTENING" else None)
                try:
                    validate_question_configuration(question_type, configuration)
                except ValueError as exc:
                    question.warnings.append("QUESTION_CONFIGURATION_INVALID")
                    warnings.append({"code": "QUESTION_CONFIGURATION_INVALID", "question": question.number, "page": question.source_page, "message": str(exc)[:240]})
    return warnings

def _create_audio_asset(db: Session, job: ExamImportJob) -> AudioAsset | None:
    if not job.source_audio_file:
        return None
    relative = f"audio/{Path(job.source_audio_file).name}"
    provider = settings.media_storage_provider.lower()
    existing = db.scalar(select(AudioAsset).where(AudioAsset.storage_provider == provider, AudioAsset.storage_key == relative))
    if existing:
        job.source_audio_asset_id = existing.id
        return existing
    asset = AudioAsset(
        storage_provider=provider,
        storage_key=relative,
        provider=provider,
        mime_type=mimetypes.guess_type(relative)[0] or "audio/mpeg",
        format=Path(relative).suffix.lstrip("."),
        language="zh-CN",
        status="READY",
        metadata_json={"exam_import_job_id": job.id, "segmentation": "not_implemented"},
    )
    db.add(asset)
    db.flush()
    source = storage_path(job.source_audio_file)
    if provider == "s3":
        get_media_storage().put_bytes(relative, source.read_bytes(), asset.mime_type)
    else:
        target = storage_path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    job.source_audio_asset_id = asset.id
    return asset


def _create_draft_content(db: Session, job: ExamImportJob, parsed: ParsedExam, audio_asset: AudioAsset | None) -> tuple[list[tuple[Question, QuestionVersion]], ExamVersion]:
    level = db.get(ExamLevel, job.exam_level_id)
    if level is None:
        raise ValueError("LEVEL_NOT_FOUND")
    hsk_level = _get_hsk_level(db, level.level_number or 1)
    course = Course(hsk_level_id=hsk_level.id, title=f"Imported exams - {job.exam_name[:120]}", course_type="practice", sort_order=0, status=ContentStatus.DRAFT)
    db.add(course)
    db.flush()
    lesson = Lesson(hsk_level_id=hsk_level.id, course_id=course.id, title=job.exam_name[:180], lesson_type="practice", sort_order=0, duration_minutes=10, content_status=ContentStatus.DRAFT, metadata_json={"exam_import_job_id": job.id})
    db.add(lesson)
    db.flush()
    exercise_set = ExerciseSet(lesson_id=lesson.id, slug=f"exam-import-{job.id}", title=job.exam_name[:180], skill="exam", sort_order=0, status=ContentStatus.DRAFT, metadata_json={"exam_import_job_id": job.id})
    db.add(exercise_set)
    db.flush()
    created: list[tuple[Question, QuestionVersion]] = []
    scoring = db.scalar(select(ScoringPolicy).where(ScoringPolicy.revision_id == job.exam_revision_id, ScoringPolicy.status == ContentStatus.PUBLISHED).order_by(ScoringPolicy.id))
    if scoring is None:
        scoring = ScoringPolicy(revision_id=job.exam_revision_id, code="GENERIC_IMPORT", name="Generic imported exam scoring", version="1", policy_type="percentage", configuration={"passing_percentage": 60, "score_label": "Estimated Practice Score"}, status=ContentStatus.PUBLISHED)
        db.add(scoring)
        db.flush()
    total_seconds = max(60, sum(max(60, len(part.questions) * 60) for section in parsed.sections for part in section.parts))
    exam = MockTest(title=job.exam_name, hsk_level=level.level_number, exam_revision_id=job.exam_revision_id, exam_level_id=job.exam_level_id, scoring_policy_id=scoring.id, duration_minutes=max(1, round(total_seconds / 60)), question_count=sum(len(part.questions) for section in parsed.sections for part in section.parts), status="DRAFT", version=1, blueprint={"schema_version": 1, "revision_id": job.exam_revision_id, "import_job_id": job.id, "sections": [{"type": section.code, "title": section.title, "question_count": sum(len(part.questions) for part in section.parts), "duration_minutes": max(1, round(sum(len(part.questions) * 60 for part in section.parts) / 60))} for section in parsed.sections]}, blueprint_schema_version=1, scoring_config=scoring.configuration or {})
    db.add(exam)
    db.flush()
    exam_version = ExamVersion(exam_id=exam.id, version_number=1, status=ContentStatus.DRAFT, exam_revision_id=job.exam_revision_id, exam_level_id=job.exam_level_id, scoring_policy_id=scoring.id, title=job.exam_name, duration_seconds=total_seconds, blueprint_schema_version=1, configuration={"import_job_id": job.id, "audio_asset_id": audio_asset.id if audio_asset else None, "audio_segmentation": "not_implemented"})
    db.add(exam_version)
    db.flush()
    for section_index, parsed_section in enumerate(parsed.sections):
        section_audio = audio_asset.id if parsed_section.code == "LISTENING" and audio_asset else None
        section = ExamSection(exam_version_id=exam_version.id, code=parsed_section.code, title=parsed_section.title, skill=parsed_section.code.lower(), sort_order=section_index, duration_seconds=max(60, sum(len(part.questions) for part in parsed_section.parts) * 60), configuration={"audio_asset_id": section_audio, "audio_required": parsed_section.code == "LISTENING"})
        db.add(section)
        db.flush()
        part_rows: list[tuple[ExamPart, list[tuple[Question, QuestionVersion]]]] = []
        for part_index, parsed_part in enumerate(parsed_section.parts):
            part = ExamPart(exam_section_id=section.id, code=parsed_part.code, title=parsed_part.title, sort_order=part_index)
            db.add(part)
            db.flush()
            part_rows.append((part, []))
            for question_index, parsed_question in enumerate(parsed_part.questions):
                qtype, config = _question_payload(parsed_question, section_audio)
                exercise_type = ExerciseType.MULTIPLE_CHOICE if qtype == "multiple_choice" else ExerciseType.TEXT_INPUT
                exercise = Exercise(exercise_set_id=exercise_set.id, external_id=f"import-{job.id}-{parsed_question.number}", exercise_type=exercise_type, title=f"Question {parsed_question.number}", skill=parsed_section.code.lower(), sort_order=len(created), status=ContentStatus.DRAFT, metadata_json={"exam_import_job_id": job.id})
                db.add(exercise)
                db.flush()
                question = Question(lesson_id=lesson.id, exercise_id=exercise.id, external_id=f"import-{job.id}-q{parsed_question.number}", question_type=qtype, prompt=parsed_question.prompt, options=[option.text for option in parsed_question.options] or None, correct_answer=parsed_question.answer or "", points=1, configuration=config, sort_order=len(created), status=ContentStatus.DRAFT, metadata_json={"exam_import_job_id": job.id, "source_page": parsed_question.source_page, "source_question_number": parsed_question.source_question_number, "confidence": parsed_question.confidence, "warnings": parsed_question.warnings})
                db.add(question)
                db.flush()
                db.add(ContentMembership(content_type="question", content_id=question.id, exam_level_id=job.exam_level_id, introduced_in_revision_id=job.exam_revision_id, metadata_json={"exam_import_job_id": job.id}))
                version = create_version(db, question, status=ContentStatus.DRAFT, values={"question_type": qtype, "configuration": config, "skill": parsed_section.code.lower(), "metadata_json": question.metadata_json})
                created.append((question, version))
                part_rows[-1][1].append((question, version))
                db.add(ExamQuestion(exam_part_id=part.id, question_version_id=version.id, sort_order=question_index, points=1, configuration={"source_page": parsed_question.source_page, "source_question_number": parsed_question.source_question_number}))

    db.flush()
    return created, exam_version


def _question_payload(parsed_question: Any, audio_asset_id: int | None) -> tuple[str, dict[str, Any]]:
    options = [{"id": option.id, "text": option.text} for option in parsed_question.options]
    answer = parsed_question.answer
    if parsed_question.options:
        config: dict[str, Any] = {"options": options, "correct_option_ids": [answer] if answer else []}
        if audio_asset_id:
            return "listening", {"audio_asset_id": audio_asset_id, "answer_type": "multiple_choice", **config}
        return "multiple_choice", config
    return "text_input", {"accepted_answers": [answer] if answer else []}


def _get_hsk_level(db: Session, level_number: int) -> HskLevel:
    level = db.scalar(select(HskLevel).where(HskLevel.level_number == level_number))
    if level:
        return level
    level = HskLevel(level_number=level_number, title=f"HSK {level_number}", display_order=level_number, total_characters=0, status=ContentStatus.DRAFT)
    db.add(level)
    db.flush()
    return level


def _question_warnings(parsed: ParsedExam) -> list[dict[str, Any]]:
    return [{"code": warning, "question": question.number, "page": question.source_page} for section in parsed.sections for part in section.parts for question in part.questions for warning in question.warnings]
