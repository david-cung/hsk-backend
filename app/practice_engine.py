import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    ContentStatus,
    Exercise,
    ExerciseSet,
    ExerciseType,
    GrammarLearningStatus,
    Lesson,
    Question,
    QuestionAttempt,
    UserGrammarProgress,
    UserVocabularyProgress,
    VocabularyLearningStatus,
)

LEGACY_TYPE_MAP: dict[str, ExerciseType] = {
    "multiple_choice": ExerciseType.MULTIPLE_CHOICE,
    "multiple_select": ExerciseType.MULTIPLE_SELECT,
    "fill_blank": ExerciseType.FILL_BLANK,
    "image_matching": ExerciseType.MATCHING,
    "matching": ExerciseType.MATCHING,
    "arrange_sentence": ExerciseType.ORDERING,
    "rearrange": ExerciseType.ORDERING,
    "ordering": ExerciseType.ORDERING,
    "translation": ExerciseType.TRANSLATION,
    "grammar": ExerciseType.GRAMMAR,
    "reading": ExerciseType.READING,
    "listening": ExerciseType.DICTATION,
    "dictation": ExerciseType.DICTATION,
    "typing": ExerciseType.TEXT_INPUT,
    "text_input": ExerciseType.TEXT_INPUT,
    "choose_meaning": ExerciseType.VOCABULARY_RECALL,
    "vocabulary_recall": ExerciseType.VOCABULARY_RECALL,
}

TEXT_TYPES = {
    ExerciseType.FILL_BLANK,
    ExerciseType.TRANSLATION,
    ExerciseType.DICTATION,
    ExerciseType.TEXT_INPUT,
    ExerciseType.VOCABULARY_RECALL,
}
CHOICE_TYPES = {
    ExerciseType.MULTIPLE_CHOICE,
    ExerciseType.GRAMMAR,
    ExerciseType.READING,
}
IMPLEMENTED_TYPES = (
    TEXT_TYPES
    | CHOICE_TYPES
    | {
        ExerciseType.MULTIPLE_SELECT,
        ExerciseType.MATCHING,
        ExerciseType.ORDERING,
    }
)


class AnswerOptionConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    translations: dict[str, str] | None = None


class NormalizationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    trim_whitespace: bool = True
    collapse_whitespace: bool = True
    unicode_form: Literal["NFC", "NFKC"] = "NFKC"
    case_sensitive: bool = False
    punctuation: str = Field(default="preserve", pattern="^(preserve|ignore)$")
    pinyin_tones: str = Field(default="preserve", pattern="^(preserve|ignore)$")


class ChoiceConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    options: list[AnswerOptionConfig] = Field(min_length=2)
    correct_option_ids: list[str] = Field(min_length=1, max_length=1)

    @model_validator(mode="after")
    def validate_ids(self) -> "ChoiceConfiguration":
        option_ids = [option.id for option in self.options]
        if len(option_ids) != len(set(option_ids)):
            raise ValueError("option ids must be unique")
        if self.correct_option_ids[0] not in set(option_ids):
            raise ValueError("correct option id must reference an option")
        return self


class MultipleSelectConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    options: list[AnswerOptionConfig] = Field(min_length=2)
    correct_option_ids: list[str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ids(self) -> "MultipleSelectConfiguration":
        option_ids = [option.id for option in self.options]
        option_id_set = set(option_ids)
        if len(option_ids) != len(option_id_set):
            raise ValueError("option ids must be unique")
        if len(self.correct_option_ids) != len(set(self.correct_option_ids)):
            raise ValueError("correct option ids must be unique")
        if not set(self.correct_option_ids).issubset(option_id_set):
            raise ValueError("correct option ids must reference options")
        return self


class TextConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    accepted_answers: list[str] = Field(min_length=1)
    normalization: NormalizationConfig = Field(default_factory=NormalizationConfig)

    @model_validator(mode="after")
    def validate_answers(self) -> "TextConfiguration":
        if not any(answer.strip() for answer in self.accepted_answers):
            raise ValueError("accepted answers must not be empty")
        return self


class MatchingItemConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1)
    translations: dict[str, str] | None = None


class MatchingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MatchingItemConfig] = Field(min_length=2)
    targets: list[MatchingItemConfig] = Field(min_length=2)
    correct_pairs: dict[str, str]

    @model_validator(mode="after")
    def validate_pairs(self) -> "MatchingConfiguration":
        item_ids = [item.id for item in self.items]
        target_ids = [target.id for target in self.targets]
        if len(item_ids) != len(set(item_ids)) or len(target_ids) != len(
            set(target_ids)
        ):
            raise ValueError("matching ids must be unique")
        if set(self.correct_pairs) != set(item_ids):
            raise ValueError("every matching item must have one correct target")
        if not set(self.correct_pairs.values()).issubset(set(target_ids)):
            raise ValueError("matching pairs must reference valid targets")
        return self


class OrderingConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[MatchingItemConfig] = Field(min_length=2)
    correct_order: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_order(self) -> "OrderingConfiguration":
        item_ids = [item.id for item in self.items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("ordering item ids must be unique")
        if len(self.correct_order) != len(set(self.correct_order)):
            raise ValueError("correct order ids must be unique")
        if set(self.correct_order) != set(item_ids):
            raise ValueError("correct order must include every item exactly once")
        return self


QuestionConfiguration = (
    ChoiceConfiguration
    | MultipleSelectConfiguration
    | TextConfiguration
    | MatchingConfiguration
    | OrderingConfiguration
)


@dataclass(frozen=True)
class EvaluationResult:
    is_correct: bool
    score: int
    max_score: int
    normalized_answer: Any
    correct_answer: Any


@dataclass
class ExerciseBackfillSummary:
    exercise_sets_created: int = 0
    exercises_created: int = 0
    questions_created: int = 0
    questions_linked: int = 0


def canonical_exercise_type(value: str | ExerciseType) -> ExerciseType:
    if isinstance(value, ExerciseType):
        return value
    normalized = value.strip().casefold()
    try:
        return ExerciseType(normalized)
    except ValueError:
        mapped = LEGACY_TYPE_MAP.get(normalized)
        if mapped is None:
            raise ValueError(f"unsupported exercise type: {value}") from None
        return mapped


def validate_question_configuration(
    question_type: str | ExerciseType, configuration: dict[str, Any]
) -> QuestionConfiguration:
    exercise_type = canonical_exercise_type(question_type)
    if exercise_type not in IMPLEMENTED_TYPES:
        raise ValueError(f"{exercise_type.value} exercises are reserved for a later phase")
    if exercise_type in CHOICE_TYPES:
        return ChoiceConfiguration.model_validate(configuration)
    if exercise_type == ExerciseType.MULTIPLE_SELECT:
        return MultipleSelectConfiguration.model_validate(configuration)
    if exercise_type in TEXT_TYPES:
        return TextConfiguration.model_validate(configuration)
    if exercise_type == ExerciseType.MATCHING:
        return MatchingConfiguration.model_validate(configuration)
    if exercise_type == ExerciseType.ORDERING:
        return OrderingConfiguration.model_validate(configuration)
    raise ValueError(f"unsupported exercise type: {exercise_type.value}")


def public_question_configuration(
    question_type: str | ExerciseType, configuration: dict[str, Any]
) -> dict[str, Any]:
    validated = validate_question_configuration(question_type, configuration)
    if isinstance(validated, (ChoiceConfiguration, MultipleSelectConfiguration)):
        return {"options": [option.model_dump() for option in validated.options]}
    if isinstance(validated, TextConfiguration):
        return {}
    if isinstance(validated, MatchingConfiguration):
        return {
            "items": [item.model_dump() for item in validated.items],
            "targets": [target.model_dump() for target in validated.targets],
        }
    return {"items": [item.model_dump() for item in validated.items]}


def _normalize_punctuation(value: str) -> str:
    return re.sub(r"[\s，。！？；：、,.!?;:'\"“”‘’（）()\[\]{}…—-]+", "", value)


def normalize_text_answer(value: str, config: NormalizationConfig) -> str:
    result = unicodedata.normalize(config.unicode_form, value)
    if config.trim_whitespace:
        result = result.strip()
    if config.collapse_whitespace:
        result = re.sub(r"\s+", " ", result)
    if not config.case_sensitive:
        result = result.casefold()
    if config.pinyin_tones == "ignore":
        result = "".join(
            character
            for character in unicodedata.normalize("NFD", result)
            if unicodedata.category(character) != "Mn"
        )
        result = re.sub(r"[1-5]", "", result)
    if config.punctuation == "ignore":
        result = _normalize_punctuation(result)
    return unicodedata.normalize(config.unicode_form, result)


def evaluate_answer(question: Question, answer: Any) -> EvaluationResult:
    exercise_type = canonical_exercise_type(question.question_type)
    configuration = validate_question_configuration(
        exercise_type, question.configuration
    )
    points = question.points

    if isinstance(configuration, ChoiceConfiguration):
        if not isinstance(answer, str):
            raise ValueError("answer must be one option id")
        valid_ids = {option.id for option in configuration.options}
        if answer not in valid_ids:
            raise ValueError("answer references an unknown option")
        normalized: Any = answer
        correct_answer: Any = configuration.correct_option_ids[0]
        correct = answer == correct_answer
    elif isinstance(configuration, MultipleSelectConfiguration):
        if not isinstance(answer, list) or not all(
            isinstance(item, str) for item in answer
        ):
            raise ValueError("answer must be a list of option ids")
        if len(answer) != len(set(answer)):
            raise ValueError("answer option ids must be unique")
        valid_ids = {option.id for option in configuration.options}
        if not set(answer).issubset(valid_ids):
            raise ValueError("answer references an unknown option")
        normalized = sorted(answer)
        correct_answer = sorted(configuration.correct_option_ids)
        correct = normalized == correct_answer
    elif isinstance(configuration, TextConfiguration):
        if not isinstance(answer, str):
            raise ValueError("answer must be text")
        normalized = normalize_text_answer(answer, configuration.normalization)
        accepted = [
            normalize_text_answer(value, configuration.normalization)
            for value in configuration.accepted_answers
        ]
        correct = normalized in accepted
        correct_answer = configuration.accepted_answers
    elif isinstance(configuration, MatchingConfiguration):
        if not isinstance(answer, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in answer.items()
        ):
            raise ValueError("answer must map item ids to target ids")
        normalized = dict(sorted(answer.items()))
        correct_answer = dict(sorted(configuration.correct_pairs.items()))
        correct = normalized == correct_answer
    else:
        if not isinstance(answer, list) or not all(
            isinstance(item, str) for item in answer
        ):
            raise ValueError("answer must be an ordered list of item ids")
        if len(answer) != len(set(answer)):
            raise ValueError("answer item ids must be unique")
        valid_ids = {item.id for item in configuration.items}
        if set(answer) != valid_ids:
            raise ValueError("answer must include every ordering item exactly once")
        normalized = answer
        correct_answer = configuration.correct_order
        correct = answer == correct_answer

    return EvaluationResult(
        is_correct=correct,
        score=points if correct else 0,
        max_score=points,
        normalized_answer=normalized,
        correct_answer=correct_answer,
    )


def _legacy_configuration(
    question_type: ExerciseType,
    options: list[str] | None,
    correct_answer: str,
    *,
    word_bank: list[str] | None = None,
) -> dict[str, Any]:
    if question_type in CHOICE_TYPES:
        values = [str(option) for option in options or []]
        if correct_answer and correct_answer not in values:
            values.append(correct_answer)
        if len(values) < 2:
            values.extend(
                value for value in ("true", "false") if value not in values
            )
        return ChoiceConfiguration(
            options=[AnswerOptionConfig(id=value, text=value) for value in values],
            correct_option_ids=[correct_answer or values[0]],
        ).model_dump()
    if question_type == ExerciseType.MULTIPLE_SELECT:
        values = [str(option) for option in options or []]
        correct_ids = [
            value.strip()
            for value in correct_answer.split("|")
            if value.strip()
        ]
        return MultipleSelectConfiguration(
            options=[AnswerOptionConfig(id=value, text=value) for value in values],
            correct_option_ids=correct_ids,
        ).model_dump()
    if question_type == ExerciseType.MATCHING:
        pairs = [part.strip() for part in correct_answer.split("|") if ":" in part]
        correct_pairs = {
            left.strip(): right.strip()
            for left, right in (pair.split(":", 1) for pair in pairs)
        }
        items = [
            MatchingItemConfig(id=value, text=value) for value in correct_pairs
        ]
        targets = [
            MatchingItemConfig(id=value, text=value)
            for value in dict.fromkeys(correct_pairs.values())
        ]
        if len(items) >= 2 and len(targets) >= 2:
            return MatchingConfiguration(
                items=items, targets=targets, correct_pairs=correct_pairs
            ).model_dump()
        return TextConfiguration(accepted_answers=[correct_answer]).model_dump()
    if question_type == ExerciseType.ORDERING:
        words = [str(word) for word in word_bank or options or [] if str(word).strip()]
        if len(words) < 2:
            words = [word for word in correct_answer.split() if word]
        if len(words) < 2:
            return TextConfiguration(accepted_answers=[correct_answer]).model_dump()
        item_ids = [f"item-{index}" for index in range(1, len(words) + 1)]
        positions: list[tuple[int, str]] = []
        cursor = 0
        for item_id, word in zip(item_ids, words, strict=True):
            position = correct_answer.find(word, cursor)
            if position < 0:
                position = correct_answer.find(word)
            positions.append((position if position >= 0 else len(positions), item_id))
            if position >= 0:
                cursor = position + len(word)
        return OrderingConfiguration(
            items=[
                MatchingItemConfig(id=item_id, text=word)
                for item_id, word in zip(item_ids, words, strict=True)
            ],
            correct_order=[item_id for _, item_id in sorted(positions)],
        ).model_dump()
    return TextConfiguration(accepted_answers=[correct_answer]).model_dump()


def ensure_question_configuration(question: Question) -> None:
    question_type = canonical_exercise_type(question.question_type)
    configuration = question.configuration or _legacy_configuration(
        question_type,
        question.options,
        question.correct_answer,
    )
    try:
        validated = validate_question_configuration(question_type, configuration)
    except ValueError:
        question_type = ExerciseType.TEXT_INPUT
        validated = TextConfiguration(
            accepted_answers=[question.correct_answer or ""]
        )
    question.question_type = question_type.value
    question.configuration = validated.model_dump()


def _exercise_type_from_json(raw: dict[str, Any]) -> ExerciseType:
    return canonical_exercise_type(str(raw.get("exercise_type") or "text_input"))


def backfill_exercise_engine(
    db: Session, *, force: bool = False
) -> ExerciseBackfillSummary:
    del force

    summary = ExerciseBackfillSummary()
    lessons = db.scalars(select(Lesson).order_by(Lesson.id)).all()
    for lesson in lessons:
        legacy_items = [
            item
            for item in (lesson.content or {}).get("practice_exercises") or []
            if isinstance(item, dict) and str(item.get("prompt") or "").strip()
        ]
        questions = db.scalars(
            select(Question)
            .where(Question.lesson_id == lesson.id)
            .order_by(Question.sort_order, Question.id)
        ).all()
        if not questions and not legacy_items:
            continue

        exercise_set = db.scalar(
            select(ExerciseSet).where(
                ExerciseSet.lesson_id == lesson.id,
                ExerciseSet.slug == "lesson-practice",
            )
        )
        if exercise_set is None:
            exercise_set = ExerciseSet(
                lesson_id=lesson.id,
                slug="lesson-practice",
                title=f"{lesson.title} Practice",
                description="Normalized practice generated from verified lesson content.",
                skill=lesson.lesson_type,
                difficulty=lesson.difficulty,
                sort_order=0,
                status=ContentStatus.PUBLISHED,
                metadata_json={"source": "legacy_backfill"},
            )
            db.add(exercise_set)
            db.flush()
            summary.exercise_sets_created += 1

        questions_by_prompt = {
            unicodedata.normalize("NFKC", question.prompt).strip(): question
            for question in questions
        }
        next_order = 1
        for question in questions:
            ensure_question_configuration(question)
            if question.exercise_id is None:
                exercise = Exercise(
                    exercise_set_id=exercise_set.id,
                    external_id=f"legacy-question-{question.id}",
                    exercise_type=canonical_exercise_type(question.question_type),
                    title=f"Question {question.sort_order or next_order}",
                    skill=lesson.lesson_type,
                    difficulty=question.difficulty,
                    sort_order=next_order,
                    status=ContentStatus.PUBLISHED,
                    metadata_json={"source": "legacy_question"},
                )
                db.add(exercise)
                db.flush()
                question.exercise_id = exercise.id
                question.external_id = question.external_id or f"legacy-question-{question.id}"
                summary.exercises_created += 1
                summary.questions_linked += 1
            next_order += 1

        next_order = max(
            next_order,
            max(
                (exercise.sort_order for exercise in exercise_set.exercises),
                default=0,
            )
            + 1,
        )
        for raw in legacy_items:
            prompt = str(raw.get("prompt") or "").strip()
            prompt_key = unicodedata.normalize("NFKC", prompt)
            existing = questions_by_prompt.get(prompt_key)
            if existing is not None:
                continue
            exercise_type = _exercise_type_from_json(raw)
            correct_answer = str(
                raw.get("correct_answer") or raw.get("expected_answer") or ""
            )
            configuration = _legacy_configuration(
                exercise_type,
                [str(option) for option in raw.get("options") or []],
                correct_answer,
                word_bank=[str(word) for word in raw.get("word_bank") or []],
            )
            try:
                validated = validate_question_configuration(
                    exercise_type, configuration
                )
            except ValueError:
                exercise_type = ExerciseType.TEXT_INPUT
                validated = TextConfiguration(
                    accepted_answers=[correct_answer or ""]
                )
            external_id = str(raw.get("id") or f"legacy-json-{next_order}")[:180]
            json_exercise = db.scalar(
                select(Exercise).where(
                    Exercise.exercise_set_id == exercise_set.id,
                    Exercise.external_id == external_id,
                )
            )
            exercise_created = json_exercise is None
            if json_exercise is None:
                json_exercise = Exercise(
                    exercise_set_id=exercise_set.id,
                    external_id=external_id,
                    exercise_type=exercise_type,
                    title=str(raw.get("title") or f"Question {next_order}")[:180],
                    sort_order=next_order,
                )
                db.add(json_exercise)
                db.flush()
            json_exercise.exercise_type = exercise_type
            json_exercise.instruction = str(raw.get("hint") or "").strip() or None
            json_exercise.skill = str(raw.get("skill") or lesson.lesson_type)[:40]
            json_exercise.difficulty = lesson.difficulty
            json_exercise.status = ContentStatus.PUBLISHED
            json_exercise.metadata_json = {"source": "legacy_jsonb_practice"}
            question = Question(
                lesson_id=lesson.id,
                exercise_id=json_exercise.id,
                external_id=external_id,
                question_type=exercise_type.value,
                prompt=prompt,
                instruction=str(raw.get("hint") or "").strip() or None,
                options=[str(option) for option in raw.get("options") or []] or None,
                correct_answer=correct_answer,
                explanation=str(raw.get("explanation") or "").strip() or None,
                difficulty=lesson.difficulty,
                points=1,
                configuration=validated.model_dump(),
                sort_order=next_order,
                status=ContentStatus.PUBLISHED,
                metadata_json={
                    "source": "legacy_jsonb_practice",
                    "prompt_translations": raw.get("prompt_translations"),
                    "explanation_translations": raw.get(
                        "explanation_translations"
                    ),
                },
            )
            db.add(question)
            questions_by_prompt[prompt_key] = question
            summary.exercises_created += int(exercise_created)
            summary.questions_created += 1
            next_order += 1

    db.flush()
    return summary


def update_content_progress(
    db: Session, attempt: QuestionAttempt, exercise: Exercise
) -> None:
    now = datetime.now(UTC)
    if exercise.vocabulary_id is not None:
        progress = db.scalar(
            select(UserVocabularyProgress).where(
                UserVocabularyProgress.user_id == attempt.user_id,
                UserVocabularyProgress.vocabulary_id == exercise.vocabulary_id,
            )
        )
        if progress is None:
            progress = UserVocabularyProgress(
                user_id=attempt.user_id,
                vocabulary_id=exercise.vocabulary_id,
                status=VocabularyLearningStatus.LEARNING,
                practiced_count=0,
                correct_count=0,
                incorrect_count=0,
            )
            db.add(progress)
        if progress.status == VocabularyLearningStatus.NEW:
            progress.status = VocabularyLearningStatus.LEARNING
        progress.practiced_count += 1
        progress.correct_count += int(attempt.is_correct)
        progress.incorrect_count += int(not attempt.is_correct)
        progress.first_practiced_at = progress.first_practiced_at or now
        progress.last_practiced_at = now

    if exercise.grammar_point_id is not None:
        grammar_progress = db.scalar(
            select(UserGrammarProgress).where(
                UserGrammarProgress.user_id == attempt.user_id,
                UserGrammarProgress.grammar_point_id == exercise.grammar_point_id,
            )
        )
        if grammar_progress is None:
            grammar_progress = UserGrammarProgress(
                user_id=attempt.user_id,
                grammar_point_id=exercise.grammar_point_id,
                status=GrammarLearningStatus.VIEWED,
                practiced_count=0,
                correct_count=0,
                incorrect_count=0,
            )
            db.add(grammar_progress)
        grammar_progress.practiced_count += 1
        grammar_progress.correct_count += int(attempt.is_correct)
        grammar_progress.incorrect_count += int(not attempt.is_correct)
        grammar_progress.first_practiced_at = (
            grammar_progress.first_practiced_at or now
        )
        grammar_progress.last_practiced_at = now
