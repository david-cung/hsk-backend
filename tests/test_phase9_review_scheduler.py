from datetime import UTC, datetime, timedelta

from app.review_scheduler import ReviewRating, ReviewState, SpacedRepetitionScheduler


def test_new_card_again_enters_learning() -> None:
    scheduler = SpacedRepetitionScheduler()
    now = datetime(2026, 8, 15, 9, tzinfo=UTC)
    card = scheduler.initialize_card(now)

    result = scheduler.process_review(card, ReviewRating.AGAIN, now)

    assert result.state == ReviewState.LEARNING
    assert result.reps == 1
    assert result.lapses == 1
    assert result.interval_days == 0
    assert result.due_at == now + timedelta(minutes=10)
    assert result.stability == 0.4026
    assert result.difficulty == 7.1949


def test_new_card_good_graduates_to_review() -> None:
    scheduler = SpacedRepetitionScheduler()
    now = datetime(2026, 8, 15, 9, tzinfo=UTC)
    card = scheduler.initialize_card(now)

    result = scheduler.process_review(card, ReviewRating.GOOD, now)

    assert result.state == ReviewState.REVIEW
    assert result.reps == 1
    assert result.lapses == 0
    assert result.interval_days == 3.173
    assert result.due_at == now + timedelta(days=3.173)
    assert result.difficulty == 5.2824


def test_new_card_easy_has_longer_interval_than_good() -> None:
    scheduler = SpacedRepetitionScheduler()
    now = datetime(2026, 8, 15, 9, tzinfo=UTC)
    card = scheduler.initialize_card(now)

    good = scheduler.process_review(card, ReviewRating.GOOD, now)
    easy = scheduler.process_review(card, ReviewRating.EASY, now)

    assert easy.state == ReviewState.REVIEW
    assert easy.interval_days > good.interval_days
    assert easy.stability == 15.6911
    assert easy.difficulty < good.difficulty


def test_review_card_again_lapses_and_becomes_relearning() -> None:
    scheduler = SpacedRepetitionScheduler()
    first = datetime(2026, 8, 1, 9, tzinfo=UTC)
    review = datetime(2026, 8, 10, 9, tzinfo=UTC)
    card = scheduler.initialize_card(first)
    learned = scheduler.process_review(card, ReviewRating.GOOD, first)
    state = card.__class__(
        state=learned.state,
        due_at=learned.due_at,
        last_reviewed_at=first,
        reps=learned.reps,
        lapses=learned.lapses,
        stability=learned.stability,
        difficulty=learned.difficulty,
        interval_days=learned.interval_days,
    )

    result = scheduler.process_review(state, ReviewRating.AGAIN, review)

    assert result.state == ReviewState.RELEARNING
    assert result.reps == 2
    assert result.lapses == 1
    assert result.due_at == review + timedelta(minutes=10)
    assert result.stability < learned.stability


def test_review_success_ratings_update_stability_and_difficulty() -> None:
    scheduler = SpacedRepetitionScheduler()
    first = datetime(2026, 8, 1, 9, tzinfo=UTC)
    review = datetime(2026, 8, 10, 9, tzinfo=UTC)
    card = scheduler.initialize_card(first)
    learned = scheduler.process_review(card, ReviewRating.GOOD, first)
    state = card.__class__(
        state=learned.state,
        due_at=learned.due_at,
        last_reviewed_at=first,
        reps=learned.reps,
        lapses=learned.lapses,
        stability=learned.stability,
        difficulty=learned.difficulty,
        interval_days=learned.interval_days,
    )

    hard = scheduler.process_review(state, ReviewRating.HARD, review)
    good = scheduler.process_review(state, ReviewRating.GOOD, review)
    easy = scheduler.process_review(state, ReviewRating.EASY, review)

    assert hard.state == ReviewState.REVIEW
    assert hard.interval_days <= good.interval_days <= easy.interval_days
    assert hard.difficulty > good.difficulty > easy.difficulty
    assert hard.reps == good.reps == easy.reps == 2
