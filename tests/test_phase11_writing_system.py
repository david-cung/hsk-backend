from app.exam_service import save_answer, start_exam, submit_attempt
from app.models import (
    HskLevel,
    Lesson,
    MockTest,
    PracticeSession,
    Profile,
    Question,
    ReviewHistory,
    User,
)
from app.practice_engine import evaluate_answer
from app.practice_router import submit_answer
from app.progress_service import summary
from app.schemas import PracticeAnswerIn
from app.writing_service import chinese_character_count, normalize_writing_text


def _user(db_session, email: str = "writing@example.com") -> User:
    user = User(email=email, display_name="Writer", password_hash="hash")
    db_session.add(user)
    db_session.flush()
    profile = Profile(user_id=user.id, current_hsk_level=1, target_hsk_level=1)
    db_session.add(profile)
    db_session.flush()
    user.profile = profile
    return user


def _lesson(db_session) -> Lesson:
    level = HskLevel(level_number=1, title="HSK 1", total_characters=150)
    db_session.add(level)
    db_session.flush()
    lesson = Lesson(hsk_level_id=level.id, title="Writing", lesson_type="writing", sort_order=1, content={})
    db_session.add(lesson)
    db_session.flush()
    return lesson


def _question(db_session, lesson: Lesson, question_type: str, config: dict, prompt: str = "Write") -> Question:
    question = Question(
        lesson_id=lesson.id,
        question_type=question_type,
        prompt=prompt,
        correct_answer="",
        points=1,
        sort_order=1,
        config=config,
        reference_type="WRITING",
        reference_id="writing",
    )
    db_session.add(question)
    db_session.flush()
    return question


def test_writing_normalization_preserves_chinese_and_punctuation_compare() -> None:
    assert normalize_writing_text("  我　学习中文！ ") == "我 学习中文!"
    assert normalize_writing_text("我学习中文！", compare=True) == "我学习中文"
    assert chinese_character_count("我 study 中文") == 3
    assert normalize_writing_text("") == ""


def test_word_order_scores_exact_and_wrong_order(db_session) -> None:
    lesson = _lesson(db_session)
    question = _question(
        db_session,
        lesson,
        "WORD_ORDER",
        {
            "items": [{"id": "w", "text": "我"}, {"id": "x", "text": "喜欢"}, {"id": "y", "text": "学习"}, {"id": "z", "text": "中文"}],
            "correct_order": ["w", "x", "y", "z"],
        },
    )

    assert evaluate_answer(question, ["w", "x", "y", "z"])["correct"] is True
    wrong = evaluate_answer(question, ["w", "x", "z", "y"])
    assert wrong["correct"] is False
    assert 0 < wrong["score"] < 1


def test_fill_blank_accepts_configured_alternative(db_session) -> None:
    lesson = _lesson(db_session)
    question = _question(
        db_session,
        lesson,
        "FILL_BLANK",
        {"writing": True, "accepted_answers": ["学习", "学中文"]},
    )

    assert evaluate_answer(question, " 学中文。 ")["correct"] is True
    assert evaluate_answer(question, "")["correct"] is False


def test_translation_requires_configured_acceptance(db_session) -> None:
    lesson = _lesson(db_session)
    question = _question(
        db_session,
        lesson,
        "TRANSLATION_TO_CHINESE",
        {
            "accepted_answers": ["我每天学习中文。", "我每天学中文。"],
            "required_keywords": ["每天", "中文"],
        },
    )

    assert evaluate_answer(question, "我每天学中文")["correct"] is True
    arbitrary = evaluate_answer(question, "我爱中文")
    assert arbitrary["correct"] is False
    assert arbitrary["score"] < 1


def test_guided_writing_returns_structured_evaluation(db_session) -> None:
    lesson = _lesson(db_session)
    question = _question(
        db_session,
        lesson,
        "GUIDED_WRITING",
        {
            "required_vocabulary": ["学习"],
            "required_grammar": ["每天"],
            "min_characters": 5,
            "max_characters": 20,
            "min_chinese_ratio": 0.6,
        },
    )

    result = evaluate_answer(question, "我每天学习中文。")

    assert result["correct"] is True
    assert result["normalized_answer"]["evaluation_source"] == "DETERMINISTIC"
    assert result["normalized_answer"]["writing_evaluation"]["label"] == "STRUCTURED_EVALUATION"


def test_practice_submission_stores_writing_evaluation_and_srs_once(db_session) -> None:
    user = _user(db_session)
    lesson = _lesson(db_session)
    question = _question(
        db_session,
        lesson,
        "GUIDED_WRITING",
        {"required_vocabulary": ["学习"], "min_characters": 5, "max_characters": 30},
    )
    session = PracticeSession(user_id=user.id, lesson_id=lesson.id, question_ids=[question.id], total_questions=1)
    db_session.add(session)
    db_session.flush()

    payload = PracticeAnswerIn(question_id=question.id, answer="我喜欢学习中文。", idempotency_key="same-writing")
    first = submit_answer(session.id, payload, user, db_session)
    second = submit_answer(session.id, payload, user, db_session)

    assert first.attempt_id == second.attempt_id
    assert first.writing_evaluation is not None
    assert db_session.query(ReviewHistory).filter_by(source="WRITING").count() == 1
    progress = summary(db_session, user)
    assert progress.writing_exercises_attempted == 1
    assert progress.guided_writing_count == 1


def test_mock_exam_scores_writing_section(db_session) -> None:
    user = _user(db_session)
    lesson = _lesson(db_session)
    question = _question(
        db_session,
        lesson,
        "TRANSLATION_TO_CHINESE",
        {"accepted_answers": ["我每天学习中文。"], "required_keywords": ["每天", "中文"]},
    )
    exam = MockTest(
        title="HSK 1 Writing Mock",
        hsk_level=1,
        duration_minutes=10,
        question_count=1,
        status="PUBLISHED",
        exam_type="MOCK",
        version=1,
        blueprint={"sections": [{"type": "WRITING", "title": "Writing", "question_count": 1, "duration_minutes": 10}]},
        scoring_config={"passing_percentage": 60},
    )
    db_session.add(exam)
    db_session.flush()

    attempt = start_exam(db_session, user, exam.id)
    save_answer(db_session, user, attempt.attempt_id, question.id, "我每天学习中文")
    result = submit_attempt(db_session, user, attempt.attempt_id)

    assert result.sections[0].section == "WRITING"
    assert result.percentage == 100
    assert result.questions[0].writing_evaluation is not None
