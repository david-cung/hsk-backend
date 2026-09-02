from __future__ import annotations

# ruff: noqa: B008
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.audio_service import validate_audio_asset_payload
from app.auth import get_current_user
from app.database import get_db
from app.models import (
    AnswerAttempt,
    AudioAsset,
    Exercise,
    ExerciseSet,
    Lesson,
    PracticeSession,
    Question,
    User,
)
from app.practice_engine import (
    build_legacy_question_config,
    canonical_type,
    complete_session,
    evaluate_answer,
    is_writing_question_type,
    public_question_config,
    recalculate_session,
    update_lesson_progress,
    validate_question_config,
)
from app.review_service import practice_review_signal
from app.schemas import (
    AdminExerciseIn,
    AdminExerciseOut,
    AdminQuestionIn,
    ExerciseImportIn,
    ExerciseImportOut,
    PracticeAnswerIn,
    PracticeAnswerOut,
    PracticeLessonOut,
    PracticeQuestionOut,
    PracticeResultsOut,
    PracticeReviewItemOut,
    PracticeSessionCreateIn,
    PracticeSessionOut,
    SpeechAnalysisOut,
)
from app.speech_service import (
    SPEAKING_TYPES,
    SpeechProviderError,
    complete_speaking_attempt,
    create_failed_speaking_attempt,
    ensure_recording_ready_for_user,
    expected_text_for_question,
    speaking_payload_from_attempt,
)
from app.writing_service import WRITING_TYPES

router = APIRouter(prefix="/api/v1/practice", tags=["practice"])
admin_router = APIRouter(prefix="/api/v1/admin/exercises", tags=["admin-exercises"])
logger = logging.getLogger("hsk.practice")


def require_admin(user: User = Depends(get_current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return user


def question_to_public(question: Question, include_explanation: bool = False) -> PracticeQuestionOut:
    return PracticeQuestionOut(
        id=question.id,
        exercise_id=question.exercise_id,
        question_type=canonical_type(question.question_type).value,
        prompt=question.prompt,
        instruction=question.instruction,
        explanation=question.explanation if include_explanation else None,
        difficulty=question.difficulty or 1,
        points=question.points or 1,
        order=question.sort_order,
        config=public_question_config(question),
    )


def session_to_out(db: Session, session: PracticeSession, include_explanation: bool = False) -> PracticeSessionOut:
    questions = _questions_for_session(db, session)
    return PracticeSessionOut(
        id=session.id,
        lesson_id=session.lesson_id,
        exercise_set_id=session.exercise_set_id,
        status=session.status,
        started_at=session.started_at,
        completed_at=session.completed_at,
        total_questions=session.total_questions,
        answered_questions=session.answered_questions,
        correct_answers=session.correct_answers,
        score=session.score,
        time_spent_seconds=session.time_spent_seconds,
        questions=[question_to_public(question, include_explanation=include_explanation) for question in questions],
    )


def _questions_for_lesson(
    db: Session,
    lesson_id: int,
    exercise_set_id: int | None = None,
    question_count: int | None = None,
    difficulty: int | None = None,
    skill: str | None = None,
) -> list[Question]:
    stmt = (
        select(Question)
        .options(selectinload(Question.exercise))
        .where(Question.lesson_id == lesson_id, Question.is_archived.is_(False))
    )
    if exercise_set_id is not None:
        stmt = stmt.join(Exercise, Exercise.id == Question.exercise_id).where(Exercise.exercise_set_id == exercise_set_id)
    if difficulty is not None:
        stmt = stmt.where(Question.difficulty == difficulty)
    if skill:
        stmt = stmt.join(Exercise, Exercise.id == Question.exercise_id, isouter=True).where(
            (Exercise.skill == skill) | (Question.reference_type == skill)
        )
    rows = db.scalars(stmt.order_by(Question.sort_order, Question.id)).unique().all()
    return list(rows[:question_count] if question_count else rows)


def _questions_for_session(db: Session, session: PracticeSession) -> list[Question]:
    ids = [int(value) for value in session.question_ids or []]
    if not ids:
        return []
    rows = db.scalars(select(Question).where(Question.id.in_(ids))).all()
    by_id = {row.id: row for row in rows}
    return [by_id[question_id] for question_id in ids if question_id in by_id]


def _default_exercise_set(db: Session, lesson: Lesson) -> ExerciseSet:
    existing = db.scalar(
        select(ExerciseSet).where(ExerciseSet.lesson_id == lesson.id, ExerciseSet.slug == "lesson-practice")
    )
    if existing:
        return existing
    exercise_set = ExerciseSet(
        lesson_id=lesson.id,
        slug="lesson-practice",
        title=f"{lesson.title} Practice",
        description="Generated practice set from normalized lesson questions.",
        skill=lesson.lesson_type,
        sort_order=lesson.sort_order,
        config={"source": "legacy_questions"},
    )
    db.add(exercise_set)
    db.flush()
    return exercise_set


def _ensure_lesson_exercises(db: Session, lesson: Lesson) -> ExerciseSet:
    exercise_set = _default_exercise_set(db, lesson)
    existing_exercise = db.scalar(
        select(Exercise).where(Exercise.exercise_set_id == exercise_set.id, Exercise.slug == "quiz")
    )
    if existing_exercise is None:
        existing_exercise = Exercise(
            exercise_set_id=exercise_set.id,
            lesson_id=lesson.id,
            slug="quiz",
            title="Lesson practice",
            exercise_type="MULTIPLE_CHOICE",
            skill=lesson.lesson_type,
            sort_order=1,
            config={"source": "legacy_questions"},
        )
        db.add(existing_exercise)
        db.flush()
    questions = db.scalars(select(Question).where(Question.lesson_id == lesson.id).order_by(Question.sort_order)).all()
    for question in questions:
        if question.exercise_id is None:
            question.exercise_id = existing_exercise.id
        if not question.config:
            question.config = build_legacy_question_config(question.question_type, question.options, question.correct_answer)
    return exercise_set


def _question_review_payload(question: Question, attempt: AnswerAttempt | None) -> PracticeReviewItemOut:
    speech_analysis = speaking_payload_from_attempt(attempt)
    if canonical_type(question.question_type).value in SPEAKING_TYPES:
        evaluation = {
            "correct_answer": expected_text_for_question(question),
        }
    else:
        evaluation = evaluate_answer(question, attempt.submitted_answer if attempt else "")
    transcript = _visible_transcript_payload(question)
    return PracticeReviewItemOut(
        question=question_to_public(question, include_explanation=True),
        user_answer=attempt.submitted_answer.get("value") if attempt and isinstance(attempt.submitted_answer, dict) else None,
        correct_answer=evaluation["correct_answer"],
        correct=bool(attempt and attempt.is_correct),
        score=attempt.score if attempt else 0,
        explanation=question.explanation,
        transcript=transcript["transcript"],
        pinyin=transcript["pinyin"],
        translation=transcript["translation"],
        processing_status=(attempt.normalized_answer or {}).get("processing_status") if attempt else None,
        speech_analysis=SpeechAnalysisOut.model_validate(speech_analysis) if speech_analysis else None,
        writing_evaluation=_writing_evaluation_payload(attempt),
        attempted_at=attempt.attempted_at if attempt else None,
    )


def _writing_evaluation_payload(attempt: AnswerAttempt | None) -> dict[str, Any] | None:
    normalized = attempt.normalized_answer if attempt else None
    if not isinstance(normalized, dict):
        return None
    value = normalized.get("writing_evaluation")
    return value if isinstance(value, dict) else None


def _visible_transcript_payload(question: Question) -> dict[str, str | None]:
    config = question.config or {}
    if canonical_type(question.question_type).value != "LISTENING":
        return {"transcript": None, "pinyin": None, "translation": None}
    if not config.get("show_transcript_after_submit", True):
        return {"transcript": None, "pinyin": None, "translation": None}
    return {
        "transcript": config.get("transcript") if isinstance(config.get("transcript"), str) else None,
        "pinyin": config.get("pinyin") if isinstance(config.get("pinyin"), str) else None,
        "translation": config.get("translation") if isinstance(config.get("translation"), str) else None,
    }


def _client_recording_id(answer: Any) -> int:
    value = answer.get("recording_id") if isinstance(answer, dict) else None
    if not isinstance(value, str | int):
        raise HTTPException(status_code=422, detail="recording_id is required for speaking answers")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail="recording_id is required for speaking answers") from exc


def _speaking_answer_out(
    db: Session,
    session: PracticeSession,
    question: Question,
    attempt: AnswerAttempt,
) -> PracticeAnswerOut:
    speech_analysis = speaking_payload_from_attempt(attempt)
    return PracticeAnswerOut(
        attempt_id=attempt.id,
        question_id=question.id,
        correct=attempt.is_correct,
        score=attempt.score,
        max_score=float(question.points or 1),
        correct_answer=expected_text_for_question(question),
        explanation=question.explanation,
        normalized_answer=attempt.normalized_answer,
        processing_status=(attempt.normalized_answer or {}).get("processing_status"),
        speech_analysis=SpeechAnalysisOut.model_validate(speech_analysis) if speech_analysis else None,
        session=session_to_out(db, session),
    )


@router.get("/lessons/{lesson_id}", response_model=PracticeLessonOut)
def lesson_practice(
    lesson_id: int,
    question_count: int | None = None,
    difficulty: int | None = None,
    skill: str | None = None,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeLessonOut:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exercise_set = _ensure_lesson_exercises(db, lesson)
    questions = _questions_for_lesson(db, lesson_id, exercise_set.id, question_count, difficulty, skill)
    db.commit()
    return PracticeLessonOut(
        lesson_id=lesson.id,
        exercise_set_id=exercise_set.id,
        title=exercise_set.title,
        total_questions=len(questions),
        questions=[question_to_public(question) for question in questions],
    )


@router.post("/sessions", response_model=PracticeSessionOut, status_code=status.HTTP_201_CREATED)
def create_session(
    payload: PracticeSessionCreateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionOut:
    lesson = db.get(Lesson, payload.lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exercise_set = _ensure_lesson_exercises(db, lesson)
    exercise_set_id = payload.exercise_set_id or exercise_set.id

    if payload.resume:
        existing = db.scalar(
            select(PracticeSession)
            .where(
                PracticeSession.user_id == user.id,
                PracticeSession.lesson_id == lesson.id,
                PracticeSession.exercise_set_id == exercise_set_id,
                PracticeSession.status == "IN_PROGRESS",
            )
            .order_by(PracticeSession.started_at.desc())
        )
        if existing:
            return session_to_out(db, existing)

    questions = _questions_for_lesson(
        db,
        lesson.id,
        exercise_set_id,
        payload.question_count,
        payload.difficulty,
        payload.skill,
    )
    if not questions:
        raise HTTPException(status_code=400, detail="Lesson has no practice questions")
    session = PracticeSession(
        user_id=user.id,
        lesson_id=lesson.id,
        exercise_set_id=exercise_set_id,
        question_ids=[question.id for question in questions],
        total_questions=len(questions),
        config=payload.model_dump(exclude_none=True),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return session_to_out(db, session)


@router.get("/sessions/{session_id}", response_model=PracticeSessionOut)
def get_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionOut:
    session = db.scalar(select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=404, detail="Practice session not found")
    recalculate_session(db, session)
    db.commit()
    return session_to_out(db, session)


@router.post("/sessions/{session_id}/answers", response_model=PracticeAnswerOut)
def submit_answer(
    session_id: int,
    payload: PracticeAnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeAnswerOut:
    session = db.scalar(select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=404, detail="Practice session not found")
    if session.status != "IN_PROGRESS":
        raise HTTPException(status_code=409, detail="Practice session is not in progress")
    if payload.question_id not in [int(value) for value in session.question_ids or []]:
        raise HTTPException(status_code=400, detail="Question does not belong to this session")
    idempotency_key = payload.idempotency_key or f"{payload.question_id}:{uuid4()}"
    existing = db.scalar(
        select(AnswerAttempt).where(
            AnswerAttempt.practice_session_id == session.id,
            AnswerAttempt.idempotency_key == idempotency_key,
        )
    )
    if existing:
        existing_question = db.get(Question, existing.question_id)
        if not existing_question:
            raise HTTPException(status_code=404, detail="Question not found")
        if canonical_type(existing_question.question_type).value in SPEAKING_TYPES:
            recalculate_session(db, session)
            return _speaking_answer_out(db, session, existing_question, existing)
        try:
            existing_evaluation = evaluate_answer(existing_question, existing.submitted_answer)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        transcript_payload = _visible_transcript_payload(existing_question)
        recalculate_session(db, session)
        return PracticeAnswerOut(
            attempt_id=existing.id,
            question_id=existing.question_id,
            correct=existing.is_correct,
            score=existing.score,
            max_score=float(existing_question.points or 1),
            correct_answer=existing_evaluation["correct_answer"],
            explanation=existing_question.explanation,
            normalized_answer=existing.normalized_answer,
            transcript=transcript_payload["transcript"],
            pinyin=transcript_payload["pinyin"],
            translation=transcript_payload["translation"],
            writing_evaluation=_writing_evaluation_payload(existing),
            session=session_to_out(db, session),
        )

    question = db.get(Question, payload.question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Question not found")
    if canonical_type(question.question_type).value in SPEAKING_TYPES:
        config = question.config or {}
        recording = ensure_recording_ready_for_user(db, _client_recording_id(payload.answer), user.id)
        attempt = AnswerAttempt(
            user_id=user.id,
            practice_session_id=session.id,
            question_id=question.id,
            submitted_answer={"value": {"recording_id": recording.id}},
            normalized_answer={"recording_id": recording.id, "processing_status": "PROCESSING"},
            attempt_metadata={"playback": payload.playback or {}, "client": {"duration_seconds": recording.duration_seconds}},
            is_correct=False,
            score=0,
            time_spent_seconds=payload.time_spent_seconds,
            idempotency_key=idempotency_key,
        )
        db.add(attempt)
        db.flush()
        try:
            speaking_attempt = complete_speaking_attempt(db, user, session, question, attempt, recording, config)
            practice_review_signal(
                db,
                user,
                question,
                attempt,
                pronunciation_score=speaking_attempt.pronunciation_score,
            )
        except SpeechProviderError as exc:
            create_failed_speaking_attempt(db, user, session, question, attempt, recording, "mock", exc)
            recalculate_session(db, session)
            update_lesson_progress(db, user, session)
            db.commit()
            logger.warning(
                "pronunciation_processing_failed",
                extra={"question_id": question.id, "recording_id": recording.id},
            )
            raise HTTPException(status_code=503 if exc.retryable else 422, detail=exc.message) from exc
        recalculate_session(db, session)
        update_lesson_progress(db, user, session)
        db.commit()
        db.refresh(attempt)
        return _speaking_answer_out(db, session, question, attempt)
    try:
        evaluation = evaluate_answer(question, payload.answer)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    attempt = AnswerAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=question.id,
        submitted_answer={"value": payload.answer},
        normalized_answer=evaluation["normalized_answer"],
        attempt_metadata={"playback": payload.playback or {}},
        is_correct=evaluation["correct"],
        score=evaluation["score"],
        time_spent_seconds=payload.time_spent_seconds,
        idempotency_key=idempotency_key,
    )
    db.add(attempt)
    db.flush()
    practice_review_signal(db, user, question, attempt)
    recalculate_session(db, session)
    update_lesson_progress(db, user, session)
    db.commit()
    db.refresh(attempt)
    transcript_payload = _visible_transcript_payload(question)
    return PracticeAnswerOut(
        attempt_id=attempt.id,
        question_id=question.id,
        correct=attempt.is_correct,
        score=attempt.score,
        max_score=evaluation["max_score"],
        correct_answer=evaluation["correct_answer"],
        explanation=evaluation["explanation"],
        normalized_answer=attempt.normalized_answer,
        transcript=transcript_payload["transcript"],
        pinyin=transcript_payload["pinyin"],
        translation=transcript_payload["translation"],
        writing_evaluation=_writing_evaluation_payload(attempt),
        session=session_to_out(db, session),
    )


@router.post("/sessions/{session_id}/complete", response_model=PracticeSessionOut)
def complete_practice_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionOut:
    session = db.scalar(select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=404, detail="Practice session not found")
    complete_session(db, user, session)
    db.commit()
    return session_to_out(db, session, include_explanation=True)


@router.get("/sessions/{session_id}/results", response_model=PracticeResultsOut)
def session_results(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeResultsOut:
    session = db.scalar(select(PracticeSession).where(PracticeSession.id == session_id, PracticeSession.user_id == user.id))
    if not session:
        raise HTTPException(status_code=404, detail="Practice session not found")
    recalculate_session(db, session)
    questions = _questions_for_session(db, session)
    attempts = db.scalars(
        select(AnswerAttempt)
        .where(AnswerAttempt.practice_session_id == session.id)
        .order_by(AnswerAttempt.attempted_at, AnswerAttempt.id)
    ).all()
    latest_by_question = {attempt.question_id: attempt for attempt in attempts}
    review = [_question_review_payload(question, latest_by_question.get(question.id)) for question in questions]
    accuracy = round((session.correct_answers / session.answered_questions) * 100, 2) if session.answered_questions else 0
    return PracticeResultsOut(
        session_id=session.id,
        total_questions=session.total_questions,
        answered_questions=session.answered_questions,
        correct_answers=session.correct_answers,
        incorrect_answers=max(session.answered_questions - session.correct_answers, 0),
        score=session.score,
        accuracy=accuracy,
        time_spent_seconds=session.time_spent_seconds,
        review=review,
    )


def _apply_question_payload(db: Session, question: Question, payload: AdminQuestionIn, exercise: Exercise) -> None:
    validate_question_config(payload.question_type, payload.config)
    _ensure_audio_reference(db, payload.config)
    question.exercise_id = exercise.id
    question.lesson_id = exercise.lesson_id or question.lesson_id
    question.question_type = canonical_type(payload.question_type).value
    question.prompt = payload.prompt
    question.instruction = payload.instruction
    question.explanation = payload.explanation
    question.difficulty = payload.difficulty
    question.points = payload.points
    question.sort_order = payload.order
    question.config = payload.config
    question.reference_type = payload.reference_type
    question.reference_id = payload.reference_id
    raw_options = payload.config.get("options")
    option_rows: list[Any] = raw_options if isinstance(raw_options, list) else []
    question.options = [str(option.get("text", "")) for option in option_rows if isinstance(option, dict)] or None
    correct_ids = set(map(str, payload.config.get("correct_option_ids", [])))
    qtype = canonical_type(payload.question_type).value
    if qtype in SPEAKING_TYPES:
        question.correct_answer = str(payload.config.get("expected_text") or payload.config.get("display_text") or "")
    elif is_writing_question_type(payload.question_type, payload.config):
        expected = payload.config.get("expected_answer") or payload.config.get("expected_answers") or payload.config.get("accepted_answers")
        question.correct_answer = ",".join(map(str, expected)) if isinstance(expected, list) else str(expected or "")
    else:
        question.correct_answer = ",".join(correct_ids) if correct_ids else ",".join(map(str, payload.config.get("accepted_answers", [])))


def _ensure_audio_reference(db: Session, config: dict[str, Any]) -> None:
    audio_asset_id = config.get("audio_asset_id")
    if audio_asset_id:
        try:
            asset_id = int(audio_asset_id)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="Invalid audio_asset_id") from exc
        if not db.get(AudioAsset, asset_id):
            raise HTTPException(status_code=422, detail="Audio asset not found")


def _upsert_import_audio_asset(db: Session, question: dict[str, Any]) -> int | None:
    audio_key = question.get("audio") or question.get("storage_key")
    if not audio_key:
        return int(question["audio_asset_id"]) if question.get("audio_asset_id") else None
    provider = str(question.get("provider", "tts"))
    mime_type = str(question.get("mime_type", "audio/mpeg"))
    duration = question.get("duration_seconds")
    duration_seconds = float(duration) if duration is not None else None
    validate_audio_asset_payload(str(audio_key), provider, mime_type, duration_seconds)
    asset = db.scalar(select(AudioAsset).where(AudioAsset.provider == provider, AudioAsset.storage_key == str(audio_key)))
    if asset is None:
        asset = AudioAsset(
            storage_key=str(audio_key),
            storage_provider=provider,
            provider=provider,
            duration_ms=round(duration_seconds * 1000) if duration_seconds is not None else None,
            format=mime_type.split("/")[-1],
            locale=str(question.get("language", "zh-CN")),
            mime_type=mime_type,
            duration_seconds=duration_seconds,
            language=str(question.get("language", "zh-CN")),
            transcript=question.get("transcript"),
            pinyin=question.get("pinyin"),
            translation=question.get("translation"),
            status="READY",
            asset_metadata={"source": "exercise_import"},
        )
        db.add(asset)
        db.flush()
    else:
        asset.transcript = question.get("transcript", asset.transcript)
        asset.pinyin = question.get("pinyin", asset.pinyin)
        asset.translation = question.get("translation", asset.translation)
        asset.status = "READY"
    return asset.id


def _exercise_to_out(exercise: Exercise) -> AdminExerciseOut:
    questions = sorted([question for question in exercise.questions if not question.is_archived], key=lambda item: item.sort_order)
    return AdminExerciseOut(
        id=exercise.id,
        exercise_set_id=exercise.exercise_set_id,
        lesson_id=exercise.lesson_id,
        slug=exercise.slug,
        title=exercise.title,
        exercise_type=exercise.exercise_type,
        skill=exercise.skill,
        order=exercise.sort_order,
        is_archived=exercise.is_archived,
        questions=[question_to_public(question, include_explanation=True) for question in questions],
    )


@admin_router.post("", response_model=AdminExerciseOut, status_code=status.HTTP_201_CREATED)
def create_exercise(
    payload: AdminExerciseIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    lesson = db.get(Lesson, payload.lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exercise_set = db.get(ExerciseSet, payload.exercise_set_id) if payload.exercise_set_id else _default_exercise_set(db, lesson)
    if exercise_set is None:
        raise HTTPException(status_code=404, detail="Exercise set not found")
    exercise = db.scalar(
        select(Exercise).where(Exercise.exercise_set_id == exercise_set.id, Exercise.slug == payload.slug)
    )
    if exercise:
        raise HTTPException(status_code=409, detail="Exercise slug already exists")
    exercise = Exercise(
        exercise_set_id=exercise_set.id,
        lesson_id=lesson.id,
        slug=payload.slug,
        title=payload.title,
        exercise_type=canonical_type(payload.exercise_type).value,
        skill=payload.skill,
        sort_order=payload.order,
        config=payload.config,
    )
    db.add(exercise)
    db.flush()
    for question_payload in payload.questions:
        question = Question(lesson_id=lesson.id, exercise_id=exercise.id)
        _apply_question_payload(db, question, question_payload, exercise)
        db.add(question)
    db.commit()
    db.refresh(exercise)
    return _exercise_to_out(exercise)


@admin_router.patch("/{exercise_id}", response_model=AdminExerciseOut)
def update_exercise(
    exercise_id: int,
    payload: AdminExerciseIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    exercise = db.scalar(select(Exercise).options(selectinload(Exercise.questions)).where(Exercise.id == exercise_id))
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    exercise.slug = payload.slug
    exercise.title = payload.title
    exercise.exercise_type = canonical_type(payload.exercise_type).value
    exercise.skill = payload.skill
    exercise.sort_order = payload.order
    exercise.config = payload.config
    existing = sorted(exercise.questions, key=lambda item: item.sort_order)
    for index, question_payload in enumerate(payload.questions):
        question = existing[index] if index < len(existing) else Question(lesson_id=payload.lesson_id, exercise_id=exercise.id)
        _apply_question_payload(db, question, question_payload, exercise)
        db.add(question)
    for question in existing[len(payload.questions) :]:
        question.is_archived = True
    db.commit()
    db.refresh(exercise)
    return _exercise_to_out(exercise)


@admin_router.post("/{exercise_id}/archive", response_model=AdminExerciseOut)
def archive_exercise(
    exercise_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    exercise = db.scalar(select(Exercise).options(selectinload(Exercise.questions)).where(Exercise.id == exercise_id))
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    exercise.is_archived = True
    for question in exercise.questions:
        question.is_archived = True
    db.commit()
    return _exercise_to_out(exercise)


@admin_router.get("/{exercise_id}/preview", response_model=AdminExerciseOut)
def preview_exercise(
    exercise_id: int,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    exercise = db.scalar(select(Exercise).options(selectinload(Exercise.questions)).where(Exercise.id == exercise_id))
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return _exercise_to_out(exercise)


@admin_router.post("/import", response_model=ExerciseImportOut, status_code=status.HTTP_201_CREATED)
def import_exercise(
    payload: ExerciseImportIn,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExerciseImportOut:
    raw = payload.exercise if isinstance(payload.exercise, dict) else payload.exercise.model_dump()
    lesson_id = payload.lesson_id or raw.get("lesson_id")
    if lesson_id is None and payload.lesson:
        lesson = db.scalar(select(Lesson).where(Lesson.title == payload.lesson))
        lesson_id = lesson.id if lesson else None
    if lesson_id is None:
        raise HTTPException(status_code=400, detail="lesson_id or resolvable lesson is required")
    raw["lesson_id"] = lesson_id
    if "slug" not in raw:
        raw["slug"] = raw.get("title", "imported-exercise").lower().replace(" ", "-")
    if "exercise_type" not in raw:
        raw["exercise_type"] = raw.get("type", "MULTIPLE_CHOICE")
    questions = []
    for index, question in enumerate(raw.get("questions", []), start=1):
        qtype = question.get("question_type") or question.get("type") or raw["exercise_type"]
        audio_asset_id = _upsert_import_audio_asset(db, question)
        config = question.get("config")
        if config is None:
            config = {
                "options": question.get("options", []),
                "correct_option_ids": question.get("correct_option_ids", []),
            }
            if question.get("accepted_answers"):
                config = {"accepted_answers": question["accepted_answers"]}
            if canonical_type(str(qtype)).value in WRITING_TYPES:
                config = _writing_import_config(question, canonical_type(str(qtype)).value)
            if canonical_type(str(qtype)).value == "FILL_BLANK" and question.get("writing"):
                config = {"writing": True, "accepted_answers": question.get("accepted_answers") or question.get("expected_answers") or []}
            if canonical_type(str(qtype)).value == "LISTENING":
                answer_type = question.get("answer_type")
                if not answer_type:
                    if question.get("correct_order"):
                        answer_type = "ORDERING"
                    elif question.get("accepted_answers"):
                        answer_type = "TEXT_INPUT"
                    else:
                        answer_type = "MULTIPLE_CHOICE"
                config = {
                    **config,
                    "audio_asset_id": audio_asset_id,
                    "answer_type": canonical_type(str(answer_type)).value,
                    "replay_limit": question.get("replay_limit"),
                    "allow_seek": question.get("allow_seek", False),
                    "auto_play": question.get("auto_play", False),
                    "show_transcript_after_submit": question.get("show_transcript_after_submit", True),
                    "transcript": question.get("transcript"),
                    "pinyin": question.get("pinyin"),
                    "translation": question.get("translation"),
                }
                if question.get("items"):
                    config["items"] = question["items"]
                    config["correct_order"] = question.get("correct_order", [])
            if canonical_type(str(qtype)).value in SPEAKING_TYPES:
                config = {
                    "expected_text": question.get("expected_text") or question.get("text") or question.get("prompt"),
                    "display_text": question.get("display_text") or question.get("expected_text") or question.get("text"),
                    "pinyin": question.get("pinyin"),
                    "translation": question.get("translation"),
                    "audio_asset_id": audio_asset_id,
                    "pronunciation_mode": str(question.get("pronunciation_mode", "READ_ALOUD")).upper(),
                    "scoring_mode": str(question.get("scoring_mode", "PRONUNCIATION")).upper(),
                    "minimum_acceptable_score": question.get("minimum_acceptable_score", 70),
                    "reference_type": question.get("reference_type"),
                    "reference_id": question.get("reference_id"),
                    "metadata": question.get("metadata", {}),
                }
        questions.append(
            {
                "prompt": question.get("prompt") or question.get("expected_text") or "",
                "question_type": qtype,
                "instruction": question.get("instruction"),
                "explanation": question.get("explanation"),
                "difficulty": question.get("difficulty", 1),
                "points": question.get("points", 1),
                "order": question.get("order", index),
                "config": config,
                "reference_type": question.get("reference_type"),
                "reference_id": question.get("reference_id"),
            }
        )
    raw["questions"] = questions
    admin_payload = AdminExerciseIn.model_validate(raw)
    lesson = db.get(Lesson, admin_payload.lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exercise_set = _default_exercise_set(db, lesson)
    exercise = db.scalar(select(Exercise).where(Exercise.exercise_set_id == exercise_set.id, Exercise.slug == admin_payload.slug))
    if exercise and not payload.upsert:
        raise HTTPException(status_code=409, detail="Exercise already exists")
    if exercise is None:
        exercise = Exercise(
            exercise_set_id=exercise_set.id,
            lesson_id=lesson.id,
            slug=admin_payload.slug,
            title=admin_payload.title,
            exercise_type=canonical_type(admin_payload.exercise_type).value,
            skill=admin_payload.skill,
            sort_order=admin_payload.order,
            config=admin_payload.config,
        )
        db.add(exercise)
        db.flush()
    else:
        exercise.title = admin_payload.title
        exercise.exercise_type = canonical_type(admin_payload.exercise_type).value
        exercise.skill = admin_payload.skill
        exercise.sort_order = admin_payload.order
        exercise.config = admin_payload.config
    for question in exercise.questions:
        question.is_archived = True
    for question_payload in admin_payload.questions:
        question = Question(lesson_id=lesson.id, exercise_id=exercise.id)
        _apply_question_payload(db, question, question_payload, exercise)
        db.add(question)
    db.commit()
    return ExerciseImportOut(imported=True, exercise_id=exercise.id, question_count=len(admin_payload.questions), warnings=[])


def _writing_import_config(question: dict[str, Any], qtype: str) -> dict[str, Any]:
    if qtype in {"WORD_ORDER", "SENTENCE_REORDER"}:
        raw_items = question.get("items") or question.get("tokens") or question.get("word_bank") or question.get("options") or []
        items = [
            item if isinstance(item, dict) else {"id": str(index), "text": str(item)}
            for index, item in enumerate(raw_items, start=1)
        ]
        config: dict[str, Any] = {"items": items}
        if question.get("correct_order"):
            config["correct_order"] = question["correct_order"]
        if question.get("expected_answer"):
            config["expected_answer"] = question["expected_answer"]
        if question.get("expected_answers"):
            config["expected_answers"] = question["expected_answers"]
        if question.get("accepted_answers"):
            config["accepted_answers"] = question["accepted_answers"]
        return config
    if qtype == "TRANSLATION_TO_CHINESE":
        return {
            "accepted_answers": question.get("accepted_answers") or question.get("expected_answers") or [],
            "expected_answers": question.get("expected_answers") or question.get("accepted_answers") or [],
            "required_keywords": question.get("required_keywords", []),
            "keyword_tolerance": question.get("keyword_tolerance", 1.0),
            "accept_keyword_match": question.get("accept_keyword_match", False),
            "placeholder": question.get("placeholder", ""),
        }
    return {
        "required_vocabulary": question.get("required_vocabulary", []),
        "required_grammar": question.get("required_grammar", []),
        "required_keywords": question.get("required_keywords", []),
        "expected_concepts": question.get("expected_concepts", []),
        "min_characters": question.get("min_characters", 0),
        "max_characters": question.get("max_characters", 0),
        "min_chinese_ratio": question.get("min_chinese_ratio", 0.6),
        "passing_score": question.get("passing_score", 60),
        "rubric": question.get("rubric", {}),
        "placeholder": question.get("placeholder", ""),
    }
