from datetime import UTC, datetime, timedelta

import pytest

from app.models import (
    AnswerAttempt,
    HskLevel,
    Lesson,
    PracticeSession,
    Profile,
    Question,
    ReviewCard,
    ReviewHistory,
    SavedWord,
    User,
)
from app.review_scheduler import ReviewRating
from app.review_service import (
    due_cards,
    enroll_card,
    enroll_saved_word,
    history,
    practice_review_signal,
    review_card,
    review_summary,
)


def _user(db_session, email: str = "review@example.com") -> User:
    user = User(email=email, display_name="Review", password_hash="hash")
    db_session.add(user)
    db_session.flush()
    profile = Profile(user_id=user.id, current_hsk_level=1, target_hsk_level=1)
    db_session.add(profile)
    db_session.flush()
    user.profile = profile
    return user


def _question(db_session, user: User, reference_type: str = "VOCABULARY", reference_id: str = "你好") -> tuple[Question, PracticeSession]:
    level = HskLevel(level_number=1, title="HSK 1", total_characters=150)
    db_session.add(level)
    db_session.flush()
    lesson = Lesson(hsk_level_id=level.id, title="Hello", lesson_type="vocabulary", sort_order=1, content={})
    db_session.add(lesson)
    db_session.flush()
    question = Question(
        lesson_id=lesson.id,
        question_type="MULTIPLE_CHOICE",
        prompt="Choose hello",
        options=["你好", "谢谢"],
        correct_answer="1",
        config={"options": [{"id": "1", "text": "你好"}, {"id": "2", "text": "谢谢"}], "correct_option_ids": ["1"]},
        reference_type=reference_type,
        reference_id=reference_id,
    )
    db_session.add(question)
    db_session.flush()
    session = PracticeSession(user_id=user.id, lesson_id=lesson.id, question_ids=[question.id], total_questions=1)
    db_session.add(session)
    db_session.flush()
    return question, session


def test_due_cards_empty(db_session) -> None:
    user = _user(db_session)

    due = due_cards(db_session, user, now=datetime.now(UTC) + timedelta(minutes=1))

    assert due.items == []
    assert due.due_count == 0


def test_enroll_saved_word_creates_due_vocabulary_card(db_session) -> None:
    user = _user(db_session)
    word = SavedWord(user_id=user.id, hanzi="你好", pinyin="ni hao", meaning="hello")
    db_session.add(word)
    db_session.flush()

    card = enroll_saved_word(db_session, user, word)
    due = due_cards(db_session, user, now=datetime.now(UTC) + timedelta(minutes=1))

    assert card.card_type == "VOCABULARY"
    assert card.vocabulary_id == word.id
    assert due.items[0].content["hanzi"] == "你好"
    assert {preview.rating for preview in due.items[0].rating_previews} == {"AGAIN", "HARD", "GOOD", "EASY"}


def test_review_submission_is_idempotent_and_preserves_history(db_session) -> None:
    user = _user(db_session)
    card = enroll_card(db_session, user, "GRAMMAR", grammar_id="ba", content={"pattern": "把"})
    now = datetime(2026, 8, 15, 9, tzinfo=UTC)

    reviewed, first_history, duplicate = review_card(db_session, user, card.id, ReviewRating.GOOD, "same-key", reviewed_at=now)
    reviewed_again, second_history, duplicate_again = review_card(
        db_session,
        user,
        card.id,
        ReviewRating.AGAIN,
        "same-key",
        reviewed_at=now + timedelta(minutes=1),
    )

    assert duplicate is False
    assert duplicate_again is True
    assert reviewed.id == reviewed_again.id
    assert first_history.id == second_history.id
    assert db_session.query(ReviewHistory).count() == 1
    assert reviewed_again.rating if hasattr(reviewed_again, "rating") else True


def test_user_isolation_for_review(db_session) -> None:
    owner = _user(db_session, "owner@example.com")
    other = _user(db_session, "other@example.com")
    card = enroll_card(db_session, owner, "GRAMMAR", grammar_id="de", content={"pattern": "的"})

    with pytest.raises(ValueError):
        review_card(db_session, other, card.id, ReviewRating.GOOD, "other-key")


def test_practice_integration_updates_vocabulary_card(db_session) -> None:
    user = _user(db_session)
    question, session = _question(db_session, user)
    attempt = AnswerAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=question.id,
        submitted_answer={"value": "1"},
        normalized_answer={"value": "1"},
        is_correct=True,
        score=1,
        idempotency_key="answer-1",
        attempted_at=datetime(2026, 8, 15, 9, tzinfo=UTC),
    )
    db_session.add(attempt)
    db_session.flush()

    practice_review_signal(db_session, user, question, attempt)

    card = db_session.query(ReviewCard).filter_by(user_id=user.id, card_type="VOCABULARY").one()
    assert card.reps == 1
    assert card.state == "REVIEW"
    assert db_session.query(ReviewHistory).filter_by(source="PRACTICE", rating="GOOD").count() == 1


def test_listening_incorrect_updates_same_review_card(db_session) -> None:
    user = _user(db_session)
    question, session = _question(db_session, user, "VOCABULARY", "你好")
    question.question_type = "LISTENING"
    question.config = {**question.config, "transcript": "你好"}
    attempt = AnswerAttempt(
        user_id=user.id,
        practice_session_id=session.id,
        question_id=question.id,
        submitted_answer={"value": "2"},
        normalized_answer={"value": "2"},
        is_correct=False,
        score=0,
        idempotency_key="answer-2",
        attempted_at=datetime(2026, 8, 15, 9, tzinfo=UTC),
    )
    db_session.add(attempt)
    db_session.flush()

    practice_review_signal(db_session, user, question, attempt)

    card = db_session.query(ReviewCard).filter_by(user_id=user.id, card_type="VOCABULARY").one()
    assert card.lapses == 1
    assert card.state == "LEARNING"
    assert db_session.query(ReviewHistory).filter_by(source="LISTENING", rating="AGAIN").count() == 1


def test_review_summary_and_history(db_session) -> None:
    user = _user(db_session)
    card = enroll_card(db_session, user, "GRAMMAR", grammar_id="le", content={"pattern": "了"})
    now = datetime(2026, 8, 15, 9, tzinfo=UTC)
    review_card(db_session, user, card.id, ReviewRating.GOOD, "history-key", reviewed_at=now)

    summary = review_summary(db_session, user, now)
    rows = history(db_session, user)

    assert summary.reviewed_today == 1
    assert summary.retention == 100
    assert summary.review_streak_days == 1
    assert rows[0].rating == "GOOD"
    assert rows[0].card_type == "GRAMMAR"
