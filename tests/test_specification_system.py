from conftest import bearer, register_user
from fastapi.testclient import TestClient

from app.database import SessionLocal
from app.models import ContentStatus, ExamLevel, ExamRevision, ExamSpecification, ExamStandard
from app.specification_schemas import ExamBlueprint, normalize_blueprint


def _metadata_fixture() -> tuple[int, int, int]:
    with SessionLocal() as db:
        standard = ExamStandard(code="TEST_HSK", name="Test HSK", status=ContentStatus.PUBLISHED)
        specification = ExamSpecification(
            standard=standard, code="TEST_SPEC", name="Test specification", status=ContentStatus.PUBLISHED
        )
        revision = ExamRevision(
            specification=specification, code="TEST_REVISION", version="1", name="Test revision",
            status=ContentStatus.PUBLISHED, is_default=True,
        )
        db.add_all([standard, specification, revision])
        db.flush()
        levels = [
            ExamLevel(
                revision_id=revision.id, code="TEST_1", level_number=1, display_name="Test Level 1",
                sort_order=1, status=ContentStatus.PUBLISHED,
            ),
            ExamLevel(
                revision_id=revision.id, code="TEST_2", level_number=2, display_name="Test Level 2",
                sort_order=2, status=ContentStatus.PUBLISHED,
            ),
        ]
        db.add_all(levels)
        db.commit()
        return standard.id, specification.id, revision.id


def test_metadata_api_and_revision_scoped_levels(client: TestClient) -> None:
    standard_id, specification_id, revision_id = _metadata_fixture()
    tokens = register_user(client)
    headers = bearer(tokens["access_token"])

    standards = client.get("/api/v1/exam-standards", headers=headers)
    assert standards.status_code == 200
    assert any(item["code"] == "TEST_HSK" for item in standards.json())

    specifications = client.get(f"/api/v1/exam-specifications?standard_id={standard_id}", headers=headers)
    assert specifications.status_code == 200
    assert any(item["id"] == specification_id for item in specifications.json())

    revisions = client.get(f"/api/v1/exam-revisions?specification_id={specification_id}", headers=headers)
    assert revisions.status_code == 200
    levels = client.get(f"/api/v1/exam-revisions/{revision_id}/levels", headers=headers)
    assert levels.status_code == 200
    assert [item["level_number"] for item in levels.json()] == [1, 2]


def test_profile_can_store_specification_aware_learning_target(client: TestClient) -> None:
    _, _, revision_id = _metadata_fixture()
    with SessionLocal() as db:
        level_id = db.query(ExamLevel).filter_by(revision_id=revision_id, level_number=2).one().id
    tokens = register_user(client)
    response = client.patch(
        "/api/v1/profile",
        headers=bearer(tokens["access_token"]),
        json={"target_exam_revision_id": revision_id, "target_exam_level_id": level_id},
    )
    assert response.status_code == 200, response.text
    assert response.json()["target_exam_revision_id"] == revision_id
    assert response.json()["target_exam_level_id"] == level_id
    assert response.json()["target_hsk_level"] == 2


def test_blueprint_contract_requires_explicit_version_and_sections() -> None:
    blueprint = normalize_blueprint(
        {"sections": [{"type": "READING", "question_count": 5, "duration_minutes": 10}]},
        revision_id=42,
    )
    assert blueprint["schema_version"] == 1
    assert blueprint["revision_id"] == 42
    assert ExamBlueprint.model_validate(blueprint).sections[0].type == "READING"
