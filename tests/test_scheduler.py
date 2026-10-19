import random
from datetime import datetime, timedelta, timezone

import pytest

from flashcards.models import Card, to_iso
from flashcards.scheduler import (
    FAIL_INTERVAL_DAYS, MIN_EASE, StudySession, apply_rating, apply_update,
    build_session, next_ease,
)

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def make_card(id=1, **kw) -> Card:
    defaults = dict(chapter_id=1, front_html="f", back_html="b",
                    created_at=to_iso(NOW - timedelta(days=30) + timedelta(seconds=id)))
    defaults.update(kw)
    return Card(id=id, **defaults)


def reviewed_card(id, days_since_review, interval, rating=4, ease=2.5, reps=3):
    last = NOW - timedelta(days=days_since_review)
    return make_card(id, ease=ease, interval_days=interval, repetitions=reps,
                     last_rating=rating, last_reviewed_at=to_iso(last),
                     due_at=to_iso(last + timedelta(days=interval)))


@pytest.mark.parametrize("rating, expected_delta", [(5, 0.1), (4, 0.0), (3, -0.14),
                                                    (2, -0.32), (1, -0.54)])
def test_ease_change_per_rating(rating, expected_delta):
    assert next_ease(2.5, rating) == pytest.approx(2.5 + expected_delta)


def test_ease_never_drops_below_minimum():
    assert next_ease(1.35, 1) == MIN_EASE


def test_new_card_good_rating_schedules_one_day():
    up = apply_rating(make_card(), 4, now=NOW)
    assert up.repetitions == 1
    assert up.interval_days == 1.0
    assert up.due_at == to_iso(NOW + timedelta(days=1))
    assert up.last_rating == 4 and not up.failed


def test_second_success_uses_3_or_6_days():
    card = make_card(repetitions=1, interval_days=1.0)
    assert apply_rating(card, 3, now=NOW).interval_days == 3.0
    assert apply_rating(card, 4, now=NOW).interval_days == 6.0


def test_mature_card_grows_by_ease_with_rating_modifiers():
    card = make_card(repetitions=3, interval_days=10.0, ease=2.5)
    assert apply_rating(card, 4, now=NOW).interval_days == pytest.approx(25.0)
    assert apply_rating(card, 5, now=NOW).interval_days == pytest.approx(10 * 2.6 * 1.3)
    assert apply_rating(card, 3, now=NOW).interval_days == pytest.approx(10 * 2.36 * 0.8)


@pytest.mark.parametrize("rating", [1, 2])
def test_failure_resets_and_relearns_soon(rating):
    card = make_card(repetitions=4, interval_days=30.0, lapses=1)
    up = apply_rating(card, rating, now=NOW)
    assert up.failed
    assert up.repetitions == 0
    assert up.interval_days == FAIL_INTERVAL_DAYS
    assert up.lapses == 2


def test_repeat_in_session_does_not_touch_ease_or_lapses():
    card = make_card(ease=2.0, lapses=1)
    up = apply_rating(card, 1, now=NOW, first_in_session=False)
    assert up.ease == 2.0 and up.lapses == 1


def test_invalid_rating_rejected():
    with pytest.raises(ValueError):
        apply_rating(make_card(), 0, now=NOW)


def test_apply_update_copies_schedule():
    card = make_card()
    apply_update(card, apply_rating(card, 5, now=NOW))
    assert card.last_rating == 5 and not card.is_new


def test_build_session_orders_due_then_new_then_weakest_not_due():
    overdue_weak = reviewed_card(1, days_since_review=10, interval=2, rating=3, ease=1.8)
    due_strong = reviewed_card(2, days_since_review=6, interval=6, rating=5, ease=2.8)
    new_card = make_card(3)
    later_almost_due = reviewed_card(4, days_since_review=9, interval=10)
    later_fresh = reviewed_card(5, days_since_review=1, interval=30)

    cards = [later_fresh, new_card, due_strong, later_almost_due, overdue_weak]
    picked = build_session(cards, n=10, now=NOW)
    assert [c.id for c in picked] == [1, 2, 3, 4, 5]


def test_build_session_respects_limit_and_new_toggle():
    cards = [make_card(1), make_card(2), reviewed_card(3, 5, 1)]
    assert [c.id for c in build_session(cards, n=2, now=NOW)] == [3, 1]
    assert [c.id for c in build_session(cards, n=5, include_new=False, now=NOW)] == [3]


def test_session_requeues_failed_cards_until_passed():
    cards = [make_card(i) for i in range(1, 7)]
    session = StudySession(cards, rng=random.Random(0))
    first = session.current
    session.rate(1)
    assert first in session.queue[3:6]
    assert session.progress == 0

    seen = []
    while not session.finished:
        seen.append(session.current.id)
        session.rate(4)
    assert seen.count(first.id) == 1
    assert session.progress == 1.0
    assert session.rating_distribution() == {1: 1, 2: 0, 3: 0, 4: 5, 5: 0}


def test_session_last_card_failure_comes_straight_back():
    session = StudySession([make_card(1)])
    session.rate(2)
    assert session.current.id == 1
    session.rate(3)
    assert session.finished
