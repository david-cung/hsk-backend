from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audio_router import admin_router as audio_admin_router
from app.audio_router import router as audio_router
from app.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
from app.exam_router import admin_router as exam_admin_router
from app.exam_router import router as exam_router
from app.models import (
    Achievement,
    HskLevel,
    Lesson,
    LessonProgress,
    MockTest,
    Profile,
    Question,
    QuizAttempt,
    SavedWord,
    User,
    UserAchievement,
)
from app.practice_router import admin_router as practice_admin_router
from app.practice_router import router as practice_router
from app.progress_router import router as progress_router
from app.progress_service import summary as progress_summary_payload
from app.review_router import router as review_router
from app.review_service import enroll_saved_word
from app.schema_compat import ensure_phase5_schema
from app.schemas import (
    AchievementOut,
    AuthIn,
    HskLevelOut,
    LessonDetailOut,
    LessonListOut,
    MistakeOut,
    MockTestOut,
    MockTestQuestionOut,
    ProfileOut,
    ProfileUpdate,
    ProgressDashboardOut,
    QuestionOut,
    QuizResultItem,
    QuizSubmitIn,
    QuizSubmitOut,
    RegisterIn,
    SavedWordIn,
    SavedWordOut,
    TokenOut,
    UserOut,
)
from app.seed import _native_text_translations, seed_data
from app.speaking_router import router as speaking_router

app = FastAPI(title="HSK Mobile API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(practice_router)
app.include_router(practice_admin_router)
app.include_router(audio_router)
app.include_router(audio_admin_router)
app.include_router(speaking_router)
app.include_router(progress_router)
app.include_router(review_router)
app.include_router(exam_router)
app.include_router(exam_admin_router)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_phase5_schema(engine)
    with SessionLocal() as db:
        seed_data(db)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def profile_to_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        target_hsk_level=profile.target_hsk_level,
        current_hsk_level=profile.current_hsk_level,
        daily_goal_minutes=profile.daily_goal_minutes,
        study_streak_days=profile.study_streak_days,
        longest_streak_days=profile.longest_streak_days,
        last_active_date=profile.last_active_date,
        timezone=profile.timezone,
        daily_new_cards_limit=profile.daily_new_cards_limit,
        daily_review_cards_limit=profile.daily_review_cards_limit,
        onboarding_completed=profile.onboarding_completed,
    )


def _translations(en: str | None = None, vi: str | None = None) -> dict[str, str]:
    return {key: value for key, value in {"en": en, "vi": vi}.items() if value}


def _content_translations(lesson: Lesson, field: str) -> dict[str, str] | None:
    content = lesson.content if isinstance(lesson.content, dict) else {}
    value = content.get(field)
    return value if isinstance(value, dict) else None


def _lesson_title_translations(lesson: Lesson) -> dict[str, str]:
    # Every seeded lesson embeds a real `title_translations` dict in its content
    # (see app/seed.py). `_native_text_translations` is only a defensive fallback
    # for a lesson row that (unexpectedly) has no precomputed translations, so we
    # never fall back to duplicating the same English string as the Vietnamese
    # translation.
    return _content_translations(lesson, "title_translations") or _native_text_translations(lesson.title) or _translations(
        lesson.title
    )


def _lesson_description_translations(lesson: Lesson) -> dict[str, str] | None:
    if not lesson.description:
        return None
    return _content_translations(lesson, "description_translations") or _native_text_translations(
        lesson.description
    ) or _translations(lesson.description)


def _question_translations(question: Question) -> dict[str, object]:
    lesson = question.lesson
    content = lesson.content if lesson and isinstance(lesson.content, dict) else {}
    rows = content.get("question_translations")
    if not isinstance(rows, list):
        return {}
    index = max(question.sort_order - 1, 0)
    if index >= len(rows) or not isinstance(rows[index], dict):
        return {}
    return rows[index]


def _mock_test_title_translations(title: str) -> dict[str, str]:
    parts = title.split()
    if len(parts) >= 3 and parts[0] == "HSK":
        level = parts[1]
        if "Mini Mock Test" in title:
            return _translations(title, f"Đề thi thử mini HSK {level}")
        if "Skills Mix Mock Test" in title:
            return _translations(title, f"Đề thi thử tổng hợp kỹ năng HSK {level}")
        if "Full Practice Mock Test" in title:
            return _translations(title, f"Đề luyện thi đầy đủ HSK {level}")
    return _translations(title, title)


def award_achievements(db: Session, user_id: int) -> None:
    earned_codes = set(
        db.scalars(
            select(Achievement.code)
            .join(UserAchievement, UserAchievement.achievement_id == Achievement.id)
            .where(UserAchievement.user_id == user_id)
        )
    )
    completed_count = db.scalar(
        select(func.count()).select_from(LessonProgress).where(
            LessonProgress.user_id == user_id, LessonProgress.status == "completed"
        )
    )
    saved_count = db.scalar(select(func.count()).select_from(SavedWord).where(SavedWord.user_id == user_id))
    attempt_count = db.scalar(select(func.count()).select_from(QuizAttempt).where(QuizAttempt.user_id == user_id))
    unlocks = []
    if attempt_count and "first_quiz" not in earned_codes:
        unlocks.append("first_quiz")
    if saved_count and "first_word" not in earned_codes:
        unlocks.append("first_word")
    if completed_count >= 3 and "three_lessons" not in earned_codes:
        unlocks.append("three_lessons")
    if not unlocks:
        return
    achievements = db.scalars(select(Achievement).where(Achievement.code.in_(unlocks))).all()
    for achievement in achievements:
        db.add(UserAchievement(user_id=user_id, achievement_id=achievement.id))


def score_questions(rows: list[Question], answers: dict[str, str]) -> tuple[int, int, list[QuizResultItem]]:
    results = []
    correct_count = 0
    for question in rows:
        user_answer = answers.get(str(question.id), "")
        correct = user_answer == question.correct_answer
        correct_count += int(correct)
        metadata = _question_translations(question)
        results.append(
            QuizResultItem(
                question_id=question.id,
                prompt=question.prompt,
                prompt_translations=metadata.get("prompt_translations")
                if isinstance(metadata.get("prompt_translations"), dict)
                else None,
                correct=correct,
                user_answer=user_answer,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
                explanation_translations=metadata.get("explanation_translations")
                if isinstance(metadata.get("explanation_translations"), dict)
                else None,
            )
        )
    score = round((correct_count / len(rows)) * 100) if rows else 0
    return score, correct_count, results


def get_mock_test_questions(db: Session, mock_test: MockTest) -> list[Question]:
    rows = (
        db.scalars(
            select(Question)
            .join(Lesson, Lesson.id == Question.lesson_id)
            .join(HskLevel, HskLevel.id == Lesson.hsk_level_id)
            .where(HskLevel.level_number == mock_test.hsk_level)
            .order_by(Lesson.lesson_type, Lesson.sort_order, Lesson.id, Question.sort_order)
        )
        .unique()
        .all()
    )
    lesson_type_order = ("listening", "reading", "vocabulary", "grammar", "writing", "mixed")
    buckets: dict[str, list[Question]] = {lesson_type: [] for lesson_type in lesson_type_order}
    for row in rows:
        lesson_type = row.lesson.lesson_type if row.lesson else "mixed"
        buckets.setdefault(lesson_type, []).append(row)

    selected: list[Question] = []
    while len(selected) < mock_test.question_count:
        added = False
        for lesson_type in lesson_type_order:
            questions = buckets.get(lesson_type)
            if not questions:
                continue
            selected.append(questions.pop(0))
            added = True
            if len(selected) == mock_test.question_count:
                break
        if not added:
            break
    return selected


@app.post("/api/v1/auth/register", response_model=TokenOut, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> TokenOut:
    email = payload.email.lower()
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status_code=409, detail="Email already registered")
    user = User(email=email, display_name=payload.display_name, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    db.add(Profile(user_id=user.id))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id))


@app.post("/api/v1/auth/login", response_model=TokenOut)
def login(payload: AuthIn, db: Session = Depends(get_db)) -> TokenOut:
    user = db.scalar(select(User).where(User.email == payload.email.lower()))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return TokenOut(access_token=create_access_token(user.id))


@app.get("/api/v1/auth/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name)


@app.get("/api/v1/auth/me/profile", response_model=ProfileOut)
def my_profile(user: User = Depends(get_current_user)) -> ProfileOut:
    return profile_to_out(user.profile)


@app.patch("/api/v1/profile", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ProfileOut:
    updates = payload.model_dump(exclude_unset=True)
    for key, value in updates.items():
        setattr(user.profile, key, value)
    db.commit()
    db.refresh(user.profile)
    return profile_to_out(user.profile)


@app.get("/api/v1/content/levels", response_model=list[HskLevelOut])
def levels(db: Session = Depends(get_db)) -> list[HskLevelOut]:
    rows = db.scalars(select(HskLevel).order_by(HskLevel.level_number)).all()
    return [
        HskLevelOut(
            id=row.id,
            level_number=row.level_number,
            title=row.title,
            # "HSK N" is a standardized proficiency-level name used unchanged in
            # both languages (like a proper noun), not a missed translation.
            title_translations=_translations(row.title, row.title),
            description=row.description,
            description_translations=_translations(
                row.description,
                f"Bài học tiếng Trung có cấu trúc cho HSK {row.level_number}." if row.description else None,
            ),
            total_characters=row.total_characters,
        )
        for row in rows
    ]


@app.get("/api/v1/content/levels/{level_id}/lessons", response_model=list[LessonListOut])
def lessons(
    level_id: int,
    lesson_type: str | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[LessonListOut]:
    stmt = select(Lesson).where(Lesson.hsk_level_id == level_id)
    if lesson_type:
        stmt = stmt.where(Lesson.lesson_type == lesson_type)
    rows = db.scalars(stmt.order_by(Lesson.sort_order, Lesson.id)).all()
    progress = {
        p.lesson_id: p
        for p in db.scalars(
            select(LessonProgress).where(
                LessonProgress.user_id == user.id,
                LessonProgress.lesson_id.in_([lesson.id for lesson in rows] or [0]),
            )
        )
    }
    return [
        LessonListOut(
            id=lesson.id,
            title=lesson.title,
            title_translations=_lesson_title_translations(lesson),
            description=lesson.description,
            description_translations=_lesson_description_translations(lesson),
            lesson_type=lesson.lesson_type,
            sort_order=lesson.sort_order,
            duration_minutes=lesson.duration_minutes,
            status=progress.get(lesson.id).status if lesson.id in progress else None,
            score_percent=progress.get(lesson.id).score_percent if lesson.id in progress else None,
        )
        for lesson in rows
    ]


@app.get("/api/v1/content/lessons/{lesson_id}", response_model=LessonDetailOut)
def lesson_detail(lesson_id: int, db: Session = Depends(get_db)) -> LessonDetailOut:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    return LessonDetailOut(
        id=lesson.id,
        hsk_level_id=lesson.hsk_level_id,
        title=lesson.title,
        title_translations=_lesson_title_translations(lesson),
        description=lesson.description,
        description_translations=_lesson_description_translations(lesson),
        lesson_type=lesson.lesson_type,
        duration_minutes=lesson.duration_minutes,
        content=lesson.content,
    )


@app.get("/api/v1/content/lessons/{lesson_id}/questions", response_model=list[QuestionOut])
def questions(lesson_id: int, db: Session = Depends(get_db)) -> list[QuestionOut]:
    rows = db.scalars(select(Question).where(Question.lesson_id == lesson_id).order_by(Question.sort_order)).all()
    return [
        (lambda metadata: QuestionOut(
            id=row.id,
            question_type=row.question_type,
            prompt=row.prompt,
            prompt_translations=metadata.get("prompt_translations")
            if isinstance(metadata.get("prompt_translations"), dict)
            else None,
            options=row.options,
            options_translations=metadata.get("options_translations")
            if isinstance(metadata.get("options_translations"), dict)
            else None,
            sort_order=row.sort_order,
        ))(_question_translations(row))
        for row in rows
    ]


@app.post("/api/v1/quiz/lessons/{lesson_id}/submit", response_model=QuizSubmitOut)
def submit_quiz(
    lesson_id: int,
    payload: QuizSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizSubmitOut:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise HTTPException(status_code=404, detail="Lesson not found")
    rows = db.scalars(select(Question).where(Question.lesson_id == lesson_id).order_by(Question.sort_order)).all()
    if not rows:
        raise HTTPException(status_code=400, detail="Lesson has no quiz questions")

    score, correct_count, results = score_questions(rows, payload.answers)
    attempt = QuizAttempt(
        user_id=user.id,
        lesson_id=lesson_id,
        score=score,
        total_questions=len(rows),
        correct_count=correct_count,
        answers=payload.answers,
    )
    db.add(attempt)
    progress = db.scalar(
        select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson_id)
    )
    if not progress:
        progress = LessonProgress(user_id=user.id, lesson_id=lesson_id)
        db.add(progress)
    progress.status = "completed" if score >= 60 else "in_progress"
    progress.score_percent = score
    progress.minutes_studied = max(progress.minutes_studied, lesson.duration_minutes)
    user.profile.study_streak_days = max(user.profile.study_streak_days, 1)
    db.flush()
    award_achievements(db, user.id)
    db.commit()
    db.refresh(attempt)
    return QuizSubmitOut(
        attempt_id=attempt.id,
        score=score,
        total_questions=len(rows),
        correct_count=correct_count,
        results=results,
    )


@app.get("/api/v1/progress/dashboard", response_model=ProgressDashboardOut)
def progress_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> ProgressDashboardOut:
    summary_payload = progress_summary_payload(db, user)
    progress_rows = db.scalars(select(LessonProgress).where(LessonProgress.user_id == user.id)).all()
    progress_by_lesson = {progress.lesson_id: progress for progress in progress_rows}

    completed = sum(1 for progress in progress_rows if progress.status == "completed")
    in_progress = sum(1 for progress in progress_rows if progress.status == "in_progress")

    today = datetime.now(UTC).date()

    def updated_today(progress: LessonProgress) -> bool:
        if not progress.updated_at:
            return False
        updated_at = progress.updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        return updated_at.astimezone(UTC).date() == today

    lessons = (
        db.scalars(
            select(Lesson)
            .join(HskLevel, HskLevel.id == Lesson.hsk_level_id)
            .where(HskLevel.level_number <= user.profile.target_hsk_level)
            .order_by(HskLevel.level_number, Lesson.sort_order, Lesson.id)
        )
        .unique()
        .all()
    )
    total_lessons = db.scalar(select(func.count()).select_from(Lesson)) or 0
    current_level = db.scalar(select(HskLevel).where(HskLevel.level_number == user.profile.current_hsk_level))
    current_level_lessons = [
        lesson for lesson in lessons if current_level and lesson.hsk_level_id == current_level.id
    ]

    def percent(done: int, total: int) -> int:
        return round((done / total) * 100) if total else 0

    current_level_completed = sum(
        1
        for lesson in current_level_lessons
        if progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed"
    )
    exam_completed = sum(
        1
        for lesson in lessons
        if progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed"
    )

    skill_totals: dict[str, dict[str, object]] = {}
    for lesson in lessons:
        bucket = skill_totals.setdefault(
            lesson.lesson_type,
            {"lesson_type": lesson.lesson_type, "completed": 0, "total": 0, "scores": []},
        )
        bucket["total"] = int(bucket["total"]) + 1
        progress = progress_by_lesson.get(lesson.id)
        if not progress:
            continue
        if progress.status == "completed":
            bucket["completed"] = int(bucket["completed"]) + 1
        if progress.score_percent is not None:
            scores = bucket["scores"]
            if isinstance(scores, list):
                scores.append(progress.score_percent)

    attempt_rows = (
        db.execute(
            select(QuizAttempt, Lesson)
            .join(Lesson, Lesson.id == QuizAttempt.lesson_id)
            .where(QuizAttempt.user_id == user.id)
            .order_by(QuizAttempt.finished_at.desc())
            .limit(5)
        )
        .unique()
        .all()
    )

    payload = ProgressDashboardOut(
        current_hsk_level=user.profile.current_hsk_level,
        target_hsk_level=user.profile.target_hsk_level,
        daily_goal_minutes=user.profile.daily_goal_minutes,
        minutes_studied_today=sum(progress.minutes_studied for progress in progress_rows if updated_today(progress)),
        study_streak_days=user.profile.study_streak_days,
        lessons_completed=completed,
        lessons_in_progress=in_progress,
        total_lessons=total_lessons,
        current_level_total_lessons=len(current_level_lessons),
        current_level_completed_lessons=current_level_completed,
        current_level_progress_percent=percent(current_level_completed, len(current_level_lessons)),
        exam_readiness_percent=percent(exam_completed, len(lessons)),
        skill_breakdown=[
            {
                "lesson_type": str(bucket["lesson_type"]),
                "completed": int(bucket["completed"]),
                "total": int(bucket["total"]),
                "average_score": round(sum(bucket["scores"]) / len(bucket["scores"]))
                if isinstance(bucket["scores"], list) and bucket["scores"]
                else None,
            }
            for bucket in skill_totals.values()
        ],
        recent_attempts=[
            {
                "attempt_id": attempt.id,
                "lesson_id": attempt.lesson_id,
                "lesson_title": lesson.title,
                "lesson_title_translations": _lesson_title_translations(lesson),
                "score": attempt.score,
                "finished_at": attempt.finished_at,
            }
            for attempt, lesson in attempt_rows
        ],
        overall_progress_percent=summary_payload.overall_progress_percent,
        today_questions=summary_payload.today_questions,
        today_accuracy=summary_payload.today_accuracy,
        longest_streak_days=summary_payload.longest_streak_days,
        last_active_date=summary_payload.last_active_date,
        cards_due=summary_payload.cards_due,
        cards_overdue=summary_payload.cards_overdue,
        cards_reviewed_today=summary_payload.cards_reviewed_today,
        review_retention=summary_payload.review_retention,
        review_streak_days=summary_payload.review_streak_days,
        exams_attempted=summary_payload.exams_attempted,
        exams_completed=summary_payload.exams_completed,
        exam_best_score=summary_payload.exam_best_score,
        exam_latest_score=summary_payload.exam_latest_score,
        exam_average_score=summary_payload.exam_average_score,
        exam_section_performance=summary_payload.exam_section_performance,
        writing_exercises_attempted=summary_payload.writing_exercises_attempted,
        writing_exercises_completed=summary_payload.writing_exercises_completed,
        writing_accuracy=summary_payload.writing_accuracy,
        writing_average_score=summary_payload.writing_average_score,
        guided_writing_count=summary_payload.guided_writing_count,
        translation_accuracy=summary_payload.translation_accuracy,
        word_order_accuracy=summary_payload.word_order_accuracy,
        recommended_practice=summary_payload.recommended_practice,
        weak_areas=summary_payload.weak_skills,
        skill_overview=summary_payload.skill_overview,
    )
    db.commit()
    return payload


@app.get("/api/v1/learning/saved-words", response_model=list[SavedWordOut])
def saved_words(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SavedWordOut]:
    rows = db.scalars(select(SavedWord).where(SavedWord.user_id == user.id).order_by(SavedWord.saved_at.desc())).all()
    return [SavedWordOut(**row.__dict__) for row in rows]


@app.get("/api/v1/learning/mistakes", response_model=list[MistakeOut])
def mistakes(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MistakeOut]:
    attempts = db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == user.id)
        .order_by(QuizAttempt.finished_at.desc())
        .limit(20)
    ).all()
    if not attempts:
        return []

    question_ids: set[int] = set()
    for attempt in attempts:
        for question_id in attempt.answers:
            if question_id.isdigit():
                question_ids.add(int(question_id))

    if not question_ids:
        return []

    question_rows = (
        db.execute(
            select(Question, Lesson)
            .join(Lesson, Lesson.id == Question.lesson_id)
            .where(Question.id.in_(question_ids))
        )
        .unique()
        .all()
    )
    question_map = {question.id: (question, lesson) for question, lesson in question_rows}

    review_items = []
    for attempt in attempts:
        for question_id, user_answer in attempt.answers.items():
            if not question_id.isdigit():
                continue
            question_row = question_map.get(int(question_id))
            if not question_row:
                continue
            question, lesson = question_row
            if user_answer == question.correct_answer:
                continue
            metadata = _question_translations(question)
            review_items.append(
                MistakeOut(
                    attempt_id=attempt.id,
                    lesson_id=question.lesson_id,
                    lesson_title=lesson.title,
                    lesson_title_translations=_lesson_title_translations(lesson),
                    question_id=question.id,
                    prompt=question.prompt,
                    prompt_translations=metadata.get("prompt_translations")
                    if isinstance(metadata.get("prompt_translations"), dict)
                    else None,
                    user_answer=user_answer,
                    correct_answer=question.correct_answer,
                    explanation=question.explanation,
                    explanation_translations=metadata.get("explanation_translations")
                    if isinstance(metadata.get("explanation_translations"), dict)
                    else None,
                    finished_at=attempt.finished_at,
                )
            )
    return review_items[:20]


@app.post("/api/v1/learning/saved-words", response_model=SavedWordOut, status_code=status.HTTP_201_CREATED)
def add_saved_word(
    payload: SavedWordIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SavedWordOut:
    existing = db.scalar(select(SavedWord).where(SavedWord.user_id == user.id, SavedWord.hanzi == payload.hanzi))
    if existing:
        existing.pinyin = payload.pinyin
        existing.meaning = payload.meaning
        existing.hsk_level = payload.hsk_level
        db.commit()
        db.refresh(existing)
        return SavedWordOut(**existing.__dict__)
    row = SavedWord(user_id=user.id, **payload.model_dump())
    db.add(row)
    db.flush()
    enroll_saved_word(db, user, row)
    award_achievements(db, user.id)
    db.commit()
    db.refresh(row)
    return SavedWordOut(**row.__dict__)


@app.delete("/api/v1/learning/saved-words/{word_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_saved_word(
    word_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    row = db.scalar(select(SavedWord).where(SavedWord.id == word_id, SavedWord.user_id == user.id))
    if not row:
        raise HTTPException(status_code=404, detail="Saved word not found")
    db.delete(row)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/api/v1/learning/achievements", response_model=list[AchievementOut])
def achievements(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[AchievementOut]:
    award_achievements(db, user.id)
    db.commit()
    earned = {
        ua.achievement_id: ua.earned_at
        for ua in db.scalars(select(UserAchievement).where(UserAchievement.user_id == user.id)).all()
    }
    rows = db.scalars(select(Achievement).order_by(Achievement.id)).all()
    return [
        AchievementOut(
            id=row.id,
            code=row.code,
            title=row.title,
            description=row.description,
            icon=row.icon,
            earned=row.id in earned,
            earned_at=earned.get(row.id),
        )
        for row in rows
    ]


@app.get("/api/v1/learning/mock-tests", response_model=list[MockTestOut])
def mock_tests(db: Session = Depends(get_db)) -> list[MockTestOut]:
    rows = db.scalars(select(MockTest).order_by(MockTest.hsk_level, MockTest.id)).all()
    return [
        MockTestOut(
            id=row.id,
            title=row.title,
            title_translations=_mock_test_title_translations(row.title),
            hsk_level=row.hsk_level,
            duration_minutes=row.duration_minutes,
            question_count=row.question_count,
        )
        for row in rows
    ]


@app.get("/api/v1/learning/mock-tests/{mock_test_id}/questions", response_model=list[MockTestQuestionOut])
def mock_test_questions(
    mock_test_id: int,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[MockTestQuestionOut]:
    mock_test = db.get(MockTest, mock_test_id)
    if not mock_test:
        raise HTTPException(status_code=404, detail="Mock test not found")
    rows = get_mock_test_questions(db, mock_test)
    return [
        (lambda metadata: MockTestQuestionOut(
            id=row.id,
            lesson_id=row.lesson_id,
            lesson_title=row.lesson.title,
            lesson_title_translations=_lesson_title_translations(row.lesson),
            question_type=row.question_type,
            prompt=row.prompt,
            prompt_translations=metadata.get("prompt_translations")
            if isinstance(metadata.get("prompt_translations"), dict)
            else None,
            options=row.options,
            options_translations=metadata.get("options_translations")
            if isinstance(metadata.get("options_translations"), dict)
            else None,
            sort_order=row.sort_order,
        ))(_question_translations(row))
        for row in rows
    ]


@app.post("/api/v1/learning/mock-tests/{mock_test_id}/submit", response_model=QuizSubmitOut)
def submit_mock_test(
    mock_test_id: int,
    payload: QuizSubmitIn,
    _user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizSubmitOut:
    mock_test = db.get(MockTest, mock_test_id)
    if not mock_test:
        raise HTTPException(status_code=404, detail="Mock test not found")
    rows = get_mock_test_questions(db, mock_test)
    if not rows:
        raise HTTPException(status_code=400, detail="Mock test has no questions")

    score, correct_count, results = score_questions(rows, payload.answers)
    return QuizSubmitOut(
        attempt_id=mock_test.id,
        score=score,
        total_questions=len(rows),
        correct_count=correct_count,
        results=results,
    )
