import csv
import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from io import StringIO
from typing import Any, Literal, cast

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AudioAsset,
    ContentStatus,
    Course,
    ExampleSentence,
    Exercise,
    ExerciseSet,
    ExerciseType,
    GrammarExample,
    GrammarPoint,
    HskLevel,
    ImportEntityType,
    ImportJob,
    ImportJobStatus,
    Lesson,
    LessonGrammarPoint,
    LessonVocabulary,
    Question,
    SavedWord,
    Vocabulary,
    VocabularyExample,
)
from app.practice_engine import (
    ChoiceConfiguration,
    MatchingConfiguration,
    MultipleSelectConfiguration,
    OrderingConfiguration,
    TextConfiguration,
    canonical_exercise_type,
    validate_question_configuration,
)
from app.question_service import sync_question_version

COURSE_TYPE_ORDER = {
    "mixed": 1,
    "vocabulary": 2,
    "grammar": 3,
    "reading": 4,
    "listening": 5,
    "writing": 6,
    "sentence_pattern": 7,
    "conversation": 8,
    "practice": 9,
    "review": 10,
    "quiz": 11,
}


class ImportValidationError(ValueError):
    def __init__(self, job_id: int, errors: list[dict[str, Any]]) -> None:
        super().__init__("Content import validation failed")
        self.job_id = job_id
        self.errors = errors


class ImportRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = Field(default=None, ge=1)
    status: ContentStatus = ContentStatus.PUBLISHED
    metadata: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def decode_csv_json_fields(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        result = dict(value)
        for key in (
            "metadata",
            "title_translations",
            "description_translations",
            "meaning_translations",
            "explanation_translations",
            "translations",
            "lesson_ids",
            "example_ids",
            "content",
            "configuration",
            "questions",
        ):
            raw = result.get(key)
            if isinstance(raw, str) and raw.strip().startswith(("{", "[")):
                result[key] = json.loads(raw)
            elif raw == "":
                result[key] = None
        return result


class HskLevelImport(ImportRecord):
    level_number: int = Field(ge=1, le=6)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    display_order: int = Field(ge=0)
    total_characters: int = Field(default=0, ge=0)


class CourseImport(ImportRecord):
    hsk_level: int = Field(ge=1, le=6)
    course_type: str = Field(min_length=1, max_length=40)
    title: str = Field(min_length=1, max_length=180)
    title_translations: dict[str, str] | None = None
    description: str | None = None
    description_translations: dict[str, str] | None = None
    thumbnail_url: str | None = Field(default=None, max_length=500)
    order: int = Field(ge=0)


class LessonImport(ImportRecord):
    course_id: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=180)
    description: str | None = None
    lesson_type: str = Field(min_length=1, max_length=40)
    order: int = Field(ge=0)
    estimated_duration: int = Field(default=10, ge=1, le=600)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    listening_audio_asset_id: int | None = Field(default=None, ge=1)
    content: dict[str, Any] | None = None


class VocabularyImport(ImportRecord):
    hsk_level: int = Field(ge=1, le=6)
    simplified: str = Field(min_length=1, max_length=80)
    traditional: str | None = Field(default=None, max_length=80)
    pinyin: str | None = Field(default=None, max_length=160)
    meaning_translations: dict[str, str]
    part_of_speech: str = Field(default="other", min_length=1, max_length=40)
    category: str | None = Field(default=None, max_length=120)
    audio_asset_id: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    order: int = Field(default=0, ge=0)
    lesson_ids: list[int] = Field(default_factory=list)
    example_ids: list[int] = Field(default_factory=list)

    @model_validator(mode="after")
    def require_pinyin_or_exception(self) -> "VocabularyImport":
        if not (self.pinyin or "").strip() and not (
            self.metadata or {}
        ).get("pinyin_not_available"):
            raise ValueError(
                "pinyin is required; set metadata.pinyin_not_available only for verified legacy gaps"
            )
        if not any(str(value).strip() for value in self.meaning_translations.values()):
            raise ValueError("meaning_translations must contain a non-empty translation")
        return self


class GrammarImport(ImportRecord):
    hsk_level: int = Field(ge=1, le=6)
    title: str = Field(min_length=1, max_length=180)
    title_translations: dict[str, str] | None = None
    explanation_translations: dict[str, str]
    pattern: str | None = Field(default=None, max_length=500)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    order: int = Field(default=0, ge=0)
    lesson_ids: list[int] = Field(default_factory=list)
    example_ids: list[int] = Field(default_factory=list)


class ExampleSentenceImport(ImportRecord):
    chinese: str = Field(min_length=1)
    pinyin: str | None = None
    translations: dict[str, str]
    audio_asset_id: int | None = Field(default=None, ge=1)


class ExerciseQuestionImport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int | None = Field(default=None, ge=1)
    external_id: str = Field(min_length=1, max_length=180)
    question_type: str
    prompt: str = Field(min_length=1)
    instruction: str | None = None
    explanation: str | None = None
    difficulty: int | None = Field(default=None, ge=1, le=6)
    points: int = Field(default=1, ge=1, le=100)
    order: int = Field(ge=0)
    configuration: dict[str, Any]
    status: ContentStatus = ContentStatus.PUBLISHED
    metadata: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_configuration(self) -> "ExerciseQuestionImport":
        question_type = canonical_exercise_type(self.question_type)
        self.question_type = question_type.value
        self.configuration = validate_question_configuration(
            question_type, self.configuration
        ).model_dump()
        return self


class ExerciseImport(ImportRecord):
    lesson_id: int = Field(ge=1)
    exercise_set_slug: str = Field(
        default="lesson-practice", min_length=1, max_length=160
    )
    exercise_set_title: str | None = Field(
        default=None, min_length=1, max_length=180
    )
    exercise_set_order: int = Field(default=0, ge=0)
    external_id: str = Field(min_length=1, max_length=180)
    exercise_type: str
    title: str = Field(min_length=1, max_length=180)
    instruction: str | None = None
    skill: str | None = Field(default=None, max_length=40)
    vocabulary_id: int | None = Field(default=None, ge=1)
    grammar_point_id: int | None = Field(default=None, ge=1)
    difficulty: int | None = Field(default=None, ge=1, le=6)
    order: int = Field(ge=0)
    questions: list[ExerciseQuestionImport] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_exercise(self) -> "ExerciseImport":
        self.exercise_type = canonical_exercise_type(self.exercise_type).value
        external_ids = [question.external_id for question in self.questions]
        orders = [question.order for question in self.questions]
        if len(external_ids) != len(set(external_ids)):
            raise ValueError("question external ids must be unique in an exercise")
        if len(orders) != len(set(orders)):
            raise ValueError("question order values must be unique in an exercise")
        return self


IMPORT_MODELS: dict[ImportEntityType, type[ImportRecord]] = {
    ImportEntityType.HSK_LEVELS: HskLevelImport,
    ImportEntityType.COURSES: CourseImport,
    ImportEntityType.LESSONS: LessonImport,
    ImportEntityType.VOCABULARY: VocabularyImport,
    ImportEntityType.GRAMMAR: GrammarImport,
    ImportEntityType.EXAMPLE_SENTENCES: ExampleSentenceImport,
    ImportEntityType.EXERCISES: ExerciseImport,
}


def parse_import_records(source_format: Literal["json", "csv"], data: Any) -> list[dict[str, Any]]:
    if source_format == "json":
        if isinstance(data, str):
            data = json.loads(data)
        if isinstance(data, dict):
            data = data.get("records")
        if not isinstance(data, list) or not all(isinstance(item, dict) for item in data):
            raise ValueError("JSON import data must be a list or an object containing a records list")
        return data
    if not isinstance(data, str) or not data.strip():
        raise ValueError("CSV import data must be a non-empty string")
    return [dict(row) for row in csv.DictReader(StringIO(data))]


def _natural_key(entity_type: ImportEntityType, record: ImportRecord) -> tuple[Any, ...]:
    if entity_type == ImportEntityType.HSK_LEVELS:
        level_item = cast(HskLevelImport, record)
        return (level_item.level_number,)
    if entity_type == ImportEntityType.COURSES:
        course_item = cast(CourseImport, record)
        return (course_item.hsk_level, course_item.course_type)
    if entity_type == ImportEntityType.LESSONS:
        lesson_item = cast(LessonImport, record)
        return (lesson_item.course_id, lesson_item.title.strip().casefold())
    if entity_type == ImportEntityType.VOCABULARY:
        vocabulary_item = cast(VocabularyImport, record)
        return (
            vocabulary_item.hsk_level,
            vocabulary_item.simplified.strip(),
            (vocabulary_item.pinyin or "").strip().casefold(),
        )
    if entity_type == ImportEntityType.GRAMMAR:
        grammar_item = cast(GrammarImport, record)
        return (grammar_item.hsk_level, grammar_item.title.strip().casefold())
    if entity_type == ImportEntityType.EXERCISES:
        exercise_item = cast(ExerciseImport, record)
        return (
            exercise_item.lesson_id,
            exercise_item.exercise_set_slug.strip().casefold(),
            exercise_item.external_id.strip().casefold(),
        )
    example_item = cast(ExampleSentenceImport, record)
    return (
        example_item.chinese.strip(),
        (example_item.pinyin or "").strip().casefold(),
    )


def _validate_records(
    entity_type: ImportEntityType, records: list[dict[str, Any]]
) -> tuple[list[ImportRecord], list[dict[str, Any]]]:
    model = IMPORT_MODELS[entity_type]
    validated: list[ImportRecord] = []
    errors: list[dict[str, Any]] = []
    seen: dict[tuple[Any, ...], int] = {}
    for index, record in enumerate(records, start=1):
        try:
            item = model.model_validate(record)
            key = _natural_key(entity_type, item)
            if key in seen:
                errors.append(
                    {
                        "row": index,
                        "field": "natural_key",
                        "message": f"duplicates row {seen[key]} in the same import",
                    }
                )
                continue
            seen[key] = index
            validated.append(item)
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            details = exc.errors() if isinstance(exc, ValidationError) else [{"msg": str(exc)}]
            errors.append({"row": index, "details": details})
    return validated, errors


def _legacy_question_fields(
    question_type: str, configuration: dict[str, Any]
) -> tuple[list[str] | None, str]:
    validated = validate_question_configuration(question_type, configuration)
    if isinstance(validated, ChoiceConfiguration):
        options = [option.text for option in validated.options]
        correct_id = validated.correct_option_ids[0]
        correct = next(
            option.text for option in validated.options if option.id == correct_id
        )
        return options, correct
    if isinstance(validated, MultipleSelectConfiguration):
        return (
            [option.text for option in validated.options],
            "|".join(validated.correct_option_ids),
        )
    if isinstance(validated, TextConfiguration):
        return None, validated.accepted_answers[0]
    if isinstance(validated, MatchingConfiguration):
        return None, "|".join(
            f"{left}:{right}" for left, right in validated.correct_pairs.items()
        )
    if isinstance(validated, OrderingConfiguration):
        by_id = {item.id: item.text for item in validated.items}
        return [item.text for item in validated.items], " ".join(
            by_id[item_id] for item_id in validated.correct_order
        )
    raise ValueError("unsupported question configuration")


class ContentImporter:
    def __init__(self, db: Session, requested_by_user_id: int | None) -> None:
        self.db = db
        self.requested_by_user_id = requested_by_user_id

    def run(
        self,
        entity_type: ImportEntityType,
        source_format: Literal["json", "csv"],
        data: Any,
    ) -> ImportJob:
        job = ImportJob(
            requested_by_user_id=self.requested_by_user_id,
            entity_type=entity_type,
            source_format=source_format,
            status=ImportJobStatus.PENDING,
        )
        self.db.add(job)
        self.db.flush()
        try:
            raw_records = parse_import_records(source_format, data)
        except (ValueError, json.JSONDecodeError) as exc:
            return self._fail(job, [{"message": str(exc)}])

        job.total_records = len(raw_records)
        validated, errors = _validate_records(entity_type, raw_records)
        if errors:
            return self._fail(job, errors)

        job.status = ImportJobStatus.RUNNING
        job.started_at = datetime.now(UTC)
        created = 0
        updated = 0
        try:
            with self.db.begin_nested():
                for record in validated:
                    if self._upsert(entity_type, record):
                        created += 1
                    else:
                        updated += 1
                self.db.flush()
        except Exception as exc:
            return self._fail(job, [{"message": str(exc)}])

        job.created_records = created
        job.updated_records = updated
        job.status = ImportJobStatus.COMPLETED
        job.finished_at = datetime.now(UTC)
        self.db.commit()
        self.db.refresh(job)
        return job

    def _fail(self, job: ImportJob, errors: list[dict[str, Any]]) -> ImportJob:
        job.status = ImportJobStatus.FAILED
        job.errors = errors
        job.finished_at = datetime.now(UTC)
        self.db.commit()
        job_id = job.id
        raise ImportValidationError(job_id, errors)

    def _upsert(self, entity_type: ImportEntityType, record: ImportRecord) -> bool:
        if entity_type == ImportEntityType.HSK_LEVELS:
            return self._upsert_level(record)  # type: ignore[arg-type]
        if entity_type == ImportEntityType.COURSES:
            return self._upsert_course(record)  # type: ignore[arg-type]
        if entity_type == ImportEntityType.LESSONS:
            return self._upsert_lesson(record)  # type: ignore[arg-type]
        if entity_type == ImportEntityType.VOCABULARY:
            return self._upsert_vocabulary(record)  # type: ignore[arg-type]
        if entity_type == ImportEntityType.GRAMMAR:
            return self._upsert_grammar(record)  # type: ignore[arg-type]
        if entity_type == ImportEntityType.EXERCISES:
            return self._upsert_exercise(record)  # type: ignore[arg-type]
        return self._upsert_example(record)  # type: ignore[arg-type]

    def _level(self, level_number: int) -> HskLevel:
        level = self.db.scalar(
            select(HskLevel).where(HskLevel.level_number == level_number)
        )
        if not level:
            raise ValueError(f"HSK level {level_number} does not exist")
        return level

    def _upsert_level(self, item: HskLevelImport) -> bool:
        level = self.db.get(HskLevel, item.id) if item.id else None
        level = level or self.db.scalar(
            select(HskLevel).where(HskLevel.level_number == item.level_number)
        )
        created = level is None
        if level is None:
            level = HskLevel(level_number=item.level_number, title=item.name)
            if item.id:
                level.id = item.id
            self.db.add(level)
        level.title = item.name.strip()
        level.description = item.description
        level.display_order = item.display_order
        level.total_characters = item.total_characters
        level.status = item.status
        level.metadata_json = item.metadata
        return created

    def _upsert_course(self, item: CourseImport) -> bool:
        level = self._level(item.hsk_level)
        course = self.db.get(Course, item.id) if item.id else None
        course = course or self.db.scalar(
            select(Course).where(
                Course.hsk_level_id == level.id,
                Course.course_type == item.course_type,
            )
        )
        created = course is None
        if course is None:
            course = Course(hsk_level_id=level.id, course_type=item.course_type)
            if item.id:
                course.id = item.id
            self.db.add(course)
        course.hsk_level_id = level.id
        course.course_type = item.course_type
        course.title = item.title.strip()
        course.title_translations = item.title_translations
        course.description = item.description
        course.description_translations = item.description_translations
        course.thumbnail_url = item.thumbnail_url
        course.sort_order = item.order
        course.status = item.status
        course.metadata_json = item.metadata
        return created

    def _upsert_lesson(self, item: LessonImport) -> bool:
        course = self.db.get(Course, item.course_id)
        if not course:
            raise ValueError(f"Course {item.course_id} does not exist")
        if item.listening_audio_asset_id and not self.db.get(
            AudioAsset, item.listening_audio_asset_id
        ):
            raise ValueError(
                f"Audio asset {item.listening_audio_asset_id} does not exist"
            )
        lesson = self.db.get(Lesson, item.id) if item.id else None
        lesson = lesson or self.db.scalar(
            select(Lesson).where(
                Lesson.course_id == course.id,
                Lesson.title == item.title.strip(),
            )
        )
        created = lesson is None
        if lesson is None:
            lesson = Lesson(
                course_id=course.id,
                hsk_level_id=course.hsk_level_id,
                title=item.title.strip(),
            )
            if item.id:
                lesson.id = item.id
            self.db.add(lesson)
        lesson.course_id = course.id
        lesson.hsk_level_id = course.hsk_level_id
        lesson.title = item.title.strip()
        lesson.description = item.description
        lesson.lesson_type = item.lesson_type
        lesson.sort_order = item.order
        lesson.duration_minutes = item.estimated_duration
        lesson.difficulty = item.difficulty
        lesson.listening_audio_asset_id = item.listening_audio_asset_id
        lesson.content_status = item.status
        lesson.metadata_json = item.metadata
        lesson.content = item.content
        return created

    def _upsert_vocabulary(self, item: VocabularyImport) -> bool:
        level = self._level(item.hsk_level)
        pinyin = (item.pinyin or "").strip() or None
        vocabulary = self.db.get(Vocabulary, item.id) if item.id else None
        vocabulary = vocabulary or self.db.scalar(
            select(Vocabulary).where(
                Vocabulary.hsk_level_id == level.id,
                Vocabulary.simplified == item.simplified.strip(),
                Vocabulary.pinyin == pinyin,
            )
        )
        created = vocabulary is None
        if vocabulary is None:
            vocabulary = Vocabulary(
                hsk_level_id=level.id,
                simplified=item.simplified.strip(),
                pinyin=pinyin,
                meaning_translations=item.meaning_translations,
            )
            if item.id:
                vocabulary.id = item.id
            self.db.add(vocabulary)
            self.db.flush()
        vocabulary.traditional = item.traditional
        vocabulary.meaning_translations = item.meaning_translations
        vocabulary.part_of_speech = item.part_of_speech
        vocabulary.category = item.category
        vocabulary.audio_asset_id = item.audio_asset_id
        vocabulary.difficulty = item.difficulty
        vocabulary.display_order = item.order
        vocabulary.status = item.status
        vocabulary.metadata_json = item.metadata
        self._sync_vocabulary_links(vocabulary, item.lesson_ids, item.example_ids)
        return created

    def _sync_vocabulary_links(
        self, vocabulary: Vocabulary, lesson_ids: list[int], example_ids: list[int]
    ) -> None:
        existing_lessons = {link.lesson_id for link in vocabulary.lesson_links}
        for order, lesson_id in enumerate(dict.fromkeys(lesson_ids), start=1):
            if not self.db.get(Lesson, lesson_id):
                raise ValueError(f"Lesson {lesson_id} does not exist")
            if lesson_id not in existing_lessons:
                self.db.add(
                    LessonVocabulary(
                        lesson_id=lesson_id,
                        vocabulary_id=vocabulary.id,
                        sort_order=order,
                    )
                )
        existing_examples = {link.example_id for link in vocabulary.example_links}
        for order, example_id in enumerate(dict.fromkeys(example_ids), start=1):
            if not self.db.get(ExampleSentence, example_id):
                raise ValueError(f"Example sentence {example_id} does not exist")
            if example_id not in existing_examples:
                self.db.add(
                    VocabularyExample(
                        vocabulary_id=vocabulary.id,
                        example_id=example_id,
                        sort_order=order,
                    )
                )

    def _upsert_grammar(self, item: GrammarImport) -> bool:
        level = self._level(item.hsk_level)
        grammar = self.db.get(GrammarPoint, item.id) if item.id else None
        grammar = grammar or self.db.scalar(
            select(GrammarPoint).where(
                GrammarPoint.hsk_level_id == level.id,
                GrammarPoint.title == item.title.strip(),
            )
        )
        created = grammar is None
        if grammar is None:
            grammar = GrammarPoint(
                hsk_level_id=level.id,
                title=item.title.strip(),
                explanation_translations=item.explanation_translations,
            )
            if item.id:
                grammar.id = item.id
            self.db.add(grammar)
            self.db.flush()
        grammar.title_translations = item.title_translations
        grammar.explanation_translations = item.explanation_translations
        grammar.pattern = item.pattern
        grammar.difficulty = item.difficulty
        grammar.display_order = item.order
        grammar.status = item.status
        grammar.metadata_json = item.metadata
        existing_lessons = {link.lesson_id for link in grammar.lesson_links}
        for order, lesson_id in enumerate(dict.fromkeys(item.lesson_ids), start=1):
            if not self.db.get(Lesson, lesson_id):
                raise ValueError(f"Lesson {lesson_id} does not exist")
            if lesson_id not in existing_lessons:
                self.db.add(
                    LessonGrammarPoint(
                        lesson_id=lesson_id,
                        grammar_point_id=grammar.id,
                        sort_order=order,
                    )
                )
        existing_examples = {link.example_id for link in grammar.example_links}
        for order, example_id in enumerate(dict.fromkeys(item.example_ids), start=1):
            if not self.db.get(ExampleSentence, example_id):
                raise ValueError(f"Example sentence {example_id} does not exist")
            if example_id not in existing_examples:
                self.db.add(
                    GrammarExample(
                        grammar_point_id=grammar.id,
                        example_id=example_id,
                        sort_order=order,
                    )
                )
        return created

    def _upsert_example(self, item: ExampleSentenceImport) -> bool:
        pinyin = (item.pinyin or "").strip() or None
        example = self.db.get(ExampleSentence, item.id) if item.id else None
        example = example or self.db.scalar(
            select(ExampleSentence).where(
                ExampleSentence.chinese == item.chinese.strip(),
                ExampleSentence.pinyin == pinyin,
            )
        )
        created = example is None
        if example is None:
            example = ExampleSentence(
                chinese=item.chinese.strip(),
                pinyin=pinyin,
                translations=item.translations,
            )
            if item.id:
                example.id = item.id
            self.db.add(example)
        example.translations = item.translations
        example.audio_asset_id = item.audio_asset_id
        example.status = item.status
        example.metadata_json = item.metadata
        return created

    def _upsert_exercise(self, item: ExerciseImport) -> bool:
        lesson = self.db.get(Lesson, item.lesson_id)
        if lesson is None:
            raise ValueError(f"Lesson {item.lesson_id} does not exist")
        if item.vocabulary_id is not None and self.db.get(
            Vocabulary, item.vocabulary_id
        ) is None:
            raise ValueError(f"Vocabulary {item.vocabulary_id} does not exist")
        if item.grammar_point_id is not None and self.db.get(
            GrammarPoint, item.grammar_point_id
        ) is None:
            raise ValueError(f"Grammar point {item.grammar_point_id} does not exist")

        exercise_set = self.db.scalar(
            select(ExerciseSet).where(
                ExerciseSet.lesson_id == lesson.id,
                ExerciseSet.slug == item.exercise_set_slug,
            )
        )
        if exercise_set is None:
            exercise_set = ExerciseSet(
                lesson_id=lesson.id,
                slug=item.exercise_set_slug,
                title=item.exercise_set_title or f"{lesson.title} Practice",
                skill=item.skill,
                difficulty=item.difficulty,
                sort_order=item.exercise_set_order,
                status=item.status,
                metadata_json={"source": "content_import"},
            )
            self.db.add(exercise_set)
            self.db.flush()
        elif item.exercise_set_title:
            exercise_set.title = item.exercise_set_title

        exercise = self.db.get(Exercise, item.id) if item.id else None
        exercise = exercise or self.db.scalar(
            select(Exercise).where(
                Exercise.exercise_set_id == exercise_set.id,
                Exercise.external_id == item.external_id,
            )
        )
        created = exercise is None
        if exercise is None:
            exercise = Exercise(
                exercise_set_id=exercise_set.id,
                external_id=item.external_id,
                exercise_type=ExerciseType(item.exercise_type),
                title=item.title,
            )
            if item.id:
                exercise.id = item.id
            self.db.add(exercise)
            self.db.flush()
        exercise.exercise_type = ExerciseType(item.exercise_type)
        exercise.title = item.title
        exercise.instruction = item.instruction
        exercise.skill = item.skill
        exercise.vocabulary_id = item.vocabulary_id
        exercise.grammar_point_id = item.grammar_point_id
        exercise.difficulty = item.difficulty
        exercise.sort_order = item.order
        exercise.status = item.status
        exercise.metadata_json = item.metadata

        for question_item in item.questions:
            question = (
                self.db.get(Question, question_item.id)
                if question_item.id
                else None
            )
            question = question or self.db.scalar(
                select(Question).where(
                    Question.exercise_id == exercise.id,
                    Question.external_id == question_item.external_id,
                )
            )
            if question is None:
                question = Question(
                    lesson_id=lesson.id,
                    exercise_id=exercise.id,
                    external_id=question_item.external_id,
                    question_type=question_item.question_type,
                    prompt=question_item.prompt,
                    correct_answer="",
                )
                if question_item.id:
                    question.id = question_item.id
                self.db.add(question)
            options, correct_answer = _legacy_question_fields(
                question_item.question_type, question_item.configuration
            )
            question.lesson_id = lesson.id
            question.exercise_id = exercise.id
            question.external_id = question_item.external_id
            question.question_type = question_item.question_type
            question.prompt = question_item.prompt.strip()
            question.instruction = question_item.instruction
            question.options = options
            question.correct_answer = correct_answer
            question.explanation = question_item.explanation
            question.difficulty = question_item.difficulty
            question.points = question_item.points
            question.configuration = question_item.configuration
            question.sort_order = question_item.order
            question.status = question_item.status
            question.metadata_json = question_item.metadata
            self.db.flush()
            sync_question_version(self.db, question)
        return created


@dataclass
class BackfillSummary:
    vocabulary_created: int = 0
    grammar_created: int = 0
    examples_created: int = 0
    vocabulary_links_created: int = 0
    grammar_links_created: int = 0


def _translations(value: dict[str, Any], fallback_key: str) -> dict[str, str]:
    translations = value.get("translations")
    if isinstance(translations, dict):
        return {
            str(key): str(text)
            for key, text in translations.items()
            if text is not None and str(text).strip()
        }
    result: dict[str, str] = {}
    for locale in ("en", "vi"):
        text = value.get(f"{fallback_key}_{locale}")
        if text:
            result[locale] = str(text)
    fallback = value.get(fallback_key)
    if fallback and not result:
        result["vi"] = str(fallback)
    return result


def backfill_normalized_content(db: Session, *, force: bool = False) -> BackfillSummary:
    if not force and db.scalar(select(Vocabulary.id).limit(1)):
        return BackfillSummary()

    summary = BackfillSummary()
    lessons = db.scalars(select(Lesson).order_by(Lesson.id)).all()
    level_numbers = {
        level.id: level.level_number for level in db.scalars(select(HskLevel)).all()
    }
    vocabulary_by_key = {
        (item.hsk_level_id, item.simplified, item.pinyin): item
        for item in db.scalars(select(Vocabulary)).all()
    }
    grammar_by_key = {
        (item.hsk_level_id, item.title): item
        for item in db.scalars(select(GrammarPoint)).all()
    }
    examples_by_key = {
        (item.chinese, item.pinyin): item
        for item in db.scalars(select(ExampleSentence)).all()
    }
    vocabulary_link_keys = {
        (link.lesson_id, link.vocabulary_id)
        for link in db.scalars(select(LessonVocabulary)).all()
    }
    grammar_link_keys = {
        (link.lesson_id, link.grammar_point_id)
        for link in db.scalars(select(LessonGrammarPoint)).all()
    }
    vocabulary_example_keys = {
        (link.vocabulary_id, link.example_id)
        for link in db.scalars(select(VocabularyExample)).all()
    }
    grammar_example_keys = {
        (link.grammar_point_id, link.example_id)
        for link in db.scalars(select(GrammarExample)).all()
    }

    pinyins_by_word: dict[tuple[int, str], set[str]] = defaultdict(set)
    for lesson in lessons:
        for raw in (lesson.content or {}).get("vocabulary") or []:
            if not isinstance(raw, dict):
                continue
            hanzi = str(raw.get("hanzi") or "").strip()
            raw_pinyin = str(raw.get("pinyin") or "").strip()
            if hanzi and raw_pinyin:
                pinyins_by_word[(lesson.hsk_level_id, hanzi)].add(raw_pinyin)

    def ensure_example(raw: dict[str, Any]) -> ExampleSentence | None:
        chinese = str(raw.get("hanzi") or raw.get("chinese") or "").strip()
        if not chinese:
            return None
        pinyin = str(raw.get("pinyin") or "").strip() or None
        key = (chinese, pinyin)
        example = examples_by_key.get(key)
        if example is None:
            example = ExampleSentence(
                chinese=chinese,
                pinyin=pinyin,
                translations=_translations(raw, "meaning"),
                status=ContentStatus.PUBLISHED,
                metadata_json={"source": "legacy_lesson_content"},
            )
            db.add(example)
            db.flush()
            examples_by_key[key] = example
            summary.examples_created += 1
        return example

    for lesson in lessons:
        content = lesson.content or {}
        seen_lesson_vocabulary: set[int] = set()
        for order, raw in enumerate(content.get("vocabulary") or [], start=1):
            if not isinstance(raw, dict):
                continue
            simplified = str(raw.get("hanzi") or "").strip()
            if not simplified:
                continue
            canonical_pinyin: str | None = (
                str(raw.get("pinyin") or "").strip() or None
            )
            variants = pinyins_by_word[(lesson.hsk_level_id, simplified)]
            if canonical_pinyin is None and len(variants) == 1:
                canonical_pinyin = next(iter(variants))
            vocabulary_key = (
                lesson.hsk_level_id,
                simplified,
                canonical_pinyin,
            )
            vocabulary = vocabulary_by_key.get(vocabulary_key)
            if vocabulary is None:
                translations = _translations(raw, "meaning")
                if not translations:
                    translations = {"und": simplified}
                vocabulary = Vocabulary(
                    hsk_level_id=lesson.hsk_level_id,
                    simplified=simplified,
                    traditional=raw.get("traditional"),
                    pinyin=canonical_pinyin,
                    meaning_translations=translations,
                    part_of_speech=str(raw.get("word_type") or "other"),
                    category=raw.get("category"),
                    difficulty=level_numbers.get(lesson.hsk_level_id),
                    display_order=len(vocabulary_by_key) + 1,
                    status=ContentStatus.PUBLISHED,
                    metadata_json={
                        "source": "legacy_lesson_content",
                        **(
                            {"pinyin_not_available": True}
                            if canonical_pinyin is None
                            else {}
                        ),
                    },
                )
                db.add(vocabulary)
                db.flush()
                vocabulary_by_key[vocabulary_key] = vocabulary
                summary.vocabulary_created += 1
            if vocabulary.id not in seen_lesson_vocabulary:
                link_key = (lesson.id, vocabulary.id)
                if link_key not in vocabulary_link_keys:
                    db.add(
                        LessonVocabulary(
                            lesson_id=lesson.id,
                            vocabulary_id=vocabulary.id,
                            sort_order=order,
                        )
                    )
                    vocabulary_link_keys.add(link_key)
                    summary.vocabulary_links_created += 1
                seen_lesson_vocabulary.add(vocabulary.id)

            example_raw = {
                "hanzi": raw.get("example_cn"),
                "pinyin": raw.get("example_pinyin"),
                "meaning": raw.get("example_vi") or raw.get("example_en"),
                "meaning_vi": raw.get("example_vi"),
                "meaning_en": raw.get("example_en"),
                "translations": raw.get("example_translations"),
            }
            example = ensure_example(example_raw)
            if example and (vocabulary.id, example.id) not in vocabulary_example_keys:
                db.add(
                    VocabularyExample(
                        vocabulary_id=vocabulary.id,
                        example_id=example.id,
                        sort_order=1,
                    )
                )
                vocabulary_example_keys.add((vocabulary.id, example.id))

        seen_lesson_grammar: set[int] = set()
        for order, raw in enumerate(content.get("grammar_points") or [], start=1):
            if not isinstance(raw, dict):
                continue
            title = str(raw.get("title") or raw.get("point") or "").strip()
            if not title:
                continue
            grammar_key = (lesson.hsk_level_id, title)
            grammar = grammar_by_key.get(grammar_key)
            if grammar is None:
                explanations = raw.get("explanation_translations")
                if not isinstance(explanations, dict):
                    explanations = _translations(raw, "explanation")
                grammar = GrammarPoint(
                    hsk_level_id=lesson.hsk_level_id,
                    title=title,
                    title_translations=raw.get("title_translations"),
                    explanation_translations=explanations or {"und": title},
                    pattern=raw.get("structure") or raw.get("pattern"),
                    difficulty=level_numbers.get(lesson.hsk_level_id),
                    display_order=len(grammar_by_key) + 1,
                    status=ContentStatus.PUBLISHED,
                    metadata_json={"source": "legacy_lesson_content"},
                )
                db.add(grammar)
                db.flush()
                grammar_by_key[grammar_key] = grammar
                summary.grammar_created += 1
            if grammar.id not in seen_lesson_grammar:
                link_key = (lesson.id, grammar.id)
                if link_key not in grammar_link_keys:
                    db.add(
                        LessonGrammarPoint(
                            lesson_id=lesson.id,
                            grammar_point_id=grammar.id,
                            sort_order=order,
                        )
                    )
                    grammar_link_keys.add(link_key)
                    summary.grammar_links_created += 1
                seen_lesson_grammar.add(grammar.id)
            for example_order, example_raw in enumerate(raw.get("examples") or [], start=1):
                if not isinstance(example_raw, dict):
                    continue
                example = ensure_example(example_raw)
                if example and (grammar.id, example.id) not in grammar_example_keys:
                    db.add(
                        GrammarExample(
                            grammar_point_id=grammar.id,
                            example_id=example.id,
                            sort_order=example_order,
                        )
                    )
                    grammar_example_keys.add((grammar.id, example.id))

    db.flush()
    for saved_word in db.scalars(
        select(SavedWord).where(SavedWord.vocabulary_id.is_(None))
    ).all():
        candidates = [
            vocabulary
            for (level_id, simplified, _), vocabulary in vocabulary_by_key.items()
            if simplified == saved_word.hanzi
            and (
                saved_word.hsk_level is None
                or level_numbers.get(level_id) == saved_word.hsk_level
            )
        ]
        if len(candidates) == 1:
            saved_word.vocabulary_id = candidates[0].id
    return summary
