from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import ClassVar

from app.config import settings


class ReviewRating(StrEnum):
    AGAIN = "AGAIN"
    HARD = "HARD"
    GOOD = "GOOD"
    EASY = "EASY"


class ReviewState(StrEnum):
    NEW = "NEW"
    LEARNING = "LEARNING"
    REVIEW = "REVIEW"
    RELEARNING = "RELEARNING"


@dataclass(frozen=True)
class CardSchedulingState:
    state: ReviewState
    due_at: datetime
    last_reviewed_at: datetime | None
    reps: int
    lapses: int
    stability: float | None
    difficulty: float | None
    interval_days: float


@dataclass(frozen=True)
class SchedulingResult:
    state: ReviewState
    due_at: datetime
    reps: int
    lapses: int
    stability: float
    difficulty: float
    interval_days: float
    scheduler_version: str


class SpacedRepetitionScheduler:
    version = "fsrs-5-default"

    # FSRS-5 default parameters from open-spaced-repetition/fsrs4anki.
    parameters: ClassVar[list[float]] = [
        0.40255,
        1.18385,
        3.173,
        15.69105,
        7.1949,
        0.5345,
        1.4604,
        0.0046,
        1.54575,
        0.1192,
        1.01925,
        1.9395,
        0.11,
        0.29605,
        2.2698,
        0.2315,
        2.9898,
        0.51655,
        0.6621,
    ]
    decay = -0.5
    factor = 19 / 81

    def initialize_card(self, now: datetime | None = None) -> CardSchedulingState:
        reviewed_at = _utc(now)
        return CardSchedulingState(
            state=ReviewState.NEW,
            due_at=reviewed_at,
            last_reviewed_at=None,
            reps=0,
            lapses=0,
            stability=None,
            difficulty=None,
            interval_days=0,
        )

    def process_review(
        self,
        card: CardSchedulingState,
        rating: ReviewRating,
        reviewed_at: datetime,
    ) -> SchedulingResult:
        reviewed_at = _utc(reviewed_at)
        grade = _grade(rating)
        stability = card.stability
        difficulty = card.difficulty
        reps = card.reps + 1
        lapses = card.lapses

        if card.reps == 0 or stability is None or difficulty is None:
            stability = self._initial_stability(grade)
            difficulty = self._initial_difficulty(grade)
        else:
            elapsed_days = max((reviewed_at - _utc(card.last_reviewed_at or card.due_at)).total_seconds() / 86400, 0)
            retrievability = self.retrievability(elapsed_days, stability)
            difficulty = self._next_difficulty(difficulty, grade)
            if rating == ReviewRating.AGAIN:
                stability = self._forget_stability(difficulty, stability, retrievability)
            elif elapsed_days < 1:
                stability = self._same_day_stability(stability, grade)
            else:
                stability = self._recall_stability(difficulty, stability, retrievability, grade)

        if rating == ReviewRating.AGAIN:
            lapses += 1
            interval_days = 0.0
            due_at = reviewed_at + timedelta(minutes=settings.review_learning_again_minutes)
            next_state = ReviewState.LEARNING if card.reps == 0 else ReviewState.RELEARNING
        else:
            interval_days = self.interval_for_stability(stability)
            if rating == ReviewRating.HARD:
                interval_days = max(1, min(interval_days, max(card.interval_days + 1, 1)))
            elif rating == ReviewRating.EASY:
                interval_days = max(interval_days, card.interval_days + 1)
            interval_days = round(interval_days, 4)
            due_at = reviewed_at + timedelta(days=interval_days)
            next_state = ReviewState.REVIEW

        return SchedulingResult(
            state=next_state,
            due_at=due_at,
            reps=reps,
            lapses=lapses,
            stability=round(_clamp(stability, 0.01, 36500), 4),
            difficulty=round(_clamp(difficulty, 1, 10), 4),
            interval_days=interval_days,
            scheduler_version=self.version,
        )

    def preview(self, card: CardSchedulingState, reviewed_at: datetime) -> dict[ReviewRating, SchedulingResult]:
        return {rating: self.process_review(card, rating, reviewed_at) for rating in ReviewRating}

    def retrievability(self, elapsed_days: float, stability: float) -> float:
        if stability <= 0:
            return 0
        return _clamp((1 + self.factor * elapsed_days / stability) ** self.decay, 0, 1)

    def interval_for_stability(self, stability: float, retention: float | None = None) -> float:
        requested = _clamp(retention or settings.review_desired_retention, 0.7, 0.97)
        return max(stability / self.factor * (requested ** (1 / self.decay) - 1), 0)

    def _initial_stability(self, grade: int) -> float:
        return self.parameters[grade - 1]

    def _initial_difficulty(self, grade: int) -> float:
        w = self.parameters
        return _clamp(w[4] - math.exp(w[5] * (grade - 1)) + 1, 1, 10)

    def _next_difficulty(self, difficulty: float, grade: int) -> float:
        w = self.parameters
        delta = -w[6] * (grade - 3)
        damped = difficulty + delta * (10 - difficulty) / 9
        easy_target = self._initial_difficulty(4)
        return _clamp(w[7] * easy_target + (1 - w[7]) * damped, 1, 10)

    def _same_day_stability(self, stability: float, grade: int) -> float:
        w = self.parameters
        increase = math.exp(w[17] * (grade - 3 + w[18]))
        if grade >= 3:
            increase = max(increase, 1)
        return stability * increase

    def _recall_stability(self, difficulty: float, stability: float, retrievability: float, grade: int) -> float:
        w = self.parameters
        hard_modifier = w[15] if grade == 2 else 1
        easy_modifier = w[16] if grade == 4 else 1
        increase = (
            math.exp(w[8])
            * (11 - difficulty)
            * stability ** (-w[9])
            * (math.exp(w[10] * (1 - retrievability)) - 1)
            * hard_modifier
            * easy_modifier
            + 1
        )
        return max(stability * increase, stability)

    def _forget_stability(self, difficulty: float, stability: float, retrievability: float) -> float:
        w = self.parameters
        value = w[11] * difficulty ** (-w[12]) * ((stability + 1) ** w[13] - 1) * math.exp(w[14] * (1 - retrievability))
        return min(value, stability)


def _grade(rating: ReviewRating) -> int:
    return {
        ReviewRating.AGAIN: 1,
        ReviewRating.HARD: 2,
        ReviewRating.GOOD: 3,
        ReviewRating.EASY: 4,
    }[rating]


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)


def _utc(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
