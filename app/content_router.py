import math
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload, selectinload

from app.auth import get_current_user, get_optional_user, require_admin
from app.content_import import ContentImporter, ImportValidationError
from app.content_security import public_lesson_content
from app.database import get_db
from app.models import (
    AudioAsset,
    ContentStatus,
    Course,
    ExampleSentence,
    GrammarExample,
    GrammarLearningStatus,
    GrammarPoint,
    HskLevel,
    ImportEntityType,
    ImportJob,
    Lesson,
    LessonGrammarPoint,
    LessonProgress,
    LessonVocabulary,
    SavedWord,
    User,
    UserGrammarProgress,
    UserVocabularyProgress,
    Vocabulary,
    VocabularyExample,
    VocabularyLearningStatus,
)
from app.schemas import (
    AudioAssetOut,
    CourseCreate,
    CourseOut,
    CourseUpdate,
    ExampleSentenceCreate,
    ExampleSentenceOut,
    ExampleSentenceUpdate,
    GrammarCreate,
    GrammarDetailOut,
    GrammarListItemOut,
    GrammarUpdate,
    HskLevelCreate,
    HskLevelOut,
    HskLevelUpdate,
    ImportJobOut,
    ImportRequest,
    LearningProgressOut,
    LessonCreate,
    LessonDetailOut,
    LessonListOut,
    LessonReferenceOut,
    LessonUpdate,
    VocabularyCreate,
    VocabularyDetailOut,
    VocabularyListItemOut,
    VocabularyPageOut,
    VocabularyStatusIn,
    VocabularyUpdate,
)

router = APIRouter(prefix="/api/v1")


def _value(value: Any) -> str:
    return value.value if hasattr(value, "value") else str(value)


def _content_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _audio_out(audio: AudioAsset | None) -> AudioAssetOut | None:
    if not audio:
        return None
    return AudioAssetOut(
        id=audio.id,
        url=audio.url,
        storage_provider=audio.storage_provider,
        storage_key=audio.storage_key,
        duration_ms=audio.duration_ms,
        format=audio.format,
        locale=audio.locale,
    )


def _example_out(example: ExampleSentence) -> ExampleSentenceOut:
    return ExampleSentenceOut(
        id=example.id,
        chinese=example.chinese,
        pinyin=example.pinyin,
        translations=example.translations,
        audio=_audio_out(example.audio_asset),
    )


def _lesson_reference(lesson: Lesson) -> LessonReferenceOut:
    return LessonReferenceOut(
        id=lesson.id,
        course_id=lesson.course_id,
        title=lesson.title,
        lesson_number=lesson.sort_order,
    )


def _vocabulary_item(
    vocabulary: Vocabulary,
    learning_status: str = "new",
    is_favorite: bool = False,
) -> VocabularyListItemOut:
    return VocabularyListItemOut(
        id=vocabulary.id,
        simplified=vocabulary.simplified,
        traditional=vocabulary.traditional,
        pinyin=vocabulary.pinyin,
        meaning_translations=vocabulary.meaning_translations,
        part_of_speech=vocabulary.part_of_speech,
        hsk_level=vocabulary.hsk_level.level_number,
        difficulty=vocabulary.difficulty,
        display_order=vocabulary.display_order,
        audio=_audio_out(vocabulary.audio_asset),
        learning_status=learning_status,
        is_favorite=is_favorite,
    )


def _grammar_item(
    grammar: GrammarPoint, learning_status: str | None = None
) -> GrammarListItemOut:
    return GrammarListItemOut(
        id=grammar.id,
        title=grammar.title,
        title_translations=grammar.title_translations,
        explanation_translations=grammar.explanation_translations,
        pattern=grammar.pattern,
        hsk_level=grammar.hsk_level.level_number,
        difficulty=grammar.difficulty,
        display_order=grammar.display_order,
        learning_status=learning_status,
    )


def _hsk_level_out(level: HskLevel) -> HskLevelOut:
    return HskLevelOut(
        id=level.id,
        level_number=level.level_number,
        name=level.title,
        title=level.title,
        title_translations={"en": level.title, "vi": level.title},
        description=level.description,
        description_translations={
            "en": level.description or "",
            "vi": f"Bài học tiếng Trung có cấu trúc cho HSK {level.level_number}.",
        },
        total_characters=level.total_characters,
        display_order=level.display_order,
        status=_value(level.status),
        metadata=level.metadata_json,
        course_count=len(
            [course for course in level.courses if course.status == ContentStatus.PUBLISHED]
        ),
    )


def _course_out(course: Course) -> CourseOut:
    return CourseOut(
        id=course.id,
        hsk_level_id=course.hsk_level_id,
        hsk_level=course.hsk_level.level_number,
        title=course.title,
        title_translations=course.title_translations,
        description=course.description,
        description_translations=course.description_translations,
        thumbnail_url=course.thumbnail_url,
        course_type=course.course_type,
        order=course.sort_order,
        status=_value(course.status),
        metadata=course.metadata_json,
        lesson_count=len(
            [
                lesson
                for lesson in course.lessons
                if lesson.content_status == ContentStatus.PUBLISHED
            ]
        ),
    )


def _lesson_list_out(
    lesson: Lesson, progress: LessonProgress | None = None
) -> LessonListOut:
    content = _content_dict(lesson.content)
    return LessonListOut(
        id=lesson.id,
        hsk_level_id=lesson.hsk_level_id,
        course_id=lesson.course_id,
        title=lesson.title,
        title_translations=content.get("title_translations"),
        description=lesson.description,
        description_translations=content.get("description_translations"),
        lesson_type=lesson.lesson_type,
        sort_order=lesson.sort_order,
        duration_minutes=lesson.duration_minutes,
        status=progress.status if progress else None,
        score_percent=progress.score_percent if progress else None,
        lesson_number=lesson.sort_order,
        difficulty=lesson.difficulty,
        content_status=_value(lesson.content_status),
    )


def _user_vocabulary_state(
    db: Session, user: User | None, vocabulary_ids: list[int]
) -> tuple[dict[int, str], set[int]]:
    if not user or not vocabulary_ids:
        return {}, set()
    progress = {
        row.vocabulary_id: _value(row.status)
        for row in db.scalars(
            select(UserVocabularyProgress).where(
                UserVocabularyProgress.user_id == user.id,
                UserVocabularyProgress.vocabulary_id.in_(vocabulary_ids),
            )
        )
    }
    favorites = set(
        db.scalars(
            select(SavedWord.vocabulary_id).where(
                SavedWord.user_id == user.id,
                SavedWord.vocabulary_id.in_(vocabulary_ids),
            )
        )
    )
    return progress, {item for item in favorites if item is not None}


def _user_grammar_state(
    db: Session, user: User | None, grammar_ids: list[int]
) -> dict[int, str]:
    if not user or not grammar_ids:
        return {}
    return {
        row.grammar_point_id: _value(row.status)
        for row in db.scalars(
            select(UserGrammarProgress).where(
                UserGrammarProgress.user_id == user.id,
                UserGrammarProgress.grammar_point_id.in_(grammar_ids),
            )
        )
    }


def _vocabulary_load_options() -> tuple[Any, ...]:
    return (
        joinedload(Vocabulary.hsk_level),
        joinedload(Vocabulary.audio_asset),
        selectinload(Vocabulary.example_links)
        .selectinload(VocabularyExample.example)
        .joinedload(ExampleSentence.audio_asset),
        selectinload(Vocabulary.lesson_links).joinedload(LessonVocabulary.lesson),
    )


def _grammar_load_options() -> tuple[Any, ...]:
    return (
        joinedload(GrammarPoint.hsk_level),
        selectinload(GrammarPoint.example_links)
        .selectinload(GrammarExample.example)
        .joinedload(ExampleSentence.audio_asset),
        selectinload(GrammarPoint.lesson_links).joinedload(
            LessonGrammarPoint.lesson
        ),
    )


@router.get("/hsk/levels", response_model=list[HskLevelOut])
def list_hsk_levels(db: Session = Depends(get_db)) -> list[HskLevelOut]:
    levels = db.scalars(
        select(HskLevel)
        .where(HskLevel.status == ContentStatus.PUBLISHED)
        .options(selectinload(HskLevel.courses))
        .order_by(HskLevel.display_order, HskLevel.level_number)
    ).all()
    return [_hsk_level_out(level) for level in levels]


@router.get("/courses", response_model=list[CourseOut])
def list_courses(
    hsk_level: int | None = Query(default=None, ge=1, le=6),
    hsk_level_id: int | None = Query(default=None, ge=1),
    db: Session = Depends(get_db),
) -> list[CourseOut]:
    stmt = (
        select(Course)
        .join(Course.hsk_level)
        .where(
            Course.status == ContentStatus.PUBLISHED,
            HskLevel.status == ContentStatus.PUBLISHED,
        )
        .options(joinedload(Course.hsk_level), selectinload(Course.lessons))
    )
    if hsk_level is not None:
        stmt = stmt.where(HskLevel.level_number == hsk_level)
    if hsk_level_id is not None:
        stmt = stmt.where(Course.hsk_level_id == hsk_level_id)
    courses = db.scalars(
        stmt.order_by(HskLevel.level_number, Course.sort_order, Course.id)
    ).unique().all()
    return [_course_out(course) for course in courses]


@router.get("/courses/{course_id}", response_model=CourseOut)
def get_course(course_id: int, db: Session = Depends(get_db)) -> CourseOut:
    course = db.scalar(
        select(Course)
        .where(
            Course.id == course_id,
            Course.status == ContentStatus.PUBLISHED,
        )
        .options(joinedload(Course.hsk_level), selectinload(Course.lessons))
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _course_out(course)


@router.get("/courses/{course_id}/lessons", response_model=list[LessonListOut])
def list_course_lessons(
    course_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[LessonListOut]:
    course = db.scalar(
        select(Course).where(
            Course.id == course_id,
            Course.status == ContentStatus.PUBLISHED,
        )
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    lessons = db.scalars(
        select(Lesson)
        .where(
            Lesson.course_id == course_id,
            Lesson.content_status == ContentStatus.PUBLISHED,
        )
        .order_by(Lesson.sort_order, Lesson.id)
    ).all()
    progress: dict[int, LessonProgress] = {}
    if user and lessons:
        progress = {
            row.lesson_id: row
            for row in db.scalars(
                select(LessonProgress).where(
                    LessonProgress.user_id == user.id,
                    LessonProgress.lesson_id.in_([lesson.id for lesson in lessons]),
                )
            )
        }
    return [_lesson_list_out(lesson, progress.get(lesson.id)) for lesson in lessons]


def _legacy_vocabulary(vocabulary: Vocabulary) -> dict[str, Any]:
    examples = [link.example for link in vocabulary.example_links]
    example = examples[0] if examples else None
    translations = vocabulary.meaning_translations
    audio = _audio_out(vocabulary.audio_asset)
    return {
        "id": vocabulary.id,
        "hanzi": vocabulary.simplified,
        "traditional": vocabulary.traditional,
        "pinyin": vocabulary.pinyin or "",
        "meaning": translations.get("vi") or translations.get("en") or "",
        "meaning_vi": translations.get("vi", ""),
        "meaning_en": translations.get("en", ""),
        "translations": translations,
        "word_type": vocabulary.part_of_speech,
        "category": vocabulary.category,
        "hsk_level": vocabulary.hsk_level.level_number,
        "example_cn": example.chinese if example else None,
        "example_pinyin": example.pinyin if example else None,
        "example_translations": example.translations if example else None,
        "audio": audio.model_dump() if audio else None,
    }


def _legacy_grammar(grammar: GrammarPoint) -> dict[str, Any]:
    return {
        "id": grammar.id,
        "title": grammar.title,
        "title_translations": grammar.title_translations,
        "structure": grammar.pattern,
        "explanation": grammar.explanation_translations.get("vi")
        or grammar.explanation_translations.get("en")
        or "",
        "explanation_translations": grammar.explanation_translations,
        "examples": [
            {
                "id": link.example.id,
                "hanzi": link.example.chinese,
                "pinyin": link.example.pinyin or "",
                "meaning": link.example.translations.get("vi")
                or link.example.translations.get("en")
                or "",
                "translations": link.example.translations,
            }
            for link in grammar.example_links
        ],
    }


@router.get("/lessons/{lesson_id}", response_model=LessonDetailOut)
def get_lesson(
    lesson_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> LessonDetailOut:
    lesson = db.scalar(
        select(Lesson)
        .where(
            Lesson.id == lesson_id,
            Lesson.content_status == ContentStatus.PUBLISHED,
        )
        .options(
            joinedload(Lesson.hsk_level),
            joinedload(Lesson.listening_audio_asset),
            selectinload(Lesson.vocabulary_links)
            .selectinload(LessonVocabulary.vocabulary)
            .options(
                joinedload(Vocabulary.hsk_level),
                joinedload(Vocabulary.audio_asset),
                selectinload(Vocabulary.example_links)
                .selectinload(VocabularyExample.example)
                .joinedload(ExampleSentence.audio_asset),
            ),
            selectinload(Lesson.grammar_links)
            .selectinload(LessonGrammarPoint.grammar_point)
            .options(
                joinedload(GrammarPoint.hsk_level),
                selectinload(GrammarPoint.example_links)
                .selectinload(GrammarExample.example)
                .joinedload(ExampleSentence.audio_asset),
            ),
        )
    )
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    vocabulary = [link.vocabulary for link in lesson.vocabulary_links]
    grammar = [link.grammar_point for link in lesson.grammar_links]
    vocabulary_status, favorites = _user_vocabulary_state(
        db, user, [item.id for item in vocabulary]
    )
    grammar_status = _user_grammar_state(db, user, [item.id for item in grammar])
    content = public_lesson_content(lesson.content)
    content["vocabulary"] = [_legacy_vocabulary(item) for item in vocabulary]
    content["grammar_points"] = [_legacy_grammar(item) for item in grammar]
    return LessonDetailOut(
        id=lesson.id,
        hsk_level_id=lesson.hsk_level_id,
        course_id=lesson.course_id,
        title=lesson.title,
        title_translations=content.get("title_translations"),
        description=lesson.description,
        description_translations=content.get("description_translations"),
        lesson_type=lesson.lesson_type,
        lesson_number=lesson.sort_order,
        duration_minutes=lesson.duration_minutes,
        difficulty=lesson.difficulty,
        content_status=_value(lesson.content_status),
        content=content,
        vocabulary=[
            _vocabulary_item(
                item,
                vocabulary_status.get(item.id, "new"),
                item.id in favorites,
            )
            for item in vocabulary
        ],
        grammar=[
            _grammar_item(item, grammar_status.get(item.id)) for item in grammar
        ],
        reading=content.get("reading") or content.get("passage"),
        listening=content.get("listening") or content.get("transcript"),
        listening_audio=_audio_out(lesson.listening_audio_asset),
        practice=content.get("practice_exercises"),
    )


def _vocabulary_page(
    db: Session,
    user: User | None,
    stmt: Any,
    page: int,
    page_size: int,
) -> VocabularyPageOut:
    total = db.scalar(select(func.count()).select_from(stmt.order_by(None).subquery())) or 0
    rows = db.scalars(
        stmt.options(
            joinedload(Vocabulary.hsk_level),
            joinedload(Vocabulary.audio_asset),
        )
        .order_by(Vocabulary.hsk_level_id, Vocabulary.display_order, Vocabulary.id)
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).unique().all()
    learning_status, favorites = _user_vocabulary_state(
        db, user, [item.id for item in rows]
    )
    return VocabularyPageOut(
        items=[
            _vocabulary_item(
                item,
                learning_status.get(item.id, "new"),
                item.id in favorites,
            )
            for item in rows
        ],
        page=page,
        page_size=page_size,
        total=total,
        pages=math.ceil(total / page_size) if total else 0,
    )


@router.get("/vocabulary", response_model=VocabularyPageOut)
def list_vocabulary(
    hsk_level: int | None = Query(default=None, ge=1, le=6),
    lesson_id: int | None = Query(default=None, ge=1),
    search: str | None = Query(default=None, min_length=1, max_length=120),
    pinyin: str | None = Query(default=None, min_length=1, max_length=160),
    part_of_speech: str | None = Query(default=None, min_length=1, max_length=40),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> VocabularyPageOut:
    stmt = (
        select(Vocabulary)
        .join(Vocabulary.hsk_level)
        .where(
            Vocabulary.status == ContentStatus.PUBLISHED,
            HskLevel.status == ContentStatus.PUBLISHED,
        )
    )
    if lesson_id is not None:
        stmt = stmt.join(Vocabulary.lesson_links).where(
            LessonVocabulary.lesson_id == lesson_id
        )
    if hsk_level is not None:
        stmt = stmt.where(HskLevel.level_number == hsk_level)
    if part_of_speech:
        stmt = stmt.where(Vocabulary.part_of_speech == part_of_speech)
    if pinyin:
        stmt = stmt.where(Vocabulary.pinyin.ilike(f"%{pinyin.strip()}%"))
    if search:
        value = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Vocabulary.simplified.ilike(value),
                Vocabulary.traditional.ilike(value),
                Vocabulary.pinyin.ilike(value),
            )
        )
    return _vocabulary_page(db, user, stmt, page, page_size)


@router.get(
    "/lessons/{lesson_id}/vocabulary", response_model=VocabularyPageOut
)
def list_lesson_vocabulary(
    lesson_id: int,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> VocabularyPageOut:
    if not db.get(Lesson, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    stmt = (
        select(Vocabulary)
        .join(Vocabulary.lesson_links)
        .where(
            LessonVocabulary.lesson_id == lesson_id,
            Vocabulary.status == ContentStatus.PUBLISHED,
        )
    )
    return _vocabulary_page(db, user, stmt, page, page_size)


@router.get("/vocabulary/favorites", response_model=VocabularyPageOut)
def list_favorite_vocabulary(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyPageOut:
    stmt = (
        select(Vocabulary)
        .join(SavedWord, SavedWord.vocabulary_id == Vocabulary.id)
        .where(
            SavedWord.user_id == user.id,
            Vocabulary.status == ContentStatus.PUBLISHED,
        )
    )
    return _vocabulary_page(db, user, stmt, page, page_size)


def _vocabulary_detail(
    db: Session, vocabulary_id: int, user: User | None
) -> VocabularyDetailOut:
    vocabulary = db.scalar(
        select(Vocabulary)
        .where(
            Vocabulary.id == vocabulary_id,
            Vocabulary.status == ContentStatus.PUBLISHED,
        )
        .options(*_vocabulary_load_options())
    )
    if not vocabulary:
        raise HTTPException(status_code=404, detail="Vocabulary not found")
    learning_status, favorites = _user_vocabulary_state(
        db, user, [vocabulary.id]
    )
    base = _vocabulary_item(
        vocabulary,
        learning_status.get(vocabulary.id, "new"),
        vocabulary.id in favorites,
    )
    return VocabularyDetailOut(
        **base.model_dump(),
        hsk_level_id=vocabulary.hsk_level_id,
        category=vocabulary.category,
        examples=[_example_out(link.example) for link in vocabulary.example_links],
        lessons=[_lesson_reference(link.lesson) for link in vocabulary.lesson_links],
        status=_value(vocabulary.status),
        metadata=vocabulary.metadata_json,
    )


@router.get("/vocabulary/{vocabulary_id}", response_model=VocabularyDetailOut)
def get_vocabulary(
    vocabulary_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> VocabularyDetailOut:
    return _vocabulary_detail(db, vocabulary_id, user)


@router.post(
    "/vocabulary/{vocabulary_id}/favorite",
    response_model=VocabularyDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def favorite_vocabulary(
    vocabulary_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> VocabularyDetailOut:
    vocabulary = db.get(Vocabulary, vocabulary_id)
    if not vocabulary or vocabulary.status != ContentStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Vocabulary not found")
    favorite = db.scalar(
        select(SavedWord).where(
            SavedWord.user_id == user.id,
            SavedWord.vocabulary_id == vocabulary_id,
        )
    )
    if not favorite:
        translations = vocabulary.meaning_translations
        favorite = SavedWord(
            user_id=user.id,
            vocabulary_id=vocabulary.id,
            hanzi=vocabulary.simplified,
            pinyin=vocabulary.pinyin,
            meaning=translations.get("vi") or translations.get("en"),
            hsk_level=vocabulary.hsk_level.level_number,
        )
        db.add(favorite)
        db.commit()
    return _vocabulary_detail(db, vocabulary_id, user)


@router.delete(
    "/vocabulary/{vocabulary_id}/favorite",
    status_code=status.HTTP_204_NO_CONTENT,
)
def unfavorite_vocabulary(
    vocabulary_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    favorite = db.scalar(
        select(SavedWord).where(
            SavedWord.user_id == user.id,
            SavedWord.vocabulary_id == vocabulary_id,
        )
    )
    if favorite:
        db.delete(favorite)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/lessons/{lesson_id}/grammar", response_model=list[GrammarListItemOut]
)
def list_lesson_grammar(
    lesson_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> list[GrammarListItemOut]:
    if not db.get(Lesson, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    grammar = db.scalars(
        select(GrammarPoint)
        .join(GrammarPoint.lesson_links)
        .where(
            LessonGrammarPoint.lesson_id == lesson_id,
            GrammarPoint.status == ContentStatus.PUBLISHED,
        )
        .options(joinedload(GrammarPoint.hsk_level))
        .order_by(LessonGrammarPoint.sort_order, GrammarPoint.id)
    ).unique().all()
    states = _user_grammar_state(db, user, [item.id for item in grammar])
    return [_grammar_item(item, states.get(item.id)) for item in grammar]


def _grammar_detail(
    db: Session, grammar_id: int, user: User | None
) -> GrammarDetailOut:
    grammar = db.scalar(
        select(GrammarPoint)
        .where(
            GrammarPoint.id == grammar_id,
            GrammarPoint.status == ContentStatus.PUBLISHED,
        )
        .options(*_grammar_load_options())
    )
    if not grammar:
        raise HTTPException(status_code=404, detail="Grammar point not found")
    states = _user_grammar_state(db, user, [grammar.id])
    base = _grammar_item(grammar, states.get(grammar.id))
    return GrammarDetailOut(
        **base.model_dump(),
        hsk_level_id=grammar.hsk_level_id,
        examples=[_example_out(link.example) for link in grammar.example_links],
        lessons=[_lesson_reference(link.lesson) for link in grammar.lesson_links],
        status=_value(grammar.status),
        metadata=grammar.metadata_json,
    )


@router.get("/grammar/{grammar_id}", response_model=GrammarDetailOut)
def get_grammar(
    grammar_id: int,
    user: User | None = Depends(get_optional_user),
    db: Session = Depends(get_db),
) -> GrammarDetailOut:
    return _grammar_detail(db, grammar_id, user)


@router.post("/lessons/{lesson_id}/start", response_model=LearningProgressOut)
def start_lesson(
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    if not db.get(Lesson, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    now = datetime.now(UTC)
    progress = db.scalar(
        select(LessonProgress).where(
            LessonProgress.user_id == user.id,
            LessonProgress.lesson_id == lesson_id,
        )
    )
    if not progress:
        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson_id,
            status="in_progress",
            started_at=now,
        )
        db.add(progress)
    progress.started_at = progress.started_at or now
    progress.last_viewed_at = now
    db.commit()
    return LearningProgressOut(
        item_id=lesson_id,
        status=progress.status,
        first_viewed_at=progress.started_at,
        last_viewed_at=progress.last_viewed_at,
        completed_at=progress.completed_at,
    )


@router.post("/lessons/{lesson_id}/complete", response_model=LearningProgressOut)
def complete_lesson(
    lesson_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    if not db.get(Lesson, lesson_id):
        raise HTTPException(status_code=404, detail="Lesson not found")
    now = datetime.now(UTC)
    progress = db.scalar(
        select(LessonProgress).where(
            LessonProgress.user_id == user.id,
            LessonProgress.lesson_id == lesson_id,
        )
    )
    if not progress:
        progress = LessonProgress(
            user_id=user.id,
            lesson_id=lesson_id,
            started_at=now,
        )
        db.add(progress)
    progress.status = "completed"
    progress.started_at = progress.started_at or now
    progress.last_viewed_at = now
    progress.completed_at = now
    db.commit()
    return LearningProgressOut(
        item_id=lesson_id,
        status=progress.status,
        first_viewed_at=progress.started_at,
        last_viewed_at=progress.last_viewed_at,
        completed_at=progress.completed_at,
    )


@router.post("/vocabulary/{vocabulary_id}/view", response_model=LearningProgressOut)
def view_vocabulary(
    vocabulary_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    if not db.get(Vocabulary, vocabulary_id):
        raise HTTPException(status_code=404, detail="Vocabulary not found")
    now = datetime.now(UTC)
    progress = db.scalar(
        select(UserVocabularyProgress).where(
            UserVocabularyProgress.user_id == user.id,
            UserVocabularyProgress.vocabulary_id == vocabulary_id,
        )
    )
    if not progress:
        progress = UserVocabularyProgress(
            user_id=user.id,
            vocabulary_id=vocabulary_id,
            status=VocabularyLearningStatus.NEW,
            first_viewed_at=now,
        )
        db.add(progress)
    progress.first_viewed_at = progress.first_viewed_at or now
    progress.last_viewed_at = now
    db.commit()
    return LearningProgressOut(
        item_id=vocabulary_id,
        status=_value(progress.status),
        first_viewed_at=progress.first_viewed_at,
        last_viewed_at=progress.last_viewed_at,
        completed_at=progress.learned_at,
    )


@router.patch(
    "/vocabulary/{vocabulary_id}/status", response_model=LearningProgressOut
)
def update_vocabulary_status(
    vocabulary_id: int,
    payload: VocabularyStatusIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    if not db.get(Vocabulary, vocabulary_id):
        raise HTTPException(status_code=404, detail="Vocabulary not found")
    now = datetime.now(UTC)
    progress = db.scalar(
        select(UserVocabularyProgress).where(
            UserVocabularyProgress.user_id == user.id,
            UserVocabularyProgress.vocabulary_id == vocabulary_id,
        )
    )
    if not progress:
        progress = UserVocabularyProgress(
            user_id=user.id,
            vocabulary_id=vocabulary_id,
            first_viewed_at=now,
        )
        db.add(progress)
    progress.status = VocabularyLearningStatus(payload.status)
    progress.first_viewed_at = progress.first_viewed_at or now
    progress.last_viewed_at = now
    if progress.status in {
        VocabularyLearningStatus.LEARNED,
        VocabularyLearningStatus.MASTERED,
    }:
        progress.learned_at = progress.learned_at or now
    db.commit()
    return LearningProgressOut(
        item_id=vocabulary_id,
        status=_value(progress.status),
        first_viewed_at=progress.first_viewed_at,
        last_viewed_at=progress.last_viewed_at,
        completed_at=progress.learned_at,
    )


def _update_grammar_progress(
    db: Session, user: User, grammar_id: int, complete: bool
) -> LearningProgressOut:
    if not db.get(GrammarPoint, grammar_id):
        raise HTTPException(status_code=404, detail="Grammar point not found")
    now = datetime.now(UTC)
    progress = db.scalar(
        select(UserGrammarProgress).where(
            UserGrammarProgress.user_id == user.id,
            UserGrammarProgress.grammar_point_id == grammar_id,
        )
    )
    if not progress:
        progress = UserGrammarProgress(
            user_id=user.id,
            grammar_point_id=grammar_id,
            first_viewed_at=now,
        )
        db.add(progress)
    progress.status = (
        GrammarLearningStatus.COMPLETED
        if complete
        else GrammarLearningStatus.VIEWED
    )
    progress.first_viewed_at = progress.first_viewed_at or now
    progress.last_viewed_at = now
    if complete:
        progress.completed_at = now
    db.commit()
    return LearningProgressOut(
        item_id=grammar_id,
        status=_value(progress.status),
        first_viewed_at=progress.first_viewed_at,
        last_viewed_at=progress.last_viewed_at,
        completed_at=progress.completed_at,
    )


@router.post("/grammar/{grammar_id}/view", response_model=LearningProgressOut)
def view_grammar(
    grammar_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    return _update_grammar_progress(db, user, grammar_id, False)


@router.post("/grammar/{grammar_id}/complete", response_model=LearningProgressOut)
def complete_grammar(
    grammar_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LearningProgressOut:
    return _update_grammar_progress(db, user, grammar_id, True)


def _import_job_out(job: ImportJob) -> ImportJobOut:
    return ImportJobOut(
        id=job.id,
        entity_type=_value(job.entity_type),
        source_format=job.source_format,
        status=_value(job.status),
        total_records=job.total_records,
        created_records=job.created_records,
        updated_records=job.updated_records,
        skipped_records=job.skipped_records,
        errors=job.errors,
    )


@router.post(
    "/admin/content/imports",
    response_model=ImportJobOut,
    status_code=status.HTTP_201_CREATED,
)
def import_content(
    payload: ImportRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportJobOut:
    try:
        job = ContentImporter(db, admin.id).run(
            ImportEntityType(payload.entity_type),
            payload.source_format,
            payload.data,
        )
    except ImportValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail={"job_id": exc.job_id, "errors": exc.errors},
        ) from exc
    return _import_job_out(job)


@router.get("/admin/content/imports/{job_id}", response_model=ImportJobOut)
def get_import_job(
    job_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ImportJobOut:
    job = db.get(ImportJob, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Import job not found")
    return _import_job_out(job)


def _commit(db: Session, detail: str = "Content conflicts with an existing record") -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=detail) from exc


def _archive(row: Any, db: Session) -> Response:
    row.status = ContentStatus.ARCHIVED
    _commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _replace_vocabulary_links(
    db: Session,
    vocabulary: Vocabulary,
    lesson_ids: list[int],
    example_ids: list[int],
) -> None:
    db.execute(
        delete(LessonVocabulary).where(
            LessonVocabulary.vocabulary_id == vocabulary.id
        )
    )
    db.execute(
        delete(VocabularyExample).where(
            VocabularyExample.vocabulary_id == vocabulary.id
        )
    )
    for order, lesson_id in enumerate(dict.fromkeys(lesson_ids), start=1):
        if not db.get(Lesson, lesson_id):
            raise HTTPException(status_code=422, detail=f"Lesson {lesson_id} not found")
        db.add(
            LessonVocabulary(
                lesson_id=lesson_id,
                vocabulary_id=vocabulary.id,
                sort_order=order,
            )
        )
    for order, example_id in enumerate(dict.fromkeys(example_ids), start=1):
        if not db.get(ExampleSentence, example_id):
            raise HTTPException(
                status_code=422, detail=f"Example sentence {example_id} not found"
            )
        db.add(
            VocabularyExample(
                vocabulary_id=vocabulary.id,
                example_id=example_id,
                sort_order=order,
            )
        )


def _replace_grammar_links(
    db: Session,
    grammar: GrammarPoint,
    lesson_ids: list[int],
    example_ids: list[int],
) -> None:
    db.execute(
        delete(LessonGrammarPoint).where(
            LessonGrammarPoint.grammar_point_id == grammar.id
        )
    )
    db.execute(
        delete(GrammarExample).where(GrammarExample.grammar_point_id == grammar.id)
    )
    for order, lesson_id in enumerate(dict.fromkeys(lesson_ids), start=1):
        if not db.get(Lesson, lesson_id):
            raise HTTPException(status_code=422, detail=f"Lesson {lesson_id} not found")
        db.add(
            LessonGrammarPoint(
                lesson_id=lesson_id,
                grammar_point_id=grammar.id,
                sort_order=order,
            )
        )
    for order, example_id in enumerate(dict.fromkeys(example_ids), start=1):
        if not db.get(ExampleSentence, example_id):
            raise HTTPException(
                status_code=422, detail=f"Example sentence {example_id} not found"
            )
        db.add(
            GrammarExample(
                grammar_point_id=grammar.id,
                example_id=example_id,
                sort_order=order,
            )
        )


@router.post(
    "/admin/content/hsk-levels",
    response_model=HskLevelOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_hsk_level(
    payload: HskLevelCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HskLevelOut:
    level = HskLevel(
        level_number=payload.level_number,
        title=payload.name.strip(),
        description=payload.description,
        display_order=payload.display_order,
        total_characters=payload.total_characters,
        status=ContentStatus(payload.status),
        metadata_json=payload.metadata,
    )
    db.add(level)
    _commit(db)
    db.refresh(level)
    level.courses = []
    return _hsk_level_out(level)


@router.patch("/admin/content/hsk-levels/{level_id}", response_model=HskLevelOut)
def admin_update_hsk_level(
    level_id: int,
    payload: HskLevelUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> HskLevelOut:
    level = db.scalar(
        select(HskLevel)
        .where(HskLevel.id == level_id)
        .options(selectinload(HskLevel.courses))
    )
    if not level:
        raise HTTPException(status_code=404, detail="HSK level not found")
    values = payload.model_dump(exclude_unset=True)
    if "name" in values:
        level.title = values.pop("name").strip()
    if "status" in values:
        values["status"] = ContentStatus(values["status"])
    if "metadata" in values:
        values["metadata_json"] = values.pop("metadata")
    for key, value in values.items():
        setattr(level, key, value)
    _commit(db)
    return _hsk_level_out(level)


@router.delete(
    "/admin/content/hsk-levels/{level_id}", status_code=status.HTTP_204_NO_CONTENT
)
def admin_delete_hsk_level(
    level_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    level = db.get(HskLevel, level_id)
    if not level:
        raise HTTPException(status_code=404, detail="HSK level not found")
    return _archive(level, db)


@router.post(
    "/admin/content/courses",
    response_model=CourseOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_course(
    payload: CourseCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CourseOut:
    level = db.get(HskLevel, payload.hsk_level_id)
    if not level:
        raise HTTPException(status_code=422, detail="HSK level not found")
    course = Course(
        hsk_level_id=level.id,
        title=payload.title.strip(),
        title_translations=payload.title_translations,
        description=payload.description,
        description_translations=payload.description_translations,
        thumbnail_url=payload.thumbnail_url,
        course_type=payload.course_type,
        sort_order=payload.order,
        status=ContentStatus(payload.status),
        metadata_json=payload.metadata,
    )
    db.add(course)
    _commit(db)
    db.refresh(course)
    course.hsk_level = level
    course.lessons = []
    return _course_out(course)


@router.patch("/admin/content/courses/{course_id}", response_model=CourseOut)
def admin_update_course(
    course_id: int,
    payload: CourseUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> CourseOut:
    course = db.scalar(
        select(Course)
        .where(Course.id == course_id)
        .options(joinedload(Course.hsk_level), selectinload(Course.lessons))
    )
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    values = payload.model_dump(exclude_unset=True)
    if "order" in values:
        values["sort_order"] = values.pop("order")
    if "status" in values:
        values["status"] = ContentStatus(values["status"])
    if "metadata" in values:
        values["metadata_json"] = values.pop("metadata")
    for key, value in values.items():
        setattr(course, key, value)
    _commit(db)
    return _course_out(course)


@router.delete(
    "/admin/content/courses/{course_id}", status_code=status.HTTP_204_NO_CONTENT
)
def admin_delete_course(
    course_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    course = db.get(Course, course_id)
    if not course:
        raise HTTPException(status_code=404, detail="Course not found")
    return _archive(course, db)


@router.post(
    "/admin/content/lessons",
    response_model=LessonDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_lesson(
    payload: LessonCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LessonDetailOut:
    course = db.get(Course, payload.course_id)
    if not course:
        raise HTTPException(status_code=422, detail="Course not found")
    if payload.listening_audio_asset_id and not db.get(
        AudioAsset, payload.listening_audio_asset_id
    ):
        raise HTTPException(status_code=422, detail="Audio asset not found")
    lesson = Lesson(
        course_id=course.id,
        hsk_level_id=course.hsk_level_id,
        title=payload.title.strip(),
        description=payload.description,
        lesson_type=payload.lesson_type,
        sort_order=payload.order,
        duration_minutes=payload.estimated_duration,
        difficulty=payload.difficulty,
        listening_audio_asset_id=payload.listening_audio_asset_id,
        content_status=ContentStatus(payload.status),
        metadata_json=payload.metadata,
        content=payload.content,
    )
    db.add(lesson)
    _commit(db)
    return get_lesson(lesson.id, None, db)


@router.patch("/admin/content/lessons/{lesson_id}", response_model=LessonDetailOut)
def admin_update_lesson(
    lesson_id: int,
    payload: LessonUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> LessonDetailOut:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("listening_audio_asset_id") and not db.get(
        AudioAsset, values["listening_audio_asset_id"]
    ):
        raise HTTPException(status_code=422, detail="Audio asset not found")
    if "course_id" in values:
        course = db.get(Course, values["course_id"])
        if not course:
            raise HTTPException(status_code=422, detail="Course not found")
        lesson.hsk_level_id = course.hsk_level_id
    aliases = {
        "order": "sort_order",
        "estimated_duration": "duration_minutes",
        "status": "content_status",
        "metadata": "metadata_json",
    }
    for key, value in values.items():
        target = aliases.get(key, key)
        if key == "status":
            value = ContentStatus(value)
        setattr(lesson, target, value)
    _commit(db)
    if lesson.content_status == ContentStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="Lesson archived")
    return get_lesson(lesson.id, None, db)


@router.delete(
    "/admin/content/lessons/{lesson_id}", status_code=status.HTTP_204_NO_CONTENT
)
def admin_delete_lesson(
    lesson_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    lesson.content_status = ContentStatus.ARCHIVED
    _commit(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/admin/content/vocabulary",
    response_model=VocabularyDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_vocabulary(
    payload: VocabularyCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VocabularyDetailOut:
    if not db.get(HskLevel, payload.hsk_level_id):
        raise HTTPException(status_code=422, detail="HSK level not found")
    vocabulary = Vocabulary(
        hsk_level_id=payload.hsk_level_id,
        simplified=payload.simplified.strip(),
        traditional=payload.traditional,
        pinyin=(payload.pinyin or "").strip() or None,
        meaning_translations=payload.meaning_translations,
        part_of_speech=payload.part_of_speech,
        category=payload.category,
        audio_asset_id=payload.audio_asset_id,
        difficulty=payload.difficulty,
        display_order=payload.display_order,
        status=ContentStatus(payload.status),
        metadata_json=payload.metadata,
    )
    db.add(vocabulary)
    db.flush()
    _replace_vocabulary_links(
        db, vocabulary, payload.lesson_ids, payload.example_ids
    )
    _commit(db)
    return _vocabulary_detail(db, vocabulary.id, None)


@router.patch(
    "/admin/content/vocabulary/{vocabulary_id}", response_model=VocabularyDetailOut
)
def admin_update_vocabulary(
    vocabulary_id: int,
    payload: VocabularyUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> VocabularyDetailOut:
    vocabulary = db.get(Vocabulary, vocabulary_id)
    if not vocabulary:
        raise HTTPException(status_code=404, detail="Vocabulary not found")
    values = payload.model_dump(exclude_unset=True)
    lesson_ids = values.pop("lesson_ids", None)
    example_ids = values.pop("example_ids", None)
    if "status" in values:
        values["status"] = ContentStatus(values["status"])
    if "metadata" in values:
        values["metadata_json"] = values.pop("metadata")
    for key, value in values.items():
        setattr(vocabulary, key, value)
    if lesson_ids is not None or example_ids is not None:
        current_lessons = (
            lesson_ids
            if lesson_ids is not None
            else [link.lesson_id for link in vocabulary.lesson_links]
        )
        current_examples = (
            example_ids
            if example_ids is not None
            else [link.example_id for link in vocabulary.example_links]
        )
        _replace_vocabulary_links(
            db, vocabulary, current_lessons, current_examples
        )
    _commit(db)
    if vocabulary.status == ContentStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="Vocabulary archived")
    return _vocabulary_detail(db, vocabulary.id, None)


@router.delete(
    "/admin/content/vocabulary/{vocabulary_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_delete_vocabulary(
    vocabulary_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    vocabulary = db.get(Vocabulary, vocabulary_id)
    if not vocabulary:
        raise HTTPException(status_code=404, detail="Vocabulary not found")
    return _archive(vocabulary, db)


@router.post(
    "/admin/content/grammar",
    response_model=GrammarDetailOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_grammar(
    payload: GrammarCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GrammarDetailOut:
    if not db.get(HskLevel, payload.hsk_level_id):
        raise HTTPException(status_code=422, detail="HSK level not found")
    grammar = GrammarPoint(
        hsk_level_id=payload.hsk_level_id,
        title=payload.title.strip(),
        title_translations=payload.title_translations,
        explanation_translations=payload.explanation_translations,
        pattern=payload.pattern,
        difficulty=payload.difficulty,
        display_order=payload.display_order,
        status=ContentStatus(payload.status),
        metadata_json=payload.metadata,
    )
    db.add(grammar)
    db.flush()
    _replace_grammar_links(db, grammar, payload.lesson_ids, payload.example_ids)
    _commit(db)
    return _grammar_detail(db, grammar.id, None)


@router.patch(
    "/admin/content/grammar/{grammar_id}", response_model=GrammarDetailOut
)
def admin_update_grammar(
    grammar_id: int,
    payload: GrammarUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> GrammarDetailOut:
    grammar = db.get(GrammarPoint, grammar_id)
    if not grammar:
        raise HTTPException(status_code=404, detail="Grammar point not found")
    values = payload.model_dump(exclude_unset=True)
    lesson_ids = values.pop("lesson_ids", None)
    example_ids = values.pop("example_ids", None)
    if "status" in values:
        values["status"] = ContentStatus(values["status"])
    if "metadata" in values:
        values["metadata_json"] = values.pop("metadata")
    for key, value in values.items():
        setattr(grammar, key, value)
    if lesson_ids is not None or example_ids is not None:
        current_lessons = (
            lesson_ids
            if lesson_ids is not None
            else [link.lesson_id for link in grammar.lesson_links]
        )
        current_examples = (
            example_ids
            if example_ids is not None
            else [link.example_id for link in grammar.example_links]
        )
        _replace_grammar_links(db, grammar, current_lessons, current_examples)
    _commit(db)
    if grammar.status == ContentStatus.ARCHIVED:
        raise HTTPException(status_code=404, detail="Grammar point archived")
    return _grammar_detail(db, grammar.id, None)


@router.delete(
    "/admin/content/grammar/{grammar_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_delete_grammar(
    grammar_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    grammar = db.get(GrammarPoint, grammar_id)
    if not grammar:
        raise HTTPException(status_code=404, detail="Grammar point not found")
    return _archive(grammar, db)


@router.post(
    "/admin/content/example-sentences",
    response_model=ExampleSentenceOut,
    status_code=status.HTTP_201_CREATED,
)
def admin_create_example(
    payload: ExampleSentenceCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExampleSentenceOut:
    if payload.audio_asset_id and not db.get(AudioAsset, payload.audio_asset_id):
        raise HTTPException(status_code=422, detail="Audio asset not found")
    example = ExampleSentence(
        chinese=payload.chinese.strip(),
        pinyin=(payload.pinyin or "").strip() or None,
        translations=payload.translations,
        audio_asset_id=payload.audio_asset_id,
        status=ContentStatus(payload.status),
        metadata_json=payload.metadata,
    )
    db.add(example)
    _commit(db)
    db.refresh(example)
    return _example_out(example)


@router.patch(
    "/admin/content/example-sentences/{example_id}",
    response_model=ExampleSentenceOut,
)
def admin_update_example(
    example_id: int,
    payload: ExampleSentenceUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> ExampleSentenceOut:
    example = db.get(ExampleSentence, example_id)
    if not example:
        raise HTTPException(status_code=404, detail="Example sentence not found")
    values = payload.model_dump(exclude_unset=True)
    if values.get("audio_asset_id") and not db.get(
        AudioAsset, values["audio_asset_id"]
    ):
        raise HTTPException(status_code=422, detail="Audio asset not found")
    if "status" in values:
        values["status"] = ContentStatus(values["status"])
    if "metadata" in values:
        values["metadata_json"] = values.pop("metadata")
    for key, value in values.items():
        setattr(example, key, value)
    _commit(db)
    return _example_out(example)


@router.delete(
    "/admin/content/example-sentences/{example_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def admin_delete_example(
    example_id: int,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Response:
    example = db.get(ExampleSentence, example_id)
    if not example:
        raise HTTPException(status_code=404, detail="Example sentence not found")
    return _archive(example, db)
