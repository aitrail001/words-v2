import uuid
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
    EntryRef,
    ImportMatcher,
    build_import_cache_key,
    create_word_list_from_entries,
    deterministic_lemmatize,
    get_or_create_import_source,
    get_or_create_import_source_sync,
    normalize_matching_text,
    parse_bulk_entry_text,
    sha256_digest_from_bytes,
)


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
    assert parse_bulk_entry_text("run walk swim") == ["run", "walk", "swim"]


def test_normalization_and_deterministic_lemmatizer_are_stable():
    assert normalize_matching_text(" On\u2014The   Other\u2019Hand ") == "on-the other'hand"
    assert deterministic_lemmatize("apples") == "apple"


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

    db = AsyncMock()
    db.execute.side_effect = [import_source_result, source_entries_result]
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
    assert db.execute.await_count == 2


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
