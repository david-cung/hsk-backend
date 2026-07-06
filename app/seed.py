import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Achievement, HskLevel, Lesson, MockTest, Question


CONTENT_DIR = Path(__file__).resolve().parent / "content"
LEVEL_CHARACTER_TOTALS = [150, 300, 600, 1200, 2500, 5000]
SORT_OFFSETS = {
    "hsk_curriculum_complete.json": 0,
    "conversation_lessons.json": 100,
    "conversation_quizzes.json": 200,
    "hsk1_reading_passages.json": 300,
}

ACHIEVEMENTS = [
    {"code": "first_quiz", "title": "First Quiz", "description": "Submit your first quiz.", "icon": "school"},
    {"code": "first_word", "title": "Word Collector", "description": "Save your first word.", "icon": "bookmark"},
    {"code": "three_lessons", "title": "Momentum", "description": "Complete three lessons.", "icon": "flame"},
]

MOCK_TESTS = [
    {"title": "HSK 1 Mini Mock Test", "hsk_level": 1, "duration_minutes": 20, "question_count": 20},
    {"title": "HSK 2 Mini Mock Test", "hsk_level": 2, "duration_minutes": 25, "question_count": 25},
    {"title": "HSK 3 Mini Mock Test", "hsk_level": 3, "duration_minutes": 35, "question_count": 30},
]


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _iter_content_lessons() -> list[tuple[dict[str, Any], str]]:
    lessons: list[tuple[dict[str, Any], str]] = []

    curriculum_path = CONTENT_DIR / "hsk_curriculum_complete.json"
    if curriculum_path.exists():
        curriculum = _load_json(curriculum_path)
        for level in curriculum.get("levels", []):
            for lesson in level.get("lessons", []):
                lessons.append((lesson, curriculum_path.name))

    for filename in ("conversation_lessons.json", "conversation_quizzes.json"):
        path = CONTENT_DIR / filename
        if path.exists():
            for lesson in _load_json(path):
                lessons.append((lesson, filename))

    reading_passages_path = CONTENT_DIR / "hsk1_reading_passages.json"
    if reading_passages_path.exists():
        for index, passage in enumerate(_load_json(reading_passages_path), start=2):
            lessons.append((_reading_passage_to_lesson(passage, index), reading_passages_path.name))

    return lessons


def _hsk_level_number(value: Any) -> int:
    if isinstance(value, int):
        return value
    return int(str(value).upper().replace("HSK", ""))


def _reading_passage_to_lesson(passage: dict[str, Any], index: int) -> dict[str, Any]:
    source_id = f"HSK1-REA-{index:03d}"
    answer_key = passage.get("answer_key", {})
    questions = []
    for question_index, question in enumerate(passage.get("comprehension_questions", []), start=1):
        question_id = question.get("id", f"q{question_index}")
        questions.append(
            {
                "id": f"{source_id}-Q{question_index:03d}",
                "type": "multiple_choice",
                "prompt": question.get("question", ""),
                "options": question.get("options", []),
                "tokens": [],
                "audio_text": "",
                "image_keyword": "",
                "correct_answer": answer_key.get(question_id, ""),
                "explanation": passage.get("explanation", ""),
            }
        )

    title = passage.get("title", f"Reading {index - 1:03d}").split(": ", 1)[-1]
    return {
        "id": source_id,
        "hsk_level": _hsk_level_number(passage.get("hsk_level", "HSK1")),
        "lesson_type": "reading",
        "title": f"HSK1 Reading: {title}",
        "estimated_duration_minutes": 10,
        "order": index,
        "learning_objectives": ["Read a short HSK1 passage", "Answer comprehension questions"],
        "vocabulary_list": [{"hanzi": word, "pinyin": "", "meaning_en": "", "meaning_vi": ""} for word in passage.get("vocabulary_list", [])],
        "grammar_points": [],
        "content": {
            "focus": "",
            "chinese": passage.get("chinese_text", ""),
            "pinyin": passage.get("pinyin", ""),
            "english": passage.get("english_translation", ""),
            "vietnamese": passage.get("vietnamese_translation", ""),
            "items": [],
            "questions": questions,
            "cultural_note": {"english": "", "vietnamese": ""},
        },
    }


def _meaning(english: str | None, vietnamese: str | None) -> str:
    return " / ".join(part for part in (english, vietnamese) if part)


def _chinese_entry(hanzi: str, pinyin: str = "", meaning: str = "") -> dict[str, str]:
    entry = {"hanzi": hanzi}
    if pinyin:
        entry["pinyin"] = pinyin
    if meaning:
        entry["meaning"] = meaning
    return entry


def _vocabulary_entries(lesson: dict[str, Any]) -> list[dict[str, str]]:
    return [
        _chinese_entry(
            item.get("hanzi", ""),
            item.get("pinyin", ""),
            _meaning(item.get("meaning_en"), item.get("meaning_vi")),
        )
        for item in lesson.get("vocabulary_list", [])
        if item.get("hanzi")
    ]


def _grammar_points(lesson: dict[str, Any]) -> list[dict[str, Any]]:
    points = []
    for item in lesson.get("grammar_points", []):
        usage = _meaning(item.get("usage_en"), item.get("usage_vi"))
        structure = item.get("structure") or ""
        explanation = usage
        if structure and usage:
            explanation = f"Structure: {structure}. {usage}"
        elif structure:
            explanation = f"Structure: {structure}."
        points.append(
            {
                "title": item.get("point", ""),
                "explanation": explanation or item.get("point", ""),
                "examples": [
                    _chinese_entry(
                        example.get("hanzi", example.get("Chinese", "")),
                        example.get("pinyin", example.get("Pinyin", "")),
                        _meaning(example.get("meaning_en", example.get("English")), example.get("meaning_vi", example.get("Vietnamese"))),
                    )
                    for example in item.get("examples", [])
                    if isinstance(example, dict)
                ],
            }
        )
    return points


def _content_entry(raw: dict[str, Any]) -> dict[str, str] | None:
    chinese = raw.get("chinese", "")
    if not chinese:
        return None
    return _chinese_entry(chinese, raw.get("pinyin", ""), _meaning(raw.get("english"), raw.get("vietnamese")))


def _mobile_content(lesson: dict[str, Any]) -> dict[str, Any]:
    raw = lesson.get("content", {})
    lesson_type = lesson.get("lesson_type", "")
    content: dict[str, Any] = {
        "source_id": lesson.get("id"),
        "focus": raw.get("focus", ""),
    }

    vocabulary = _vocabulary_entries(lesson)
    grammar_points = _grammar_points(lesson)
    if vocabulary:
        content["vocabulary"] = vocabulary
    if grammar_points:
        content["grammar_points"] = grammar_points

    text_entry = _content_entry(raw)
    if text_entry:
        if lesson_type == "reading":
            content["passage_title"] = lesson.get("title", "").split(": ", 1)[-1]
            content["passage"] = [text_entry]
        elif lesson_type == "listening":
            content["transcript"] = [text_entry]
        elif lesson_type == "conversation":
            content["dialogue"] = text_entry
        else:
            content["passage"] = [text_entry]

    items = raw.get("items", [])
    item_texts = [item.get("text", "") for item in items if item.get("text")]
    item_entries = [_chinese_entry(text) for text in item_texts]
    item_types = {item.get("type") for item in items}
    if "pattern" in item_types:
        content["patterns"] = item_entries
    elif "review_scope" in item_types:
        content["review_items"] = item_texts
    elif "activity" in item_types:
        content["activities"] = item_texts
    elif item_texts:
        content["items"] = item_texts

    translations = {
        "english": raw.get("english", ""),
        "vietnamese": raw.get("vietnamese", ""),
    }
    if translations["english"] or translations["vietnamese"]:
        content["translations"] = translations

    cultural_note = raw.get("cultural_note", {})
    if cultural_note.get("english") or cultural_note.get("vietnamese"):
        content["cultural_note"] = cultural_note

    return content


def _lesson_description(lesson: dict[str, Any]) -> str | None:
    objectives = lesson.get("learning_objectives", [])
    if objectives:
        return objectives[0]
    focus = lesson.get("content", {}).get("focus")
    return focus or None


def _question_prompt(question: dict[str, Any]) -> str:
    prompt = question.get("prompt", "")
    if question.get("audio_text"):
        prompt = f"{prompt}\nAudio: {question['audio_text']}"
    if question.get("image_keyword"):
        prompt = f"{prompt}\nImage: {question['image_keyword']}"
    if question.get("tokens"):
        prompt = f"{prompt}\nTokens: {' / '.join(question['tokens'])}"
    return prompt


def _ensure_levels(db: Session) -> dict[int, HskLevel]:
    levels = {level.level_number: level for level in db.scalars(select(HskLevel)).all()}
    for level_number in range(1, 7):
        if level_number not in levels:
            level = HskLevel(
                level_number=level_number,
                title=f"HSK {level_number}",
                description=f"Structured Mandarin lessons for HSK {level_number}.",
                total_characters=LEVEL_CHARACTER_TOTALS[level_number - 1],
            )
            db.add(level)
            levels[level_number] = level
    db.flush()
    return levels


def _upsert_content_lessons(db: Session, levels: dict[int, HskLevel]) -> None:
    existing_by_source_id = {
        lesson.content.get("source_id"): lesson
        for lesson in db.scalars(select(Lesson)).all()
        if isinstance(lesson.content, dict) and lesson.content.get("source_id")
    }

    for lesson_data, source_name in _iter_content_lessons():
        source_id = lesson_data["id"]
        hsk_level = int(lesson_data["hsk_level"])
        lesson = existing_by_source_id.get(source_id)
        if lesson is None:
            lesson = Lesson(hsk_level_id=levels[hsk_level].id)
            db.add(lesson)

        lesson.title = lesson_data["title"]
        lesson.description = _lesson_description(lesson_data)
        lesson.lesson_type = lesson_data["lesson_type"]
        lesson.sort_order = SORT_OFFSETS[source_name] + int(lesson_data["order"])
        lesson.duration_minutes = int(lesson_data["estimated_duration_minutes"])
        lesson.content = _mobile_content(lesson_data)
        db.flush()

        existing_questions = {
            question.sort_order: question
            for question in db.scalars(select(Question).where(Question.lesson_id == lesson.id)).all()
        }
        questions = lesson_data.get("content", {}).get("questions", [])
        for index, question_data in enumerate(questions, start=1):
            question = existing_questions.get(index)
            if question is None:
                question = Question(lesson_id=lesson.id, sort_order=index)
                db.add(question)
            question.question_type = question_data.get("type", "multiple_choice")
            question.prompt = _question_prompt(question_data)
            question.options = question_data.get("options") or None
            question.correct_answer = question_data.get("correct_answer", "")
            question.explanation = question_data.get("explanation", "")


def _upsert_achievements(db: Session) -> None:
    existing = {achievement.code: achievement for achievement in db.scalars(select(Achievement)).all()}
    for item in ACHIEVEMENTS:
        achievement = existing.get(item["code"])
        if achievement is None:
            achievement = Achievement(code=item["code"])
            db.add(achievement)
        achievement.title = item["title"]
        achievement.description = item["description"]
        achievement.icon = item["icon"]


def _upsert_mock_tests(db: Session) -> None:
    existing = {mock_test.title: mock_test for mock_test in db.scalars(select(MockTest)).all()}
    for item in MOCK_TESTS:
        mock_test = existing.get(item["title"])
        if mock_test is None:
            mock_test = MockTest(title=item["title"])
            db.add(mock_test)
        mock_test.hsk_level = item["hsk_level"]
        mock_test.duration_minutes = item["duration_minutes"]
        mock_test.question_count = item["question_count"]


def seed_data(db: Session) -> None:
    levels = _ensure_levels(db)
    _upsert_content_lessons(db, levels)
    _upsert_achievements(db)
    _upsert_mock_tests(db)
    db.commit()
