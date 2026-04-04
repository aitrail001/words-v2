import uuid
import zipfile
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.models.import_source import ImportSource
from app.models.import_source_entry import ImportSourceEntry
from app.models.word import Word
from app.models.word_form import WordForm
from app.services.source_imports import (
    EpubTextExtractor,
    EntryRef,
    ImportCacheDeletedError,
    ImportMatcher,
    build_import_cache_key,
    create_word_list_from_entries,
    deterministic_lemmatize,
    get_or_create_import_source,
    get_or_create_import_source_sync,
    normalize_matching_text,
    normalize_extraction_text,
    parse_bulk_entry_text,
    sha256_digest_from_bytes,
    _normalize_source_title,
)


def _write_epub_fixture(tmp_path, *, metadata_xml: str, body_title: str = "Chapter", body_text: str = "Hello world"):
    file_path = tmp_path / f"{uuid.uuid4()}.epub"
    container_xml = """<?xml version="1.0" encoding="UTF-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
"""
    content_opf = f"""<?xml version="1.0" encoding="UTF-8"?>
<package xmlns="http://www.idpf.org/2007/opf" xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0" unique-identifier="bookid">
  <metadata>
    {metadata_xml}
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />
    <item id="chapter1" href="chapter1.xhtml" media-type="application/xhtml+xml" />
  </manifest>
  <spine>
    <itemref idref="nav" />
    <itemref idref="chapter1" />
  </spine>
</package>
"""
    nav_xhtml = """<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops">
  <head><title>Contents</title></head>
  <body><nav epub:type="toc"><ol><li>Chapter 1</li></ol></nav></body>
</html>
"""
    chapter_xhtml = f"""<?xml version="1.0" encoding="utf-8"?>
<html xmlns="http://www.w3.org/1999/xhtml">
  <head><title>{body_title}</title></head>
  <body><p>{body_text}</p></body>
</html>
"""

    with zipfile.ZipFile(file_path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", container_xml)
        archive.writestr("OEBPS/content.opf", content_opf)
        archive.writestr("OEBPS/nav.xhtml", nav_xhtml)
        archive.writestr("OEBPS/chapter1.xhtml", chapter_xhtml)
    return file_path


def test_sha256_digest_from_bytes_is_stable():
    assert sha256_digest_from_bytes(b"abc") == sha256_digest_from_bytes(b"abc")
    assert sha256_digest_from_bytes(b"abc") != sha256_digest_from_bytes(b"abcd")


def test_build_import_cache_key_changes_with_versions():
    key_one = build_import_cache_key(source_type="epub", source_hash_sha256="a" * 64)
    key_two = build_import_cache_key(
        source_type="epub",
        source_hash_sha256="a" * 64,
        pipeline_version="other",
    )
    key_three = build_import_cache_key(
        source_type="epub",
        source_hash_sha256="a" * 64,
        lexicon_version="other",
    )

    assert key_one != key_two
    assert key_one != key_three


def test_exact_surface_form_wins_over_word_form_mapping():
    ran_word_id = uuid.uuid4()
    run_word_id = uuid.uuid4()
    matcher = ImportMatcher.from_rows(
        exact_words=[
            Word(id=ran_word_id, word="ran", language="en"),
            Word(id=run_word_id, word="run", language="en"),
        ],
        word_forms=[
            WordForm(word_id=run_word_id, form_kind="past", value="ran", order_index=0),
        ],
        phrase_rows=[],
    )

    resolved = matcher.resolve_terms(
        ["ran"],
        phrase_catalog={},
        learner_catalog={
            ("word", ran_word_id): {
                "entry_type": "word",
                "entry_id": ran_word_id,
                "display_text": "ran",
                "normalized_form": "ran",
            }
        },
    )

    assert resolved["found_entries"][0]["entry_id"] == ran_word_id


def test_word_form_mapping_resolves_plural_when_exact_missing():
    apple_id = uuid.uuid4()
    matcher = ImportMatcher.from_rows(
        exact_words=[Word(id=apple_id, word="apple", language="en")],
        word_forms=[WordForm(word_id=apple_id, form_kind="plural", value="apples", order_index=0)],
        phrase_rows=[],
    )
    resolved = matcher.resolve_terms(
        ["apples"],
        phrase_catalog={},
        learner_catalog={
            ("word", apple_id): {
                "entry_type": "word",
                "entry_id": apple_id,
                "display_text": "apple",
                "normalized_form": "apple",
            }
        },
    )

    assert resolved["found_entries"][0]["entry_id"] == apple_id


def test_ambiguous_word_form_returns_ambiguous_entry():
    matcher = ImportMatcher.from_rows(
        exact_words=[],
        word_forms=[
            WordForm(word_id=uuid.uuid4(), form_kind="plural", value="axes", order_index=0),
            WordForm(word_id=uuid.uuid4(), form_kind="plural", value="axes", order_index=0),
        ],
        phrase_rows=[],
    )

    resolved = matcher.resolve_terms(["axes"], phrase_catalog={}, learner_catalog={})
    assert resolved["ambiguous_entries"] == ["axes"]


def test_phrase_matching_is_case_insensitive_and_prefers_longer_overlap():
    longer_id = uuid.uuid4()
    shorter_id = uuid.uuid4()
    matcher = ImportMatcher.from_rows(
        exact_words=[],
        word_forms=[],
        phrase_rows=[
            {
                "entry_type": "phrase",
                "entry_id": longer_id,
                "display_text": "on the other hand",
                "normalized_form": "on the other hand",
                "browse_rank": 10,
                "cefr_level": "B2",
                "phrase_kind": "idiom",
            },
            {
                "entry_type": "phrase",
                "entry_id": shorter_id,
                "display_text": "other hand",
                "normalized_form": "other hand",
                "browse_rank": 20,
                "cefr_level": "B2",
                "phrase_kind": "collocation",
            },
        ],
    )

    matched = matcher.match_chunks(["We saw it On the Other Hand yesterday."])

    assert [item.entry_id for item in matched if item.entry_type == "phrase"] == [longer_id]


def test_parse_bulk_entry_text_supports_csv_newlines_and_whitespace_modes():
    assert parse_bulk_entry_text('run, "make up for", "on the other hand"') == [
        "run",
        "make up for",
        "on the other hand",
    ]
    assert parse_bulk_entry_text("run\nmake up for\non the other hand") == [
        "run",
        "make up for",
        "on the other hand",
    ]
    assert parse_bulk_entry_text('run,"make up for"\nwalk,"on the other hand"') == [
        "run",
        "make up for",
        "walk",
        "on the other hand",
    ]
    assert parse_bulk_entry_text("run walk swim") == ["run", "walk", "swim"]


def test_normalization_and_deterministic_lemmatizer_are_stable():
    assert normalize_matching_text(" On\u2014The   Other\u2019Hand ") == "on-the other'hand"
    assert deterministic_lemmatize("apples") == "apple"


def test_normalize_extraction_text_repairs_soft_hyphens_dashes_and_fragmented_caps():
    raw = "An imprint of P ENGUIN R AND OM H OUSE LLC with co-\noperate and re\u00adentered plus ﬁnal touch."

    normalized = normalize_extraction_text(raw)

    assert "imprintof" not in normalized.casefold()
    assert "Penguin Random House LLC" in normalized
    assert "cooperate" in normalized
    assert "reentered" in normalized
    assert "final" in normalized


def test_deterministic_lemmatize_handles_common_inflections_and_irregulars():
    assert deterministic_lemmatize("studied") == "study"
    assert deterministic_lemmatize("running") == "run"
    assert deterministic_lemmatize("carried") == "carry"
    assert deterministic_lemmatize("went") == "go"
    assert deterministic_lemmatize("better") == "good"


def test_match_chunks_repairs_split_words_before_word_matching():
    cooperate_id = uuid.uuid4()
    matcher = ImportMatcher.from_rows(
        exact_words=[Word(id=cooperate_id, word="cooperate", language="en")],
        word_forms=[],
        phrase_rows=[],
    )

    matched = matcher.match_chunks(["We need to co-\noperate to finish the project."])

    assert [item.entry_id for item in matched] == [cooperate_id]


def test_match_chunks_repairs_ligatures_and_fragmented_hyphenated_words():
    final_id = uuid.uuid4()
    reenter_id = uuid.uuid4()
    matcher = ImportMatcher.from_rows(
        exact_words=[
            Word(id=final_id, word="final", language="en"),
            Word(id=reenter_id, word="reenter", language="en"),
        ],
        word_forms=[],
        phrase_rows=[],
    )

    matched = matcher.match_chunks(["The ﬁnal draft was re\u00adentered into the archive."])

    assert {item.entry_id for item in matched} == {final_id, reenter_id}


def test_normalize_source_title_strips_vendor_noise_and_extensions():
    assert _normalize_source_title("Pygmalion by George Bernard Shaw ( PDFDrive.com ).epub") == (
        "Pygmalion by George Bernard Shaw"
    )
    assert _normalize_source_title("Pygmalion.epub") == "Pygmalion"


def test_epub_text_extractor_combines_title_subtitle_and_isbn_publisher(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title id="maintitle">The 5 Types of Wealth</dc:title>
<dc:title id="subtitle">A Transformative Guide to Design Your Dream Life</dc:title>
<meta refines="#maintitle" property="title-type">main</meta>
<meta refines="#subtitle" property="title-type">subtitle</meta>
<dc:creator id="creator1">Sahil Bloom</dc:creator>
<meta refines="#creator1" property="role">aut</meta>
<dc:publisher>Random House Publishing Group</dc:publisher>
<dc:date>2025-02-04</dc:date>
<dc:identifier id="uuid_id">urn:uuid:12345678-1234-1234-1234-123456789abc</dc:identifier>
<dc:identifier id="EbookISBN">9780593723197</dc:identifier>
<dc:language>en-US</dc:language>
""",
    )

    metadata, chunks = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.title == "The 5 Types of Wealth: A Transformative Guide to Design Your Dream Life"
    assert metadata.author == "Sahil Bloom"
    assert metadata.publisher == "Random House Publishing Group"
    assert metadata.published_year == 2025
    assert metadata.isbn == "9780593723197"
    assert metadata.source_identifier == "9780593723197"
    assert list(chunks) == ["Hello world"]


def test_epub_text_extractor_prefers_author_and_content_title_when_package_title_is_noisy(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title>Pygmalion by George Bernard Shaw ( PDFDrive.com ).epub</dc:title>
<dc:creator id="creator1">Jim Manis, ed.; George Bernard Shaw</dc:creator>
<meta refines="#creator1" property="role">aut</meta>
<dc:date>2011-07-22T05:15:47+00:00</dc:date>
<dc:identifier id="uuid_id">a81a033e-90ef-4945-bf84-88dcaffcc26e</dc:identifier>
<dc:language>en</dc:language>
""",
        body_title="Unknown",
        body_text="Unknown PYGMALION By George Bernard Shaw A Penn State Electronic Classics Series Publication",
    )

    metadata, _ = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.title == "Pygmalion"
    assert metadata.author == "George Bernard Shaw"
    assert metadata.publisher is None
    assert metadata.published_year == 2011
    assert metadata.isbn is None
    assert metadata.source_identifier == "a81a033e-90ef-4945-bf84-88dcaffcc26e"


def test_epub_text_extractor_prefers_non_modification_year_and_uuid_fallback_identifier(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title>Scrambled or Sunny-Side Up?</dc:title>
<dc:creator>Loren Ridinger</dc:creator>
<dc:publisher>Post Hill Press</dc:publisher>
<dc:date opf:event="modification" xmlns:opf="http://www.idpf.org/2007/opf">2025-01-22</dc:date>
<dc:date>2025-01-17T17:08:08+00:00</dc:date>
<dc:identifier id="bookid">urn:uuid:54eb2f5a-76d9-4b41-b742-483199aa625e</dc:identifier>
<dc:language>en-US</dc:language>
""",
    )

    metadata, _ = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.title == "Scrambled or Sunny-Side Up?"
    assert metadata.author == "Loren Ridinger"
    assert metadata.publisher == "Post Hill Press"
    assert metadata.published_year == 2025
    assert metadata.isbn is None
    assert metadata.source_identifier == "urn:uuid:54eb2f5a-76d9-4b41-b742-483199aa625e"


def test_epub_text_extractor_includes_secondary_creator_when_ranked_close(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title id="maintitle">Good Energy</dc:title>
<dc:title id="subtitle">The Surprising Connection Between Metabolism and Limitless Health</dc:title>
<meta refines="#maintitle" property="title-type">main</meta>
<meta refines="#subtitle" property="title-type">subtitle</meta>
<dc:creator id="creator1">Casey Means, MD</dc:creator>
<meta refines="#creator1" property="role">aut</meta>
<meta refines="#creator1" property="display-seq">1</meta>
<dc:creator id="creator2">Calley Means</dc:creator>
<meta refines="#creator2" property="role">ive</meta>
<meta refines="#creator2" property="display-seq">2</meta>
<dc:publisher>Penguin Publishing Group</dc:publisher>
<dc:date>2024-05-14</dc:date>
<dc:identifier id="EbookISBN">9780593712665</dc:identifier>
""",
    )

    metadata, _ = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.author == "Casey Means, MD, Calley Means"


def test_epub_text_extractor_reorders_last_first_and_drops_noisy_publisher(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title>Things That Matter: Three Decades of Passions, Pastimes and Politics.epub</dc:title>
<dc:creator>Krauthammer, Charles</dc:creator>
<dc:publisher>chenjin5.com 万千书友聚集地</dc:publisher>
<dc:date>2013-10-21T18:30:00+00:00</dc:date>
<dc:identifier id="uuid_id">9f21bbd8-8f9e-42e4-933d-661e9623508b</dc:identifier>
""",
    )

    metadata, _ = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.author == "Charles Krauthammer"
    assert metadata.publisher is None


def test_epub_text_extractor_falls_back_to_imprint_publisher_with_fragmented_caps(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title>Atomic Habits: Tiny Changes, Remarkable Results</dc:title>
<dc:creator>James Clear [James Clear]</dc:creator>
<dc:publisher>chenjin5.com 万千书友聚集地</dc:publisher>
<dc:date>2018-10-16</dc:date>
<dc:identifier id="uuid_id">1b20ac53-08ed-40ec-9887-ad3f85944d88</dc:identifier>
""",
        body_title="copyright",
        body_text="AN IMPRINT OF P ENGUIN R AND OM H OUSE LLC 375 Hudson Street New York, New York 10014 Copyright © 2018 by James Clear Ebook ISBN 9780735211308",
    )

    metadata, _ = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.publisher == "Penguin Random House LLC"


def test_epub_text_extractor_falls_back_to_content_authors_publisher_and_isbn(tmp_path):
    epub_path = _write_epub_fixture(
        tmp_path,
        metadata_xml="""
<dc:title>The Phoenix Project : A Novel about IT, DevOps, and Helping Your Business Win \\( PDFDrive.com \\).epub</dc:title>
<dc:creator>Unknown</dc:creator>
<dc:date>2014-08-05T21:17:02+00:00</dc:date>
<dc:identifier id="uuid_id">71c48faa-e199-4507-8004-4c1c212a67e1</dc:identifier>
""",
        body_title="index",
        body_text="The Phoenix Project A Novel About IT, DevOps, and Helping Your Business Win Gene Kim, Kevin Behr & George Spafford © 2013 Gene Kim, Kevin Behr & George Spafford ISBN13: 978-0-9882625-0-8 IT Revolution Press Portland, Oregon",
    )

    metadata, _ = EpubTextExtractor().extract_metadata_and_chunks(epub_path)

    assert metadata.author == "Gene Kim, Kevin Behr, George Spafford"
    assert metadata.publisher == "IT Revolution Press"
    assert metadata.isbn == "9780988262508"
    assert metadata.source_identifier == "71c48faa-e199-4507-8004-4c1c212a67e1"


@pytest.mark.asyncio
async def test_create_word_list_from_entries_uses_import_source_id_without_lazy_relationship():
    user_id = uuid.uuid4()
    job_id = uuid.uuid4()
    import_source_id = uuid.uuid4()
    phrase_entry_id = uuid.uuid4()

    job = SimpleNamespace(
        id=job_id,
        import_source_id=import_source_id,
        word_list_id=None,
        created_count=0,
    )
    selected_entries = [EntryRef(entry_type="phrase", entry_id=phrase_entry_id)]

    import_source_result = MagicMock()
    import_source_result.scalar_one.return_value = ImportSource(
        id=import_source_id,
        source_type="epub",
        source_hash_sha256="a" * 64,
        pipeline_version="epub-import-v2",
        lexicon_version="learner-catalog-v1",
        status="completed",
    )
    source_entries_result = MagicMock()
    source_entries_result.scalars.return_value.all.return_value = [
        ImportSourceEntry(
            import_source_id=import_source_id,
            entry_type="phrase",
            entry_id=phrase_entry_id,
            frequency_count=3,
        )
    ]
    cache_presence_result = MagicMock()
    cache_presence_result.scalar_one_or_none.return_value = uuid.uuid4()

    db = AsyncMock()
    db.execute.side_effect = [import_source_result, cache_presence_result, source_entries_result]
    db.add = MagicMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    async def fake_flush():
        for added in db.add.call_args_list:
            obj = added.args[0]
            if obj.__class__.__name__ == "WordList" and getattr(obj, "id", None) is None:
                obj.id = uuid.uuid4()

    async def fake_refresh(obj):
        if obj.__class__.__name__ == "WordList":
            obj.created_at = datetime.now(timezone.utc)

    db.flush.side_effect = fake_flush
    db.refresh.side_effect = fake_refresh

    word_list = await create_word_list_from_entries(
        db,
        user_id=user_id,
        job=job,
        name="Runtime list",
        description="Created from reviewed entries",
        selected_entries=selected_entries,
    )

    assert word_list.source_type == "epub"
    assert word_list.source_reference == str(job_id)
    assert job.word_list_id == word_list.id
    assert job.created_count == 1
    assert db.execute.await_count == 3


@pytest.mark.asyncio
async def test_create_word_list_from_entries_rejects_unavailable_cache_without_rows():
    import_source_id = uuid.uuid4()
    entry_id = uuid.uuid4()
    job = SimpleNamespace(
        id=uuid.uuid4(),
        import_source_id=import_source_id,
        word_list_id=None,
        created_count=0,
    )

    import_source_result = MagicMock()
    import_source_result.scalar_one.return_value = ImportSource(
        id=import_source_id,
        source_type="epub",
        source_hash_sha256="a" * 64,
        pipeline_version="epub-import-v2",
        lexicon_version="learner-catalog-v1",
        status="completed",
    )
    source_entries_result = MagicMock()
    source_entries_result.scalars.return_value.all.return_value = []
    cache_presence_result = MagicMock()
    cache_presence_result.scalar_one_or_none.return_value = None

    db = AsyncMock()
    db.execute.side_effect = [import_source_result, cache_presence_result]

    with pytest.raises(ImportCacheDeletedError, match="cached import is no longer available"):
        await create_word_list_from_entries(
            db,
            user_id=uuid.uuid4(),
            job=job,
            name="Runtime list",
            description=None,
            selected_entries=[EntryRef(entry_type="word", entry_id=entry_id)],
        )


@pytest.mark.asyncio
async def test_get_or_create_import_source_keeps_deleted_source_tombstoned_until_regenerated():
    deleted_source = ImportSource(
        id=uuid.uuid4(),
        source_type="epub",
        source_hash_sha256="b" * 64,
        pipeline_version="epub-import-v2",
        lexicon_version="learner-catalog-v1",
        status="deleted",
        deleted_at=datetime.now(timezone.utc),
        matched_entry_count=123,
    )

    select_result_existing = MagicMock()
    select_result_existing.scalar_one_or_none.return_value = deleted_source

    db = AsyncMock()
    db.execute.return_value = select_result_existing
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    result = await get_or_create_import_source(
        db,
        source_type="epub",
        source_hash_sha256="b" * 64,
    )

    assert result is deleted_source
    assert result.deleted_at is not None
    assert result.status == "deleted"
    assert result.matched_entry_count == 123
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


def test_get_or_create_import_source_sync_keeps_deleted_source_tombstoned_until_regenerated():
    deleted_source = ImportSource(
        id=uuid.uuid4(),
        source_type="epub",
        source_hash_sha256="c" * 64,
        pipeline_version="epub-import-v2",
        lexicon_version="learner-catalog-v1",
        status="deleted",
        deleted_at=datetime.now(timezone.utc),
        matched_entry_count=55,
    )

    select_result_existing = MagicMock()
    select_result_existing.scalar_one_or_none.return_value = deleted_source

    db = MagicMock()
    db.execute.return_value = select_result_existing

    result = get_or_create_import_source_sync(
        db,
        source_type="epub",
        source_hash_sha256="c" * 64,
    )

    assert result is deleted_source
    assert result.deleted_at is not None
    assert result.status == "deleted"
    assert result.matched_entry_count == 55
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


@pytest.mark.asyncio
async def test_get_or_create_import_source_recovers_from_concurrent_insert_conflict():
    existing_source = ImportSource(
        id=uuid.uuid4(),
        source_type="epub",
        source_hash_sha256="b" * 64,
        pipeline_version="epub-import-v2",
        lexicon_version="learner-catalog-v1",
    )

    select_result_missing = MagicMock()
    select_result_missing.scalar_one_or_none.return_value = None
    select_result_existing = MagicMock()
    select_result_existing.scalar_one.return_value = existing_source

    db = AsyncMock()
    db.execute.side_effect = [select_result_missing, select_result_existing]
    db.add = MagicMock()
    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate key"))
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()

    result = await get_or_create_import_source(
        db,
        source_type="epub",
        source_hash_sha256="b" * 64,
    )

    assert result is existing_source
    db.rollback.assert_awaited_once()
    db.refresh.assert_not_awaited()


def test_get_or_create_import_source_sync_recovers_from_concurrent_insert_conflict():
    existing_source = ImportSource(
        id=uuid.uuid4(),
        source_type="epub",
        source_hash_sha256="c" * 64,
        pipeline_version="epub-import-v2",
        lexicon_version="learner-catalog-v1",
    )

    select_result_missing = MagicMock()
    select_result_missing.scalar_one_or_none.return_value = None
    select_result_existing = MagicMock()
    select_result_existing.scalar_one.return_value = existing_source

    db = MagicMock()
    db.execute.side_effect = [select_result_missing, select_result_existing]
    db.commit.side_effect = IntegrityError("insert", {}, Exception("duplicate key"))

    result = get_or_create_import_source_sync(
        db,
        source_type="epub",
        source_hash_sha256="c" * 64,
    )

    assert result is existing_source
    db.rollback.assert_called_once()
    db.refresh.assert_not_called()
