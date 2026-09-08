from conftest import bearer, register_user
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_phase2_question_bank import BankRows, bank_rows  # noqa: F401

from app.database import SessionLocal
from app.models import ScoringPolicy, User


def _admin_headers(client: TestClient) -> dict[str, str]:
    tokens = register_user(client, email="phase3-admin@example.com")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "phase3-admin@example.com"))
        assert user is not None
        user.is_admin = True
        db.commit()
    return bearer(tokens["access_token"])


def _payload(rows: BankRows, scoring_id: int, title: str = "Phase 3 Exam") -> dict[str, object]:
    return {
        "title": title,
        "description": "Versioned exam",
        "exam_revision_id": rows.revision_id,
        "exam_level_id": rows.level_id,
        "scoring_policy_id": scoring_id,
        "duration_seconds": 600,
        "sections": [
            {
                "code": "VOCABULARY",
                "title": "Vocabulary",
                "skill": "vocabulary",
                "sort_order": 0,
                "duration_seconds": 300,
                "parts": [
                    {
                        "code": "VOCABULARY_1",
                        "title": "Part 1",
                        "sort_order": 0,
                        "questions": [
                            {"question_version_id": rows.version_id, "sort_order": 0, "points": 2, "required": True}
                        ],
                    }
                ],
            }
        ],
    }


def test_exam_builder_publish_runner_and_version_snapshot(client: TestClient, bank_rows: BankRows) -> None:  # noqa: F811
    with SessionLocal() as db:
        policy = ScoringPolicy(
            revision_id=bank_rows.revision_id,
            code="PHASE3_GENERIC",
            name="Phase 3 generic",
            version="1",
            policy_type="percentage",
            configuration={"passing_percentage": 60, "score_label": "Practice score"},
        )
        db.add(policy)
        db.commit()
        scoring_id = policy.id

    admin = _admin_headers(client)
    created = client.post("/api/v1/admin/exam-builder", headers=admin, json=_payload(bank_rows, scoring_id))
    assert created.status_code == 201, created.text
    version = created.json()
    assert version["version_number"] == 1
    assert version["sections"][0]["parts"][0]["questions"][0]["question_version_id"] == bank_rows.version_id

    listed = client.get("/api/v1/admin/exams", headers=admin)
    assert listed.status_code == 200, listed.text
    assert listed.json()["total"] == 1

    validation = client.post(f"/api/v1/admin/exam-builder/{version['id']}/validate", headers=admin)
    assert validation.status_code == 200, validation.text
    assert validation.json() == {"valid": True, "errors": []}

    published = client.post(f"/api/v1/admin/exam-builder/{version['id']}/publish", headers=admin)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    learner = bearer(register_user(client, email="phase3-learner@example.com")["access_token"])
    started = client.post(f"/api/v1/exams/{version['exam_id']}/start", headers=learner)
    assert started.status_code == 201, started.text
    attempt = started.json()
    assert attempt["exam_version_id"] == version["id"]
    assert attempt["questions"][0]["part_title"] == "Part 1"
    assert "correct_option_ids" not in attempt["questions"][0]["config"]

    question_id = attempt["questions"][0]["id"]
    saved = client.put(
        f"/api/v1/exam-attempts/{attempt['attempt_id']}/answers/{question_id}",
        headers=learner,
        json={"answer": "a"},
    )
    assert saved.status_code == 200, saved.text
    result = client.post(f"/api/v1/exam-attempts/{attempt['attempt_id']}/submit", headers=learner)
    assert result.status_code == 200, result.text
    assert result.json()["percentage"] == 100

    cloned = client.post(f"/api/v1/admin/exam-builder/{version['id']}/clone", headers=admin)
    assert cloned.status_code == 201, cloned.text
    clone = cloned.json()
    updated = _payload(bank_rows, scoring_id, title="Phase 3 Exam v2")
    patched = client.patch(f"/api/v1/admin/exam-builder/{clone['id']}", headers=admin, json=updated)
    assert patched.status_code == 200, patched.text
    published_v2 = client.post(f"/api/v1/admin/exam-builder/{clone['id']}/publish", headers=admin)
    assert published_v2.status_code == 200, published_v2.text

    old_result = client.get(f"/api/v1/exam-attempts/{attempt['attempt_id']}/result", headers=learner)
    assert old_result.status_code == 200
    assert old_result.json()["questions"][0]["prompt"] == "你好 means:"
