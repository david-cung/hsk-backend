from __future__ import annotations

from pathlib import Path

from conftest import bearer, register_user
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_phase2_question_bank import bank_rows as bank_rows_fixture  # noqa: F401

from app.config import settings
from app.database import SessionLocal
from app.exam_import_parser import ExtractedPdf, parse_exam_pages
from app.models import ExamVersion, QuestionVersion, User


def _admin_headers(client: TestClient) -> dict[str, str]:
    tokens = register_user(client, email="phase4-admin@example.com")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "phase4-admin@example.com"))
        assert user is not None
        user.is_admin = True
        db.commit()
    return bearer(tokens["access_token"])


def _exam_text() -> str:
    return """LISTENING
Part 1
1. Choose the greeting A. 你好 B. 再见
2. Choose the farewell A. 你好 B. 再见
READING
Part 1
3. Choose the meaning A. 学生 B. 老师
"""


def test_parser_preserves_section_part_question_and_options() -> None:
    parsed = parse_exam_pages(ExtractedPdf(pages=[_exam_text()], text_characters=len(_exam_text())))
    assert [section.code for section in parsed.sections] == ["LISTENING", "READING"]
    assert parsed.sections[0].parts[0].title == "Part 1"
    question = parsed.sections[0].parts[0].questions[0]
    assert question.number == 1
    assert question.section == "LISTENING"
    assert [option.id for option in question.options] == ["A", "B"]
    assert question.source_page == 1


def test_import_creates_canonical_drafts_and_is_idempotent(
    client: TestClient, bank_rows_fixture, monkeypatch, tmp_path: Path  # noqa: F811
) -> None:
    monkeypatch.setattr(settings, "exam_import_storage_dir", str(tmp_path))
    monkeypatch.setattr(
        "app.exam_import_service.extract_pdf_text",
        lambda path: ExtractedPdf(pages=[_exam_text()], text_characters=len(_exam_text())),
    )
    admin = _admin_headers(client)
    files = {
        "exam_pdf": ("sample.pdf", b"pdf fixture", "application/pdf"),
        "answer_file": ("answers.txt", b"1 A\n2 B\n3 A\n", "text/plain"),
        "listening_audio": ("listening.mp3", b"ID3 fixture", "audio/mpeg"),
    }
    payload = {
        "exam_name": "Imported Phase 4 Exam",
        "exam_revision_id": str(bank_rows_fixture.revision_id),
        "exam_level_id": str(bank_rows_fixture.level_id),
    }
    created = client.post("/api/v1/admin/exam-imports", headers=admin, data=payload, files=files)
    assert created.status_code == 202, created.text
    first = client.get(f"/api/v1/admin/exam-imports/{created.json()['id']}", headers=admin)
    assert first.status_code == 200, first.text
    job = first.json()
    assert job["status"] == "COMPLETED"
    assert job["summary"] == {"sections": 2, "questions": 3, "answers_matched": 3, "warnings": 0, "review_required": False}
    assert job["created_exam_version_id"] is not None
    assert len(job["parsed_document"]["created_question_ids"]) == 3

    with SessionLocal() as db:
        question_version_ids = job["parsed_document"]["created_question_version_ids"]
        assert db.scalar(select(func.count()).where(QuestionVersion.id.in_(question_version_ids))) == 3
        version = db.get(ExamVersion, job["created_exam_version_id"])
        assert version is not None
        assert version.status.value == "draft"

    duplicate = client.post("/api/v1/admin/exam-imports", headers=admin, data=payload, files=files)
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == job["id"]

    forced = client.post(
        "/api/v1/admin/exam-imports",
        headers=admin,
        data={**payload, "force_new": "true"},
        files=files,
    )
    assert forced.status_code == 202, forced.text
    assert forced.json()["id"] != job["id"]


def test_import_review_required_when_answer_key_is_missing(
    client: TestClient, bank_rows_fixture, monkeypatch, tmp_path: Path  # noqa: F811
) -> None:
    monkeypatch.setattr(settings, "exam_import_storage_dir", str(tmp_path))
    monkeypatch.setattr(
        "app.exam_import_service.extract_pdf_text",
        lambda path: ExtractedPdf(pages=[_exam_text()], text_characters=len(_exam_text())),
    )
    admin = _admin_headers(client)
    response = client.post(
        "/api/v1/admin/exam-imports",
        headers=admin,
        data={
            "exam_name": "Needs Review",
            "exam_revision_id": str(bank_rows_fixture.revision_id),
            "exam_level_id": str(bank_rows_fixture.level_id),
        },
        files={"exam_pdf": ("sample.pdf", b"pdf fixture", "application/pdf")},
    )
    assert response.status_code == 202, response.text
    job = client.get(f"/api/v1/admin/exam-imports/{response.json()['id']}", headers=admin).json()
    assert job["status"] == "REVIEW_REQUIRED"
    assert any(item["code"] == "ANSWER_KEY_NOT_PROVIDED" for item in job["warnings"])


def test_imported_questions_and_exam_can_publish_after_review(
    client: TestClient, bank_rows_fixture, monkeypatch, tmp_path: Path  # noqa: F811
) -> None:
    monkeypatch.setattr(settings, "exam_import_storage_dir", str(tmp_path))
    monkeypatch.setattr(
        "app.exam_import_service.extract_pdf_text",
        lambda path: ExtractedPdf(pages=[_exam_text()], text_characters=len(_exam_text())),
    )
    admin = _admin_headers(client)
    response = client.post(
        "/api/v1/admin/exam-imports",
        headers=admin,
        data={
            "exam_name": "Publishable Imported Exam",
            "exam_revision_id": str(bank_rows_fixture.revision_id),
            "exam_level_id": str(bank_rows_fixture.level_id),
        },
        files={
            "exam_pdf": ("sample.pdf", b"pdf fixture", "application/pdf"),
            "answer_file": ("answers.txt", b"1 A\n2 B\n3 A\n", "text/plain"),
            "listening_audio": ("listening.mp3", b"ID3 fixture", "audio/mpeg"),
        },
    )
    job = client.get(f"/api/v1/admin/exam-imports/{response.json()['id']}", headers=admin).json()
    for question_id in job["parsed_document"]["created_question_ids"]:
        published = client.post(f"/api/v1/admin/question-bank/{question_id}/publish", headers=admin)
        assert published.status_code == 200, published.text
    validation = client.post(f"/api/v1/admin/exam-builder/{job['created_exam_version_id']}/validate", headers=admin)
    assert validation.status_code == 200, validation.text
    assert validation.json() == {"valid": True, "errors": []}
    published_exam = client.post(f"/api/v1/admin/exam-builder/{job['created_exam_version_id']}/publish", headers=admin)
    assert published_exam.status_code == 200, published_exam.text

    learner = bearer(register_user(client, email="phase4-learner@example.com")["access_token"])
    started = client.post(f"/api/v1/exams/{job['created_exam_id']}/start", headers=learner)
    assert started.status_code == 201, started.text
    assert started.json()["questions"][0]["question_type"] == "listening"
    assert "correct_option_ids" not in started.json()["questions"][0]["config"]
