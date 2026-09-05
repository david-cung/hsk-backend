from __future__ import annotations

import random
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.gamification_service import record_event
from app.models import (
    ExamAttempt,
    ExamQuestionResult,
    HskLevel,
    Lesson,
    MockTest,
    Question,
    User,
)
from app.practice_engine import (
    canonical_exercise_type,
    evaluate_answer,
    public_question_configuration,
)
from app.review_service import content_review_signal
from app.skill_schemas import (
    ExamAttemptHistoryOut,
    ExamAttemptOut,
    ExamDetailOut,
    ExamListOut,
    ExamQuestionOut,
    ExamQuestionResultOut,
    ExamResultOut,
    ExamSectionOut,
    ExamSectionResultOut,
    RecommendationOut,
    WeakAreaOut,
)


def canonical_type_value(question_type: str) -> str:
    """Canonical exercise-type value, tolerant of skill types (writing/speaking)."""
    try:
        return canonical_exercise_type(question_type).value
    except ValueError:
        return str(question_type or "").strip().lower()


def public_question_config(question: Question) -> dict[str, Any]:
    return public_question_configuration(question.question_type, question.configuration or {})


EXAM_SECTION_TITLES = {
    "LISTENING": "Listening",
    "READING": "Reading",
    "VOCABULARY": "Vocabulary",
    "GRAMMAR": "Grammar",
    "WRITING": "Writing",
}
SUPPORTED_EXAM_SECTIONS = set(EXAM_SECTION_TITLES)


def default_blueprint(exam: MockTest) -> dict[str, Any]:
    listening = max(1, round(exam.question_count * 0.35))
    reading = max(1, round(exam.question_count * 0.25))
    grammar = max(1, round(exam.question_count * 0.2))
    vocabulary = max(exam.question_count - listening - reading - grammar, 0)
    raw_sections = [
        ("LISTENING", listening),
        ("READING", reading),
        ("GRAMMAR", grammar),
        ("VOCABULARY", vocabulary),
    ]
    sections = [
        {
            "type": section_type,
            "title": EXAM_SECTION_TITLES[section_type],
            "question_count": count,
            "duration_minutes": max(1, round(exam.duration_minutes * count / max(exam.question_count, 1))),
            "allow_previous": True,
        }
        for section_type, count in raw_sections
        if count > 0
    ]
    return {
        "hsk_level": exam.hsk_level,
        "randomized": False,
        "allow_previous_section": True,
        "sections": sections,
    }


def sections_from_exam(exam: MockTest) -> list[ExamSectionOut]:
    blueprint = exam.blueprint if isinstance(exam.blueprint, dict) and exam.blueprint.get("sections") else default_blueprint(exam)
    return [
        ExamSectionOut(
            type=str(section.get("type", "")).upper(),
            title=str(section.get("title") or EXAM_SECTION_TITLES.get(str(section.get("type", "")).upper(), section.get("type", ""))),
            duration_minutes=int(section.get("duration_minutes") or 0),
            question_count=int(section.get("question_count") or 0),
            allow_previous=bool(section.get("allow_previous", True)),
        )
        for section in blueprint.get("sections", [])
    ]


def validate_exam_content(db: Session, exam: MockTest) -> None:
    if exam.status == "ARCHIVED":
        raise HTTPException(status_code=409, detail="Exam is archived")
    sections = sections_from_exam(exam)
    if not sections:
        raise HTTPException(status_code=422, detail="Exam has no sections")
    for section in sections:
        if section.type not in SUPPORTED_EXAM_SECTIONS:
            raise HTTPException(status_code=422, detail=f"Section {section.type} is not supported in Phase 10")
        available = len(_eligible_questions(db, exam.hsk_level, section.type))
        if available < section.question_count:
            raise HTTPException(
                status_code=422,
                detail=f"Not enough {section.type.lower()} questions for this exam: {available}/{section.question_count}",
            )


def list_exams(db: Session, user: User | None, hsk_level: int | None = None, published: bool = True) -> list[ExamListOut]:
    stmt = select(MockTest)
    if hsk_level is not None:
        stmt = stmt.where(MockTest.hsk_level == hsk_level)
    if published:
        stmt = stmt.where(MockTest.status == "PUBLISHED")
    rows = db.scalars(stmt.order_by(MockTest.hsk_level, MockTest.id)).all()
    attempts: dict[int, tuple[int, float | None]] = {}
    if user and rows:
        data = db.execute(
            select(ExamAttempt.exam_id, func.count(ExamAttempt.id), func.max(ExamAttempt.percentage))
            .where(ExamAttempt.user_id == user.id, ExamAttempt.exam_id.in_([row.id for row in rows]))
            .group_by(ExamAttempt.exam_id)
        ).all()
        attempts = {int(exam_id): (int(count or 0), float(best) if best is not None else None) for exam_id, count, best in data}
    return [
        ExamListOut(
            id=exam.id,
            title=exam.title,
            description=exam.description,
            hsk_level=exam.hsk_level,
            exam_type=exam.exam_type,
            duration_minutes=exam.duration_minutes,
            question_count=exam.question_count,
            sections=sections_from_exam(exam),
            attempt_count=attempts.get(exam.id, (0, None))[0],
            best_percentage=attempts.get(exam.id, (0, None))[1],
            status=exam.status,
        )
        for exam in rows
    ]


def exam_detail(db: Session, user: User, exam_id: int) -> ExamDetailOut:
    exam = _exam_or_404(db, exam_id)
    latest = db.scalar(
        select(ExamAttempt)
        .where(ExamAttempt.user_id == user.id, ExamAttempt.exam_id == exam.id)
        .order_by(ExamAttempt.started_at.desc(), ExamAttempt.id.desc())
    )
    return ExamDetailOut(
        id=exam.id,
        title=exam.title,
        description=exam.description,
        hsk_level=exam.hsk_level,
        exam_type=exam.exam_type,
        duration_minutes=exam.duration_minutes,
        question_count=exam.question_count,
        sections=sections_from_exam(exam),
        attempt_count=int(
            db.scalar(select(func.count()).select_from(ExamAttempt).where(ExamAttempt.user_id == user.id, ExamAttempt.exam_id == exam.id))
            or 0
        ),
        best_percentage=db.scalar(
            select(func.max(ExamAttempt.percentage)).where(ExamAttempt.user_id == user.id, ExamAttempt.exam_id == exam.id)
        ),
        status=exam.status,
        instructions=exam.instructions,
        availability="AVAILABLE" if exam.status == "PUBLISHED" else exam.status,
        latest_attempt_id=latest.id if latest else None,
    )


def start_exam(db: Session, user: User, exam_id: int) -> ExamAttemptOut:
    exam = _exam_or_404(db, exam_id)
    if exam.status != "PUBLISHED":
        raise HTTPException(status_code=409, detail="Exam is not available")
    validate_exam_content(db, exam)
    now = datetime.now(UTC)
    seed = random.SystemRandom().randint(1, 2_147_483_647)
    snapshot = _build_snapshot(db, exam, seed)
    attempt = ExamAttempt(
        user_id=user.id,
        exam_id=exam.id,
        exam_version=exam.version,
        status="IN_PROGRESS",
        started_at=now,
        expires_at=now + timedelta(minutes=exam.duration_minutes),
        random_seed=seed,
        current_section=(snapshot.get("sections") or [{}])[0].get("type"),
        question_snapshot=snapshot,
    )
    db.add(attempt)
    db.flush()
    for section in snapshot.get("sections", []):
        for question in section.get("questions", []):
            db.add(
                ExamQuestionResult(
                    exam_attempt_id=attempt.id,
                    user_id=user.id,
                    question_id=int(question["id"]),
                    section=str(section["type"]),
                    max_points=float(question.get("points", 1)),
                )
            )
    db.flush()
    return attempt_to_out(db, attempt, exam)


def resume_attempt(db: Session, user: User, attempt_id: int) -> ExamAttemptOut:
    attempt = _attempt_or_404(db, user, attempt_id)
    exam = _exam_or_404(db, attempt.exam_id)
    _expire_if_needed(db, user, attempt, exam)
    return attempt_to_out(db, attempt, exam)


def save_answer(db: Session, user: User, attempt_id: int, question_id: int, answer: Any) -> ExamAttemptOut:
    attempt = _attempt_or_404(db, user, attempt_id, lock=True)
    exam = _exam_or_404(db, attempt.exam_id)
    _expire_if_needed(db, user, attempt, exam)
    if attempt.status != "IN_PROGRESS":
        raise HTTPException(status_code=409, detail="Exam attempt is not accepting answers")
    if question_id not in set(_snapshot_question_ids(attempt)):
        raise HTTPException(status_code=400, detail="Question does not belong to this exam attempt")
    row = db.scalar(
        select(ExamQuestionResult).where(
            ExamQuestionResult.exam_attempt_id == attempt.id,
            ExamQuestionResult.question_id == question_id,
        )
    )
    if not row:
        raise HTTPException(status_code=404, detail="Exam question not found")
    row.answer = {"value": answer}
    row.answered_at = datetime.now(UTC)
    db.flush()
    return attempt_to_out(db, attempt, exam)


def submit_attempt(db: Session, user: User, attempt_id: int) -> ExamResultOut:
    attempt = _attempt_or_404(db, user, attempt_id, lock=True)
    exam = _exam_or_404(db, attempt.exam_id)
    if attempt.status in {"SUBMITTED", "EXPIRED"} and attempt.score is not None:
        return result_for_attempt(db, user, attempt.id)
    _finalize(db, user, attempt, exam, expired=datetime.now(UTC) >= _utc(attempt.expires_at))
    db.flush()
    return result_for_attempt(db, user, attempt.id)


def result_for_attempt(db: Session, user: User, attempt_id: int) -> ExamResultOut:
    attempt = _attempt_or_404(db, user, attempt_id)
    exam = _exam_or_404(db, attempt.exam_id)
    if attempt.status == "IN_PROGRESS":
        _expire_if_needed(db, user, attempt, exam)
    if attempt.status == "IN_PROGRESS":
        raise HTTPException(status_code=409, detail="Exam attempt is not submitted")
    rows = _result_rows(db, attempt.id)
    questions = {row.id: row for row in db.scalars(select(Question).where(Question.id.in_([r.question_id for r in rows] or [0]))).all()}
    return ExamResultOut(
        attempt_id=attempt.id,
        exam_id=exam.id,
        title=exam.title,
        hsk_level=exam.hsk_level,
        status=attempt.status,
        raw_score=float(attempt.score or 0),
        total_points=float((attempt.result_summary or {}).get("total_points", len(rows))),
        percentage=float(attempt.percentage or 0),
        passed=attempt.passed,
        started_at=attempt.started_at,
        submitted_at=attempt.submitted_at,
        expires_at=attempt.expires_at,
        time_used_seconds=max(round(((_utc(attempt.submitted_at) if attempt.submitted_at else _utc(attempt.expires_at)) - _utc(attempt.started_at)).total_seconds()), 0),
        sections=[ExamSectionResultOut(**item) for item in attempt.section_results or []],
        questions=[
            ExamQuestionResultOut(
                question_id=row.question_id,
                section=row.section,
                prompt=questions[row.question_id].prompt if row.question_id in questions else None,
                user_answer=(row.answer or {}).get("value") if isinstance(row.answer, dict) else None,
                correct_answer=_correct_answer_for_question(questions.get(row.question_id)),
                correct=row.correct,
                points=row.points,
                max_points=row.max_points,
                explanation=questions[row.question_id].explanation if row.question_id in questions else None,
                evaluation_source=(row.result_metadata or {}).get("evaluation_source"),
                writing_evaluation=(row.result_metadata or {}).get("writing_evaluation"),
            )
            for row in rows
        ],
        weak_areas=_weak_areas(attempt),
        recommended_practice=_recommendations(attempt),
    )


def attempt_history(db: Session, user: User, limit: int = 50, offset: int = 0) -> list[ExamAttemptHistoryOut]:
    rows = db.execute(
        select(ExamAttempt, MockTest)
        .join(MockTest, MockTest.id == ExamAttempt.exam_id)
        .where(ExamAttempt.user_id == user.id)
        .order_by(ExamAttempt.started_at.desc(), ExamAttempt.id.desc())
        .offset(offset)
        .limit(limit)
    ).all()
    return [
        ExamAttemptHistoryOut(
            attempt_id=attempt.id,
            exam_id=exam.id,
            title=exam.title,
            hsk_level=exam.hsk_level,
            status=attempt.status,
            score=attempt.score,
            percentage=attempt.percentage,
            passed=attempt.passed,
            started_at=attempt.started_at,
            submitted_at=attempt.submitted_at,
        )
        for attempt, exam in rows
    ]


class ExamScoringService:
    def finalize(self, db: Session, user: User, attempt: ExamAttempt, exam: MockTest, expired: bool = False) -> None:
        rows = _result_rows(db, attempt.id)
        questions = {row.id: row for row in db.scalars(select(Question).where(Question.id.in_([r.question_id for r in rows] or [0]))).all()}
        section_totals: dict[str, dict[str, float | int]] = {}
        now = datetime.now(UTC)
        for row in rows:
            question = questions.get(row.question_id)
            max_points = float(question.points if question else row.max_points or 1)
            correct = False
            points = 0.0
            if question and row.answer is not None:
                try:
                    evaluation = evaluate_answer(question, (row.answer or {}).get("value"))
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail=str(exc)) from exc
                correct = bool(evaluation.is_correct)
                points = float(evaluation.score)
                normalized = evaluation.normalized_answer
                if isinstance(normalized, dict) and normalized.get("writing_evaluation"):
                    row.result_metadata = {
                        **(row.result_metadata or {}),
                        "evaluation_source": normalized.get("evaluation_source"),
                        "writing_evaluation": normalized.get("writing_evaluation"),
                        "normalized_answer": normalized.get("value"),
                    }
            row.correct = correct
            row.points = points
            row.max_points = max_points
            row.evaluated_at = now
            bucket = section_totals.setdefault(row.section, {"total": 0, "answered": 0, "correct": 0, "points": 0.0, "max": 0.0})
            bucket["total"] = int(bucket["total"]) + 1
            bucket["answered"] = int(bucket["answered"]) + int(row.answer is not None)
            bucket["correct"] = int(bucket["correct"]) + int(correct)
            bucket["points"] = float(bucket["points"]) + points
            bucket["max"] = float(bucket["max"]) + max_points
            if question and row.answer is not None and not correct:
                section = _section_for_question(question).upper()
                source = "LISTENING" if section == "LISTENING" else "WRITING" if section == "WRITING" else "PRACTICE"
                content_review_signal(
                    db,
                    user,
                    question,
                    correct=False,
                    source=source,
                    idempotency_key=f"exam:{attempt.id}:{row.question_id}",
                    metadata={"exam_attempt_id": attempt.id, "question_id": row.question_id},
                    reviewed_at=now,
                )
        total_points = sum(float(bucket["points"]) for bucket in section_totals.values())
        max_points = sum(float(bucket["max"]) for bucket in section_totals.values())
        percentage = round((total_points / max_points) * 100, 2) if max_points else 0
        attempt.status = "EXPIRED" if expired else "SUBMITTED"
        attempt.submitted_at = now
        attempt.score = round(total_points, 2)
        attempt.percentage = percentage
        passing = (exam.scoring_config or {}).get("passing_percentage", 60) if isinstance(exam.scoring_config, dict) else 60
        attempt.passed = percentage >= float(passing)
        attempt.section_results = [
            {
                "section": section,
                "total_questions": int(bucket["total"]),
                "answered": int(bucket["answered"]),
                "correct": int(bucket["correct"]),
                "incorrect": int(bucket["answered"]) - int(bucket["correct"]),
                "skipped": int(bucket["total"]) - int(bucket["answered"]),
                "raw_score": round(float(bucket["points"]), 2),
                "percentage": round((float(bucket["points"]) / float(bucket["max"])) * 100, 2) if float(bucket["max"]) else 0,
                "time_used_seconds": 0,
            }
            for section, bucket in section_totals.items()
        ]
        attempt.result_summary = {"score_label": "Estimated Practice Score", "total_points": round(max_points, 2)}


def attempt_to_out(db: Session, attempt: ExamAttempt, exam: MockTest) -> ExamAttemptOut:
    now = datetime.now(UTC)
    rows = _result_rows(db, attempt.id)
    answers = {
        str(row.question_id): row.answer.get("value")
        for row in rows
        if isinstance(row.answer, dict) and "value" in row.answer
    }
    return ExamAttemptOut(
        attempt_id=attempt.id,
        exam_id=exam.id,
        exam_version=attempt.exam_version,
        status=attempt.status,
        title=exam.title,
        hsk_level=exam.hsk_level,
        duration_minutes=exam.duration_minutes,
        sections=[ExamSectionOut(**section) for section in attempt.question_snapshot.get("sections_meta", [])],
        questions=_questions_from_snapshot(attempt),
        answers=answers,
        server_time=now,
        started_at=attempt.started_at,
        expires_at=attempt.expires_at,
        submitted_at=attempt.submitted_at,
        remaining_seconds=max(round((_utc(attempt.expires_at) - now).total_seconds()), 0),
        current_section=attempt.current_section,
        allow_previous_section=bool((exam.blueprint or {}).get("allow_previous_section", True)) if isinstance(exam.blueprint, dict) else True,
    )


def _build_snapshot(db: Session, exam: MockTest, seed: int) -> dict[str, Any]:
    rng = random.Random(seed)
    randomized = bool((exam.blueprint or {}).get("randomized", False)) if isinstance(exam.blueprint, dict) else False
    sections = []
    sections_meta = []
    for index, section in enumerate(sections_from_exam(exam)):
        rows = _eligible_questions(db, exam.hsk_level, section.type)
        if randomized:
            rng.shuffle(rows)
        selected = rows[: section.question_count]
        sections_meta.append(section.model_dump())
        sections.append(
            {
                "type": section.type,
                "section_index": index,
                "questions": [_question_snapshot(row, section.type, index, qindex) for qindex, row in enumerate(selected)],
            }
        )
    return {"exam_version": exam.version, "seed": seed, "sections_meta": sections_meta, "sections": sections}


def _eligible_questions(db: Session, hsk_level: int, section_type: str) -> list[Question]:
    rows = (
        db.scalars(
            select(Question)
            .join(Lesson, Lesson.id == Question.lesson_id)
            .join(HskLevel, HskLevel.id == Lesson.hsk_level_id)
            .where(HskLevel.level_number == hsk_level, Question.is_archived.is_(False))
            .order_by(Lesson.sort_order, Lesson.id, Question.sort_order, Question.id)
        )
        .unique()
        .all()
    )
    return [row for row in rows if _section_for_question(row).upper() == section_type.upper()]


def _section_for_question(question: Question) -> str:
    qtype = canonical_type_value(question.question_type).upper()
    if qtype in {"LISTENING", "DICTATION"}:
        return "LISTENING"
    if qtype in {"READING"}:
        return "READING"
    if qtype in {"GRAMMAR"} or (question.reference_type or "").upper() == "GRAMMAR":
        return "GRAMMAR"
    if qtype in {"WORD_ORDER", "SENTENCE_REORDER", "TRANSLATION_TO_CHINESE", "GUIDED_WRITING"}:
        return "WRITING"
    if (question.reference_type or "").upper() == "WRITING":
        return "WRITING"
    lesson_type = question.lesson.lesson_type.upper() if question.lesson else ""
    if lesson_type in SUPPORTED_EXAM_SECTIONS:
        return lesson_type
    return "VOCABULARY"


def _question_snapshot(question: Question, section: str, section_index: int, question_index: int) -> dict[str, Any]:
    return {
        "id": question.id,
        "section": section,
        "section_index": section_index,
        "question_index": question_index,
        "exercise_id": question.exercise_id,
        "question_type": canonical_type_value(question.question_type),
        "prompt": question.prompt,
        "instruction": question.instruction,
        "difficulty": question.difficulty or 1,
        "points": question.points or 1,
        "order": question.sort_order,
        "config": public_question_config(question),
        "lesson_title": question.lesson.title if question.lesson else None,
    }


def _questions_from_snapshot(attempt: ExamAttempt) -> list[ExamQuestionOut]:
    rows = []
    for section in attempt.question_snapshot.get("sections", []):
        for item in section.get("questions", []):
            rows.append(ExamQuestionOut(**item))
    return rows


def _snapshot_question_ids(attempt: ExamAttempt) -> list[int]:
    return [question.id for question in _questions_from_snapshot(attempt)]


def _finalize(db: Session, user: User, attempt: ExamAttempt, exam: MockTest, expired: bool = False) -> None:
    ExamScoringService().finalize(db, user, attempt, exam, expired=expired)
    started = _utc(attempt.started_at)
    ended = _utc(attempt.submitted_at or datetime.now(UTC))
    minutes = max(round((ended - started).total_seconds() / 60), 0)
    record_event(
        db,
        user,
        "EXAM_COMPLETED",
        f"exam-attempt:{attempt.id}",
        minutes=minutes,
        exercises=len(_snapshot_question_ids(attempt)),
        metadata={"expired": expired, "percentage": attempt.percentage},
    )


def _expire_if_needed(db: Session, user: User, attempt: ExamAttempt, exam: MockTest) -> None:
    if attempt.status == "IN_PROGRESS" and datetime.now(UTC) >= _utc(attempt.expires_at):
        _finalize(db, user, attempt, exam, expired=True)
        db.flush()


def _result_rows(db: Session, attempt_id: int) -> list[ExamQuestionResult]:
    return list(
        db.scalars(
            select(ExamQuestionResult)
            .where(ExamQuestionResult.exam_attempt_id == attempt_id)
            .order_by(ExamQuestionResult.id)
        ).all()
    )


def _exam_or_404(db: Session, exam_id: int) -> MockTest:
    exam = db.get(MockTest, exam_id)
    if not exam:
        raise HTTPException(status_code=404, detail="Exam not found")
    return exam


def _attempt_or_404(db: Session, user: User, attempt_id: int, lock: bool = False) -> ExamAttempt:
    stmt = select(ExamAttempt).where(ExamAttempt.id == attempt_id, ExamAttempt.user_id == user.id)
    if lock and db.bind and db.bind.dialect.name == "postgresql":
        stmt = stmt.with_for_update()
    attempt = db.scalar(stmt)
    if not attempt:
        raise HTTPException(status_code=404, detail="Exam attempt not found")
    return attempt


def _correct_answer_for_question(question: Question | None) -> Any:
    if not question:
        return None
    try:
        return evaluate_answer(question, "").correct_answer
    except (AttributeError, KeyError, TypeError, ValueError):
        return question.correct_answer


def _weak_areas(attempt: ExamAttempt) -> list[WeakAreaOut]:
    weak = []
    for section in attempt.section_results or []:
        if float(section.get("percentage", 0)) < 70 and int(section.get("total_questions", 0)) > 0:
            weak.append(
                WeakAreaOut(
                    type="EXAM_SECTION",
                    label=f"{section['section'].title()} section",
                    skill=str(section["section"]),
                    metric=float(section.get("percentage", 0)),
                    attempts=int(section.get("total_questions", 0)),
                    reason=f"{section['section'].title()} scored below 70% on this mock exam.",
                )
            )
    return weak


def _recommendations(attempt: ExamAttempt) -> list[RecommendationOut]:
    weak = _weak_areas(attempt)
    if not weak:
        return []
    area = weak[0]
    return [
        RecommendationOut(
            type=f"{area.skill}_PRACTICE",
            target_label=area.label,
            reason=area.reason,
            activity_type="PRACTICE",
        )
    ]


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
