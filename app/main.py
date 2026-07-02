from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Response, status
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_user, hash_password, verify_password
from app.config import settings
from app.database import Base, SessionLocal, engine, get_db
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
from app.schemas import (
    AchievementOut,
    AuthIn,
    HskLevelOut,
    LessonDetailOut,
    LessonListOut,
    MockTestOut,
    MockTestQuestionOut,
    MistakeOut,
    ProgressDashboardOut,
    ProfileOut,
    ProfileUpdate,
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
from app.seed import seed_data


app = FastAPI(title="HSK Mobile API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE profiles ADD COLUMN IF NOT EXISTS learning_goal VARCHAR(80)"))
        conn.execute(text("ALTER TABLE quiz_attempts ADD COLUMN IF NOT EXISTS results JSONB"))
    with SessionLocal() as db:
        seed_data(db)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def profile_to_out(profile: Profile) -> ProfileOut:
    return ProfileOut(
        target_hsk_level=profile.target_hsk_level,
        current_hsk_level=profile.current_hsk_level,
        learning_goal=profile.learning_goal,
        daily_goal_minutes=profile.daily_goal_minutes,
        study_streak_days=profile.study_streak_days,
        onboarding_completed=profile.onboarding_completed,
    )


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
    return [HskLevelOut(**row.__dict__) for row in rows]


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
            description=lesson.description,
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
        description=lesson.description,
        lesson_type=lesson.lesson_type,
        duration_minutes=lesson.duration_minutes,
        content=lesson.content,
    )


@app.get("/api/v1/content/lessons/{lesson_id}/questions", response_model=list[QuestionOut])
def questions(lesson_id: int, db: Session = Depends(get_db)) -> list[QuestionOut]:
    rows = db.scalars(select(Question).where(Question.lesson_id == lesson_id).order_by(Question.sort_order)).all()
    return [
        QuestionOut(
            id=row.id,
            question_type=row.question_type,
            prompt=row.prompt,
            options=row.options,
            sort_order=row.sort_order,
        )
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

    results = []
    correct_count = 0
    for question in rows:
        user_answer = payload.answers.get(str(question.id), "")
        correct = user_answer == question.correct_answer
        correct_count += int(correct)
        results.append(
            QuizResultItem(
                question_id=question.id,
                prompt=question.prompt,
                correct=correct,
                user_answer=user_answer,
                correct_answer=question.correct_answer,
                explanation=question.explanation,
            )
        )
    score = round((correct_count / len(rows)) * 100)
    attempt = QuizAttempt(
        user_id=user.id,
        lesson_id=lesson_id,
        score=score,
        total_questions=len(rows),
        correct_count=correct_count,
        answers=payload.answers,
        results=[item.model_dump() for item in results],
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
def progress_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    completed = db.scalar(
        select(func.count()).select_from(LessonProgress).where(
            LessonProgress.user_id == user.id, LessonProgress.status == "completed"
        )
    )
    in_progress = db.scalar(
        select(func.count()).select_from(LessonProgress).where(
            LessonProgress.user_id == user.id, LessonProgress.status == "in_progress"
        )
    )
    minutes = db.scalar(
        select(func.coalesce(func.sum(LessonProgress.minutes_studied), 0)).where(LessonProgress.user_id == user.id)
    )
    total_lessons = db.scalar(select(func.count()).select_from(Lesson))
    current_level = db.scalar(select(HskLevel).where(HskLevel.level_number == user.profile.current_hsk_level))
    current_level_total = 0
    current_level_completed = 0
    if current_level:
        current_level_total = db.scalar(
            select(func.count()).select_from(Lesson).where(Lesson.hsk_level_id == current_level.id)
        ) or 0
        current_level_completed = db.scalar(
            select(func.count())
            .select_from(LessonProgress)
            .join(Lesson, Lesson.id == LessonProgress.lesson_id)
            .where(
                LessonProgress.user_id == user.id,
                LessonProgress.status == "completed",
                Lesson.hsk_level_id == current_level.id,
            )
        ) or 0
    attempts = db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == user.id)
        .order_by(QuizAttempt.finished_at.desc())
        .limit(5)
    ).all()
    lesson_titles = {
        lesson.id: lesson.title
        for lesson in db.scalars(select(Lesson).where(Lesson.id.in_([attempt.lesson_id for attempt in attempts] or [0])))
    }
    current_level_percent = round((current_level_completed / current_level_total) * 100) if current_level_total else 0
    readiness = round(((completed or 0) / (total_lessons or 1)) * 100)
    skills = []
    lesson_types = db.scalars(select(Lesson.lesson_type).distinct().order_by(Lesson.lesson_type)).all()
    for lesson_type in lesson_types:
        total_for_type = db.scalar(select(func.count()).select_from(Lesson).where(Lesson.lesson_type == lesson_type)) or 0
        completed_for_type = db.scalar(
            select(func.count())
            .select_from(LessonProgress)
            .join(Lesson, Lesson.id == LessonProgress.lesson_id)
            .where(
                LessonProgress.user_id == user.id,
                Lesson.lesson_type == lesson_type,
                LessonProgress.status == "completed",
            )
        ) or 0
        average_score = db.scalar(
            select(func.avg(LessonProgress.score_percent))
            .select_from(LessonProgress)
            .join(Lesson, Lesson.id == LessonProgress.lesson_id)
            .where(
                LessonProgress.user_id == user.id,
                Lesson.lesson_type == lesson_type,
                LessonProgress.score_percent.is_not(None),
            )
        )
        skills.append(
            {
                "lesson_type": lesson_type,
                "completed": completed_for_type,
                "total": total_for_type,
                "average_score": round(float(average_score)) if average_score is not None else None,
            }
        )
    return {
        "current_hsk_level": user.profile.current_hsk_level,
        "target_hsk_level": user.profile.target_hsk_level,
        "daily_goal_minutes": user.profile.daily_goal_minutes,
        "minutes_studied_today": int(minutes or 0),
        "study_streak_days": user.profile.study_streak_days,
        "lessons_completed": completed or 0,
        "lessons_in_progress": in_progress or 0,
        "total_lessons": total_lessons or 0,
        "current_level_total_lessons": current_level_total,
        "current_level_completed_lessons": current_level_completed,
        "current_level_progress_percent": current_level_percent,
        "exam_readiness_percent": readiness,
        "skill_breakdown": skills,
        "recent_attempts": [
            {
                "attempt_id": attempt.id,
                "lesson_id": attempt.lesson_id,
                "lesson_title": lesson_titles.get(attempt.lesson_id),
                "score": attempt.score,
                "finished_at": attempt.finished_at,
            }
            for attempt in attempts
        ],
    }


@app.get("/api/v1/learning/saved-words", response_model=list[SavedWordOut])
def saved_words(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[SavedWordOut]:
    rows = db.scalars(select(SavedWord).where(SavedWord.user_id == user.id).order_by(SavedWord.saved_at.desc())).all()
    return [SavedWordOut(**row.__dict__) for row in rows]


@app.get("/api/v1/learning/mistakes", response_model=list[MistakeOut])
def mistakes(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MistakeOut]:
    attempts = db.scalars(
        select(QuizAttempt)
        .where(QuizAttempt.user_id == user.id, QuizAttempt.results.is_not(None))
        .order_by(QuizAttempt.finished_at.desc())
        .limit(20)
    ).all()
    lesson_titles = {
        lesson.id: lesson.title
        for lesson in db.scalars(select(Lesson).where(Lesson.id.in_([attempt.lesson_id for attempt in attempts] or [0])))
    }
    rows = []
    for attempt in attempts:
        for result in attempt.results or []:
            if result.get("correct"):
                continue
            rows.append(
                MistakeOut(
                    attempt_id=attempt.id,
                    lesson_id=attempt.lesson_id,
                    lesson_title=lesson_titles.get(attempt.lesson_id),
                    question_id=result["question_id"],
                    prompt=result.get("prompt"),
                    user_answer=result.get("user_answer", ""),
                    correct_answer=result.get("correct_answer", ""),
                    explanation=result.get("explanation"),
                    finished_at=attempt.finished_at,
                )
            )
    return rows[:20]


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
    return [MockTestOut(**row.__dict__) for row in rows]


@app.get("/api/v1/learning/mock-tests/{mock_test_id}/questions", response_model=list[MockTestQuestionOut])
def mock_test_questions(mock_test_id: int, db: Session = Depends(get_db)) -> list[MockTestQuestionOut]:
    mock_test = db.get(MockTest, mock_test_id)
    if not mock_test:
        raise HTTPException(status_code=404, detail="Mock test not found")
    levels = db.scalars(select(HskLevel).where(HskLevel.level_number <= mock_test.hsk_level)).all()
    lesson_ids = [lesson.id for lesson in db.scalars(select(Lesson).where(Lesson.hsk_level_id.in_([l.id for l in levels] or [0])))]
    rows = db.scalars(
        select(Question).where(Question.lesson_id.in_(lesson_ids or [0])).order_by(Question.id).limit(mock_test.question_count)
    ).all()
    lesson_titles = {
        lesson.id: lesson.title
        for lesson in db.scalars(select(Lesson).where(Lesson.id.in_([question.lesson_id for question in rows] or [0])))
    }
    return [
        MockTestQuestionOut(
            id=row.id,
            lesson_id=row.lesson_id,
            lesson_title=lesson_titles.get(row.lesson_id, "Lesson"),
            question_type=row.question_type,
            prompt=row.prompt,
            options=row.options,
            sort_order=row.sort_order,
        )
        for row in rows
    ]


@app.post("/api/v1/learning/mock-tests/{mock_test_id}/submit", response_model=QuizSubmitOut)
def submit_mock_test(
    mock_test_id: int,
    payload: QuizSubmitIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> QuizSubmitOut:
    questions = mock_test_questions(mock_test_id, db)
    if not questions:
        raise HTTPException(status_code=400, detail="Mock test has no questions")
    rows = db.scalars(select(Question).where(Question.id.in_([question.id for question in questions]))).all()
    by_id = {row.id: row for row in rows}
    results = []
    correct_count = 0
    for question in questions:
        row = by_id[question.id]
        user_answer = payload.answers.get(str(question.id), "")
        correct = user_answer == row.correct_answer
        correct_count += int(correct)
        results.append(
            QuizResultItem(
                question_id=row.id,
                prompt=row.prompt,
                correct=correct,
                user_answer=user_answer,
                correct_answer=row.correct_answer,
                explanation=row.explanation,
            )
        )
    score = round((correct_count / len(questions)) * 100)
    attempt = QuizAttempt(
        user_id=user.id,
        lesson_id=mock_test_id,
        score=score,
        total_questions=len(questions),
        correct_count=correct_count,
        answers=payload.answers,
        results=[item.model_dump() for item in results],
    )
    db.add(attempt)
    user.profile.study_streak_days = max(user.profile.study_streak_days, 1)
    db.flush()
    award_achievements(db, user.id)
    db.commit()
    db.refresh(attempt)
    return QuizSubmitOut(
        attempt_id=attempt.id,
        score=score,
        total_questions=len(questions),
        correct_count=correct_count,
        results=results,
    )
