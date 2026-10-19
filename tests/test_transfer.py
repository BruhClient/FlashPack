import json
import zipfile

import pytest

from flashcards import media
from flashcards.db import Database
from flashcards.scheduler import apply_rating
from flashcards.transfer import MODE_MERGE, MODE_REPLACE, PackError, export_pack, import_pack

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake"


def make_db(path):
    return Database(path / "flashcards.db")


@pytest.fixture
def source(tmp_path):
    db = make_db(tmp_path / "src")
    cls = db.add_class("Biology")
    ch1, ch2 = db.add_chapter(cls, "Cells"), db.add_chapter(cls, "Genetics")
    image = media.new_media_name()
    (media.media_dir(db.data_dir) / image).write_bytes(PNG_BYTES)
    card = db.add_card(ch1, f'<p>Q <img src="{media.reference(image)}" /></p>', "<p>A</p>")
    db.add_card(ch2, "<p>Q2</p>", "<p>A2</p>")
    db.record_review(card, 5, apply_rating(db.get_card(card), 5))
    yield db, image
    db.close()


def test_round_trip_into_empty_device(source, tmp_path):
    src, image = source
    pack = export_pack(src, tmp_path / "out.flashpack")

    dst = make_db(tmp_path / "dst")
    result = import_pack(dst, pack, MODE_MERGE)
    assert (result.classes, result.chapters, result.cards) == (1, 2, 2)

    (cls,) = dst.list_classes()
    assert cls.name == "Biology"
    cards = dst.list_cards_for_class(cls.id)
    reviewed = next(c for c in cards if c.last_rating)
    assert reviewed.last_rating == 5 and reviewed.repetitions == 1
    assert (dst.data_dir / "media" / image).read_bytes() == PNG_BYTES
    (n,) = dst.conn.execute("SELECT COUNT(*) FROM reviews").fetchone()
    assert n == 1
    dst.close()


def test_merge_renames_clashing_class(source, tmp_path):
    src, _ = source
    pack = export_pack(src, tmp_path / "out.flashpack")
    import_pack(src, pack, MODE_MERGE)
    import_pack(src, pack, MODE_MERGE)
    assert [c.name for c in src.list_classes()] == [
        "Biology", "Biology (imported)", "Biology (imported 2)"]


def test_replace_wipes_existing_and_writes_backup(source, tmp_path):
    src, _ = source
    pack = export_pack(src, tmp_path / "out.flashpack")

    dst = make_db(tmp_path / "dst")
    dst.add_class("Old stuff")
    result = import_pack(dst, pack, MODE_REPLACE)
    assert [c.name for c in dst.list_classes()] == ["Biology"]
    assert result.backup_path is not None and result.backup_path.exists()
    with zipfile.ZipFile(result.backup_path) as zf:
        backup = json.loads(zf.read("data.json"))
    assert [c["name"] for c in backup["classes"]] == ["Old stuff"]
    dst.close()


def test_rejects_non_pack_files(tmp_path):
    db = make_db(tmp_path)
    bad = tmp_path / "bad.flashpack"
    bad.write_text("not a zip")
    with pytest.raises(PackError):
        import_pack(db, bad)

    no_data = tmp_path / "empty.flashpack"
    with zipfile.ZipFile(no_data, "w") as zf:
        zf.writestr("other.txt", "x")
    with pytest.raises(PackError):
        import_pack(db, no_data)
    db.close()


def test_ignores_unsafe_media_paths(source, tmp_path):
    src, _ = source
    pack = export_pack(src, tmp_path / "out.flashpack")
    with zipfile.ZipFile(pack, "a") as zf:
        zf.writestr("media/../../evil.png", b"x")

    dst = make_db(tmp_path / "dst")
    import_pack(dst, pack, MODE_MERGE)
    assert not (tmp_path / "evil.png").exists()
    assert not (tmp_path / "dst" / "evil.png").exists()
    dst.close()


def test_cleanup_orphans_keeps_referenced(source):
    src, image = source
    orphan = media.media_dir(src.data_dir) / media.new_media_name()
    orphan.write_bytes(PNG_BYTES)
    assert media.cleanup_orphans(src.data_dir, src.all_card_html()) == 1
    assert not orphan.exists()
    assert (src.data_dir / "media" / image).exists()
