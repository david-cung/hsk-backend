from datetime import UTC, datetime, timedelta

from app.models import (
    AnswerAttempt,
    HskLevel,
    Lesson,
    LessonProgress,
    PracticeSession,
    Profile,
    Question,
    SpeakingAttempt,
    User,
)
from app.progress_service import (
    daily_activity,
    hsk_progress,
    streak_from_activity,
    summary,
)
from app.schemas import DailyActivityOut


def _seed_progress_data(db):
    user = User(email="phase8@example.com", password_hash="x")
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id, current_hsk_level=1, target_hsk_level=1, daily_goal_minutes=5))
    level = HskLevel(level_number=1, title="HSK 1", total_characters=10)
    db.add(level)
    db.flush()
    lesson = Lesson(
        hsk_level_id=level.id,
        title="Lesson 1",
        lesson_type="listening",
        sort_order=1,
        duration_minutes=10,
        content={
            "vocabulary": [{"hanzi": "你"}, {"hanzi": "好"}],
            "grammar_points": [{"title": "A 是 B"}],
        },
    )
    db.add(lesson)
    db.flush()
    question = Question(
        lesson_id=lesson.id,
        question_type="LISTENING",
        prompt="听",
        correct_answer="a",
        reference_type="LISTENING",
        config={
            "audio_asset_id": 1,
            "answer_type": "TEXT_INPUT",
            "accepted_answers": ["a"],
        },
    )
    speaking_question = Question(
        lesson_id=lesson.id,
        question_type="PRONUNCIATION",
        prompt="说",
        correct_answer="你好",
        reference_type="VOCABULARY",
        config={"expected_text": "你好", "pronunciation_mode": "READ_ALOUD"},
    )
    db.add_all([question, speaking_question])
    db.flush()
    now = datetime.now(UTC)
    session = PracticeSession(
        user_id=user.id,
        lesson_id=lesson.id,
        status="COMPLETED",
        question_ids=[question.id, speaking_question.id],
        total_questions=2,
        answered_questions=2,
        correct_answers=1,
        score=50,
        time_spent_seconds=600,
        started_at=now,
        completed_at=now,
    )
    db.add(session)
    db.flush()
    for index in range(5):
        db.add(
            AnswerAttempt(
                user_id=user.id,
                practice_session_id=session.id,
                question_id=question.id,
                submitted_answer={"value": "a" if index < 2 else "b"},
                normalized_answer={"value": "a" if index < 2 else "b"},
                is_correct=index < 2,
                score=1 if index < 2 else 0,
                time_spent_seconds=30,
                idempotency_key=f"k-{index}",
                attempted_at=now - timedelta(minutes=index),
            )
        )
    speech_answer = AnswerAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=speaking_question.id,
        submitted_answer={"value": {"recording_id": 1}},
        normalized_answer={"processing_status": "COMPLETED"},
        is_correct=True,
        score=1,
        time_spent_seconds=45,
        idempotency_key="speaking",
        attempted_at=now,
    )
    db.add(speech_answer)
    db.flush()
    db.add(
        SpeakingAttempt(
            user_id=user.id,
            practice_session_id=session.id,
            question_id=speaking_question.id,
            answer_attempt_id=speech_answer.id,
            recording_id=1,
            provider="mock",
            pronunciation_score=82,
            accuracy_score=82,
            fluency_score=82,
            completeness_score=82,
            processing_status="COMPLETED",
            created_at=now,
            completed_at=now,
        )
    )
    db.add(LessonProgress(user_id=user.id, lesson_id=lesson.id, status="completed", score_percent=80, minutes_studied=10))
    db.commit()
    db.refresh(user)
    return user, level, lesson


def test_summary_empty_user_has_no_fake_skill_scores(db_session) -> None:
    user = User(email="empty-progress@example.com", password_hash="x")
    db_session.add(user)
    db_session.flush()
    db_session.add(Profile(user_id=user.id, current_hsk_level=1, target_hsk_level=1))
    db_session.add(HskLevel(level_number=1, title="HSK 1", total_characters=10))
    db_session.commit()
    db_session.refresh(user)

    payload = summary(db_session, user)

    assert payload.today_questions == 0
    assert payload.today_accuracy is None
    assert payload.skill_overview == []
    assert payload.weak_skills == []


def test_summary_detects_weak_listening_and_recommends_practice(db_session) -> None:
    user, _level, _lesson = _seed_progress_data(db_session)

    payload = summary(db_session, user)

    listening = next(item for item in payload.skill_overview if item.skill == "LISTENING")
    assert listening.accuracy == 40
    assert payload.weak_skills[0].skill == "LISTENING"
    assert payload.recommended_practice[0].type == "LISTENING_PRACTICE"


def test_hsk_progress_calculates_content_and_speaking_metrics(db_session) -> None:
    user, _level, _lesson = _seed_progress_data(db_session)

    payload = hsk_progress(db_session, user, 1)

    assert payload.vocabulary.total == 2
    assert payload.vocabulary.completed == 2
    assert payload.grammar.total == 1
    assert payload.lessons.percent == 100
    assert payload.speaking is not None
    assert payload.speaking.average_score == 82


def test_daily_activity_aggregates_without_raw_history(db_session) -> None:
    user, _level, _lesson = _seed_progress_data(db_session)
    today = datetime.now(UTC).date()

    rows = daily_activity(db_session, user.id, today, today)

    assert len(rows) == 1
    assert rows[0].study_minutes == 10
    assert rows[0].questions == 6
    assert rows[0].correct == 3
    assert rows[0].listening_practiced == 5
    assert rows[0].speaking_practiced == 1


def test_streak_uses_configured_activity_days() -> None:
    today = datetime.now(UTC).date()
    activity = [
        DailyActivityOut(date=(today - timedelta(days=2)).isoformat(), study_minutes=5),
        DailyActivityOut(date=(today - timedelta(days=1)).isoformat(), study_minutes=5),
        DailyActivityOut(date=today.isoformat(), study_minutes=5),
    ]

    current, longest, last_active = streak_from_activity(activity, today)

    assert current == 3
    assert longest == 3
    assert last_active == today.isoformat()
