from datetime import datetime, timedelta, timezone

import pytest

from flashcards.models import Card, Chapter, to_iso
from flashcards.stats import (
    LEARNING, MASTERED, STRUGGLING, UNTESTED, card_mastery, card_status,
    class_stats, review_activity,
)

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=timezone.utc)


def card(id, chapter_id=1, rating=None, interval=0.0, due_in_days=1.0):
    kw = {}
    if rating is not None:
        kw = dict(last_rating=rating, interval_days=interval,
                  last_reviewed_at=to_iso(NOW - timedelta(days=1)),
                  due_at=to_iso(NOW + timedelta(days=due_in_days)))
    return Card(id=id, chapter_id=chapter_id, front_html="", back_html="",
                created_at=to_iso(NOW), **kw)


@pytest.mark.parametrize("c, status", [
    (card(1), UNTESTED),
    (card(2, rating=1), STRUGGLING),
    (card(3, rating=2, interval=40), STRUGGLING),
    (card(4, rating=3, interval=40), LEARNING),
    (card(5, rating=5, interval=5), LEARNING),
    (card(6, rating=4, interval=21), MASTERED),
])
def test_card_status(c, status):
    assert card_status(c) == status


def test_card_mastery_range():
    assert card_mastery(card(1)) is None
    assert card_mastery(card(2, rating=1, interval=0)) == 0.0
    assert card_mastery(card(3, rating=5, interval=60)) == 1.0
    assert card_mastery(card(4, rating=3, interval=10.5)) == pytest.approx(0.5)


def test_class_stats_per_chapter_and_untested():
    chapters = [Chapter(1, 1, "A", 0), Chapter(2, 1, "B", 1), Chapter(3, 1, "Empty", 2)]
    cards = [
        card(1, 1, rating=5, interval=60),                 # mastery 1.0
        card(2, 1, rating=1, interval=0, due_in_days=-1),  # mastery 0.0, due
        card(3, 1),                                        # untested
        card(4, 2), card(5, 2),                            # all untested
    ]
    overall, per = class_stats(chapters, cards, NOW)

    a, b, empty = per
    assert (a.total, a.untested, a.tested) == (3, 1, 2)
    assert a.proficiency == pytest.approx(0.5)
    assert a.counts == {UNTESTED: 1, STRUGGLING: 1, LEARNING: 0, MASTERED: 1}
    assert a.due_today == 1

    assert b.untested == 2 and b.proficiency is None
    assert empty.total == 0 and empty.proficiency is None

    assert overall.total == 5 and overall.untested == 3
    assert overall.proficiency == pytest.approx(0.5)


def test_review_activity_buckets_by_day():
    local_noon = NOW.astimezone()
    stamps = [to_iso(local_noon), to_iso(local_noon),
              to_iso(local_noon - timedelta(days=2)),
              to_iso(local_noon - timedelta(days=40))]
    activity = review_activity(stamps, NOW, days=7)
    assert len(activity) == 7
    assert activity[-1] == (local_noon.date(), 2)
    assert activity[-3][1] == 1
    assert sum(n for _, n in activity) == 3
