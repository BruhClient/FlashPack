from datetime import datetime, timedelta, timezone

import pytest

from flashcards.db import Database
from flashcards.scheduler import apply_rating


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "flashcards.db")
    yield database
    database.close()


def test_class_chapter_card_crud(db):
    cls = db.add_class("Biology")
    ch1 = db.add_chapter(cls, "Cells")
    ch2 = db.add_chapter(cls, "Genetics")
    card = db.add_card(ch1, "<p>Q</p>", "<p>A</p>")

    assert [c.name for c in db.list_classes()] == ["Biology"]
    assert [c.name for c in db.list_chapters(cls)] == ["Cells", "Genetics"]
    assert db.get_card(card).front_html == "<p>Q</p>"
    assert db.get_card(card).is_new

    db.rename_chapter(ch2, "DNA")
    db.update_card_content(card, "<p>Q2</p>", "<p>A2</p>")
    assert db.get_chapter(ch2).name == "DNA"
    assert db.get_card(card).back_html == "<p>A2</p>"


def test_move_chapter_reorders(db):
    cls = db.add_class("C")
    a, b, c = (db.add_chapter(cls, n) for n in "abc")
    db.move_chapter(c, -1)
    assert [ch.name for ch in db.list_chapters(cls)] == ["a", "c", "b"]
    db.move_chapter(a, -1)  # already first: no-op
    assert [ch.name for ch in db.list_chapters(cls)] == ["a", "c", "b"]


def test_rename_class_and_chapter(db):
    cls = db.add_class("Bio")
    ch = db.add_chapter(cls, "Ch 1")
    db.rename_class(cls, "Biology 101")
    db.rename_chapter(ch, "Cells")
    assert db.get_class(cls).name == "Biology 101"
    assert db.get_chapter(ch).name == "Cells"


def test_move_chapter_to_other_class_keeps_cards(db):
    bio, chem = db.add_class("Bio"), db.add_class("Chem")
    db.add_chapter(chem, "Existing")
    ch = db.add_chapter(bio, "Atoms")
    db.add_card(ch, "q", "a")
    db.move_chapter_to_class(ch, chem)
    assert [c.name for c in db.list_chapters(chem)] == ["Existing", "Atoms"]
    assert db.list_chapters(bio) == []
    assert len(db.list_cards_for_class(chem)) == 1


def test_move_cards_keeps_schedule_and_history(db):
    cls = db.add_class("C")
    src, dst = db.add_chapter(cls, "src"), db.add_chapter(cls, "dst")
    card_id = db.add_card(src, "q", "a")
    db.record_review(card_id, 4, apply_rating(db.get_card(card_id), 4))

    db.move_cards([card_id], dst)
    moved = db.get_card(card_id)
    assert moved.chapter_id == dst
    assert moved.last_rating == 4 and moved.repetitions == 1
    assert db.count_cards(src) == 0 and db.count_cards(dst) == 1
    since = datetime.now(timezone.utc) - timedelta(days=1)
    assert len(db.review_times_for_class(cls, since)) == 1


def test_deleting_class_cascades(db):
    cls = db.add_class("C")
    ch = db.add_chapter(cls, "ch")
    card = db.add_card(ch, "q", "a")
    db.record_review(card, 2, apply_rating(db.get_card(card), 2))

    db.delete_class(cls)
    for table in ("chapters", "cards", "reviews"):
        (n,) = db.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
        assert n == 0, table


def test_list_cards_for_class_and_chapters(db):
    c1, c2 = db.add_class("one"), db.add_class("two")
    ch1, ch2, ch3 = db.add_chapter(c1, "a"), db.add_chapter(c1, "b"), db.add_chapter(c2, "c")
    for ch in (ch1, ch2, ch3):
        db.add_card(ch, "q", "a")
    assert len(db.list_cards_for_class(c1)) == 2
    assert len(db.list_cards_for_chapters([ch1, ch3])) == 2
    assert db.list_cards_for_chapters([]) == []
