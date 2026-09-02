from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException

from app.exam_service import resume_attempt, save_answer, start_exam, submit_attempt
from app.models import ExamAttempt, HskLevel, Lesson, MockTest, Profile, Question, User


def _user(db_session, email: str = "exam@example.com") -> User:
    user = User(email=email, display_name="Exam", password_hash="hash")
    db_session.add(user)
    db_session.flush()
    profile = Profile(user_id=user.id, current_hsk_level=1, target_hsk_level=1)
    db_session.add(profile)
    db_session.flush()
    user.profile = profile
    return user


def _exam(db_session) -> MockTest:
    level = HskLevel(level_number=1, title="HSK 1", total_characters=150)
    db_session.add(level)
    db_session.flush()
    lesson = Lesson(hsk_level_id=level.id, title="Vocab", lesson_type="vocabulary", sort_order=1, content={})
    db_session.add(lesson)
    db_session.flush()
    for index, correct in enumerate(["1", "2"], start=1):
        db_session.add(
            Question(
                lesson_id=lesson.id,
                question_type="MULTIPLE_CHOICE",
                prompt=f"Question {index}",
                options=["A", "B"],
                correct_answer=correct,
                points=1,
                sort_order=index,
                config={
                    "options": [{"id": "1", "text": "A"}, {"id": "2", "text": "B"}],
                    "correct_option_ids": [correct],
                },
                reference_type="VOCABULARY",
                reference_id=f"词{index}",
            )
        )
    exam = MockTest(
        title="HSK 1 Mock",
        hsk_level=1,
        duration_minutes=30,
        question_count=2,
        status="PUBLISHED",
        exam_type="MOCK",
        version=1,
        blueprint={
            "randomized": False,
            "allow_previous_section": True,
            "sections": [{"type": "VOCABULARY", "title": "Vocabulary", "question_count": 2, "duration_minutes": 30}],
        },
        scoring_config={"score_label": "Estimated Practice Score", "passing_percentage": 60},
    )
    db_session.add(exam)
    db_session.flush()
    return exam


def test_start_exam_snapshots_questions_and_resume_is_stable(db_session) -> None:
    user = _user(db_session)
    exam = _exam(db_session)

    started = start_exam(db_session, user, exam.id)
    resumed = resume_attempt(db_session, user, started.attempt_id)

    assert started.status == "IN_PROGRESS"
    assert started.exam_version == 1
    assert started.expires_at > started.started_at
    assert [question.id for question in resumed.questions] == [question.id for question in started.questions]
    assert resumed.questions[0].config["options"][0]["id"] == "1"
    assert "correct_option_ids" not in resumed.questions[0].config


def test_autosave_and_submit_scores_sections(db_session) -> None:
    user = _user(db_session)
    exam = _exam(db_session)
    started = start_exam(db_session, user, exam.id)
    q1, q2 = [question.id for question in started.questions]

    save_answer(db_session, user, started.attempt_id, q1, "1")
    save_answer(db_session, user, started.attempt_id, q2, "1")
    result = submit_attempt(db_session, user, started.attempt_id)

    assert result.status == "SUBMITTED"
    assert result.raw_score == 1
    assert result.total_points == 2
    assert result.percentage == 50
    assert result.passed is False
    assert result.sections[0].correct == 1
    assert result.sections[0].incorrect == 1
    assert result.questions[0].correct_answer == "1"


def test_submit_is_idempotent(db_session) -> None:
    user = _user(db_session)
    exam = _exam(db_session)
    started = start_exam(db_session, user, exam.id)

    first = submit_attempt(db_session, user, started.attempt_id)
    second = submit_attempt(db_session, user, started.attempt_id)

    assert first.percentage == second.percentage
    assert db_session.query(ExamAttempt).filter_by(user_id=user.id).count() == 1


def test_expired_resume_finalizes_attempt(db_session) -> None:
    user = _user(db_session)
    exam = _exam(db_session)
    started = start_exam(db_session, user, exam.id)
    attempt = db_session.get(ExamAttempt, started.attempt_id)
    assert attempt is not None
    attempt.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.flush()

    resumed = resume_attempt(db_session, user, started.attempt_id)

    assert resumed.status == "EXPIRED"
    assert resumed.remaining_seconds == 0


def test_user_cannot_access_another_users_attempt(db_session) -> None:
    owner = _user(db_session, "owner-exam@example.com")
    other = _user(db_session, "other-exam@example.com")
    exam = _exam(db_session)
    started = start_exam(db_session, owner, exam.id)

    with pytest.raises(HTTPException) as exc:
        resume_attempt(db_session, other, started.attempt_id)

    assert exc.value.status_code == 404


def test_retake_creates_independent_attempt(db_session) -> None:
    user = _user(db_session)
    exam = _exam(db_session)

    first = start_exam(db_session, user, exam.id)
    second = start_exam(db_session, user, exam.id)

    assert first.attempt_id != second.attempt_id
    assert db_session.query(ExamAttempt).filter_by(user_id=user.id, exam_id=exam.id).count() == 2
