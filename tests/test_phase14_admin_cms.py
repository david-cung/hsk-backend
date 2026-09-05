from datetime import UTC, datetime

from conftest import bearer, register_user
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.admin_cms_service import log_admin_action
from app.database import SessionLocal
from app.models import AdminAuditLog, Course, HskLevel, Lesson, User, Vocabulary


def _headers(client: TestClient, email: str, admin: bool = False) -> dict[str, str]:
    tokens = register_user(client, email=email)
    if admin:
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            assert user is not None
            user.is_admin = True
            db.commit()
    return bearer(tokens["access_token"])


def _seed_course_and_lesson(admin: dict[str, str], client: TestClient) -> tuple[int, int]:
    with SessionLocal() as db:
        if db.get(HskLevel, 1) is None:
            db.add(HskLevel(id=1, level_number=1, title="HSK 1", display_order=1, total_characters=150))
            db.commit()
    course = client.post(
        "/api/v1/admin/content/courses",
        headers=admin,
        json={
            "hsk_level_id": 1,
            "title": "Admin Course",
            "course_type": "phase14",
            "order": 44,
            "status": "draft",
        },
    )
    assert course.status_code == 201, course.text
    lesson = client.post(
        "/api/v1/admin/content/lessons",
        headers=admin,
        json={
            "course_id": course.json()["id"],
            "title": "Admin Lesson",
            "lesson_type": "vocabulary",
            "order": 1,
            "status": "draft",
            "content": {"title_translations": {"en": "Admin Lesson", "vi": "Bai admin"}},
        },
    )
    assert lesson.status_code == 201, lesson.text
    return course.json()["id"], lesson.json()["id"]


def test_admin_cms_authorization_dashboard_and_search(client: TestClient) -> None:
    normal = _headers(client, "normal-phase14@example.com")
    admin = _headers(client, "admin-phase14@example.com", admin=True)

    assert client.get("/api/v1/admin/cms/dashboard").status_code == 401
    assert client.get("/api/v1/admin/cms/dashboard", headers=normal).status_code == 403

    dashboard = client.get("/api/v1/admin/cms/dashboard", headers=admin)
    assert dashboard.status_code == 200
    keys = {item["key"] for item in dashboard.json()["metrics"]}
    assert {"hsk_levels", "courses", "lessons", "vocabulary", "grammar", "exercises", "audio", "exams"} <= keys

    _seed_course_and_lesson(admin, client)
    search = client.get(
        "/api/v1/admin/cms/search?query=Admin&content_type=lessons&page_size=5",
        headers=admin,
    )
    assert search.status_code == 200
    assert search.json()["total"] >= 1
    assert search.json()["items"][0]["entity_type"] == "lessons"

    ready_search = client.get("/api/v1/admin/cms/search?status=READY", headers=admin)
    assert ready_search.status_code == 200


def test_publish_archive_validation_audit_and_mobile_visibility(client: TestClient) -> None:
    admin = _headers(client, "publisher-phase14@example.com", admin=True)
    _, lesson_id = _seed_course_and_lesson(admin, client)

    invalid_publish = client.post(
        f"/api/v1/admin/cms/publish/lessons/{lesson_id}",
        headers=admin,
        json={},
    )
    assert invalid_publish.status_code == 200
    assert invalid_publish.json()["valid"] is True

    mobile = client.get(f"/api/v1/lessons/{lesson_id}", headers=admin)
    assert mobile.status_code == 200
    assert mobile.json()["title"] == "Admin Lesson"

    archive = client.post(
        f"/api/v1/admin/cms/archive/lessons/{lesson_id}",
        headers=admin,
        json={},
    )
    assert archive.status_code == 200
    assert client.get(f"/api/v1/lessons/{lesson_id}", headers=admin).status_code == 404

    audit = client.get("/api/v1/admin/cms/audit?entity_type=lessons", headers=admin)
    assert audit.status_code == 200
    actions = [item["action"] for item in audit.json()["items"]]
    assert "published" in actions
    assert "archived" in actions


def test_concurrency_conflict_uses_updated_at(client: TestClient) -> None:
    admin = _headers(client, "concurrency-phase14@example.com", admin=True)
    _, lesson_id = _seed_course_and_lesson(admin, client)
    with SessionLocal() as db:
        lesson = db.get(Lesson, lesson_id)
        assert lesson is not None
        stale = lesson.updated_at.replace(tzinfo=UTC).isoformat()
        lesson.title = "Updated elsewhere"
        lesson.updated_at = datetime(2026, 2, 1, tzinfo=UTC)
        db.commit()

    conflict = client.post(
        f"/api/v1/admin/cms/publish/lessons/{lesson_id}",
        headers=admin,
        json={"expected_updated_at": stale},
    )
    assert conflict.status_code == 409


def test_import_preview_export_and_audit_secret_redaction(client: TestClient) -> None:
    admin = _headers(client, "import-preview-phase14@example.com", admin=True)
    preview = client.post(
        "/api/v1/admin/cms/imports/preview",
        headers=admin,
        json={
            "entity_type": "vocabulary",
            "source_format": "json",
            "data": [
                {
                    "hsk_level": 1,
                    "simplified": "管理",
                    "pinyin": "guan3 li3",
                    "meaning_translations": {"en": "manage", "vi": "quan ly"},
                }
            ],
        },
    )
    assert preview.status_code == 200
    assert preview.json()["records_to_create"] == 1

    exported = client.get("/api/v1/admin/cms/export/vocabulary?format=json", headers=admin)
    assert exported.status_code == 200
    assert exported.headers["content-disposition"].endswith('filename="vocabulary.json"')

    with SessionLocal() as db:
        admin_user = db.scalar(select(User).where(User.email == "import-preview-phase14@example.com"))
        assert admin_user is not None
        log = log_admin_action(
            db,
            admin_user,
            "test",
            "vocabulary",
            1,
            {"token": "secret", "safe": "value"},
        )
        db.commit()
        db.refresh(log)
        count = db.scalar(select(func.count(AdminAuditLog.id)))
        assert log.metadata_json == {"safe": "value"}
    assert count and count >= 1


def test_admin_created_vocabulary_grammar_lesson_are_available_to_mobile(client: TestClient) -> None:
    admin = _headers(client, "mobile-compat-phase14@example.com", admin=True)
    _, lesson_id = _seed_course_and_lesson(admin, client)
    vocab = client.post(
        "/api/v1/admin/content/vocabulary",
        headers=admin,
        json={
            "hsk_level_id": 1,
            "simplified": "内容",
            "pinyin": "nei4 rong2",
            "meaning_translations": {"en": "content", "vi": "noi dung"},
            "lesson_ids": [lesson_id],
        },
    )
    assert vocab.status_code == 201, vocab.text
    client.post(f"/api/v1/admin/cms/publish/lessons/{lesson_id}", headers=admin, json={})

    mobile_lesson = client.get(f"/api/v1/lessons/{lesson_id}", headers=admin)
    assert mobile_lesson.status_code == 200
    assert mobile_lesson.json()["vocabulary"][0]["simplified"] == "内容"

    with SessionLocal() as db:
        assert db.scalar(select(Course).where(Course.title == "Admin Course")) is not None
        assert db.scalar(select(HskLevel).where(HskLevel.level_number == 1)) is not None
        assert db.scalar(select(Vocabulary).where(Vocabulary.simplified == "内容")) is not None
