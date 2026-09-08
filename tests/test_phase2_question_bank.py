from dataclasses import dataclass

import pytest
from conftest import bearer, register_user
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import SessionLocal
from app.models import (
    ContentMembership,
    ContentStatus,
    Course,
    ExamLevel,
    ExamQuestionResult,
    ExamRevision,
    ExamSpecification,
    ExamStandard,
    Exercise,
    ExerciseSet,
    ExerciseType,
    HskLevel,
    Lesson,
    MockTest,
    Question,
    QuestionAttempt,
    QuestionOption,
    QuestionVersion,
    User,
)
from app.question_service import create_version, ensure_current_version


@dataclass
class BankRows:
    lesson_id: int
    exercise_set_id: int
    exercise_id: int
    question_id: int
    revision_id: int
    level_id: int
    version_id: int


def _choice_configuration(correct: str = "a") -> dict[str, object]:
    return {
        "options": [
            {"id": "a", "text": "Hello"},
            {"id": "b", "text": "Goodbye"},
        ],
        "correct_option_ids": [correct],
    }


@pytest.fixture
def bank_rows() -> BankRows:
    with SessionLocal() as db:
        standard = ExamStandard(code="HSK", name="HSK")
        db.add(standard)
        db.flush()
        specification = ExamSpecification(
            standard_id=standard.id,
            code="2.x",
            name="HSK 2.x",
        )
        db.add(specification)
        db.flush()
        revision = ExamRevision(
            specification_id=specification.id,
            code="hsk-2x-2025",
            version="2025.1",
            name="HSK 2.x 2025",
        )
        db.add(revision)
        db.flush()
        exam_level = ExamLevel(
            revision_id=revision.id,
            code="hsk-2x-1",
            level_number=1,
            display_name="HSK 2.x Level 1",
        )
        db.add(exam_level)
        db.flush()

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
            content_status=ContentStatus.PUBLISHED,
        )
        db.add(lesson)
        db.flush()
        exercise_set = ExerciseSet(
            lesson_id=lesson.id,
            slug="canonical-bank",
            title="Canonical Bank",
            skill="vocabulary",
            sort_order=1,
            status=ContentStatus.PUBLISHED,
        )
        db.add(exercise_set)
        db.flush()
        exercise = Exercise(
            exercise_set_id=exercise_set.id,
            external_id="canonical-choice",
            exercise_type=ExerciseType.MULTIPLE_CHOICE,
            title="Canonical choice",
            skill="vocabulary",
            sort_order=1,
            status=ContentStatus.PUBLISHED,
        )
        db.add(exercise)
        db.flush()
        question = Question(
            lesson_id=lesson.id,
            exercise_id=exercise.id,
            external_id="canonical-q1",
            question_type="multiple_choice",
            prompt="你好 means:",
            options=["Hello", "Goodbye"],
            correct_answer="Hello",
            explanation="It is a greeting.",
            points=2,
            configuration=_choice_configuration(),
            sort_order=1,
            status=ContentStatus.PUBLISHED,
        )
        db.add(question)
        db.flush()
        db.add(
            ContentMembership(
                content_type="question",
                content_id=question.id,
                exam_level_id=exam_level.id,
                introduced_in_revision_id=revision.id,
            )
        )
        version = ensure_current_version(db, question)
        db.commit()
        return BankRows(
            lesson_id=lesson.id,
            exercise_set_id=exercise_set.id,
            exercise_id=exercise.id,
            question_id=question.id,
            revision_id=revision.id,
            level_id=exam_level.id,
            version_id=version.id,
        )


def _admin_headers(client: TestClient, email: str = "phase2-admin@example.com") -> dict[str, str]:
    tokens = register_user(client, email=email)
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        assert user is not None
        user.is_admin = True
        db.commit()
    return bearer(tokens["access_token"])


def test_canonical_practice_source_and_answer_redaction(
    client: TestClient, bank_rows: BankRows
) -> None:
    headers = bearer(register_user(client)["access_token"])
    started = client.post(
        "/api/v1/practice/sessions",
        headers=headers,
        json={
            "lesson_id": bank_rows.lesson_id,
            "exercise_set_id": bank_rows.exercise_set_id,
            "question_count": 1,
        },
    )
    assert started.status_code == 201, started.text
    question = started.json()["questions"][0]
    assert question["question_version_id"] == bank_rows.version_id
    assert "correct_option_ids" not in question["configuration"]
    assert "correct_answer" not in question
    assert "accepted_answers" not in question["configuration"]

    submitted = client.post(
        f"/api/v1/practice/sessions/{started.json()['id']}/answers",
        headers=headers,
        json={"question_id": bank_rows.question_id, "answer": "a", "idempotency_key": "phase2-a1"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["correct"] is True
    assert submitted.json()["correct_answer"] == "a"
    with SessionLocal() as db:
        attempt = db.scalar(select(QuestionAttempt).where(QuestionAttempt.question_id == bank_rows.question_id))
        version = db.get(QuestionVersion, bank_rows.version_id)
        options = db.scalars(select(QuestionOption).where(QuestionOption.question_version_id == bank_rows.version_id)).all()
        assert attempt is not None and attempt.question_version_id == bank_rows.version_id
        assert version is not None and version.version_number == 1
        assert {item.option_id for item in options} == {"a", "b"}
        assert sum(item.is_correct for item in options) == 1


def test_admin_question_bank_crud_and_revision_membership(
    client: TestClient, bank_rows: BankRows
) -> None:
    headers = _admin_headers(client)
    payload = {
        "lesson_id": bank_rows.lesson_id,
        "exercise_id": bank_rows.exercise_id,
        "external_id": "admin-canonical-q",
        "question_type": "multiple_choice",
        "prompt": "再见 means:",
        "order": 2,
        "configuration": _choice_configuration("b"),
        "status": "draft",
        "exam_revision_id": bank_rows.revision_id,
        "exam_level_id": bank_rows.level_id,
        "skill": "vocabulary",
    }
    created = client.post("/api/v1/admin/question-bank", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    created_body = created.json()
    assert created_body["version_number"] == 1
    assert created_body["status"] == "draft"
    assert created_body["exam_revision_id"] == bank_rows.revision_id
    assert created_body["exam_level_id"] == bank_rows.level_id

    listed = client.get(
        "/api/v1/admin/question-bank",
        headers=headers,
        params={"exam_revision_id": bank_rows.revision_id, "skill": "vocabulary", "status": "draft"},
    )
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1

    question_id = created_body["id"]
    updated = client.patch(
        f"/api/v1/admin/question-bank/{question_id}",
        headers=headers,
        json={"prompt": "再见 means what?", "status": "published"},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["version_number"] == 2
    assert updated.json()["status"] == "published"
    assert updated.json()["prompt"] == "再见 means what?"

    draft = client.patch(
        f"/api/v1/admin/question-bank/{question_id}",
        headers=headers,
        json={"prompt": "Draft prompt", "status": "draft"},
    )
    assert draft.status_code == 200, draft.text
    assert draft.json()["version_number"] == 3
    assert client.get(
        "/api/v1/admin/question-bank",
        headers=headers,
        params={"status": "draft", "query": "Draft prompt"},
    ).json()["total"] == 1
    assert client.get(
        "/api/v1/admin/question-bank",
        headers=headers,
        params={"status": "published", "query": "Draft prompt"},
    ).json()["total"] == 0

    published = client.get(
        "/api/v1/admin/question-bank",
        headers=headers,
        params={"exam_level_id": bank_rows.level_id, "status": "published"},
    )
    assert published.status_code == 200
    assert published.json()["total"] == 1
    archived = client.post(f"/api/v1/admin/question-bank/{question_id}/archive", headers=headers)
    assert archived.status_code == 200, archived.text
    assert archived.json()["status"] == "archived"


def test_exam_uses_canonical_version_and_preserves_historical_result(
    client: TestClient, bank_rows: BankRows
) -> None:
    headers = bearer(register_user(client, email="phase2-exam@example.com")["access_token"])
    with SessionLocal() as db:
        exam = MockTest(
            title="Canonical HSK Exam",
            hsk_level=1,
            exam_revision_id=bank_rows.revision_id,
            exam_level_id=bank_rows.level_id,
            duration_minutes=10,
            question_count=1,
            status="PUBLISHED",
            blueprint={
                "sections": [
                    {"type": "VOCABULARY", "title": "Vocabulary", "question_count": 1, "duration_minutes": 10}
                ]
            },
            question_version_ids=[bank_rows.version_id],
        )
        db.add(exam)
        db.commit()
        exam_id = exam.id

    started = client.post(f"/api/v1/exams/{exam_id}/start", headers=headers)
    assert started.status_code == 201, started.text
    attempt_id = started.json()["attempt_id"]
    exam_question = started.json()["questions"][0]
    assert exam_question["question_version_id"] == bank_rows.version_id
    assert "correct_option_ids" not in exam_question["config"]
    assert "correct_answer" not in exam_question

    with SessionLocal() as db:
        question = db.get(Question, bank_rows.question_id)
        assert question is not None
        create_version(
            db,
            question,
            status=ContentStatus.PUBLISHED,
            values={
                "question_type": "multiple_choice",
                "prompt": "Edited prompt",
                "correct_answer": "Goodbye",
                "explanation": "Edited explanation.",
                "configuration": _choice_configuration("b"),
                "skill": "vocabulary",
            },
        )
        db.commit()

    saved = client.put(
        f"/api/v1/exam-attempts/{attempt_id}/answers/{bank_rows.question_id}",
        headers=headers,
        json={"answer": "a"},
    )
    assert saved.status_code == 200, saved.text
    result = client.post(f"/api/v1/exam-attempts/{attempt_id}/submit", headers=headers)
    assert result.status_code == 200, result.text
    item = result.json()["questions"][0]
    assert item["question_version_id"] == bank_rows.version_id
    assert item["prompt"] == "你好 means:"
    assert item["correct_answer"] == "a"
    assert item["explanation"] == "It is a greeting."

    with SessionLocal() as db:
        row = db.scalar(select(ExamQuestionResult).where(ExamQuestionResult.exam_attempt_id == attempt_id))
        assert row is not None and row.question_version_id == bank_rows.version_id
