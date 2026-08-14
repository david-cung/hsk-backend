from dataclasses import dataclass

import pytest
from conftest import bearer, register_user
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.database import SessionLocal
from app.models import (
    ContentStatus,
    Course,
    ExampleSentence,
    GrammarExample,
    GrammarPoint,
    HskLevel,
    Lesson,
    LessonGrammarPoint,
    LessonVocabulary,
    User,
    Vocabulary,
    VocabularyExample,
)
from app.seed import seed_data


@dataclass
class ContentRows:
    level_1: HskLevel
    level_2: HskLevel
    course_1: Course
    course_2: Course
    lesson_1: Lesson
    lesson_2: Lesson
    vocabulary_1: Vocabulary
    vocabulary_2: Vocabulary
    grammar: GrammarPoint


@pytest.fixture
def content_rows() -> ContentRows:
    with SessionLocal() as db:
        level_1 = HskLevel(
            level_number=1,
            title="HSK 1",
            description="Beginner",
            total_characters=150,
            display_order=1,
        )
        level_2 = HskLevel(
            level_number=2,
            title="HSK 2",
            description="Elementary",
            total_characters=300,
            display_order=2,
        )
        db.add_all([level_1, level_2])
        db.flush()
        course_1 = Course(
            hsk_level_id=level_1.id,
            title="HSK 1 Vocabulary",
            course_type="vocabulary",
            sort_order=1,
        )
        course_2 = Course(
            hsk_level_id=level_2.id,
            title="HSK 2 Vocabulary",
            course_type="vocabulary",
            sort_order=1,
        )
        db.add_all([course_1, course_2])
        db.flush()
        lesson_1 = Lesson(
            hsk_level_id=level_1.id,
            course_id=course_1.id,
            title="Greetings",
            lesson_type="vocabulary",
            sort_order=1,
            duration_minutes=10,
            content={"reading": {"chinese": "你好"}},
        )
        lesson_2 = Lesson(
            hsk_level_id=level_2.id,
            course_id=course_2.id,
            title="Travel",
            lesson_type="vocabulary",
            sort_order=1,
            duration_minutes=12,
            content={},
        )
        db.add_all([lesson_1, lesson_2])
        db.flush()
        example = ExampleSentence(
            chinese="你好！",
            pinyin="ni3 hao3",
            translations={"en": "Hello!", "vi": "Xin chào!"},
        )
        db.add(example)
        db.flush()
        vocabulary_1 = Vocabulary(
            hsk_level_id=level_1.id,
            simplified="你好",
            traditional="你好",
            pinyin="ni3 hao3",
            meaning_translations={"en": "hello", "vi": "xin chào"},
            part_of_speech="phrase",
            display_order=1,
        )
        vocabulary_2 = Vocabulary(
            hsk_level_id=level_2.id,
            simplified="旅行",
            traditional="旅行",
            pinyin="lü3 xing2",
            meaning_translations={"en": "travel", "vi": "du lịch"},
            part_of_speech="verb",
            display_order=1,
        )
        grammar = GrammarPoint(
            hsk_level_id=level_1.id,
            title="吗 questions",
            explanation_translations={
                "en": "Add 吗 to form a yes/no question.",
                "vi": "Thêm 吗 để tạo câu hỏi có/không.",
            },
            pattern="Statement + 吗？",
            display_order=1,
        )
        db.add_all([vocabulary_1, vocabulary_2, grammar])
        db.flush()
        db.add_all(
            [
                LessonVocabulary(
                    lesson_id=lesson_1.id,
                    vocabulary_id=vocabulary_1.id,
                    sort_order=1,
                ),
                LessonVocabulary(
                    lesson_id=lesson_2.id,
                    vocabulary_id=vocabulary_2.id,
                    sort_order=1,
                ),
                VocabularyExample(
                    vocabulary_id=vocabulary_1.id,
                    example_id=example.id,
                    sort_order=1,
                ),
                LessonGrammarPoint(
                    lesson_id=lesson_1.id,
                    grammar_point_id=grammar.id,
                    sort_order=1,
                ),
                GrammarExample(
                    grammar_point_id=grammar.id,
                    example_id=example.id,
                    sort_order=1,
                ),
            ]
        )
        db.commit()
        for row in (
            level_1,
            level_2,
            course_1,
            course_2,
            lesson_1,
            lesson_2,
            vocabulary_1,
            vocabulary_2,
            grammar,
        ):
            db.refresh(row)
            db.expunge(row)
        return ContentRows(
            level_1,
            level_2,
            course_1,
            course_2,
            lesson_1,
            lesson_2,
            vocabulary_1,
            vocabulary_2,
            grammar,
        )


def _registered_headers(
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


def test_hsk_course_and_lesson_apis(
    client: TestClient, content_rows: ContentRows
) -> None:
    levels = client.get("/api/v1/hsk/levels")
    assert levels.status_code == 200
    assert [item["level_number"] for item in levels.json()] == [1, 2]
    assert levels.json()[0]["course_count"] == 1

    courses = client.get("/api/v1/courses?hsk_level=1")
    assert courses.status_code == 200
    assert [item["id"] for item in courses.json()] == [content_rows.course_1.id]
    detail = client.get(f"/api/v1/courses/{content_rows.course_1.id}")
    assert detail.status_code == 200
    assert detail.json()["hsk_level"] == 1

    lessons = client.get(
        f"/api/v1/courses/{content_rows.course_1.id}/lessons"
    )
    assert lessons.status_code == 200
    assert lessons.json()[0]["course_id"] == content_rows.course_1.id
    lesson = client.get(f"/api/v1/lessons/{content_rows.lesson_1.id}")
    assert lesson.status_code == 200
    assert lesson.json()["vocabulary"][0]["simplified"] == "你好"
    assert lesson.json()["grammar"][0]["title"] == "吗 questions"
    assert lesson.json()["reading"] == {"chinese": "你好"}


def test_vocabulary_list_search_detail_and_filters(
    client: TestClient, content_rows: ContentRows
) -> None:
    page = client.get("/api/v1/vocabulary?page=1&page_size=1")
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["pages"] == 2
    assert len(page.json()["items"]) == 1

    search = client.get("/api/v1/vocabulary?search=%E4%BD%A0")
    assert search.status_code == 200
    assert [item["simplified"] for item in search.json()["items"]] == ["你好"]
    by_level = client.get("/api/v1/vocabulary?hsk_level=2")
    assert [item["simplified"] for item in by_level.json()["items"]] == ["旅行"]
    by_lesson = client.get(
        f"/api/v1/lessons/{content_rows.lesson_1.id}/vocabulary"
    )
    assert [item["id"] for item in by_lesson.json()["items"]] == [
        content_rows.vocabulary_1.id
    ]
    detail = client.get(f"/api/v1/vocabulary/{content_rows.vocabulary_1.id}")
    assert detail.status_code == 200
    assert detail.json()["examples"][0]["chinese"] == "你好！"
    assert detail.json()["lessons"][0]["id"] == content_rows.lesson_1.id


def test_favorites_and_learning_status_are_user_isolated(
    client: TestClient, content_rows: ContentRows
) -> None:
    user_a = _registered_headers(client, "a@example.com")
    user_b = _registered_headers(client, "b@example.com")
    vocabulary_id = content_rows.vocabulary_1.id

    favorite = client.post(
        f"/api/v1/vocabulary/{vocabulary_id}/favorite", headers=user_a
    )
    assert favorite.status_code == 201
    assert favorite.json()["is_favorite"] is True
    assert (
        client.get("/api/v1/vocabulary/favorites", headers=user_a).json()["total"]
        == 1
    )
    assert (
        client.get("/api/v1/vocabulary/favorites", headers=user_b).json()["total"]
        == 0
    )
    assert (
        client.get(
            f"/api/v1/vocabulary/{vocabulary_id}", headers=user_b
        ).json()["is_favorite"]
        is False
    )

    viewed = client.post(
        f"/api/v1/vocabulary/{vocabulary_id}/view", headers=user_a
    )
    assert viewed.status_code == 200
    learned = client.patch(
        f"/api/v1/vocabulary/{vocabulary_id}/status",
        headers=user_a,
        json={"status": "learned"},
    )
    assert learned.json()["status"] == "learned"
    assert (
        client.get(
            f"/api/v1/vocabulary/{vocabulary_id}", headers=user_b
        ).json()["learning_status"]
        == "new"
    )
    assert (
        client.delete(
            f"/api/v1/vocabulary/{vocabulary_id}/favorite", headers=user_a
        ).status_code
        == 204
    )


def test_grammar_and_progress_hooks(
    client: TestClient, content_rows: ContentRows
) -> None:
    headers = _registered_headers(client, "progress@example.com")
    grammar = client.get(
        f"/api/v1/lessons/{content_rows.lesson_1.id}/grammar", headers=headers
    )
    assert grammar.status_code == 200
    assert grammar.json()[0]["id"] == content_rows.grammar.id
    detail = client.get(
        f"/api/v1/grammar/{content_rows.grammar.id}", headers=headers
    )
    assert detail.json()["examples"][0]["chinese"] == "你好！"
    assert client.post(
        f"/api/v1/grammar/{content_rows.grammar.id}/view", headers=headers
    ).json()["status"] == "viewed"
    assert client.post(
        f"/api/v1/grammar/{content_rows.grammar.id}/complete", headers=headers
    ).json()["status"] == "completed"
    assert client.post(
        f"/api/v1/lessons/{content_rows.lesson_1.id}/start", headers=headers
    ).json()["status"] == "in_progress"
    assert client.post(
        f"/api/v1/lessons/{content_rows.lesson_1.id}/complete", headers=headers
    ).json()["status"] == "completed"


def test_admin_content_crud_and_authorization(
    client: TestClient, content_rows: ContentRows
) -> None:
    normal = _registered_headers(client, "normal@example.com")
    admin = _registered_headers(client, "admin@example.com", admin=True)
    denied = client.post(
        "/api/v1/admin/content/courses",
        headers=normal,
        json={
            "hsk_level_id": content_rows.level_1.id,
            "title": "Denied",
            "course_type": "denied",
            "order": 3,
        },
    )
    assert denied.status_code == 403

    level = client.post(
        "/api/v1/admin/content/hsk-levels",
        headers=admin,
        json={
            "level_number": 3,
            "name": "HSK 3",
            "display_order": 3,
            "total_characters": 600,
        },
    )
    assert level.status_code == 201
    level_id = level.json()["id"]
    assert client.patch(
        f"/api/v1/admin/content/hsk-levels/{level_id}",
        headers=admin,
        json={"description": "Intermediate"},
    ).status_code == 200
    assert client.delete(
        f"/api/v1/admin/content/hsk-levels/{level_id}", headers=admin
    ).status_code == 204

    course = client.post(
        "/api/v1/admin/content/courses",
        headers=admin,
        json={
            "hsk_level_id": content_rows.level_1.id,
            "title": "Conversation",
            "course_type": "conversation",
            "order": 3,
        },
    )
    assert course.status_code == 201
    course_id = course.json()["id"]
    assert client.patch(
        f"/api/v1/admin/content/courses/{course_id}",
        headers=admin,
        json={"title": "Conversation Updated"},
    ).status_code == 200

    lesson = client.post(
        "/api/v1/admin/content/lessons",
        headers=admin,
        json={
            "course_id": course_id,
            "title": "Introductions",
            "lesson_type": "conversation",
            "order": 1,
        },
    )
    assert lesson.status_code == 201
    lesson_id = lesson.json()["id"]
    assert client.patch(
        f"/api/v1/admin/content/lessons/{lesson_id}",
        headers=admin,
        json={"estimated_duration": 15},
    ).status_code == 200

    example = client.post(
        "/api/v1/admin/content/example-sentences",
        headers=admin,
        json={
            "chinese": "谢谢。",
            "pinyin": "xie4 xie5",
            "translations": {"en": "Thank you.", "vi": "Cảm ơn."},
        },
    )
    assert example.status_code == 201
    example_id = example.json()["id"]
    assert client.patch(
        f"/api/v1/admin/content/example-sentences/{example_id}",
        headers=admin,
        json={"translations": {"en": "Thanks.", "vi": "Cảm ơn."}},
    ).status_code == 200

    vocabulary = client.post(
        "/api/v1/admin/content/vocabulary",
        headers=admin,
        json={
            "hsk_level_id": content_rows.level_1.id,
            "simplified": "谢谢",
            "pinyin": "xie4 xie5",
            "meaning_translations": {"en": "thanks", "vi": "cảm ơn"},
            "lesson_ids": [lesson_id],
            "example_ids": [example_id],
        },
    )
    assert vocabulary.status_code == 201
    vocabulary_id = vocabulary.json()["id"]
    assert client.patch(
        f"/api/v1/admin/content/vocabulary/{vocabulary_id}",
        headers=admin,
        json={"part_of_speech": "phrase"},
    ).status_code == 200

    grammar = client.post(
        "/api/v1/admin/content/grammar",
        headers=admin,
        json={
            "hsk_level_id": content_rows.level_1.id,
            "title": "很 adjective",
            "explanation_translations": {
                "en": "Use 很 before an adjective.",
                "vi": "Dùng 很 trước tính từ.",
            },
            "lesson_ids": [lesson_id],
            "example_ids": [example_id],
        },
    )
    assert grammar.status_code == 201
    grammar_id = grammar.json()["id"]
    assert client.patch(
        f"/api/v1/admin/content/grammar/{grammar_id}",
        headers=admin,
        json={"pattern": "Subject + 很 + adjective"},
    ).status_code == 200

    for path in (
        f"/api/v1/admin/content/grammar/{grammar_id}",
        f"/api/v1/admin/content/vocabulary/{vocabulary_id}",
        f"/api/v1/admin/content/example-sentences/{example_id}",
        f"/api/v1/admin/content/lessons/{lesson_id}",
        f"/api/v1/admin/content/courses/{course_id}",
    ):
        assert client.delete(path, headers=admin).status_code == 204


def test_content_import_json_csv_upsert_and_validation(
    client: TestClient, content_rows: ContentRows
) -> None:
    admin = _registered_headers(client, "importer@example.com", admin=True)
    vocabulary_record = {
        "hsk_level": 1,
        "simplified": "谢谢",
        "pinyin": "xie4 xie5",
        "meaning_translations": {"en": "thanks", "vi": "cảm ơn"},
        "part_of_speech": "phrase",
        "order": 9,
    }
    imported = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "vocabulary",
            "source_format": "json",
            "data": [vocabulary_record],
        },
    )
    assert imported.status_code == 201
    assert imported.json()["created_records"] == 1
    repeated = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "vocabulary",
            "source_format": "json",
            "data": [vocabulary_record],
        },
    )
    assert repeated.status_code == 201
    assert repeated.json()["updated_records"] == 1

    csv_data = (
        "hsk_level,course_type,title,description,order,status\n"
        "1,conversation,Imported conversation,Imported from CSV,4,published\n"
    )
    csv_import = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "courses",
            "source_format": "csv",
            "data": csv_data,
        },
    )
    assert csv_import.status_code == 201
    assert csv_import.json()["created_records"] == 1

    duplicate = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "vocabulary",
            "source_format": "json",
            "data": [vocabulary_record, vocabulary_record],
        },
    )
    assert duplicate.status_code == 422
    assert "job_id" in duplicate.json()["detail"]

    rollback = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "vocabulary",
            "source_format": "json",
            "data": [
                {
                    **vocabulary_record,
                    "simplified": "回滚",
                    "pinyin": "hui2 gun3",
                },
                {
                    **vocabulary_record,
                    "hsk_level": 6,
                    "simplified": "不存在",
                    "pinyin": "bu4 cun2 zai4",
                },
            ],
        },
    )
    assert rollback.status_code == 422
    with SessionLocal() as db:
        assert not db.scalar(
            select(Vocabulary).where(Vocabulary.simplified == "回滚")
        )

    invalid = client.post(
        "/api/v1/admin/content/imports",
        headers=admin,
        json={
            "entity_type": "vocabulary",
            "source_format": "json",
            "data": [{"hsk_level": 1, "simplified": ""}],
        },
    )
    assert invalid.status_code == 422


def test_existing_seed_is_normalized_without_duplicates() -> None:
    with SessionLocal() as db:
        seed_data(db)
        counts = {
            "levels": db.scalar(select(func.count()).select_from(HskLevel)),
            "courses": db.scalar(select(func.count()).select_from(Course)),
            "lessons": db.scalar(select(func.count()).select_from(Lesson)),
            "vocabulary": db.scalar(select(func.count()).select_from(Vocabulary)),
            "grammar": db.scalar(select(func.count()).select_from(GrammarPoint)),
        }
        assert counts == {
            "levels": 6,
            "courses": 66,
            "lessons": 685,
            "vocabulary": 483,
            "grammar": 141,
        }
        assert (
            db.scalar(
                select(func.count()).select_from(Lesson).where(
                    Lesson.course_id.is_(None)
                )
            )
            == 0
        )
        seed_data(db)
        assert db.scalar(select(func.count()).select_from(Vocabulary)) == 483
        assert db.scalar(select(func.count()).select_from(GrammarPoint)) == 141
        assert all(
            status == ContentStatus.PUBLISHED
            for status in db.scalars(select(HskLevel.status)).all()
        )
