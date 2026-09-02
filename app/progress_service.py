from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import (
    AnswerAttempt,
    ExamAttempt,
    HskLevel,
    Lesson,
    LessonProgress,
    PracticeSession,
    Question,
    SpeakingAttempt,
    User,
)
from app.review_service import review_recommendation, review_summary
from app.schemas import (
    AccuracyMetricOut,
    ContinueLearningOut,
    CourseProgressOut,
    DailyActivityOut,
    HskProgressOut,
    LessonProgressAnalyticsOut,
    ProgressMetricOut,
    ProgressSummaryOut,
    RecommendationOut,
    SkillPerformanceOut,
    WeakAreaOut,
)
from app.writing_service import WRITING_TYPES

OBJECTIVE_SKILLS = {"VOCABULARY", "GRAMMAR", "READING", "LISTENING", "WRITING"}
COMPLETION_RULE = "Lesson is completed when existing LessonProgress status is completed, set by completed practice with score >= 60."


@dataclass(frozen=True)
class SkillRawMetric:
    attempts: int = 0
    correct: int = 0
    score_sum: float = 0
    score_count: int = 0
    study_seconds: int = 0
    previous_attempts: int = 0
    previous_correct: int = 0
    current_attempts: int = 0
    current_correct: int = 0


def _percent(done: float, total: float) -> float | None:
    if not total:
        return None
    return round((float(done) / float(total)) * 100, 2)


def _content(lesson: Lesson) -> dict[str, Any]:
    return lesson.content if isinstance(lesson.content, dict) else {}


def _title_translations(lesson: Lesson | HskLevel) -> dict[str, str] | None:
    content = _content(lesson) if isinstance(lesson, Lesson) else {}
    value = content.get("title_translations")
    return value if isinstance(value, dict) else None


def _lesson_hsk_level(lesson: Lesson, levels_by_id: dict[int, HskLevel]) -> int:
    level = levels_by_id.get(lesson.hsk_level_id)
    return level.level_number if level else 0


def _skill_for_question(question: Question, lesson: Lesson | None = None) -> str:
    qtype = question.question_type.upper()
    if qtype in WRITING_TYPES:
        return "WRITING"
    if qtype in {"LISTENING", "DICTATION"}:
        return "LISTENING"
    if qtype in {"SPEAKING", "PRONUNCIATION"}:
        return "SPEAKING"
    if qtype in {"GRAMMAR"}:
        return "GRAMMAR"
    if qtype in {"READING"}:
        return "READING"
    reference = (question.reference_type or "").upper()
    if reference in {"VOCABULARY", "GRAMMAR", "READING", "LISTENING", "WRITING"}:
        return reference
    if lesson and lesson.lesson_type:
        mapped = lesson.lesson_type.upper()
        if mapped in {"VOCABULARY", "GRAMMAR", "READING", "LISTENING", "WRITING"}:
            return mapped
    return "VOCABULARY"


def _skill_from_values(question_type: str | None, reference_type: str | None, lesson_type: str | None) -> str:
    qtype = (question_type or "").upper()
    if qtype in WRITING_TYPES:
        return "WRITING"
    if qtype in {"LISTENING", "DICTATION"}:
        return "LISTENING"
    if qtype in {"SPEAKING", "PRONUNCIATION"}:
        return "SPEAKING"
    if qtype == "GRAMMAR":
        return "GRAMMAR"
    if qtype == "READING":
        return "READING"
    reference = (reference_type or "").upper()
    if reference in {"VOCABULARY", "GRAMMAR", "READING", "LISTENING", "WRITING"}:
        return reference
    mapped = (lesson_type or "").upper()
    if mapped in {"VOCABULARY", "GRAMMAR", "READING", "LISTENING", "WRITING"}:
        return mapped
    return "VOCABULARY"


def _lesson_content_totals(lessons: list[Lesson]) -> tuple[set[str], set[str]]:
    vocabulary: set[str] = set()
    grammar: set[str] = set()
    for lesson in lessons:
        content = _content(lesson)
        for item in content.get("vocabulary", []) if isinstance(content.get("vocabulary"), list) else []:
            if isinstance(item, dict):
                key = str(item.get("hanzi") or item.get("pinyin") or item.get("meaning") or "").strip()
                if key:
                    vocabulary.add(key)
        for item in content.get("grammar_points", []) if isinstance(content.get("grammar_points"), list) else []:
            if isinstance(item, dict):
                key = str(item.get("title") or item.get("structure") or "").strip()
                if key:
                    grammar.add(key)
    return vocabulary, grammar


def _learned_content(lessons: list[Lesson], progress_by_lesson: dict[int, LessonProgress]) -> tuple[set[str], set[str]]:
    completed_lessons = [
        lesson for lesson in lessons if progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed"
    ]
    return _lesson_content_totals(completed_lessons)


def _progress_by_lesson(db: Session, user_id: int) -> dict[int, LessonProgress]:
    rows = db.scalars(select(LessonProgress).where(LessonProgress.user_id == user_id)).all()
    return {row.lesson_id: row for row in rows}


def _levels(db: Session) -> list[HskLevel]:
    return list(db.scalars(select(HskLevel).order_by(HskLevel.level_number)).all())


def _lessons_for_level(db: Session, level_id: int) -> list[Lesson]:
    return list(db.scalars(select(Lesson).where(Lesson.hsk_level_id == level_id).order_by(Lesson.sort_order, Lesson.id)).all())


def _lesson_attempt_stats(db: Session, user_id: int, lesson_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    stmt = (
        select(
            PracticeSession.lesson_id,
            func.count(AnswerAttempt.id),
            func.sum(case((AnswerAttempt.is_correct.is_(True), 1), else_=0)),
            func.sum(AnswerAttempt.time_spent_seconds),
            func.max(AnswerAttempt.attempted_at),
        )
        .join(PracticeSession, PracticeSession.id == AnswerAttempt.practice_session_id)
        .where(AnswerAttempt.user_id == user_id, PracticeSession.status != "ABANDONED")
        .group_by(PracticeSession.lesson_id)
    )
    if lesson_ids is not None:
        stmt = stmt.where(PracticeSession.lesson_id.in_(lesson_ids or [0]))
    rows = db.execute(stmt).all()
    return {
        int(lesson_id): {
            "attempts": int(attempts or 0),
            "correct": int(correct or 0),
            "attempt_seconds": int(seconds or 0),
            "last_practiced": last_practiced,
        }
        for lesson_id, attempts, correct, seconds, last_practiced in rows
        if lesson_id is not None
    }


def _lesson_speaking_stats(db: Session, user_id: int, lesson_ids: list[int] | None = None) -> dict[int, dict[str, Any]]:
    stmt = (
        select(
            PracticeSession.lesson_id,
            func.count(SpeakingAttempt.id),
            func.avg(SpeakingAttempt.pronunciation_score),
            func.max(SpeakingAttempt.completed_at),
        )
        .join(PracticeSession, PracticeSession.id == SpeakingAttempt.practice_session_id)
        .where(
            SpeakingAttempt.user_id == user_id,
            SpeakingAttempt.processing_status == "COMPLETED",
            SpeakingAttempt.pronunciation_score.is_not(None),
        )
        .group_by(PracticeSession.lesson_id)
    )
    if lesson_ids is not None:
        stmt = stmt.where(PracticeSession.lesson_id.in_(lesson_ids or [0]))
    rows = db.execute(stmt).all()
    return {
        int(lesson_id): {
            "attempts": int(attempts or 0),
            "average_score": round(float(avg_score), 2) if avg_score is not None else None,
            "last_practiced": last_practiced,
        }
        for lesson_id, attempts, avg_score, last_practiced in rows
        if lesson_id is not None
    }


def _study_minutes_by_lesson(db: Session, user_id: int, lesson_ids: list[int] | None = None) -> dict[int, int]:
    stmt = (
        select(PracticeSession.lesson_id, func.sum(PracticeSession.time_spent_seconds))
        .where(PracticeSession.user_id == user_id, PracticeSession.status != "ABANDONED")
        .group_by(PracticeSession.lesson_id)
    )
    if lesson_ids is not None:
        stmt = stmt.where(PracticeSession.lesson_id.in_(lesson_ids or [0]))
    rows = db.execute(stmt).all()
    return {int(lesson_id): round(int(seconds or 0) / 60) for lesson_id, seconds in rows if lesson_id is not None}


def _accuracy_metric(attempts: int, correct: int) -> AccuracyMetricOut:
    return AccuracyMetricOut(attempts=attempts, correct=correct, accuracy=_percent(correct, attempts))


def _question_accuracy_stats(db: Session, user_id: int, skill: str, lesson_ids: list[int] | None = None) -> tuple[int, int]:
    stmt = (
        select(
            Question.question_type,
            Question.reference_type,
            Lesson.lesson_type,
            func.count(AnswerAttempt.id),
            func.sum(case((AnswerAttempt.is_correct.is_(True), 1), else_=0)),
        )
        .join(Question, Question.id == AnswerAttempt.question_id)
        .join(Lesson, Lesson.id == Question.lesson_id)
        .join(PracticeSession, PracticeSession.id == AnswerAttempt.practice_session_id)
        .where(AnswerAttempt.user_id == user_id, PracticeSession.status != "ABANDONED")
        .group_by(Question.question_type, Question.reference_type, Lesson.lesson_type)
    )
    if lesson_ids is not None:
        stmt = stmt.where(PracticeSession.lesson_id.in_(lesson_ids or [0]))
    attempts = 0
    correct = 0
    for question_type, reference_type, lesson_type, count, correct_count in db.execute(stmt).all():
        if _skill_from_values(question_type, reference_type, lesson_type) == skill:
            attempts += int(count or 0)
            correct += int(correct_count or 0)
    return attempts, correct


def _skill_metrics(db: Session, user_id: int) -> list[SkillPerformanceOut]:
    now = datetime.now(UTC)
    current_start = now - timedelta(days=7)
    previous_start = now - timedelta(days=14)
    raw: dict[str, dict[str, float | int]] = defaultdict(
        lambda: {
            "attempts": 0,
            "correct": 0,
            "study_seconds": 0,
            "previous_attempts": 0,
            "previous_correct": 0,
            "current_attempts": 0,
            "current_correct": 0,
        }
    )

    def merge_attempt_rows(start: datetime | None = None, end: datetime | None = None, prefix: str | None = None) -> None:
        stmt = (
            select(
                Question.question_type,
                Question.reference_type,
                Lesson.lesson_type,
                func.count(AnswerAttempt.id),
                func.sum(case((AnswerAttempt.is_correct.is_(True), 1), else_=0)),
                func.sum(AnswerAttempt.time_spent_seconds),
            )
            .join(Question, Question.id == AnswerAttempt.question_id)
            .join(Lesson, Lesson.id == Question.lesson_id)
            .join(PracticeSession, PracticeSession.id == AnswerAttempt.practice_session_id)
            .where(AnswerAttempt.user_id == user_id, PracticeSession.status != "ABANDONED")
            .group_by(Question.question_type, Question.reference_type, Lesson.lesson_type)
        )
        if start is not None:
            stmt = stmt.where(AnswerAttempt.attempted_at >= start)
        if end is not None:
            stmt = stmt.where(AnswerAttempt.attempted_at < end)
        for question_type, reference_type, lesson_type, attempts, correct, seconds in db.execute(stmt).all():
            skill = _skill_from_values(question_type, reference_type, lesson_type)
            if skill == "SPEAKING":
                continue
            bucket = raw[skill]
            if prefix:
                bucket[f"{prefix}_attempts"] += int(attempts or 0)
                bucket[f"{prefix}_correct"] += int(correct or 0)
            else:
                bucket["attempts"] += int(attempts or 0)
                bucket["correct"] += int(correct or 0)
                bucket["study_seconds"] += int(seconds or 0)

    merge_attempt_rows()
    merge_attempt_rows(current_start, None, "current")
    merge_attempt_rows(previous_start, current_start, "previous")

    speaking = db.execute(
        select(
            func.count(SpeakingAttempt.id),
            func.avg(SpeakingAttempt.pronunciation_score),
        ).where(
            SpeakingAttempt.user_id == user_id,
            SpeakingAttempt.processing_status == "COMPLETED",
            SpeakingAttempt.pronunciation_score.is_not(None),
        )
    ).one()
    if speaking[0]:
        raw["SPEAKING"]["attempts"] = int(speaking[0] or 0)
        raw["SPEAKING"]["correct"] = 0
        raw["SPEAKING"]["average_score"] = round(float(speaking[1]), 2) if speaking[1] is not None else 0

    metrics: list[SkillPerformanceOut] = []
    for skill, bucket in sorted(raw.items()):
        attempts = int(bucket.get("attempts", 0))
        correct = int(bucket.get("correct", 0))
        current_attempts = int(bucket.get("current_attempts", 0))
        previous_attempts = int(bucket.get("previous_attempts", 0))
        trend = None
        trend_delta = None
        if current_attempts >= settings.progress_trend_min_attempts and previous_attempts >= settings.progress_trend_min_attempts:
            current_accuracy = _percent(int(bucket["current_correct"]), current_attempts) or 0
            previous_accuracy = _percent(int(bucket["previous_correct"]), previous_attempts) or 0
            trend_delta = round(current_accuracy - previous_accuracy, 2)
            trend = "improving" if trend_delta > 3 else "declining" if trend_delta < -3 else "stable"
        metrics.append(
            SkillPerformanceOut(
                skill=skill,
                attempts=attempts,
                correct=correct,
                accuracy=None if skill == "SPEAKING" else _percent(correct, attempts),
                average_score=float(bucket["average_score"]) if "average_score" in bucket else None,
                study_minutes=round(int(bucket.get("study_seconds", 0)) / 60),
                practiced=attempts > 0,
                trend=trend,
                trend_delta=trend_delta,
            )
        )
    return metrics


def _weak_areas(skill_metrics: list[SkillPerformanceOut]) -> list[WeakAreaOut]:
    weak: list[WeakAreaOut] = []
    for metric in skill_metrics:
        if metric.skill == "SPEAKING":
            score = metric.average_score
            threshold = settings.progress_weak_speaking_threshold
        else:
            score = metric.accuracy
            threshold = settings.progress_weak_accuracy_threshold
        if score is None or metric.attempts < settings.progress_min_attempts_for_weak_area or score >= threshold:
            continue
        weak.append(
            WeakAreaOut(
                type="SKILL",
                label=metric.skill.title(),
                skill=metric.skill,
                metric=score,
                attempts=metric.attempts,
                reason=f"{metric.skill.title()} is below {threshold:.0f}% after {metric.attempts} attempts.",
            )
        )
    return weak


def _continue_lesson(db: Session, user: User, levels: list[HskLevel], progress_by_lesson: dict[int, LessonProgress]) -> ContinueLearningOut | None:
    eligible_level_ids = [level.id for level in levels if level.level_number <= user.profile.target_hsk_level]
    lessons = db.scalars(
        select(Lesson)
        .where(Lesson.hsk_level_id.in_(eligible_level_ids or [0]))
        .order_by(Lesson.hsk_level_id, Lesson.sort_order, Lesson.id)
    ).all()
    row: Lesson | None = None
    for lesson in lessons:
        progress = progress_by_lesson.get(lesson.id)
        if not progress or progress.status != "completed":
            row = lesson
            break
    if not row:
        return None
    level_by_id = {level.id: level for level in levels}
    return ContinueLearningOut(
        lesson_id=row.id,
        lesson_title=row.title,
        lesson_title_translations=_title_translations(row),
        hsk_level=_lesson_hsk_level(row, level_by_id),
        lesson_type=row.lesson_type,
    )


def _recommendations(
    weak: list[WeakAreaOut],
    continue_learning: ContinueLearningOut | None,
    due_review: RecommendationOut | None = None,
) -> list[RecommendationOut]:
    recommendations: list[RecommendationOut] = []
    if due_review:
        recommendations.append(due_review)
    if weak:
        area = weak[0]
        recommendations.append(
            RecommendationOut(
                type=f"{area.skill}_PRACTICE" if area.skill else "PRACTICE",
                target_id=area.target_id,
                target_label=area.label,
                reason=area.reason,
                activity_type="PRACTICE",
            )
        )
    if continue_learning:
        recommendations.append(
            RecommendationOut(
                type="CONTINUE_LESSON",
                target_id=continue_learning.lesson_id,
                target_label=continue_learning.lesson_title,
                reason="Continue the next incomplete lesson.",
                activity_type="LESSON",
            )
        )
    return recommendations[:3]


def daily_activity(db: Session, user_id: int, start_date: date, end_date: date) -> list[DailyActivityOut]:
    days = {
        start_date + timedelta(days=offset): DailyActivityOut(date=(start_date + timedelta(days=offset)).isoformat())
        for offset in range((end_date - start_date).days + 1)
    }
    sessions = db.execute(
        select(
            func.date(PracticeSession.started_at),
            func.sum(PracticeSession.time_spent_seconds),
            func.count(func.distinct(PracticeSession.lesson_id)),
        ).where(
            PracticeSession.user_id == user_id,
            PracticeSession.status != "ABANDONED",
            PracticeSession.started_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
            PracticeSession.started_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
        ).group_by(func.date(PracticeSession.started_at))
    ).all()
    for day_value, seconds, lessons in sessions:
        day = date.fromisoformat(str(day_value))
        if day in days:
            days[day].study_minutes = round(int(seconds or 0) / 60)
            days[day].lessons_studied = int(lessons or 0)

    attempts = db.execute(
        select(
            func.date(AnswerAttempt.attempted_at),
            func.count(AnswerAttempt.id),
            func.sum(case((AnswerAttempt.is_correct.is_(True), 1), else_=0)),
            Question.question_type,
            Question.reference_type,
        )
        .join(Question, Question.id == AnswerAttempt.question_id)
        .where(
            AnswerAttempt.user_id == user_id,
            AnswerAttempt.attempted_at >= datetime.combine(start_date, datetime.min.time(), tzinfo=UTC),
            AnswerAttempt.attempted_at < datetime.combine(end_date + timedelta(days=1), datetime.min.time(), tzinfo=UTC),
        )
        .group_by(func.date(AnswerAttempt.attempted_at), Question.question_type, Question.reference_type)
    ).all()
    for day_value, count, correct, qtype, reference_type in attempts:
        day = date.fromisoformat(str(day_value))
        if day not in days:
            continue
        item = days[day]
        item.practice_attempts += int(count or 0)
        item.questions += int(count or 0)
        item.correct += int(correct or 0)
        skill = (reference_type or qtype or "").upper()
        if qtype in {"SPEAKING", "PRONUNCIATION"}:
            item.speaking_practiced += int(count or 0)
        elif qtype in WRITING_TYPES or skill == "WRITING":
            item.writing_practiced += int(count or 0)
        elif qtype == "LISTENING":
            item.listening_practiced += int(count or 0)
        elif skill == "VOCABULARY":
            item.vocabulary_practiced += int(count or 0)
        elif skill == "GRAMMAR":
            item.grammar_practiced += int(count or 0)
    for item in days.values():
        item.accuracy = _percent(item.correct, item.questions)
    return list(days.values())


def streak_from_activity(activity: list[DailyActivityOut], today: date | None = None) -> tuple[int, int, str | None]:
    threshold = settings.progress_min_daily_study_minutes
    active_days = {date.fromisoformat(item.date) for item in activity if item.study_minutes >= threshold or item.questions > 0}
    if not active_days:
        return 0, 0, None
    longest = 0
    run = 0
    previous = None
    for day in sorted(active_days):
        run = run + 1 if previous and day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = day
    current = 0
    cursor = today or datetime.now(UTC).date()
    if cursor not in active_days:
        cursor -= timedelta(days=1)
    while cursor in active_days:
        current += 1
        cursor -= timedelta(days=1)
    return current, longest, max(active_days).isoformat()


def summary(db: Session, user: User) -> ProgressSummaryOut:
    levels = _levels(db)
    progress_by_lesson = _progress_by_lesson(db, user.id)
    current_level = next((level for level in levels if level.level_number == user.profile.current_hsk_level), None)
    current_lessons = _lessons_for_level(db, current_level.id) if current_level else []
    completed_current = sum(
        1
        for lesson in current_lessons
        if progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed"
    )
    skill_metrics = _skill_metrics(db, user.id)
    weak = _weak_areas(skill_metrics)
    continue_learning = _continue_lesson(db, user, levels, progress_by_lesson)
    today = datetime.now(UTC).date()
    activity = daily_activity(db, user.id, today - timedelta(days=60), today)
    current_streak, longest_streak, last_active = streak_from_activity(activity, today)
    review = review_summary(db, user)
    exam = _exam_metrics(db, user.id)
    writing = _writing_metrics(db, user.id)
    user.profile.study_streak_days = current_streak
    user.profile.longest_streak_days = max(user.profile.longest_streak_days or 0, longest_streak)
    user.profile.last_active_date = date.fromisoformat(last_active) if last_active else None
    today_item = activity[-1] if activity else DailyActivityOut(date=today.isoformat())
    return ProgressSummaryOut(
        current_hsk_level=user.profile.current_hsk_level,
        target_hsk_level=user.profile.target_hsk_level,
        overall_progress_percent=_percent(completed_current, len(current_lessons)) or 0,
        today_study_minutes=today_item.study_minutes,
        today_questions=today_item.questions,
        today_accuracy=today_item.accuracy,
        current_streak_days=current_streak,
        longest_streak_days=max(user.profile.longest_streak_days or 0, longest_streak),
        last_active_date=last_active,
        cards_due=review.due_count,
        cards_overdue=review.overdue_count,
        cards_reviewed_today=review.reviewed_today,
        review_retention=review.retention,
        review_streak_days=review.review_streak_days,
        exams_attempted=exam["attempted"],
        exams_completed=exam["completed"],
        exam_best_score=exam["best"],
        exam_latest_score=exam["latest"],
        exam_average_score=exam["average"],
        exam_section_performance=exam["sections"],
        writing_exercises_attempted=writing["attempted"],
        writing_exercises_completed=writing["completed"],
        writing_accuracy=writing["accuracy"],
        writing_average_score=writing["average_score"],
        guided_writing_count=writing["guided_count"],
        translation_accuracy=writing["translation_accuracy"],
        word_order_accuracy=writing["word_order_accuracy"],
        weak_skills=weak,
        recommended_practice=_recommendations(weak, continue_learning, review_recommendation(db, user)),
        continue_learning=continue_learning,
        skill_overview=skill_metrics,
    )


def _exam_metrics(db: Session, user_id: int) -> dict[str, Any]:
    rows = list(
        db.scalars(
            select(ExamAttempt)
            .where(ExamAttempt.user_id == user_id)
            .order_by(ExamAttempt.started_at.desc(), ExamAttempt.id.desc())
        ).all()
    )
    completed = [row for row in rows if row.status in {"SUBMITTED", "EXPIRED"} and row.percentage is not None]
    section_totals: dict[str, dict[str, float | int]] = {}
    for attempt in completed:
        for section in attempt.section_results or []:
            key = str(section.get("section", "UNKNOWN"))
            bucket = section_totals.setdefault(key, {"count": 0, "percentage": 0.0})
            bucket["count"] = int(bucket["count"]) + 1
            bucket["percentage"] = float(bucket["percentage"]) + float(section.get("percentage", 0))
    return {
        "attempted": len(rows),
        "completed": len(completed),
        "best": max((attempt.percentage or 0 for attempt in completed), default=None),
        "latest": completed[0].percentage if completed else None,
        "average": round(sum(attempt.percentage or 0 for attempt in completed) / len(completed), 2) if completed else None,
        "sections": [
            {"section": section, "average_percentage": round(float(values["percentage"]) / int(values["count"]), 2)}
            for section, values in sorted(section_totals.items())
            if int(values["count"])
        ],
    }


def _writing_metrics(db: Session, user_id: int) -> dict[str, Any]:
    rows = db.execute(
        select(
            Question.question_type,
            Question.reference_type,
            Lesson.lesson_type,
            func.count(AnswerAttempt.id),
            func.sum(case((AnswerAttempt.is_correct.is_(True), 1), else_=0)),
            func.sum(AnswerAttempt.score),
        )
        .join(Question, Question.id == AnswerAttempt.question_id)
        .join(Lesson, Lesson.id == Question.lesson_id)
        .join(PracticeSession, PracticeSession.id == AnswerAttempt.practice_session_id)
        .where(AnswerAttempt.user_id == user_id, PracticeSession.status != "ABANDONED")
        .group_by(Question.question_type, Question.reference_type, Lesson.lesson_type)
    ).all()
    attempted = completed = correct = guided = 0
    score_sum = 0.0
    subtype: dict[str, dict[str, int]] = defaultdict(lambda: {"attempts": 0, "correct": 0})
    for question_type, reference_type, lesson_type, count, correct_count, score in rows:
        qtype = (question_type or "").upper()
        if _skill_from_values(question_type, reference_type, lesson_type) != "WRITING":
            continue
        row_count = int(count or 0)
        row_correct = int(correct_count or 0)
        attempted += row_count
        completed += row_count
        correct += row_correct
        score_sum += float(score or 0)
        if qtype == "GUIDED_WRITING":
            guided += row_count
        if qtype in {"TRANSLATION_TO_CHINESE", "WORD_ORDER", "SENTENCE_REORDER"}:
            subtype[qtype]["attempts"] += row_count
            subtype[qtype]["correct"] += row_correct
    order_attempts = subtype["WORD_ORDER"]["attempts"] + subtype["SENTENCE_REORDER"]["attempts"]
    order_correct = subtype["WORD_ORDER"]["correct"] + subtype["SENTENCE_REORDER"]["correct"]
    translation_attempts = subtype["TRANSLATION_TO_CHINESE"]["attempts"]
    return {
        "attempted": attempted,
        "completed": completed,
        "accuracy": _percent(correct, attempted),
        "average_score": round(score_sum / attempted, 2) if attempted else None,
        "guided_count": guided,
        "translation_accuracy": _percent(subtype["TRANSLATION_TO_CHINESE"]["correct"], translation_attempts),
        "word_order_accuracy": _percent(order_correct, order_attempts),
    }


def hsk_progress(db: Session, user: User, level_number: int) -> HskProgressOut:
    level = db.scalar(select(HskLevel).where(HskLevel.level_number == level_number))
    if not level:
        raise ValueError("HSK level not found")
    lessons = _lessons_for_level(db, level.id)
    progress_by_lesson = _progress_by_lesson(db, user.id)
    total_vocab, total_grammar = _lesson_content_totals(lessons)
    learned_vocab, learned_grammar = _learned_content(lessons, progress_by_lesson)
    lesson_ids = [lesson.id for lesson in lessons]
    attempt_stats = _lesson_attempt_stats(db, user.id, lesson_ids)
    speaking_stats = _lesson_speaking_stats(db, user.id, lesson_ids)
    attempts = sum(value["attempts"] for value in attempt_stats.values())
    correct = sum(value["correct"] for value in attempt_stats.values())
    listening_attempts, listening_correct = _question_accuracy_stats(db, user.id, "LISTENING", lesson_ids)
    speaking_attempts = sum(value["attempts"] for value in speaking_stats.values())
    speaking_scores = [value["average_score"] for value in speaking_stats.values() if value["average_score"] is not None]
    completed_lessons = sum(
        1 for lesson in lessons if progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed"
    )
    return HskProgressOut(
        level=level.level_number,
        level_id=level.id,
        title=level.title,
        title_translations=None,
        vocabulary=ProgressMetricOut(total=len(total_vocab), completed=len(learned_vocab), percent=_percent(len(learned_vocab), len(total_vocab))),
        grammar=ProgressMetricOut(total=len(total_grammar), completed=len(learned_grammar), percent=_percent(len(learned_grammar), len(total_grammar))),
        lessons=ProgressMetricOut(total=len(lessons), completed=completed_lessons, percent=_percent(completed_lessons, len(lessons))),
        practice=_accuracy_metric(attempts, correct),
        listening=_accuracy_metric(listening_attempts, listening_correct) if listening_attempts else None,
        speaking=AccuracyMetricOut(
            attempts=speaking_attempts,
            correct=0,
            accuracy=None,
            average_score=round(sum(speaking_scores) / len(speaking_scores), 2) if speaking_scores else None,
        )
        if speaking_attempts
        else None,
        skill_performance=[metric for metric in _skill_metrics(db, user.id) if metric.practiced],
        study_minutes=sum(_study_minutes_by_lesson(db, user.id, lesson_ids).values()),
    )


def course_progress(db: Session, user: User, course_id: int) -> CourseProgressOut:
    level = db.get(HskLevel, course_id)
    if not level:
        raise ValueError("Course not found")
    lessons = _lessons_for_level(db, level.id)
    lesson_ids = [lesson.id for lesson in lessons]
    progress_by_lesson = _progress_by_lesson(db, user.id)
    attempt_stats = _lesson_attempt_stats(db, user.id, lesson_ids)
    study_minutes = _study_minutes_by_lesson(db, user.id, lesson_ids)
    attempts = sum(value["attempts"] for value in attempt_stats.values())
    correct = sum(value["correct"] for value in attempt_stats.values())
    completed = sum(1 for lesson in lessons if progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed")
    last_studied = max(
        [value["last_practiced"] for value in attempt_stats.values() if value["last_practiced"]] or [None]
    )
    return CourseProgressOut(
        course_id=level.id,
        title=level.title,
        hsk_level=level.level_number,
        total_lessons=len(lessons),
        completed_lessons=completed,
        progress_percent=_percent(completed, len(lessons)) or 0,
        practice_attempts=attempts,
        accuracy=_percent(correct, attempts),
        last_studied=last_studied,
        total_study_minutes=sum(study_minutes.values()),
        lessons=[
            {
                "lesson_id": lesson.id,
                "title": lesson.title,
                "title_translations": _title_translations(lesson),
                "lesson_type": lesson.lesson_type,
                "completed": bool(progress_by_lesson.get(lesson.id) and progress_by_lesson[lesson.id].status == "completed"),
                "study_minutes": study_minutes.get(lesson.id, 0),
                "accuracy": _percent(attempt_stats.get(lesson.id, {}).get("correct", 0), attempt_stats.get(lesson.id, {}).get("attempts", 0)),
            }
            for lesson in lessons
        ],
    )


def lesson_progress(db: Session, user: User, lesson_id: int) -> LessonProgressAnalyticsOut:
    lesson = db.get(Lesson, lesson_id)
    if not lesson:
        raise ValueError("Lesson not found")
    level = db.get(HskLevel, lesson.hsk_level_id)
    progress = db.scalar(select(LessonProgress).where(LessonProgress.user_id == user.id, LessonProgress.lesson_id == lesson_id))
    attempt = _lesson_attempt_stats(db, user.id, [lesson_id]).get(lesson_id, {"attempts": 0, "correct": 0})
    listening_attempts, listening_correct = _question_accuracy_stats(db, user.id, "LISTENING", [lesson_id])
    speaking = _lesson_speaking_stats(db, user.id, [lesson_id]).get(lesson_id)
    minutes = _study_minutes_by_lesson(db, user.id, [lesson_id]).get(lesson_id, 0)
    total_vocab, total_grammar = _lesson_content_totals([lesson])
    completed = bool(progress and progress.status == "completed")
    started = bool(progress or attempt["attempts"] or minutes)
    completion_percent = 100.0 if completed else 50.0 if started else 0.0
    return LessonProgressAnalyticsOut(
        lesson_id=lesson.id,
        title=lesson.title,
        title_translations=_title_translations(lesson),
        hsk_level=level.level_number if level else 0,
        lesson_type=lesson.lesson_type,
        started=started,
        completed=completed,
        completion_percent=completion_percent,
        vocabulary=ProgressMetricOut(total=len(total_vocab), completed=len(total_vocab) if completed else 0, percent=100 if completed and total_vocab else 0),
        grammar=ProgressMetricOut(total=len(total_grammar), completed=len(total_grammar) if completed else 0, percent=100 if completed and total_grammar else 0),
        practice=_accuracy_metric(int(attempt["attempts"]), int(attempt["correct"])),
        listening=_accuracy_metric(listening_attempts, listening_correct) if listening_attempts else None,
        speaking=AccuracyMetricOut(
            attempts=int(speaking["attempts"]),
            average_score=speaking["average_score"],
        )
        if speaking
        else None,
        study_minutes=minutes,
        last_practiced=attempt.get("last_practiced") if isinstance(attempt, dict) else None,
        completion_rule=COMPLETION_RULE,
    )
