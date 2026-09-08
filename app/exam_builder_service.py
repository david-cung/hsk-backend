from __future__ import annotations

from copy import deepcopy
from math import ceil
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    AudioAsset,
    ContentStatus,
    ExamLevel,
    ExamPart,
    ExamQuestion,
    ExamRevision,
    ExamSection,
    ExamVersion,
    MockTest,
    QuestionVersion,
    ScoringPolicy,
)
from app.practice_engine import public_question_configuration
from app.skill_schemas import (
    AdminExamDocumentIn,
    AdminExamListItem,
    AdminExamListOut,
    AdminExamPartOut,
    AdminExamQuestionOut,
    AdminExamSectionOut,
    AdminExamVersionOut,
    ExamValidationIssue,
    ExamValidationOut,
)
from app.specification_service import validate_revision_level


def _value(value: Any) -> str:
    return str(getattr(value, "value", value)).lower()


def latest_version(db: Session, exam_id: int, *, published_only: bool = False) -> ExamVersion | None:
    stmt = select(ExamVersion).where(ExamVersion.exam_id == exam_id)
    if published_only:
        stmt = stmt.where(ExamVersion.status == ContentStatus.PUBLISHED)
    return db.scalar(stmt.order_by(ExamVersion.version_number.desc(), ExamVersion.id.desc()))


def load_version(db: Session, version_id: int) -> ExamVersion:
    version = db.scalar(
        select(ExamVersion)
        .where(ExamVersion.id == version_id)
        .options(
            selectinload(ExamVersion.sections)
            .selectinload(ExamSection.parts)
            .selectinload(ExamPart.questions)
            .selectinload(ExamQuestion.question_version)
        )
    )
    if version is None:
        raise HTTPException(status_code=404, detail="Exam version not found")
    return version


def _question_out(row: ExamQuestion) -> AdminExamQuestionOut:
    version = row.question_version
    return AdminExamQuestionOut(
        id=row.id,
        question_version_id=row.question_version_id,
        sort_order=row.sort_order,
        points=row.points,
        required=row.required,
        question_id=version.question_id,
        question_type=version.question_type,
        skill=version.skill,
        prompt=version.prompt,
        instruction=version.instruction,
        configuration=public_question_configuration(version.question_type, version.configuration or {}),
    )


def version_out(version: ExamVersion) -> AdminExamVersionOut:
    return AdminExamVersionOut(
        id=version.id,
        exam_id=version.exam_id,
        version_number=version.version_number,
        status=_value(version.status),
        title=version.title,
        description=version.description,
        exam_revision_id=version.exam_revision_id,
        exam_level_id=version.exam_level_id,
        scoring_policy_id=version.scoring_policy_id,
        duration_seconds=version.duration_seconds,
        instructions=version.instructions,
        blueprint_schema_version=version.blueprint_schema_version,
        configuration=version.configuration or {},
        metadata=version.metadata_json or {},
        sections=[
            AdminExamSectionOut(
                id=section.id,
                code=section.code,
                title=section.title,
                skill=section.skill,
                sort_order=section.sort_order,
                duration_seconds=section.duration_seconds,
                instructions=section.instructions,
                configuration=section.configuration or {},
                parts=[
                    AdminExamPartOut(
                        id=part.id,
                        code=part.code,
                        title=part.title,
                        instructions=part.instructions,
                        sort_order=part.sort_order,
                        configuration=part.configuration or {},
                        questions=[_question_out(question) for question in part.questions],
                    )
                    for part in section.parts
                ],
            )
            for section in version.sections
        ],
    )


def _document_blueprint(payload: AdminExamDocumentIn) -> dict[str, Any]:
    return {
        "schema_version": payload.blueprint_schema_version,
        "randomized": bool(payload.configuration.get("randomized", False)),
        "allow_previous_section": bool(payload.configuration.get("allow_previous_section", True)),
        "sections": [
            {"type": section.code, "title": section.title, "question_count": sum(len(part.questions) for part in section.parts),
             "duration_minutes": ceil(section.duration_seconds / 60) if section.duration_seconds else 0,
             "allow_previous": bool(section.configuration.get("allow_previous", True))}
            for section in payload.sections
        ],
    }


def _validate_scope(db: Session, payload: AdminExamDocumentIn) -> None:
    validate_revision_level(db, payload.exam_revision_id, payload.exam_level_id)
    policy = db.get(ScoringPolicy, payload.scoring_policy_id)
    if policy is None:
        raise HTTPException(status_code=422, detail="Scoring policy does not exist")
    if policy.revision_id is not None and policy.revision_id != payload.exam_revision_id:
        raise HTTPException(status_code=422, detail="Scoring policy does not belong to the selected revision")


def _replace_sections(db: Session, version: ExamVersion, sections: list[Any]) -> None:
    version.sections.clear()
    db.flush()
    for section_input in sections:
        section = ExamSection(
            code=section_input.code,
            title=section_input.title,
            skill=section_input.skill,
            sort_order=section_input.sort_order,
            duration_seconds=section_input.duration_seconds,
            instructions=section_input.instructions,
            configuration=section_input.configuration,
        )
        version.sections.append(section)
        for part_input in section_input.parts:
            part = ExamPart(
                code=part_input.code,
                title=part_input.title,
                instructions=part_input.instructions,
                sort_order=part_input.sort_order,
                configuration=part_input.configuration,
            )
            section.parts.append(part)
            for question_input in part_input.questions:
                question_version = db.get(QuestionVersion, question_input.question_version_id)
                if question_version is None:
                    raise HTTPException(status_code=422, detail=f"Question version {question_input.question_version_id} not found")
                if _value(question_version.status) != "published":
                    raise HTTPException(status_code=422, detail=f"Question version {question_input.question_version_id} must be published")
                part.questions.append(
                    ExamQuestion(
                        question_version_id=question_version.id,
                        sort_order=question_input.sort_order,
                        points=question_input.points,
                        required=question_input.required,
                        configuration=question_input.configuration,
                    )
                )


def apply_document(db: Session, version: ExamVersion, payload: AdminExamDocumentIn) -> ExamVersion:
    if _value(version.status) != "draft":
        raise HTTPException(status_code=409, detail="Published exam versions are immutable; clone a new version")
    _validate_scope(db, payload)
    version.title = payload.title
    version.description = payload.description
    version.exam_revision_id = payload.exam_revision_id
    version.exam_level_id = payload.exam_level_id
    version.scoring_policy_id = payload.scoring_policy_id
    version.duration_seconds = payload.duration_seconds
    version.instructions = payload.instructions
    version.blueprint_schema_version = payload.blueprint_schema_version
    version.configuration = payload.configuration
    version.metadata_json = payload.metadata
    _replace_sections(db, version, payload.sections)
    return version


def create_exam(db: Session, payload: AdminExamDocumentIn) -> ExamVersion:
    _validate_scope(db, payload)
    exam = MockTest(
        title=payload.title,
        description=payload.description,
        exam_revision_id=payload.exam_revision_id,
        exam_level_id=payload.exam_level_id,
        scoring_policy_id=payload.scoring_policy_id,
        duration_minutes=max(1, ceil(payload.duration_seconds / 60)),
        question_count=sum(len(part.questions) for section in payload.sections for part in section.parts),
        exam_type="MOCK",
        status="DRAFT",
        version=1,
        blueprint=_document_blueprint(payload),
        blueprint_schema_version=payload.blueprint_schema_version,
        scoring_config={},
        instructions=payload.instructions,
    )
    db.add(exam)
    db.flush()
    version = ExamVersion(
        exam=exam,
        version_number=1,
        status=ContentStatus.DRAFT,
        exam_revision_id=payload.exam_revision_id,
        exam_level_id=payload.exam_level_id,
        scoring_policy_id=payload.scoring_policy_id,
        title=payload.title,
        description=payload.description,
        duration_seconds=payload.duration_seconds,
        instructions=payload.instructions,
        blueprint_schema_version=payload.blueprint_schema_version,
        configuration=payload.configuration,
        metadata_json=payload.metadata,
    )
    db.add(version)
    db.flush()
    _replace_sections(db, version, payload.sections)
    db.flush()
    return version


def clone_version(db: Session, source: ExamVersion) -> ExamVersion:
    version = ExamVersion(
        exam_id=source.exam_id,
        version_number=(db.scalar(select(func.max(ExamVersion.version_number)).where(ExamVersion.exam_id == source.exam_id)) or 0) + 1,
        status=ContentStatus.DRAFT,
        exam_revision_id=source.exam_revision_id,
        exam_level_id=source.exam_level_id,
        scoring_policy_id=source.scoring_policy_id,
        title=source.title,
        description=source.description,
        duration_seconds=source.duration_seconds,
        instructions=source.instructions,
        blueprint_schema_version=source.blueprint_schema_version,
        configuration=deepcopy(source.configuration or {}),
        metadata_json=deepcopy(source.metadata_json or {}),
    )
    db.add(version)
    db.flush()
    for section in source.sections:
        new_section = ExamSection(
            code=section.code, title=section.title, skill=section.skill, sort_order=section.sort_order,
            duration_seconds=section.duration_seconds, instructions=section.instructions,
            configuration=deepcopy(section.configuration or {}),
        )
        version.sections.append(new_section)
        for part in section.parts:
            new_part = ExamPart(
                code=part.code, title=part.title, instructions=part.instructions, sort_order=part.sort_order,
                configuration=deepcopy(part.configuration or {}),
            )
            new_section.parts.append(new_part)
            for question in part.questions:
                new_part.questions.append(
                    ExamQuestion(
                        question_version_id=question.question_version_id,
                        sort_order=question.sort_order, points=question.points, required=question.required,
                        configuration=deepcopy(question.configuration or {}),
                    )
                )
    db.flush()
    return version


def validate_version(db: Session, version: ExamVersion, *, require_publishable: bool = True) -> ExamValidationOut:
    errors: list[ExamValidationIssue] = []
    if version.exam_revision_id is None:
        errors.append(ExamValidationIssue(code="REVISION_REQUIRED", field="exam_revision_id", message="Exam revision is required"))
    elif db.get(ExamRevision, version.exam_revision_id) is None:
        errors.append(ExamValidationIssue(code="REVISION_NOT_FOUND", field="exam_revision_id", message="Exam revision does not exist"))
    if version.exam_level_id is None:
        errors.append(ExamValidationIssue(code="LEVEL_REQUIRED", field="exam_level_id", message="Exam level is required"))
    elif version.exam_revision_id and db.get(ExamLevel, version.exam_level_id) is None:
        errors.append(ExamValidationIssue(code="LEVEL_NOT_FOUND", field="exam_level_id", message="Exam level does not exist"))
    elif version.exam_revision_id:
        try:
            validate_revision_level(db, version.exam_revision_id, version.exam_level_id)
        except HTTPException:
            errors.append(ExamValidationIssue(code="LEVEL_REVISION_MISMATCH", field="exam_level_id", message="Exam level does not belong to the selected revision"))
    if require_publishable and version.scoring_policy_id is None:
        errors.append(ExamValidationIssue(code="SCORING_POLICY_REQUIRED", field="scoring_policy_id", message="Scoring policy is required before publishing"))
    elif version.scoring_policy_id and db.get(ScoringPolicy, version.scoring_policy_id) is None:
        errors.append(ExamValidationIssue(code="SCORING_POLICY_NOT_FOUND", field="scoring_policy_id", message="Scoring policy does not exist"))
    if not version.sections:
        errors.append(ExamValidationIssue(code="NO_SECTIONS", field="sections", message="At least one section is required"))
    if version.duration_seconds <= 0:
        errors.append(ExamValidationIssue(code="INVALID_DURATION", field="duration_seconds", message="Exam duration must be positive"))
    seen_sections: set[str] = set()
    seen_questions: set[int] = set()
    section_duration = 0
    for section in version.sections:
        field = f"sections[{section.sort_order}]"
        if section.code in seen_sections:
            errors.append(ExamValidationIssue(code="DUPLICATE_SECTION", field=field, message=f"Duplicate section code: {section.code}"))
        seen_sections.add(section.code)
        section_duration += section.duration_seconds
        if not section.parts:
            errors.append(ExamValidationIssue(code="NO_PARTS", field=f"{field}.parts", message="Section must contain at least one part"))
        section_config = section.configuration or {}
        if section_config.get("audio_required"):
            audio_id = section_config.get("audio_asset_id")
            if not audio_id:
                errors.append(ExamValidationIssue(code="AUDIO_ASSET_REQUIRED", field=f"{field}.configuration.audio_asset_id", message="This listening section requires an audio asset"))
            elif db.get(AudioAsset, audio_id) is None:
                errors.append(ExamValidationIssue(code="AUDIO_ASSET_MISSING", field=f"{field}.configuration.audio_asset_id", message="Listening section audio asset does not exist"))
        for part in section.parts:
            if not part.questions:
                errors.append(ExamValidationIssue(code="NO_QUESTIONS", field=f"{field}.parts[{part.sort_order}].questions", message="Part must contain at least one question"))
            for row in part.questions:
                qfield = f"{field}.parts[{part.sort_order}].questions[{row.sort_order}]"
                if row.question_version_id in seen_questions:
                    errors.append(ExamValidationIssue(code="DUPLICATE_QUESTION", field=qfield, message="Question version is assigned more than once"))
                seen_questions.add(row.question_version_id)
                question = row.question_version
                if question is None or _value(question.status) != "published":
                    errors.append(ExamValidationIssue(code="QUESTION_NOT_PUBLISHED", field=qfield, message="Assigned question version must be published"))
                if row.points <= 0:
                    errors.append(ExamValidationIssue(code="INVALID_POINTS", field=f"{qfield}.points", message="Points must be positive"))
                if (section.skill or "").lower() == "listening" or (section.code or "").lower() == "listening":
                    config = (question.configuration if question else {}) or {}
                    asset_id = config.get("audio_asset_id")
                    if asset_id and db.get(AudioAsset, asset_id) is None:
                        errors.append(ExamValidationIssue(code="AUDIO_ASSET_MISSING", field=qfield, message="Listening question audio asset does not exist"))
    if section_duration > version.duration_seconds:
        errors.append(ExamValidationIssue(code="TIMING_EXCEEDS_EXAM", field="sections", message="Section durations exceed exam duration"))
    return ExamValidationOut(valid=not errors, errors=errors)


def list_admin_exams(db: Session, *, status: str | None = None, revision_id: int | None = None,
                     level_id: int | None = None, query: str | None = None, page: int = 1,
                     page_size: int = 20) -> AdminExamListOut:
    stmt = select(ExamVersion, MockTest).join(MockTest, MockTest.id == ExamVersion.exam_id)
    if status:
        stmt = stmt.where(ExamVersion.status == status.lower())
    if revision_id:
        stmt = stmt.where(ExamVersion.exam_revision_id == revision_id)
    if level_id:
        stmt = stmt.where(ExamVersion.exam_level_id == level_id)
    if query:
        stmt = stmt.where(ExamVersion.title.ilike(f"%{query.strip()}%"))
    total = int(db.scalar(select(func.count()).select_from(stmt.subquery())) or 0)
    rows = db.execute(stmt.order_by(ExamVersion.updated_at.desc(), ExamVersion.id.desc()).offset((page - 1) * page_size).limit(page_size)).all()
    items = [
        AdminExamListItem(
            id=exam.id, title=version.title, description=version.description,
            exam_revision_id=version.exam_revision_id, exam_level_id=version.exam_level_id,
            scoring_policy_id=version.scoring_policy_id, version_number=version.version_number,
            version_id=version.id, status=_value(version.status), duration_seconds=version.duration_seconds,
            question_count=sum(len(part.questions) for section in version.sections for part in section.parts),
        )
        for version, exam in rows
    ]
    return AdminExamListOut(items=items, total=total, page=page, page_size=page_size, pages=ceil(total / page_size) if total else 0)
