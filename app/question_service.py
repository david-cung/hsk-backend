from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from app.models import ContentStatus, Question, QuestionOption, QuestionVersion


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def legacy_answer_from_configuration(configuration: dict[str, Any]) -> str:
    if "correct_option_ids" in configuration:
        correct_ids = configuration.get("correct_option_ids") or []
        options = configuration.get("options") or []
        by_id = {str(item.get("id")): item for item in options if isinstance(item, dict)}
        values = [str(by_id[item].get("text", item)) for item in correct_ids if item in by_id]
        return "|".join(values)
    if "accepted_answers" in configuration:
        return str((configuration.get("accepted_answers") or [""])[0])
    if "correct_pairs" in configuration:
        return json.dumps(configuration.get("correct_pairs") or {}, ensure_ascii=False, sort_keys=True)
    if "correct_order" in configuration:
        items = {str(item.get("id")): str(item.get("text", "")) for item in configuration.get("items") or []}
        return " ".join(items[item] for item in configuration.get("correct_order") or [] if item in items)
    return ""


def _option_payloads(configuration: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    correct_ids = {str(item) for item in configuration.get("correct_option_ids") or []}
    for index, item in enumerate(configuration.get("options") or []):
        if isinstance(item, dict) and item.get("id") is not None:
            rows.append(
                {
                    "option_group": "options",
                    "option_id": str(item["id"]),
                    "text": str(item.get("text") or ""),
                    "translations": item.get("translations"),
                    "is_correct": str(item["id"]) in correct_ids,
                    "sort_order": index,
                }
            )
    for group in ("items", "targets"):
        for index, item in enumerate(configuration.get(group) or []):
            if isinstance(item, dict) and item.get("id") is not None:
                rows.append(
                    {
                        "option_group": group,
                        "option_id": str(item["id"]),
                        "text": str(item.get("text") or ""),
                        "translations": item.get("translations"),
                        "is_correct": False,
                        "sort_order": index,
                    }
                )
    return rows


def _version_kwargs(question: Question) -> dict[str, Any]:
    return {
        "question_type": question.question_type,
        "skill": question.exercise.skill if question.exercise is not None else None,
        "prompt": question.prompt,
        "instruction": question.instruction,
        "correct_answer": question.correct_answer,
        "explanation": question.explanation,
        "difficulty": question.difficulty,
        "points": question.points,
        "configuration": question.configuration or {},
        "reference_type": question.reference_type,
        "reference_id": question.reference_id,
        "metadata_json": question.metadata_json,
    }


def _sync_legacy_columns(question: Question, version: QuestionVersion) -> None:
    question.question_type = version.question_type
    question.prompt = version.prompt
    question.instruction = version.instruction
    question.correct_answer = version.correct_answer
    question.explanation = version.explanation
    question.difficulty = version.difficulty
    question.points = version.points
    question.configuration = version.configuration
    question.reference_type = version.reference_type
    question.reference_id = version.reference_id
    question.metadata_json = version.metadata_json
    question.options = [
        str(item.get("text") or "")
        for item in (version.configuration or {}).get("options") or []
        if isinstance(item, dict)
    ] or None


def _replace_options(db: Session, version: QuestionVersion) -> None:
    version.options.clear()
    version.options.extend(
        QuestionOption(question_version_id=version.id, **payload)
        for payload in _option_payloads(version.configuration or {})
    )


def ensure_current_version(db: Session, question: Question) -> QuestionVersion:
    """Return the active version, lazily backfilling direct legacy inserts in tests/imports."""
    if question.current_version_id:
        version = db.get(QuestionVersion, question.current_version_id)
        if version is not None:
            return version
    version = db.scalar(
        select(QuestionVersion)
        .where(
            QuestionVersion.question_id == question.id,
            QuestionVersion.status == ContentStatus.PUBLISHED,
        )
        .order_by(desc(QuestionVersion.version_number), desc(QuestionVersion.id))
    )
    if version is None:
        version = QuestionVersion(
            question_id=question.id,
            version_number=1,
            status=ContentStatus.PUBLISHED,
            **_version_kwargs(question),
            published_at=datetime.now(UTC),
        )
        db.add(version)
        db.flush()
        _replace_options(db, version)
    question.current_version_id = version.id
    return version


def sync_question_version(db: Session, question: Question) -> QuestionVersion:
    """Create a new immutable version only when legacy/imported content changed."""
    latest = db.scalar(
        select(QuestionVersion)
        .where(QuestionVersion.question_id == question.id)
        .order_by(desc(QuestionVersion.version_number), desc(QuestionVersion.id))
    )
    values = _version_kwargs(question)
    target_status = _value(question.status or ContentStatus.DRAFT)
    if latest is not None:
        matches = all(getattr(latest, key) == value for key, value in values.items())
        if matches and _value(latest.status) == target_status:
            if latest.status == ContentStatus.PUBLISHED:
                question.current_version_id = latest.id
            return latest
    return create_version(db, question, status=ContentStatus(target_status), values=values)


def create_version(
    db: Session,
    question: Question,
    *,
    status: ContentStatus,
    values: dict[str, Any] | None = None,
) -> QuestionVersion:
    latest_number = db.scalar(
        select(QuestionVersion.version_number)
        .where(QuestionVersion.question_id == question.id)
        .order_by(desc(QuestionVersion.version_number))
        .limit(1)
    ) or 0
    payload = _version_kwargs(question)
    payload.update(values or {})
    version = QuestionVersion(
        question_id=question.id,
        version_number=int(latest_number) + 1,
        status=status,
        published_at=datetime.now(UTC) if status == ContentStatus.PUBLISHED else None,
        **payload,
    )
    db.add(version)
    db.flush()
    _replace_options(db, version)
    if status == ContentStatus.PUBLISHED:
        question.current_version_id = version.id
        question.status = ContentStatus.PUBLISHED
        question.is_archived = False
        _sync_legacy_columns(question, version)
    return version


def publish_version(db: Session, question: Question, version: QuestionVersion) -> QuestionVersion:
    version.status = ContentStatus.PUBLISHED
    version.published_at = version.published_at or datetime.now(UTC)
    question.current_version_id = version.id
    question.status = ContentStatus.PUBLISHED
    question.is_archived = False
    _sync_legacy_columns(question, version)
    return version


def current_version_for_id(db: Session, question_id: int, version_id: int | None = None) -> QuestionVersion | None:
    question = db.get(Question, question_id)
    if question is None:
        return None
    if version_id is not None:
        version = db.get(QuestionVersion, version_id)
        if version is not None and version.question_id == question_id:
            return version
    return ensure_current_version(db, question)
