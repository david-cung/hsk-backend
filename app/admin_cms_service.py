from __future__ import annotations

import csv
import io
import math
from datetime import datetime
from typing import Any, Literal

from fastapi import HTTPException
from sqlalchemy import Select, Text, func, or_, select
from sqlalchemy.orm import Session

from app.content_import import _natural_key, _validate_records, parse_import_records
from app.exam_service import validate_exam_content
from app.models import (
    AdminAuditLog,
    AudioAsset,
    ContentStatus,
    Course,
    ExamLevel,
    ExampleSentence,
    ExamRevision,
    Exercise,
    ExerciseSet,
    GrammarPoint,
    HskLevel,
    ImportEntityType,
    ImportJob,
    ImportJobStatus,
    Lesson,
    MockTest,
    Question,
    User,
    Vocabulary,
)
from app.practice_engine import validate_question_configuration

ENTITY_MODELS: dict[str, type[Any]] = {
    "hsk_levels": HskLevel,
    "courses": Course,
    "lessons": Lesson,
    "vocabulary": Vocabulary,
    "grammar": GrammarPoint,
    "example_sentences": ExampleSentence,
    "audio": AudioAsset,
    "exercise_sets": ExerciseSet,
    "exercises": Exercise,
    "questions": Question,
    "writing": Question,
    "exams": MockTest,
}

CONTENT_ENTITY_TYPES = {
    "hsk_levels",
    "courses",
    "lessons",
    "vocabulary",
    "grammar",
    "example_sentences",
    "exercise_sets",
    "exercises",
    "questions",
    "writing",
}

SAFE_SORTS = {
    "created": "created_at",
    "updated": "updated_at",
    "title": "title",
    "order": "sort_order",
    "hsk_level": "hsk_level_id",
}


def log_admin_action(
    db: Session,
    admin: User,
    action: str,
    entity_type: str,
    entity_id: str | int | None,
    metadata: dict[str, Any] | None = None,
) -> AdminAuditLog:
    sanitized = _sanitize_metadata(metadata or {})
    row = AdminAuditLog(
        admin_user_id=admin.id,
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        metadata_json=sanitized,
    )
    db.add(row)
    return row


def dashboard(db: Session) -> dict[str, Any]:
    metrics = [
        _metric("hsk_levels", "HSK levels", db.scalar(select(func.count(HskLevel.id))) or 0),
        _metric("courses", "Courses", db.scalar(select(func.count(Course.id))) or 0),
        _metric("lessons", "Lessons", db.scalar(select(func.count(Lesson.id))) or 0),
        _metric("vocabulary", "Vocabulary", db.scalar(select(func.count(Vocabulary.id))) or 0),
        _metric("grammar", "Grammar", db.scalar(select(func.count(GrammarPoint.id))) or 0),
        _metric("examples", "Examples", db.scalar(select(func.count(ExampleSentence.id))) or 0),
        _metric("exercises", "Exercises", db.scalar(select(func.count(Exercise.id))) or 0),
        _metric("audio", "Audio assets", db.scalar(select(func.count(AudioAsset.id))) or 0),
        _metric("exams", "Mock exams", db.scalar(select(func.count(MockTest.id))) or 0),
    ]
    status_counts = {"draft": 0, "published": 0, "archived": 0}
    for model, column in (
        (HskLevel, HskLevel.status),
        (Course, Course.status),
        (Lesson, Lesson.content_status),
        (Vocabulary, Vocabulary.status),
        (GrammarPoint, GrammarPoint.status),
        (ExampleSentence, ExampleSentence.status),
        (ExerciseSet, ExerciseSet.status),
        (Exercise, Exercise.status),
        (Question, Question.status),
    ):
        rows = db.execute(select(column, func.count(model.id)).group_by(column)).all()
        for state, count in rows:
            status_counts[_value(state)] = status_counts.get(_value(state), 0) + int(count or 0)
    failed_imports = db.scalar(
        select(func.count(ImportJob.id)).where(ImportJob.status == ImportJobStatus.FAILED)
    ) or 0
    vocab_total = db.scalar(select(func.count(Vocabulary.id))) or 0
    vocab_with_audio = db.scalar(
        select(func.count(Vocabulary.id)).where(Vocabulary.audio_asset_id.is_not(None))
    ) or 0
    coverage = round((int(vocab_with_audio) / int(vocab_total)) * 100, 2) if vocab_total else 0
    return {
        "metrics": metrics,
        "content_status": status_counts,
        "import_errors": int(failed_imports),
        "audio_coverage": {
            "vocabulary_total": int(vocab_total),
            "vocabulary_with_audio": int(vocab_with_audio),
            "vocabulary_missing_audio": int(vocab_total) - int(vocab_with_audio),
            "percent": coverage,
        },
    }


def global_search(
    db: Session,
    *,
    query: str | None,
    content_type: str | None,
    status_filter: str | None,
    hsk_level: int | None,
    exam_revision_id: int | None = None,
    exam_level_id: int | None = None,
    page: int,
    page_size: int,
    sort: str,
) -> dict[str, Any]:
    entity_types = [content_type] if content_type else ["lessons", "vocabulary", "grammar", "courses", "exams"]
    items: list[dict[str, Any]] = []
    for entity_type in entity_types:
        if entity_type not in ENTITY_MODELS:
            raise HTTPException(status_code=422, detail="Unsupported content type")
        items.extend(
            _search_entity(
                db, entity_type, query, status_filter, hsk_level, sort,
                exam_revision_id, exam_level_id,
            )
        )
    offset = (page - 1) * page_size
    page_items = items[offset : offset + page_size]
    return {
        "items": page_items,
        "total": len(items),
        "page": page,
        "page_size": page_size,
        "pages": math.ceil(len(items) / page_size) if items else 0,
    }


def validate_entity(db: Session, entity_type: str, entity_id: int) -> dict[str, Any]:
    row = _entity_row(db, entity_type, entity_id)
    issues = _validate_row(db, entity_type, row)
    return {
        "entity_type": entity_type,
        "entity_id": str(entity_id),
        "valid": not any(issue["severity"] == "error" for issue in issues),
        "issues": issues,
    }


def change_status(
    db: Session,
    admin: User,
    *,
    entity_type: str,
    entity_id: int,
    next_status: Literal["published", "archived"],
    expected_updated_at: datetime | None,
) -> dict[str, Any]:
    row = _entity_row(db, entity_type, entity_id)
    if expected_updated_at is not None and hasattr(row, "updated_at"):
        current = _normalize_dt(row.updated_at)
        expected = _normalize_dt(expected_updated_at)
        if current and expected and current != expected:
            raise HTTPException(status_code=409, detail="Content changed since it was loaded")
    if next_status == "published":
        validation = validate_entity(db, entity_type, entity_id)
        if not validation["valid"]:
            raise HTTPException(status_code=422, detail=validation["issues"])
    _set_status(row, entity_type, next_status)
    log_admin_action(db, admin, next_status, entity_type, entity_id)
    db.commit()
    return validate_entity(db, entity_type, entity_id)


def export_entity(db: Session, admin: User, entity_type: str, output_format: str) -> tuple[str, str, str]:
    if entity_type not in ENTITY_MODELS:
        raise HTTPException(status_code=422, detail="Unsupported export entity")
    if output_format not in {"json", "csv"}:
        raise HTTPException(status_code=422, detail="Unsupported export format")
    rows = db.scalars(select(ENTITY_MODELS[entity_type]).limit(5000)).all()
    records = [_export_record(entity_type, row) for row in rows]
    log_admin_action(db, admin, "export", entity_type, None, {"records": len(records)})
    db.commit()
    if output_format == "json":
        import json

        return (
            "application/json",
            f"{entity_type}.json",
            json.dumps({"records": records}, ensure_ascii=False, default=str),
        )
    buffer = io.StringIO()
    fieldnames = sorted({key for record in records for key in record}) or ["id"]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    writer.writerows(records)
    return "text/csv", f"{entity_type}.csv", buffer.getvalue()


def import_preview(db: Session, entity_type: str, source_format: str, data: Any) -> dict[str, Any]:
    try:
        import_type = ImportEntityType(entity_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Unsupported import entity") from exc
    if source_format not in {"json", "csv"}:
        raise HTTPException(status_code=422, detail="Unsupported import format")
    try:
        raw = parse_import_records(source_format, data)  # type: ignore[arg-type]
    except Exception as exc:
        return {
            "entity_type": entity_type,
            "source_format": source_format,
            "total_records": 0,
            "records_to_create": 0,
            "records_to_update": 0,
            "duplicates": 0,
            "invalid_records": 1,
            "warnings": [],
            "errors": [{"message": str(exc)}],
        }
    validated, errors = _validate_records(import_type, raw)
    seen: set[tuple[Any, ...]] = set()
    duplicates = 0
    creates = 0
    updates = 0
    for record in validated:
        key = _natural_key(import_type, record)
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        if _existing_import_record(db, import_type, key):
            updates += 1
        else:
            creates += 1
    return {
        "entity_type": entity_type,
        "source_format": source_format,
        "total_records": len(raw),
        "records_to_create": creates,
        "records_to_update": updates,
        "duplicates": duplicates,
        "invalid_records": len(errors),
        "warnings": [],
        "errors": errors,
    }


def audit_logs(
    db: Session, *, limit: int, offset: int, action: str | None, entity_type: str | None
) -> dict[str, Any]:
    stmt = select(AdminAuditLog)
    count_stmt = select(func.count(AdminAuditLog.id))
    if action:
        stmt = stmt.where(AdminAuditLog.action == action)
        count_stmt = count_stmt.where(AdminAuditLog.action == action)
    if entity_type:
        stmt = stmt.where(AdminAuditLog.entity_type == entity_type)
        count_stmt = count_stmt.where(AdminAuditLog.entity_type == entity_type)
    total = db.scalar(count_stmt) or 0
    rows = db.scalars(
        stmt.order_by(AdminAuditLog.created_at.desc(), AdminAuditLog.id.desc()).offset(offset).limit(limit)
    ).all()
    return {
        "items": [
            {
                "id": row.id,
                "admin_user_id": row.admin_user_id,
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": row.entity_id,
                "metadata": row.metadata_json,
                "created_at": row.created_at,
            }
            for row in rows
        ],
        "total": int(total),
        "limit": limit,
        "offset": offset,
    }


def _metric(key: str, label: str, value: int) -> dict[str, int | str]:
    return {"key": key, "label": label, "value": int(value)}


def _value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value).lower()


def _entity_row(db: Session, entity_type: str, entity_id: int) -> Any:
    model = ENTITY_MODELS.get(entity_type)
    if model is None:
        raise HTTPException(status_code=422, detail="Unsupported entity type")
    row = db.get(model, entity_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Content not found")
    return row


def _status_column(entity_type: str, model: type[Any]) -> Any:
    if entity_type == "lessons":
        return Lesson.content_status
    return getattr(model, "status", None)


def _search_entity(
    db: Session,
    entity_type: str,
    query: str | None,
    status_filter: str | None,
    hsk_level: int | None,
    sort: str,
    exam_revision_id: int | None = None,
    exam_level_id: int | None = None,
) -> list[dict[str, Any]]:
    model = ENTITY_MODELS[entity_type]
    stmt: Select[Any] = select(model)
    status_column = _status_column(entity_type, model)
    if status_filter and status_column is not None:
        if entity_type in {"audio", "exams"}:
            status_value: Any = status_filter.upper()
        else:
            try:
                status_value = ContentStatus(status_filter)
            except ValueError:
                return []
        stmt = stmt.where(status_column == status_value)
    if hsk_level is not None:
        if entity_type in {"lessons", "vocabulary", "grammar", "courses"}:
            stmt = stmt.join(HskLevel, model.hsk_level_id == HskLevel.id).where(
                HskLevel.level_number == hsk_level
            )
        elif entity_type == "exams":
            stmt = stmt.where(MockTest.hsk_level == hsk_level)
    if entity_type in {"lessons", "vocabulary", "grammar", "courses"} and (
        exam_revision_id is not None or exam_level_id is not None
    ):
        if hsk_level is None:
            stmt = stmt.join(HskLevel, model.hsk_level_id == HskLevel.id)
        if exam_level_id is not None:
            stmt = stmt.where(HskLevel.exam_level_id == exam_level_id)
        else:
            stmt = stmt.join(ExamLevel, HskLevel.exam_level_id == ExamLevel.id).join(
                ExamRevision, ExamLevel.revision_id == ExamRevision.id
            ).where(ExamRevision.id == exam_revision_id)
    elif entity_type == "exams":
        if exam_revision_id is not None:
            stmt = stmt.where(MockTest.exam_revision_id == exam_revision_id)
        if exam_level_id is not None:
            stmt = stmt.where(MockTest.exam_level_id == exam_level_id)
    if query:
        value = f"%{query.strip()}%"
        if entity_type == "vocabulary":
            stmt = stmt.where(
                or_(
                    Vocabulary.simplified.ilike(value),
                    Vocabulary.traditional.ilike(value),
                    Vocabulary.pinyin.ilike(value),
                    Vocabulary.meaning_translations.cast(Text).ilike(value),
                )
            )
        elif entity_type == "grammar":
            stmt = stmt.where(
                or_(
                    GrammarPoint.title.ilike(value),
                    GrammarPoint.pattern.ilike(value),
                    GrammarPoint.explanation_translations.cast(Text).ilike(value),
                )
            )
        elif entity_type == "example_sentences":
            stmt = stmt.where(
                or_(
                    ExampleSentence.chinese.ilike(value),
                    ExampleSentence.pinyin.ilike(value),
                    ExampleSentence.translations.cast(Text).ilike(value),
                )
            )
        else:
            title = getattr(model, "title", None)
            if title is not None:
                stmt = stmt.where(title.ilike(value))
    stmt = _apply_sort(stmt, model, entity_type, sort).limit(250)
    rows = db.scalars(stmt).all()
    return [_search_item(entity_type, row) for row in rows]


def _apply_sort(stmt: Select[Any], model: type[Any], entity_type: str, sort: str) -> Select[Any]:
    field = SAFE_SORTS.get(sort, "updated_at")
    if entity_type == "exams" and field == "hsk_level_id":
        return stmt.order_by(MockTest.hsk_level, MockTest.id)
    column = getattr(model, field, None)
    if column is None:
        column = model.id
    if sort in {"created", "updated"}:
        column = column.desc()
    return stmt.order_by(column, model.id)


def _search_item(entity_type: str, row: Any) -> dict[str, Any]:
    title = getattr(row, "title", None) or getattr(row, "simplified", None) or getattr(row, "chinese", None) or getattr(row, "storage_key", None) or f"{entity_type} #{row.id}"
    subtitle = getattr(row, "pinyin", None) or getattr(row, "description", None) or getattr(row, "pattern", None)
    return {
        "id": str(row.id),
        "entity_type": entity_type,
        "title": str(title),
        "subtitle": subtitle,
        "hsk_level": getattr(row, "hsk_level_id", None) or getattr(row, "hsk_level", None),
        "exam_revision_id": getattr(row, "exam_revision_id", None),
        "exam_level_id": getattr(row, "exam_level_id", None),
        "status": _row_status(row, entity_type),
        "updated_at": getattr(row, "updated_at", None),
    }


def _row_status(row: Any, entity_type: str) -> str | None:
    if entity_type == "lessons":
        return _value(row.content_status)
    status_value = getattr(row, "status", None)
    return _value(status_value) if status_value is not None else None


def _validate_row(db: Session, entity_type: str, row: Any) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if entity_type == "courses":
        if not db.get(HskLevel, row.hsk_level_id):
            issues.append(_issue("hsk_level_id", "HSK level does not exist"))
        if not row.title.strip():
            issues.append(_issue("title", "Course title is required"))
    elif entity_type == "lessons":
        if not row.title.strip():
            issues.append(_issue("title", "Lesson title is required"))
        if not db.get(Course, row.course_id):
            issues.append(_issue("course_id", "Course does not exist"))
        exercise_count = db.scalar(select(func.count(ExerciseSet.id)).where(ExerciseSet.lesson_id == row.id)) or 0
        if exercise_count == 0:
            issues.append(_issue("exercises", "Lesson has no exercises", "warning"))
    elif entity_type == "vocabulary":
        if not row.simplified.strip():
            issues.append(_issue("simplified", "Chinese text is required"))
        if not row.pinyin and not (row.metadata_json or {}).get("pinyin_not_available"):
            issues.append(_issue("pinyin", "Pinyin is required"))
        if not row.meaning_translations:
            issues.append(_issue("meaning_translations", "Meaning translation is required"))
        if row.audio_asset_id and not db.get(AudioAsset, row.audio_asset_id):
            issues.append(_issue("audio_asset_id", "Audio asset does not exist"))
    elif entity_type == "grammar":
        if not row.title.strip():
            issues.append(_issue("title", "Grammar title is required"))
        if not row.explanation_translations:
            issues.append(_issue("explanation_translations", "Grammar explanation is required"))
    elif entity_type == "example_sentences":
        if not row.chinese.strip():
            issues.append(_issue("chinese", "Chinese sentence is required"))
        if not row.translations:
            issues.append(_issue("translations", "Translation is required"))
    elif entity_type in {"exercises", "questions", "writing"}:
        if entity_type == "exercises":
            questions = db.scalar(select(func.count(Question.id)).where(Question.exercise_id == row.id)) or 0
            if questions == 0:
                issues.append(_issue("questions", "Exercise has no questions"))
        else:
            try:
                validate_question_configuration(row.question_type, row.configuration)
            except ValueError as exc:
                issues.append(_issue("configuration", str(exc)))
    elif entity_type == "exams":
        try:
            validate_exam_content(db, row)
        except HTTPException as exc:
            issues.append(_issue("sections", str(exc.detail)))
    elif entity_type == "audio":
        if not row.storage_key:
            issues.append(_issue("storage_key", "Storage key is required"))
        if row.status == "ARCHIVED":
            issues.append(_issue("status", "Audio asset is archived", "warning"))
    return issues


def _issue(field: str, message: str, severity: str = "error") -> dict[str, str]:
    return {"severity": severity, "field": field, "message": message}


def _set_status(row: Any, entity_type: str, next_status: str) -> None:
    if entity_type == "lessons":
        row.content_status = ContentStatus(next_status)
    elif entity_type in CONTENT_ENTITY_TYPES:
        row.status = ContentStatus(next_status)
    elif entity_type == "exams":
        row.status = next_status.upper()
    elif entity_type == "audio":
        row.status = "READY" if next_status == "published" else "ARCHIVED"
    else:
        raise HTTPException(status_code=422, detail="Unsupported status entity")


def _export_record(entity_type: str, row: Any) -> dict[str, Any]:
    if entity_type == "vocabulary":
        return {
            "id": row.id,
            "hsk_level_id": row.hsk_level_id,
            "simplified": row.simplified,
            "traditional": row.traditional,
            "pinyin": row.pinyin,
            "meaning_translations": row.meaning_translations,
            "part_of_speech": row.part_of_speech,
            "status": _row_status(row, entity_type),
        }
    return {
        "id": row.id,
        "title": getattr(row, "title", None),
        "status": _row_status(row, entity_type),
        "hsk_level_id": getattr(row, "hsk_level_id", None),
        "updated_at": getattr(row, "updated_at", None),
    }


def _existing_import_record(db: Session, entity_type: ImportEntityType, key: tuple[Any, ...]) -> bool:
    if entity_type == ImportEntityType.HSK_LEVELS:
        return db.scalar(select(HskLevel.id).where(HskLevel.level_number == key[0])) is not None
    if entity_type == ImportEntityType.COURSES:
        level = db.scalar(select(HskLevel.id).where(HskLevel.level_number == key[0]))
        return bool(level and db.scalar(select(Course.id).where(Course.hsk_level_id == level, Course.course_type == key[1])))
    if entity_type == ImportEntityType.VOCABULARY:
        level = db.scalar(select(HskLevel.id).where(HskLevel.level_number == key[0]))
        return bool(level and db.scalar(select(Vocabulary.id).where(Vocabulary.hsk_level_id == level, Vocabulary.simplified == key[1], Vocabulary.pinyin == (key[2] or None))))
    return False


def _normalize_dt(value: datetime | None) -> datetime | None:
    return value.replace(microsecond=0) if value else None


def _sanitize_metadata(value: dict[str, Any]) -> dict[str, Any]:
    blocked = {"password", "token", "secret", "api_key", "authorization"}
    return {key: item for key, item in value.items() if key.lower() not in blocked}
