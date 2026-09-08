from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth import get_current_user, require_admin
from app.database import get_db
from app.gamification_service import record_event
from app.models import (
    ContentStatus,
    Exercise,
    ExerciseSet,
    ExerciseType,
    GrammarPoint,
    Lesson,
    LessonProgress,
    PracticeSession,
    PracticeSessionStatus,
    Question,
    QuestionAttempt,
    QuestionVersion,
    User,
    Vocabulary,
)
from app.practice_engine import (
    ChoiceConfiguration,
    MatchingConfiguration,
    MultipleSelectConfiguration,
    OrderingConfiguration,
    TextConfiguration,
    canonical_exercise_type,
    evaluate_answer,
    public_question_configuration,
    update_content_progress,
    validate_question_configuration,
)
from app.question_service import create_version, current_version_for_id, ensure_current_version
from app.schemas import (
    AdminExerciseOut,
    AdminQuestionOut,
    ExerciseCreate,
    ExerciseSetSummaryOut,
    ExerciseSummaryOut,
    ExerciseUpdate,
    LessonPracticeOut,
    PracticeAnswerIn,
    PracticeAnswerOut,
    PracticeQuestionOut,
    PracticeResultsOut,
    PracticeReviewItemOut,
    PracticeSessionCreate,
    PracticeSessionOut,
    QuestionCreate,
    QuestionReorderIn,
    QuestionUpdate,
)

router = APIRouter(prefix="/api/v1")


def _value(value: Any) -> str:
    return str(getattr(value, "value", value))


def _question_metadata(question: Question | QuestionVersion, key: str) -> dict[str, str] | None:
    value = (question.metadata_json or {}).get(key)
    if not isinstance(value, dict):
        return None
    return {
        str(locale): str(text)
        for locale, text in value.items()
        if text is not None and str(text).strip()
    } or None


def _practice_question(
    question: Question, version: QuestionVersion | None = None
) -> PracticeQuestionOut:
    if question.exercise_id is None:
        raise HTTPException(
            status_code=500, detail=f"Question {question.id} is not normalized"
        )
    content = version or question
    return PracticeQuestionOut(
        id=question.id,
        question_version_id=getattr(content, "id", None) if version is not None else question.current_version_id,
        exercise_id=question.exercise_id,
        question_type=content.question_type,
        prompt=content.prompt,
        prompt_translations=_question_metadata(content, "prompt_translations"),
        instruction=content.instruction,
        explanation_available=bool(content.explanation),
        difficulty=content.difficulty,
        points=content.points,
        order=question.sort_order,
        configuration=public_question_configuration(
            content.question_type, content.configuration
        ),
    )


def _exercise_summary(exercise: Exercise) -> ExerciseSummaryOut:
    published_questions = [
        question
        for question in exercise.questions
        if question.status == ContentStatus.PUBLISHED
    ]
    return ExerciseSummaryOut(
        id=exercise.id,
        exercise_set_id=exercise.exercise_set_id,
        exercise_type=_value(exercise.exercise_type),
        title=exercise.title,
        instruction=exercise.instruction,
        skill=exercise.skill,
        vocabulary_id=exercise.vocabulary_id,
        grammar_point_id=exercise.grammar_point_id,
        difficulty=exercise.difficulty,
        order=exercise.sort_order,
        question_count=len(published_questions),
        status=_value(exercise.status),
    )


def _exercise_set_summary(exercise_set: ExerciseSet) -> ExerciseSetSummaryOut:
    exercises = [
        exercise
        for exercise in exercise_set.exercises
        if exercise.status == ContentStatus.PUBLISHED
    ]
    summaries = [_exercise_summary(exercise) for exercise in exercises]
    return ExerciseSetSummaryOut(
        id=exercise_set.id,
        lesson_id=exercise_set.lesson_id,
        title=exercise_set.title,
        description=exercise_set.description,
        skill=exercise_set.skill,
        difficulty=exercise_set.difficulty,
        question_count=sum(item.question_count for item in summaries),
        exercises=summaries,
    )


def _exercise_set_options() -> tuple[Any, ...]:
    return (
        selectinload(ExerciseSet.exercises).selectinload(Exercise.questions),
    )


@router.get(
    "/practice/lessons/{lesson_id}",
    response_model=LessonPracticeOut,
)
def lesson_practice(
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LessonPracticeOut:
    del user
    lesson = db.get(Lesson, lesson_id)
    if not lesson or lesson.content_status != ContentStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Lesson not found")
    exercise_sets = db.scalars(
        select(ExerciseSet)
        .where(
            ExerciseSet.lesson_id == lesson_id,
            ExerciseSet.status == ContentStatus.PUBLISHED,
        )
        .options(*_exercise_set_options())
        .order_by(ExerciseSet.sort_order, ExerciseSet.id)
    ).unique().all()
    summaries = [_exercise_set_summary(item) for item in exercise_sets]
    summaries = [item for item in summaries if item.question_count]
    return LessonPracticeOut(
        lesson_id=lesson.id,
        lesson_title=lesson.title,
        exercise_sets=summaries,
        total_questions=sum(item.question_count for item in summaries),
    )


def _selected_questions(
    exercise_set: ExerciseSet, payload: PracticeSessionCreate
) -> list[Question]:
    questions: list[Question] = []
    for exercise in exercise_set.exercises:
        if exercise.status != ContentStatus.PUBLISHED:
            continue
        if payload.skill and exercise.skill != payload.skill:
            continue
        if payload.difficulty and exercise.difficulty not in {
            None,
            payload.difficulty,
        }:
            continue
        for question in exercise.questions:
            if question.status != ContentStatus.PUBLISHED:
                continue
            if payload.difficulty and question.difficulty not in {
                None,
                payload.difficulty,
            }:
                continue
            questions.append(question)
    questions.sort(
        key=lambda question: (
            question.exercise.sort_order if question.exercise else 0,
            question.sort_order,
            question.id,
        )
    )
    if payload.question_count is not None:
        questions = questions[: payload.question_count]
    return questions


def _session_questions(db: Session, session: PracticeSession) -> list[Question]:
    if not session.question_ids:
        return []
    rows = db.scalars(
        select(Question)
        .where(Question.id.in_(session.question_ids))
        .options(joinedload(Question.exercise))
    ).unique().all()
    by_id = {question.id: question for question in rows}
    return [by_id[item_id] for item_id in session.question_ids if item_id in by_id]


def _session_question_versions(
    db: Session, session: PracticeSession, questions: list[Question]
) -> dict[int, QuestionVersion]:
    version_ids = [int(item) for item in session.question_version_ids or []]
    versions = db.scalars(
        select(QuestionVersion).where(QuestionVersion.id.in_(version_ids or [0]))
    ).all()
    by_version_id = {version.id: version for version in versions}
    result: dict[int, QuestionVersion] = {}
    for index, question in enumerate(questions):
        version_id = version_ids[index] if index < len(version_ids) else None
        version = by_version_id.get(version_id) if version_id is not None else None
        if version is None:
            version = ensure_current_version(db, question)
        result[question.id] = version
    return result


def _session_out(db: Session, session: PracticeSession) -> PracticeSessionOut:
    answered_question_ids = list(_latest_attempts(db, session.id))
    questions = _session_questions(db, session)
    versions = _session_question_versions(db, session, questions)
    return PracticeSessionOut(
        id=session.id,
        lesson_id=session.lesson_id,
        exercise_set_id=session.exercise_set_id,
        status=_value(session.status),
        questions=[
            _practice_question(question, versions.get(question.id))
            for question in questions
        ],
        total_questions=session.total_questions,
        answered_questions=session.answered_questions,
        answered_question_ids=answered_question_ids,
        correct_answers=session.correct_answers,
        score=session.score,
        time_spent_seconds=session.time_spent_seconds,
        started_at=session.started_at,
        completed_at=session.completed_at,
    )


@router.post(
    "/practice/sessions",
    response_model=PracticeSessionOut,
    status_code=status.HTTP_201_CREATED,
)
def create_practice_session(
    payload: PracticeSessionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionOut:
    lesson = db.get(Lesson, payload.lesson_id)
    if not lesson or lesson.content_status != ContentStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Lesson not found")
    stmt = (
        select(ExerciseSet)
        .where(
            ExerciseSet.lesson_id == lesson.id,
            ExerciseSet.status == ContentStatus.PUBLISHED,
        )
        .options(*_exercise_set_options())
        .order_by(ExerciseSet.sort_order, ExerciseSet.id)
    )
    if payload.exercise_set_id is not None:
        stmt = stmt.where(ExerciseSet.id == payload.exercise_set_id)
    exercise_set = db.scalars(stmt).unique().first()
    if exercise_set is None:
        raise HTTPException(status_code=404, detail="Exercise set not found")

    selection_config = {
        "question_count": payload.question_count,
        "difficulty": payload.difficulty,
        "skill": payload.skill,
    }
    if payload.resume:
        candidates = db.scalars(
            select(PracticeSession)
            .where(
                PracticeSession.user_id == user.id,
                PracticeSession.lesson_id == lesson.id,
                PracticeSession.exercise_set_id == exercise_set.id,
                PracticeSession.status == PracticeSessionStatus.IN_PROGRESS,
            )
            .order_by(PracticeSession.last_activity_at.desc())
        ).all()
        resumed = next(
            (
                candidate
                for candidate in candidates
                if (candidate.selection_config or {}) == selection_config
            ),
            None,
        )
        if resumed is not None:
            return _session_out(db, resumed)

    questions = _selected_questions(exercise_set, payload)
    if not questions:
        raise HTTPException(
            status_code=409,
            detail="No published questions match the requested practice filters",
        )
    versions = [ensure_current_version(db, question) for question in questions]
    session = PracticeSession(
        user_id=user.id,
        lesson_id=lesson.id,
        exercise_set_id=exercise_set.id,
        status=PracticeSessionStatus.IN_PROGRESS,
        question_ids=[question.id for question in questions],
        question_version_ids=[version.id for version in versions],
        selection_config=selection_config,
        total_questions=len(questions),
        answered_questions=0,
        correct_answers=0,
        score=0,
        time_spent_seconds=0,
        last_activity_at=datetime.now(UTC),
    )
    db.add(session)
    db.commit()
    db.refresh(session)
    return _session_out(db, session)


def _owned_session(db: Session, session_id: int, user: User) -> PracticeSession:
    session = db.get(PracticeSession, session_id)
    if session is None or session.user_id != user.id:
        raise HTTPException(status_code=404, detail="Practice session not found")
    return session


@router.get(
    "/practice/sessions/{session_id}",
    response_model=PracticeSessionOut,
)
def get_practice_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeSessionOut:
    return _session_out(db, _owned_session(db, session_id, user))


def _latest_attempts(
    db: Session, session_id: int
) -> dict[int, QuestionAttempt]:
    attempts = db.scalars(
        select(QuestionAttempt)
        .where(QuestionAttempt.practice_session_id == session_id)
        .order_by(QuestionAttempt.attempted_at, QuestionAttempt.id)
    ).all()
    latest: dict[int, QuestionAttempt] = {}
    for attempt in attempts:
        latest[attempt.question_id] = attempt
    return latest


def _update_session_statistics(
    db: Session, session: PracticeSession
) -> dict[int, QuestionAttempt]:
    latest = _latest_attempts(db, session.id)
    session.answered_questions = len(latest)
    session.correct_answers = sum(
        int(attempt.is_correct) for attempt in latest.values()
    )
    earned = sum(attempt.score for attempt in latest.values())
    available = sum(attempt.max_score for attempt in latest.values())
    session.score = round((earned / available) * 100) if available else 0
    session.last_activity_at = datetime.now(UTC)
    return latest


def _answer_out(
    attempt: QuestionAttempt, session: PracticeSession
) -> PracticeAnswerOut:
    snapshot = attempt.result_snapshot
    return PracticeAnswerOut(
        attempt_id=attempt.id,
        question_id=attempt.question_id,
        correct=attempt.is_correct,
        score=attempt.score,
        max_score=attempt.max_score,
        submitted_answer=attempt.submitted_answer,
        normalized_answer=attempt.normalized_answer,
        correct_answer=snapshot["correct_answer"],
        explanation=snapshot.get("explanation"),
        explanation_translations=snapshot.get("explanation_translations"),
        answered_questions=session.answered_questions,
        correct_answers=session.correct_answers,
        session_score=session.score,
    )


@router.post(
    "/practice/sessions/{session_id}/answers",
    response_model=PracticeAnswerOut,
)
def submit_practice_answer(
    session_id: int,
    payload: PracticeAnswerIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeAnswerOut:
    session = _owned_session(db, session_id, user)
    if session.status != PracticeSessionStatus.IN_PROGRESS:
        raise HTTPException(status_code=409, detail="Practice session is not active")

    previous = db.scalar(
        select(QuestionAttempt).where(
            QuestionAttempt.practice_session_id == session.id,
            QuestionAttempt.idempotency_key == payload.idempotency_key,
        )
    )
    if previous is not None:
        if previous.question_id != payload.question_id:
            raise HTTPException(
                status_code=409,
                detail="Idempotency key was already used for another question",
            )
        _update_session_statistics(db, session)
        return _answer_out(previous, session)

    if payload.question_id not in session.question_ids:
        raise HTTPException(
            status_code=400, detail="Question does not belong to this session"
        )
    question = db.scalar(
        select(Question)
        .where(Question.id == payload.question_id)
        .options(joinedload(Question.exercise))
    )
    if question is None or question.exercise is None:
        raise HTTPException(status_code=404, detail="Question not found")
    version_ids = [int(item) for item in session.question_version_ids or []]
    try:
        version_index = session.question_ids.index(question.id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Question does not belong to this session") from None
    version_id = version_ids[version_index] if version_index < len(version_ids) else None
    version = current_version_for_id(db, question.id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail="Question version not found")
    try:
        result = evaluate_answer(version, payload.answer)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    snapshot = {
        "question_version_id": version.id,
        "prompt": version.prompt,
        "prompt_translations": _question_metadata(
            version, "prompt_translations"
        ),
        "correct_answer": result.correct_answer,
        "explanation": version.explanation,
        "explanation_translations": _question_metadata(
            version, "explanation_translations"
        ),
    }
    attempt = QuestionAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=question.id,
        question_version_id=version.id,
        idempotency_key=payload.idempotency_key,
        submitted_answer=payload.answer,
        normalized_answer=result.normalized_answer,
        is_correct=result.is_correct,
        score=result.score,
        max_score=result.max_score,
        time_spent_seconds=payload.time_spent_seconds,
        result_snapshot=snapshot,
    )
    db.add(attempt)
    db.flush()
    update_content_progress(db, attempt, question.exercise)
    session.time_spent_seconds += payload.time_spent_seconds
    _update_session_statistics(db, session)
    db.commit()
    db.refresh(attempt)
    return _answer_out(attempt, session)


@router.post(
    "/practice/sessions/{session_id}/complete",
    response_model=PracticeResultsOut,
)
def complete_practice_session(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeResultsOut:
    session = _owned_session(db, session_id, user)
    if session.status == PracticeSessionStatus.ABANDONED:
        raise HTTPException(status_code=409, detail="Practice session was abandoned")
    _update_session_statistics(db, session)
    if session.status != PracticeSessionStatus.COMPLETED:
        now = datetime.now(UTC)
        session.status = PracticeSessionStatus.COMPLETED
        session.completed_at = now
        session.last_activity_at = now
        progress = db.scalar(
            select(LessonProgress).where(
                LessonProgress.user_id == user.id,
                LessonProgress.lesson_id == session.lesson_id,
            )
        )
        if progress is None:
            progress = LessonProgress(
                user_id=user.id,
                lesson_id=session.lesson_id,
                status="in_progress",
                minutes_studied=0,
            )
            db.add(progress)
        progress.started_at = progress.started_at or session.started_at
        progress.last_viewed_at = now
        progress.score_percent = session.score
        progress.minutes_studied = max(
            progress.minutes_studied,
            round(session.time_spent_seconds / 60),
        )
        if session.score >= 60 and session.answered_questions:
            progress.status = "completed"
            progress.completed_at = now
        _emit_practice_events(db, user, session)
        db.commit()
    return _results_out(db, session)


SKILL_EVENTS = {
    "WRITING": "WRITING_COMPLETED",
    "LISTENING": "LISTENING_COMPLETED",
    "SPEAKING": "SPEAKING_COMPLETED",
}


def _emit_practice_events(db: Session, user: User, session: PracticeSession) -> None:
    minutes = max(round(session.time_spent_seconds / 60), 0)
    perfect = bool(session.answered_questions and session.score == 100)
    record_event(
        db,
        user,
        "PRACTICE_COMPLETED",
        f"practice:{session.id}",
        minutes=minutes,
        exercises=session.answered_questions,
        metadata={"perfect": perfect, "score": session.score},
    )
    skill = str((session.selection_config or {}).get("skill") or "").upper()
    skill_event = SKILL_EVENTS.get(skill)
    if skill_event:
        record_event(db, user, skill_event, f"practice-skill:{session.id}")
    if session.score >= 60 and session.answered_questions:
        record_event(
            db,
            user,
            "LESSON_COMPLETED",
            f"lesson:{session.lesson_id}",
            lessons=1,
        )


def _results_out(db: Session, session: PracticeSession) -> PracticeResultsOut:
    latest = _latest_attempts(db, session.id)
    review: list[PracticeReviewItemOut] = []
    for question_id in session.question_ids:
        attempt = latest.get(question_id)
        if attempt is None:
            continue
        snapshot = attempt.result_snapshot
        review.append(
            PracticeReviewItemOut(
                question_id=question_id,
                prompt=str(snapshot.get("prompt") or ""),
                prompt_translations=snapshot.get("prompt_translations"),
                submitted_answer=attempt.submitted_answer,
                correct_answer=snapshot.get("correct_answer"),
                correct=attempt.is_correct,
                score=attempt.score,
                max_score=attempt.max_score,
                explanation=snapshot.get("explanation"),
                explanation_translations=snapshot.get(
                    "explanation_translations"
                ),
            )
        )
    accuracy = (
        round((session.correct_answers / session.answered_questions) * 100)
        if session.answered_questions
        else 0
    )
    return PracticeResultsOut(
        session_id=session.id,
        status=_value(session.status),
        total_questions=session.total_questions,
        answered_questions=session.answered_questions,
        correct_answers=session.correct_answers,
        incorrect_answers=session.answered_questions - session.correct_answers,
        score=session.score,
        accuracy=accuracy,
        time_spent_seconds=session.time_spent_seconds,
        review=review,
    )


@router.get(
    "/practice/sessions/{session_id}/results",
    response_model=PracticeResultsOut,
)
def practice_session_results(
    session_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PracticeResultsOut:
    session = _owned_session(db, session_id, user)
    if session.status != PracticeSessionStatus.COMPLETED:
        raise HTTPException(
            status_code=409, detail="Complete the practice session before viewing results"
        )
    return _results_out(db, session)


def _admin_question(
    question: Question, version: QuestionVersion | None = None
) -> AdminQuestionOut:
    content = version or question
    return AdminQuestionOut(
        id=question.id,
        question_version_id=getattr(content, "id", None) if version is not None else question.current_version_id,
        version_number=getattr(content, "version_number", None),
        exercise_id=question.exercise_id,
        lesson_id=question.lesson_id,
        external_id=question.external_id,
        question_type=content.question_type,
        prompt=content.prompt,
        instruction=content.instruction,
        explanation=content.explanation,
        difficulty=content.difficulty,
        points=content.points,
        order=question.sort_order,
        configuration=content.configuration,
        status=_value(content.status),
        metadata=content.metadata_json,
    )


def _admin_exercise(exercise: Exercise) -> AdminExerciseOut:
    return AdminExerciseOut(
        **_exercise_summary(exercise).model_dump(),
        external_id=exercise.external_id,
        metadata=exercise.metadata_json,
        questions=[_admin_question(question) for question in exercise.questions],
    )


def _legacy_answer_fields(
    question_type: str, configuration: dict[str, Any]
) -> tuple[list[str] | None, str]:
    validated = validate_question_configuration(question_type, configuration)
    if isinstance(validated, ChoiceConfiguration):
        options = [option.text for option in validated.options]
        correct_id = validated.correct_option_ids[0]
        correct = next(
            option.text for option in validated.options if option.id == correct_id
        )
        return options, correct
    if isinstance(validated, MultipleSelectConfiguration):
        return (
            [option.text for option in validated.options],
            "|".join(validated.correct_option_ids),
        )
    if isinstance(validated, TextConfiguration):
        return None, validated.accepted_answers[0]
    if isinstance(validated, MatchingConfiguration):
        return None, "|".join(
            f"{left}:{right}" for left, right in validated.correct_pairs.items()
        )
    if isinstance(validated, OrderingConfiguration):
        by_id = {item.id: item.text for item in validated.items}
        return [item.text for item in validated.items], " ".join(
            by_id[item_id] for item_id in validated.correct_order
        )
    raise ValueError("unsupported question configuration")


def _validate_content_references(
    db: Session,
    *,
    vocabulary_id: int | None,
    grammar_point_id: int | None,
) -> None:
    if vocabulary_id is not None and db.get(Vocabulary, vocabulary_id) is None:
        raise HTTPException(status_code=422, detail="Vocabulary not found")
    if grammar_point_id is not None and db.get(GrammarPoint, grammar_point_id) is None:
        raise HTTPException(status_code=422, detail="Grammar point not found")


@router.post(
    "/admin/exercises",
    response_model=AdminExerciseOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_exercise(
    payload: ExerciseCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    del admin
    lesson = db.get(Lesson, payload.lesson_id)
    if lesson is None:
        raise HTTPException(status_code=422, detail="Lesson not found")
    _validate_content_references(
        db,
        vocabulary_id=payload.vocabulary_id,
        grammar_point_id=payload.grammar_point_id,
    )
    exercise_set = (
        db.get(ExerciseSet, payload.exercise_set_id)
        if payload.exercise_set_id is not None
        else None
    )
    if exercise_set is not None and exercise_set.lesson_id != lesson.id:
        raise HTTPException(
            status_code=422, detail="Exercise set belongs to another lesson"
        )
    if exercise_set is None and payload.exercise_set_id is not None:
        raise HTTPException(status_code=422, detail="Exercise set not found")
    if exercise_set is None:
        exercise_set = db.scalar(
            select(ExerciseSet).where(
                ExerciseSet.lesson_id == lesson.id,
                ExerciseSet.slug == "admin-practice",
            )
        )
    if exercise_set is None:
        next_set_order = (
            db.scalar(
                select(func.max(ExerciseSet.sort_order)).where(
                    ExerciseSet.lesson_id == lesson.id
                )
            )
            or 0
        ) + 1
        exercise_set = ExerciseSet(
            lesson_id=lesson.id,
            slug="admin-practice",
            title=payload.exercise_set_title or f"{lesson.title} Practice",
            skill=payload.skill,
            difficulty=payload.difficulty,
            sort_order=next_set_order,
            status=ContentStatus.PUBLISHED,
            metadata_json={"source": "admin"},
        )
        db.add(exercise_set)
        db.flush()
    exercise = Exercise(
        exercise_set_id=exercise_set.id,
        external_id=payload.external_id,
        exercise_type=ExerciseType(payload.exercise_type),
        title=payload.title,
        instruction=payload.instruction,
        skill=payload.skill,
        vocabulary_id=payload.vocabulary_id,
        grammar_point_id=payload.grammar_point_id,
        difficulty=payload.difficulty,
        sort_order=payload.order,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    db.add(exercise)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Exercise id or order conflicts in this set"
        ) from exc
    db.refresh(exercise)
    return _admin_exercise(exercise)


def _admin_exercise_row(db: Session, exercise_id: int) -> Exercise:
    exercise = db.scalar(
        select(Exercise)
        .where(Exercise.id == exercise_id)
        .options(selectinload(Exercise.questions))
    )
    if exercise is None:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return exercise


@router.get(
    "/admin/exercises/{exercise_id}",
    response_model=AdminExerciseOut,
)
def admin_get_exercise(
    exercise_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    del admin
    return _admin_exercise(_admin_exercise_row(db, exercise_id))


@router.get(
    "/admin/exercises/{exercise_id}/preview",
    response_model=list[PracticeQuestionOut],
)
def admin_preview_exercise(
    exercise_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[PracticeQuestionOut]:
    del admin
    exercise = _admin_exercise_row(db, exercise_id)
    return [_practice_question(question) for question in exercise.questions]


@router.patch(
    "/admin/exercises/{exercise_id}",
    response_model=AdminExerciseOut,
)
def admin_update_exercise(
    exercise_id: int,
    payload: ExerciseUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminExerciseOut:
    del admin
    exercise = _admin_exercise_row(db, exercise_id)
    updates = payload.model_dump(exclude_unset=True)
    _validate_content_references(
        db,
        vocabulary_id=updates.get("vocabulary_id"),
        grammar_point_id=updates.get("grammar_point_id"),
    )
    field_map = {
        "order": "sort_order",
        "metadata": "metadata_json",
    }
    for key, value in updates.items():
        target = field_map.get(key, key)
        if key == "exercise_type" and value is not None:
            value = ExerciseType(value)
        setattr(exercise, target, value)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Exercise order conflicts in this set"
        ) from exc
    return _admin_exercise(_admin_exercise_row(db, exercise_id))


@router.delete(
    "/admin/exercises/{exercise_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_archive_exercise(
    exercise_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    del admin
    exercise = _admin_exercise_row(db, exercise_id)
    exercise.status = ContentStatus.ARCHIVED
    for question in exercise.questions:
        question.status = ContentStatus.ARCHIVED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/exercises/{exercise_id}/questions",
    response_model=AdminQuestionOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_question(
    exercise_id: int,
    payload: QuestionCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminQuestionOut:
    del admin
    exercise = _admin_exercise_row(db, exercise_id)
    options, correct_answer = _legacy_answer_fields(
        payload.question_type, payload.configuration
    )
    question = Question(
        lesson_id=exercise.exercise_set.lesson_id,
        exercise_id=exercise.id,
        external_id=payload.external_id,
        question_type=payload.question_type,
        prompt=payload.prompt.strip(),
        instruction=payload.instruction,
        options=options,
        correct_answer=correct_answer,
        explanation=payload.explanation,
        difficulty=payload.difficulty,
        points=payload.points,
        configuration=payload.configuration,
        sort_order=payload.order,
        status=payload.status,
        metadata_json=payload.metadata,
    )
    db.add(question)
    try:
        db.flush()
        version = create_version(db, question, status=payload.status)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Question order conflicts in this exercise"
        ) from exc
    db.refresh(question)
    return _admin_question(question, version)


def _question_row(db: Session, question_id: int) -> Question:
    question = db.get(Question, question_id)
    if question is None:
        raise HTTPException(status_code=404, detail="Question not found")
    return question


@router.patch(
    "/admin/questions/{question_id}",
    response_model=AdminQuestionOut,
)
def admin_update_question(
    question_id: int,
    payload: QuestionUpdate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AdminQuestionOut:
    del admin
    question = _question_row(db, question_id)
    updates = payload.model_dump(exclude_unset=True)
    question_type = updates.get("question_type", question.question_type)
    configuration = updates.get("configuration", question.configuration)
    try:
        question_type = canonical_exercise_type(question_type).value
        configuration = validate_question_configuration(
            question_type, configuration
        ).model_dump()
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    options, correct_answer = _legacy_answer_fields(
        question_type, configuration
    )
    field_map = {
        "order": "sort_order",
        "metadata": "metadata_json",
    }
    for key, value in updates.items():
        setattr(question, field_map.get(key, key), value)
    question.question_type = question_type
    question.configuration = configuration
    question.options = options
    question.correct_answer = correct_answer
    try:
        version = create_version(db, question, status=question.status)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Question order conflicts in this exercise"
        ) from exc
    db.refresh(question)
    return _admin_question(question, version)


@router.delete(
    "/admin/questions/{question_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_archive_question(
    question_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    del admin
    question = _question_row(db, question_id)
    question.status = ContentStatus.ARCHIVED
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/exercises/{exercise_id}/questions/reorder",
    response_model=list[AdminQuestionOut],
)
def admin_reorder_questions(
    exercise_id: int,
    payload: QuestionReorderIn,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> list[AdminQuestionOut]:
    del admin
    exercise = _admin_exercise_row(db, exercise_id)
    by_id = {question.id: question for question in exercise.questions}
    if set(payload.question_ids) != set(by_id):
        raise HTTPException(
            status_code=422,
            detail="Reorder must include every question in this exercise exactly once",
        )
    for offset, question in enumerate(exercise.questions, start=1):
        question.sort_order = -offset
    db.flush()
    for order, question_id in enumerate(payload.question_ids, start=1):
        by_id[question_id].sort_order = order
    db.commit()
    return [
        _admin_question(by_id[question_id])
        for question_id in payload.question_ids
    ]
