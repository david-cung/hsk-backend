from dataclasses import dataclass

import pytest
from conftest import bearer, register_user
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import (
    ContentStatus,
    Course,
    Exercise,
    ExerciseSet,
    ExerciseType,
    GrammarPoint,
    HskLevel,
    Lesson,
    PracticeSession,
    Question,
    QuestionAttempt,
    User,
    UserGrammarProgress,
    UserVocabularyProgress,
    Vocabulary,
)
from app.practice_engine import evaluate_answer


@dataclass
class PracticeRows:
    lesson_id: int
    exercise_set_id: int
    choice_exercise_id: int
    choice_question_id: int
    grammar_question_id: int
    vocabulary_id: int
    grammar_id: int


def _choice_configuration() -> dict[str, object]:
    return {
        "options": [
            {"id": "a", "text": "Hello"},
            {"id": "b", "text": "Goodbye"},
        ],
        "correct_option_ids": ["a"],
    }


@pytest.fixture
def practice_rows() -> PracticeRows:
    with SessionLocal() as db:
        level = HskLevel(
            level_number=1,
            title="HSK 1",
            display_order=1,
            total_characters=150,
        )
        db.add(level)
        db.flush()
        course = Course(
            hsk_level_id=level.id,
            title="Vocabulary",
            course_type="vocabulary",
            sort_order=1,
        )
        db.add(course)
        db.flush()
        lesson = Lesson(
            hsk_level_id=level.id,
            course_id=course.id,
            title="Greetings",
            lesson_type="vocabulary",
            sort_order=1,
            duration_minutes=10,
            content={
                "practice_exercises": [
                    {
                        "id": "legacy-q",
                        "exercise_type": "multiple_choice",
                        "prompt": "你好 means:",
                        "options": ["Hello", "Goodbye"],
                        "correct_answer": "Hello",
                    }
                ]
            },
        )
        vocabulary = Vocabulary(
            hsk_level_id=level.id,
            simplified="你好",
            pinyin="ni3 hao3",
            meaning_translations={"en": "hello"},
            part_of_speech="phrase",
            display_order=1,
        )
        grammar = GrammarPoint(
            hsk_level_id=level.id,
            title="吗 questions",
            explanation_translations={"en": "Add 吗."},
            display_order=1,
        )
        db.add_all([lesson, vocabulary, grammar])
        db.flush()
        exercise_set = ExerciseSet(
            lesson_id=lesson.id,
            slug="lesson-practice",
            title="Greetings Practice",
            skill="vocabulary",
            sort_order=0,
        )
        db.add(exercise_set)
        db.flush()
        choice_exercise = Exercise(
            exercise_set_id=exercise_set.id,
            external_id="greeting-choice",
            exercise_type=ExerciseType.MULTIPLE_CHOICE,
            title="Vocabulary choice",
            skill="vocabulary",
            vocabulary_id=vocabulary.id,
            sort_order=1,
        )
        grammar_exercise = Exercise(
            exercise_set_id=exercise_set.id,
            external_id="grammar-choice",
            exercise_type=ExerciseType.GRAMMAR,
            title="Grammar choice",
            skill="grammar",
            grammar_point_id=grammar.id,
            sort_order=2,
        )
        db.add_all([choice_exercise, grammar_exercise])
        db.flush()
        choice_question = Question(
            lesson_id=lesson.id,
            exercise_id=choice_exercise.id,
            external_id="q-choice",
            question_type="multiple_choice",
            prompt="你好 means:",
            options=["Hello", "Goodbye"],
            correct_answer="Hello",
            explanation="你好 is a greeting.",
            points=2,
            configuration=_choice_configuration(),
            sort_order=1,
        )
        grammar_question = Question(
            lesson_id=lesson.id,
            exercise_id=grammar_exercise.id,
            external_id="q-grammar",
            question_type="grammar",
            prompt="Choose the question particle.",
            options=["吗", "很"],
            correct_answer="吗",
            explanation="吗 forms yes/no questions.",
            configuration={
                "options": [
                    {"id": "ma", "text": "吗"},
                    {"id": "hen", "text": "很"},
                ],
                "correct_option_ids": ["ma"],
            },
            sort_order=1,
        )
        db.add_all([choice_question, grammar_question])
        db.commit()
        return PracticeRows(
            lesson_id=lesson.id,
            exercise_set_id=exercise_set.id,
            choice_exercise_id=choice_exercise.id,
            choice_question_id=choice_question.id,
            grammar_question_id=grammar_question.id,
            vocabulary_id=vocabulary.id,
            grammar_id=grammar.id,
        )


def _headers(
    client: TestClient, email: str, *, admin: bool = False
) -> dict[str, str]:
    tokens = register_user(client, email=email)
    if admin:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            assert user
            user.is_admin = True
            db.commit()
    return bearer(tokens["access_token"])


@pytest.mark.parametrize(
    ("question_type", "configuration", "answer", "correct"),
    [
        ("multiple_choice", _choice_configuration(), "a", True),
        (
            "multiple_select",
            {
                "options": [
                    {"id": "a", "text": "A"},
                    {"id": "b", "text": "B"},
                    {"id": "c", "text": "C"},
                ],
                "correct_option_ids": ["a", "c"],
            },
            ["c", "a"],
            True,
        ),
        (
            "ordering",
            {
                "items": [
                    {"id": "one", "text": "我"},
                    {"id": "two", "text": "学习"},
                ],
                "correct_order": ["one", "two"],
            },
            ["one", "two"],
            True,
        ),
        (
            "matching",
            {
                "items": [
                    {"id": "hello", "text": "你好"},
                    {"id": "bye", "text": "再见"},
                ],
                "targets": [
                    {"id": "a", "text": "hello"},
                    {"id": "b", "text": "goodbye"},
                ],
                "correct_pairs": {"hello": "a", "bye": "b"},
            },
            {"bye": "b", "hello": "a"},
            True,
        ),
        (
            "fill_blank",
            {
                "accepted_answers": ["nǐ hǎo"],
                "normalization": {
                    "pinyin_tones": "ignore",
                    "punctuation": "ignore",
                },
            },
            "  ni3 hao! ",
            True,
        ),
        (
            "text_input",
            {
                "accepted_answers": ["你好"],
                "normalization": {"punctuation": "ignore"},
            },
            "你好。",
            True,
        ),
    ],
)
def test_server_evaluation_types_and_normalization(
    question_type: str,
    configuration: dict[str, object],
    answer: object,
    correct: bool,
) -> None:
    question = Question(
        lesson_id=1,
        question_type=question_type,
        prompt="Prompt",
        correct_answer="legacy",
        configuration=configuration,
        points=3,
        sort_order=1,
    )
    result = evaluate_answer(question, answer)
    assert result.is_correct is correct
    assert result.score == 3


def test_invalid_answer_is_rejected() -> None:
    question = Question(
        lesson_id=1,
        question_type="multiple_choice",
        prompt="Prompt",
        correct_answer="Hello",
        configuration=_choice_configuration(),
        points=1,
        sort_order=1,
    )
    with pytest.raises(ValueError, match="unknown option"):
        evaluate_answer(question, "missing")


def test_practice_session_flow_idempotency_history_and_progress(
    client: TestClient, practice_rows: PracticeRows
) -> None:
    headers = _headers(client, "practice@example.com")
    lesson_detail = client.get(f"/api/v1/lessons/{practice_rows.lesson_id}")
    assert lesson_detail.status_code == 200
    legacy_question = lesson_detail.json()["content"]["practice_exercises"][0]
    assert "correct_answer" not in legacy_question
    availability = client.get(
        f"/api/v1/practice/lessons/{practice_rows.lesson_id}",
        headers=headers,
    )
    assert availability.status_code == 200
    assert availability.json()["total_questions"] == 2

    created = client.post(
        "/api/v1/practice/sessions",
        headers=headers,
        json={"lesson_id": practice_rows.lesson_id},
    )
    assert created.status_code == 201, created.text
    session = created.json()
    session_id = session["id"]
    assert session["total_questions"] == 2
    first_question = next(
        item
        for item in session["questions"]
        if item["id"] == practice_rows.choice_question_id
    )
    assert "correct_option_ids" not in first_question["configuration"]
    assert "correct_answer" not in first_question

    resumed = client.post(
        "/api/v1/practice/sessions",
        headers=headers,
        json={"lesson_id": practice_rows.lesson_id},
    )
    assert resumed.json()["id"] == session_id

    answer_payload = {
        "question_id": practice_rows.choice_question_id,
        "answer": "a",
        "idempotency_key": "choice-attempt-0001",
        "time_spent_seconds": 8,
    }
    answered = client.post(
        f"/api/v1/practice/sessions/{session_id}/answers",
        headers=headers,
        json=answer_payload,
    )
    assert answered.status_code == 200, answered.text
    assert answered.json()["correct"] is True
    assert answered.json()["correct_answer"] == "a"
    attempt_id = answered.json()["attempt_id"]

    repeated = client.post(
        f"/api/v1/practice/sessions/{session_id}/answers",
        headers=headers,
        json=answer_payload,
    )
    assert repeated.status_code == 200
    assert repeated.json()["attempt_id"] == attempt_id

    wrong = client.post(
        f"/api/v1/practice/sessions/{session_id}/answers",
        headers=headers,
        json={
            **answer_payload,
            "answer": "b",
            "idempotency_key": "choice-attempt-0002",
        },
    )
    assert wrong.json()["correct"] is False

    grammar = client.post(
        f"/api/v1/practice/sessions/{session_id}/answers",
        headers=headers,
        json={
            "question_id": practice_rows.grammar_question_id,
            "answer": "ma",
            "idempotency_key": "grammar-attempt-001",
            "time_spent_seconds": 4,
        },
    )
    assert grammar.json()["correct"] is True

    completed = client.post(
        f"/api/v1/practice/sessions/{session_id}/complete",
        headers=headers,
    )
    assert completed.status_code == 200
    assert completed.json()["answered_questions"] == 2
    assert completed.json()["correct_answers"] == 1
    assert len(completed.json()["review"]) == 2
    results = client.get(
        f"/api/v1/practice/sessions/{session_id}/results",
        headers=headers,
    )
    assert results.status_code == 200

    with SessionLocal() as db:
        assert (
            db.scalar(
                select(func.count())
                .select_from(QuestionAttempt)
                .where(QuestionAttempt.practice_session_id == session_id)
            )
            == 3
        )
        vocabulary_progress = db.scalar(
            select(UserVocabularyProgress).where(
                UserVocabularyProgress.vocabulary_id
                == practice_rows.vocabulary_id
            )
        )
        assert vocabulary_progress
        assert vocabulary_progress.practiced_count == 2
        assert vocabulary_progress.correct_count == 1
        assert vocabulary_progress.incorrect_count == 1
        grammar_progress = db.scalar(
            select(UserGrammarProgress).where(
                UserGrammarProgress.grammar_point_id == practice_rows.grammar_id
            )
        )
        assert grammar_progress
        assert grammar_progress.practiced_count == 1
        assert grammar_progress.correct_count == 1


def test_practice_session_user_isolation(
    client: TestClient, practice_rows: PracticeRows
) -> None:
    owner = _headers(client, "owner@example.com")
    other = _headers(client, "other@example.com")
    session = client.post(
        "/api/v1/practice/sessions",
        headers=owner,
        json={"lesson_id": practice_rows.lesson_id},
    ).json()
    session_id = session["id"]
    assert (
        client.get(
            f"/api/v1/practice/sessions/{session_id}", headers=other
        ).status_code
        == 404
    )
    assert (
        client.post(
            f"/api/v1/practice/sessions/{session_id}/complete", headers=other
        ).status_code
        == 404
    )


def test_admin_exercise_question_crud_and_authorization(
    client: TestClient, practice_rows: PracticeRows
) -> None:
    normal = _headers(client, "normal-practice@example.com")
    admin = _headers(client, "admin-practice@example.com", admin=True)
    payload = {
        "lesson_id": practice_rows.lesson_id,
        "exercise_set_id": practice_rows.exercise_set_id,
        "external_id": "admin-fill",
        "exercise_type": "fill_blank",
        "title": "Admin fill blank",
        "order": 3,
    }
    assert (
        client.post("/api/v1/admin/exercises", headers=normal, json=payload).status_code
        == 403
    )
    exercise = client.post(
        "/api/v1/admin/exercises", headers=admin, json=payload
    )
    assert exercise.status_code == 201, exercise.text
    exercise_id = exercise.json()["id"]
    question = client.post(
        f"/api/v1/admin/exercises/{exercise_id}/questions",
        headers=admin,
        json={
            "external_id": "fill-1",
            "question_type": "fill_blank",
            "prompt": "你___。",
            "order": 1,
            "configuration": {
                "accepted_answers": ["好"],
                "normalization": {"punctuation": "ignore"},
            },
        },
    )
    assert question.status_code == 201, question.text
    question_id = question.json()["id"]
    preview = client.get(
        f"/api/v1/admin/exercises/{exercise_id}/preview", headers=admin
    )
    assert preview.status_code == 200
    assert "accepted_answers" not in preview.json()[0]["configuration"]
    assert client.patch(
        f"/api/v1/admin/questions/{question_id}",
        headers=admin,
        json={"points": 2},
    ).json()["points"] == 2
    assert client.delete(
        f"/api/v1/admin/exercises/{exercise_id}", headers=admin
    ).status_code == 204
    with SessionLocal() as db:
        assert db.get(Exercise, exercise_id).status == ContentStatus.ARCHIVED
        assert db.get(Question, question_id).status == ContentStatus.ARCHIVED


def test_exercise_import_upsert_duplicate_and_rollback(
    client: TestClient, practice_rows: PracticeRows
) -> None:
    admin = _headers(client, "exercise-import@example.com", admin=True)
    record = {
        "lesson_id": practice_rows.lesson_id,
        "exercise_set_slug": "lesson-practice",
        "external_id": "imported-recall",
        "exercise_type": "vocabulary_recall",
        "title": "Imported recall",
        "order": 3,
        "questions": [
            {
                "external_id": "imported-recall-q1",
                "question_type": "text_input",
                "prompt": "Type 你好",
                "order": 1,
                "configuration": {
                    "accepted_answers": ["你好"],
                    "normalization": {"punctuation": "ignore"},
                },
            }
        ],
    }
    imported = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "exercises",
            "source_format": "json",
            "data": [record],
        },
    )
    assert imported.status_code == 201, imported.text
    assert imported.json()["created_records"] == 1
    repeated = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "exercises",
            "source_format": "json",
            "data": [record],
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["updated_records"] == 1

    duplicate = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "exercises",
            "source_format": "json",
            "data": [record, record],
        },
    )
    assert duplicate.status_code == 422
    invalid = {
        **record,
        "external_id": "invalid-exercise",
        "questions": [
            {
                **record["questions"][0],
                "external_id": "invalid-q",
                "configuration": {
                    "options": [{"id": "a", "text": "Only one"}],
                    "correct_option_ids": ["missing"],
                },
            }
        ],
    }
    failed = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "exercises",
            "source_format": "json",
            "data": [invalid],
        },
    )
    assert failed.status_code == 422
    with SessionLocal() as db:
        assert db.scalar(
            select(Exercise).where(Exercise.external_id == "invalid-exercise")
        ) is None
        assert db.scalar(
            select(func.count())
            .select_from(PracticeSession)
        ) == 0
