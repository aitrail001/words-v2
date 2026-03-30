from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid
import json

from tools.lexicon.tests.test_voice_generate import FakeSynthProvider
from tools.lexicon.voice_generate import run_voice_generation
from tools.lexicon.voice_import_db import (
    _find_or_create_storage_policy,
    group_voice_manifest_rows,
    import_voice_manifest_rows,
    run_voice_import_file,
)


def _phrase_manifest_row(*, content_scope: str, source_text: str, sense_id: str = "take_off.v.01", example_index: int | None = None) -> dict[str, object]:
    return {
        "status": "generated",
        "entry_type": "phrase",
        "entry_id": "phrase_take_off",
        "word": "take off",
        "language": "en",
        "source_reference": "phrases-001",
        "content_scope": content_scope,
        "sense_id": sense_id,
        "meaning_index": 0 if content_scope != "word" else None,
        "example_index": example_index,
        "source_text": source_text,
        "locale": "en-US",
        "voice_role": "female",
        "provider": "google",
        "family": "neural2",
        "voice_id": "en-US-Neural2-C",
        "profile_key": "word" if content_scope == "word" else content_scope,
        "audio_format": "mp3",
        "mime_type": "audio/mpeg",
        "storage_kind": "local",
        "storage_base": "/tmp/voice",
        "relative_path": f"phrase_take_off/{content_scope}/en_us/example.mp3",
        "source_text_hash": f"hash-{content_scope}",
    }


def _word_manifest_row(
    *,
    word: str,
    entry_id: str,
    source_reference: str,
    content_scope: str,
    source_text: str,
    relative_path: str,
    source_text_hash: str,
    example_index: int | None = None,
) -> dict[str, object]:
    row = _phrase_manifest_row(
        content_scope=content_scope,
        source_text=source_text,
        sense_id=f"{word}.n.01",
        example_index=example_index,
    )
    row.update({
        "entry_type": "word",
        "entry_id": entry_id,
        "word": word,
        "source_reference": source_reference,
        "meaning_index": 0 if content_scope != "word" else None,
        "profile_key": content_scope,
        "relative_path": relative_path,
        "source_text_hash": source_text_hash,
    })
    return row


def test_import_voice_manifest_rows_creates_phrase_entry_asset():
    session = MagicMock()
    phrase_entry = SimpleNamespace(id=uuid.uuid4())
    storage_policy = SimpleNamespace(id=uuid.uuid4())

    with patch("tools.lexicon.voice_import_db._find_word", return_value=None), \
         patch("tools.lexicon.voice_import_db._find_phrase_entry", return_value=phrase_entry), \
         patch("tools.lexicon.voice_import_db._find_phrase_sense") as mocked_sense, \
         patch("tools.lexicon.voice_import_db._find_phrase_example") as mocked_example, \
         patch("tools.lexicon.voice_import_db._find_voice_asset", return_value=None), \
         patch("tools.lexicon.voice_import_db._find_or_create_storage_policy", return_value=storage_policy):
        summary = import_voice_manifest_rows(session, [_phrase_manifest_row(content_scope="word", source_text="take off")])

    assert summary.created_assets == 1
    mocked_sense.assert_not_called()
    mocked_example.assert_not_called()
    created_asset = session.add.call_args.args[0]
    assert created_asset.phrase_entry_id == phrase_entry.id
    assert created_asset.word_id is None
    assert created_asset.content_scope == "word"


def test_import_voice_manifest_rows_creates_phrase_sense_and_example_assets():
    session = MagicMock()
    phrase_entry = SimpleNamespace(id=uuid.uuid4())
    phrase_sense = SimpleNamespace(id=uuid.uuid4())
    phrase_example = SimpleNamespace(id=uuid.uuid4())
    storage_policy = SimpleNamespace(id=uuid.uuid4())

    with patch("tools.lexicon.voice_import_db._find_word", return_value=None), \
         patch("tools.lexicon.voice_import_db._find_phrase_entry", return_value=phrase_entry), \
         patch("tools.lexicon.voice_import_db._find_phrase_sense", return_value=phrase_sense), \
         patch("tools.lexicon.voice_import_db._find_phrase_example", return_value=phrase_example), \
         patch("tools.lexicon.voice_import_db._find_voice_asset", return_value=None), \
         patch("tools.lexicon.voice_import_db._find_or_create_storage_policy", return_value=storage_policy):
        summary = import_voice_manifest_rows(
            session,
            [
                _phrase_manifest_row(content_scope="definition", source_text="to depart"),
                _phrase_manifest_row(content_scope="example", source_text="The plane will take off.", example_index=0),
            ],
        )

    assert summary.created_assets == 2
    created_definition_asset = session.add.call_args_list[0].args[0]
    created_example_asset = session.add.call_args_list[1].args[0]
    assert created_definition_asset.phrase_sense_id == phrase_sense.id
    assert created_definition_asset.meaning_id is None
    assert created_example_asset.phrase_sense_example_id == phrase_example.id
    assert created_example_asset.meaning_example_id is None


def test_run_voice_generation_manifest_preserves_phrase_entry_type():
    approved_jsonl = """{"entry_id":"phrase_take_off","entry_type":"phrase","word":"take off","language":"en","source_reference":"phrases-001","senses":[{"sense_id":"take_off.v.01","definition":"to depart","examples":[{"sentence":"The plane will take off."}]}]}\n"""
    with TemporaryDirectory() as tmpdir:
        input_path = Path(tmpdir) / "approved.jsonl"
        output_dir = Path(tmpdir) / "voice"
        input_path.write_text(approved_jsonl, encoding="utf-8")

        summary = run_voice_generation(
            input_path=input_path,
            output_dir=output_dir,
            locales=["en-US"],
            max_concurrency=1,
            synth_provider=FakeSynthProvider(),
        )

        assert summary["generated_count"] == 6
        manifest_lines = (output_dir / "voice_manifest.jsonl").read_text(encoding="utf-8").strip().splitlines()
        assert manifest_lines
        assert all('"entry_type": "phrase"' in line for line in manifest_lines)


def test_import_voice_manifest_rows_skip_existing_honors_conflict_mode_skip():
    session = MagicMock()
    existing_asset = SimpleNamespace(id=uuid.uuid4())

    with patch("tools.lexicon.voice_import_db._find_word", return_value=SimpleNamespace(id=uuid.uuid4())), \
         patch("tools.lexicon.voice_import_db._find_voice_asset", return_value=existing_asset):
        summary = import_voice_manifest_rows(
            session,
            [_phrase_manifest_row(content_scope="word", source_text="take off", sense_id="") | {"entry_type": "word"}],
            conflict_mode="skip",
        )

    assert summary.skipped_rows == 1
    session.add.assert_not_called()


def test_group_voice_manifest_rows_orders_word_then_definition_then_example() -> None:
    rows = [
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="example",
            source_text="She went to the bank.",
            example_index=0,
            relative_path="bank/example/en_us/example.mp3",
            source_text_hash="hash-example-1",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="word",
            source_text="bank",
            relative_path="bank/word/en_us/example.mp3",
            source_text_hash="hash-word",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="definition",
            source_text="a financial institution",
            relative_path="bank/definition/en_us/example.mp3",
            source_text_hash="hash-definition",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="example",
            source_text="The river overflowed the bank.",
            example_index=1,
            relative_path="bank/example/en_us/example-2.mp3",
            source_text_hash="hash-example-2",
        ),
    ]

    groups = group_voice_manifest_rows(rows)

    assert len(groups) == 1
    assert [row["content_scope"] for row in groups[0].rows] == ["word", "definition", "example", "example"]
    assert [row["source_text"] for row in groups[0].rows[-2:]] == [
        "She went to the bank.",
        "The river overflowed the bank.",
    ]


def test_group_voice_manifest_rows_preserves_first_seen_group_order() -> None:
    rows = [
        _word_manifest_row(
            word="zebra",
            entry_id="word_zebra",
            source_reference="words-001",
            content_scope="word",
            source_text="zebra",
            relative_path="zebra/word/en_us/example.mp3",
            source_text_hash="hash-zebra-word",
        ),
        _word_manifest_row(
            word="apple",
            entry_id="word_apple",
            source_reference="words-002",
            content_scope="word",
            source_text="apple",
            relative_path="apple/word/en_us/example.mp3",
            source_text_hash="hash-apple-word",
        ),
        _word_manifest_row(
            word="zebra",
            entry_id="word_zebra",
            source_reference="words-001",
            content_scope="definition",
            source_text="a striped animal",
            relative_path="zebra/definition/en_us/example.mp3",
            source_text_hash="hash-zebra-definition",
        ),
    ]

    groups = group_voice_manifest_rows(rows)

    assert [(group.lexical_text, group.language) for group in groups] == [("zebra", "en"), ("apple", "en")]


def test_run_voice_import_file_groups_manifest_rows_by_lexical_scope_before_importing(tmp_path: Path):
    manifest_rows = [
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="example",
            source_text="She went to the bank.",
            example_index=0,
            relative_path="bank/example/en_us/example.mp3",
            source_text_hash="hash-example",
        ),
        _word_manifest_row(
            word="harbor",
            entry_id="word_harbor",
            source_reference="words-002",
            content_scope="definition",
            source_text="a sheltered place",
            relative_path="harbor/definition/en_us/example.mp3",
            source_text_hash="hash-harbor-definition",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="definition",
            source_text="a financial institution",
            relative_path="bank/definition/en_us/example.mp3",
            source_text_hash="hash-definition",
        ),
        _word_manifest_row(
            word="harbor",
            entry_id="word_harbor",
            source_reference="words-002",
            content_scope="word",
            source_text="harbor",
            relative_path="harbor/word/en_us/example.mp3",
            source_text_hash="hash-harbor-word",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="word",
            source_text="bank",
            relative_path="bank/word/en_us/example.mp3",
            source_text_hash="hash-word",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="example",
            source_text="She went to the bank.",
            example_index=0,
            relative_path="bank/example/en_us/example.mp3",
            source_text_hash="hash-example",
        ),
    ]
    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = None
    imported_groups: list[list[str]] = []

    def fake_import_group(_session, rows, **kwargs):
        imported_groups.append([row["content_scope"] for row in rows])
        return SimpleNamespace(created_assets=len(rows), updated_assets=0, skipped_rows=0, missing_words=0, missing_meanings=0, missing_examples=0, failed_rows=0)

    with patch("tools.lexicon.voice_import_db._ensure_backend_path"), \
         patch("tools.lexicon.voice_import_db.create_engine"), \
         patch("tools.lexicon.voice_import_db.Session", return_value=session_cm), \
         patch("tools.lexicon.voice_import_db.get_settings", return_value=SimpleNamespace(database_url_sync="postgresql://test")), \
         patch("tools.lexicon.voice_import_db.import_voice_manifest_group", side_effect=fake_import_group):
        run_voice_import_file(tmp_path / "voice_manifest.jsonl", rows=manifest_rows)

    assert imported_groups == [["word", "definition", "example", "example"], ["word", "definition"]]


def test_run_voice_import_file_continue_mode_commits_partial_group_success(tmp_path: Path):
    manifest_rows = [
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="definition",
            source_text="a financial institution",
            relative_path="bank/definition/en_us/example.mp3",
            source_text_hash="hash-definition",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="word",
            source_text="bank",
            relative_path="bank/word/en_us/example.mp3",
            source_text_hash="hash-word",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="example",
            source_text="She went to the bank.",
            example_index=0,
            relative_path="bank/example/en_us/example.mp3",
            source_text_hash="hash-example",
        ),
        _word_manifest_row(
            word="harbor",
            entry_id="word_harbor",
            source_reference="words-002",
            content_scope="word",
            source_text="harbor",
            relative_path="harbor/word/en_us/example.mp3",
            source_text_hash="hash-harbor-word",
        ),
    ]
    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = None
    imported_groups: list[list[str]] = []

    def fake_import_group(_session, rows, **kwargs):
        imported_groups.append([row["content_scope"] for row in rows])
        if len(rows) == 3:
            return SimpleNamespace(created_assets=2, updated_assets=0, skipped_rows=0, missing_words=0, missing_meanings=1, missing_examples=0, failed_rows=1)
        return SimpleNamespace(created_assets=1, updated_assets=0, skipped_rows=0, missing_words=0, missing_meanings=0, missing_examples=0, failed_rows=0)

    with patch("tools.lexicon.voice_import_db._ensure_backend_path"), \
         patch("tools.lexicon.voice_import_db.create_engine"), \
         patch("tools.lexicon.voice_import_db.Session", return_value=session_cm), \
         patch("tools.lexicon.voice_import_db.get_settings", return_value=SimpleNamespace(database_url_sync="postgresql://test")), \
         patch("tools.lexicon.voice_import_db.import_voice_manifest_group", side_effect=fake_import_group):
        summary = run_voice_import_file(tmp_path / "voice_manifest.jsonl", rows=manifest_rows, error_mode="continue")

    assert imported_groups == [["word", "definition", "example"], ["word"]]
    assert summary["created_assets"] == 3
    assert summary["failed_rows"] == 1
    assert session.commit.call_count == 2
    session.rollback.assert_not_called()


def test_run_voice_import_file_fail_fast_rolls_back_only_current_group(tmp_path: Path):
    manifest_rows = [
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="definition",
            source_text="a financial institution",
            relative_path="bank/definition/en_us/example.mp3",
            source_text_hash="hash-definition",
        ),
        _word_manifest_row(
            word="bank",
            entry_id="word_bank",
            source_reference="words-001",
            content_scope="word",
            source_text="bank",
            relative_path="bank/word/en_us/example.mp3",
            source_text_hash="hash-word",
        ),
        _word_manifest_row(
            word="harbor",
            entry_id="word_harbor",
            source_reference="words-002",
            content_scope="word",
            source_text="harbor",
            relative_path="harbor/word/en_us/example.mp3",
            source_text_hash="hash-harbor-word",
        ),
    ]
    bank_session = MagicMock()
    bank_cm = MagicMock()
    bank_cm.__enter__.return_value = bank_session
    bank_cm.__exit__.return_value = None
    harbor_session = MagicMock()
    harbor_cm = MagicMock()
    harbor_cm.__enter__.return_value = harbor_session
    harbor_cm.__exit__.return_value = None
    imported_groups: list[list[str]] = []

    def fake_import_group(_session, rows, **kwargs):
        imported_groups.append([row["content_scope"] for row in rows])
        if rows[0]["word"] == "harbor":
            raise RuntimeError("duplicate voice asset")
        return SimpleNamespace(
            created_assets=len(rows),
            updated_assets=0,
            skipped_rows=0,
            missing_words=0,
            missing_meanings=0,
            missing_examples=0,
            failed_rows=0,
        )

    with patch("tools.lexicon.voice_import_db._ensure_backend_path"), \
         patch("tools.lexicon.voice_import_db.create_engine"), \
         patch("tools.lexicon.voice_import_db.Session", side_effect=[bank_cm, harbor_cm]), \
         patch("tools.lexicon.voice_import_db.get_settings", return_value=SimpleNamespace(database_url_sync="postgresql://test")), \
         patch("tools.lexicon.voice_import_db.import_voice_manifest_group", side_effect=fake_import_group):
        try:
            run_voice_import_file(tmp_path / "voice_manifest.jsonl", rows=manifest_rows, error_mode="fail_fast")
        except RuntimeError as exc:
            assert str(exc) == "duplicate voice asset"
        else:
            raise AssertionError("run_voice_import_file should raise in fail_fast mode")

    assert imported_groups == [["word", "definition"], ["word"]]
    bank_session.commit.assert_called_once()
    bank_session.rollback.assert_not_called()
    harbor_session.rollback.assert_called_once()
    harbor_session.commit.assert_not_called()


def test_run_voice_import_file_fail_fast_stops_on_first_manifest_group(tmp_path: Path):
    manifest_rows = [
        _word_manifest_row(
            word="zebra",
            entry_id="word_zebra",
            source_reference="words-001",
            content_scope="word",
            source_text="zebra",
            relative_path="zebra/word/en_us/example.mp3",
            source_text_hash="hash-zebra-word",
        ),
        _word_manifest_row(
            word="apple",
            entry_id="word_apple",
            source_reference="words-002",
            content_scope="word",
            source_text="apple",
            relative_path="apple/word/en_us/example.mp3",
            source_text_hash="hash-apple-word",
        ),
    ]
    zebra_session = MagicMock()
    zebra_cm = MagicMock()
    zebra_cm.__enter__.return_value = zebra_session
    zebra_cm.__exit__.return_value = None
    imported_groups: list[str] = []

    def fake_import_group(_session, rows, **kwargs):
        imported_groups.append(str(rows[0]["word"]))
        raise RuntimeError("duplicate voice asset")

    with patch("tools.lexicon.voice_import_db._ensure_backend_path"), \
         patch("tools.lexicon.voice_import_db.create_engine"), \
         patch("tools.lexicon.voice_import_db.Session", side_effect=[zebra_cm]), \
         patch("tools.lexicon.voice_import_db.get_settings", return_value=SimpleNamespace(database_url_sync="postgresql://test")), \
         patch("tools.lexicon.voice_import_db.import_voice_manifest_group", side_effect=fake_import_group):
        try:
            run_voice_import_file(tmp_path / "voice_manifest.jsonl", rows=manifest_rows, error_mode="fail_fast")
        except RuntimeError as exc:
            assert str(exc) == "duplicate voice asset"
        else:
            raise AssertionError("run_voice_import_file should raise in fail_fast mode")

    assert imported_groups == ["zebra"]
    zebra_session.rollback.assert_called_once()


def test_find_or_create_storage_policy_creates_missing_default_policy():
    _ = _find_or_create_storage_policy
    session = MagicMock()
    session.execute.return_value.scalar_one_or_none.return_value = None

    from tools.lexicon.import_db import _ensure_backend_path

    _ensure_backend_path()
    from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy

    policy = _find_or_create_storage_policy(
        session,
        LexiconVoiceStoragePolicy,
        source_reference="words-001",
        content_scope="definition",
        provider="google",
        family="neural2",
        locale="en-US",
        primary_storage_kind="local",
        primary_storage_base="/tmp/voice",
    )

    assert policy.policy_key == "definition_default"
    assert policy.source_reference == "global"
    assert policy.provider == "default"
    assert policy.family == "default"
    assert policy.locale == "all"
    assert policy.primary_storage_kind == "local"
    assert policy.primary_storage_base == "/tmp/voice"
    session.add.assert_called_once_with(policy)
    session.flush.assert_called_once()


def test_import_voice_manifest_rows_updates_relative_path_without_touching_storage_policy_rows():
    session = MagicMock()
    original_storage_policy_id = uuid.uuid4()
    existing_asset = SimpleNamespace(
        id=uuid.uuid4(),
        storage_policy_id=original_storage_policy_id,
        relative_path="old/path.mp3",
        mime_type="audio/mpeg",
        status="generated",
    )
    row = _word_manifest_row(
        word="bank",
        entry_id="word_bank",
        source_reference="words-001",
        content_scope="word",
        source_text="bank",
        relative_path="new/path.mp3",
        source_text_hash="hash-word",
    )

    with patch("tools.lexicon.voice_import_db._find_word", return_value=SimpleNamespace(id=uuid.uuid4())), \
         patch("tools.lexicon.voice_import_db._find_voice_asset", return_value=existing_asset):
        summary = import_voice_manifest_rows(session, [row], conflict_mode="upsert")

    assert summary.updated_assets == 1
    assert existing_asset.storage_policy_id == original_storage_policy_id
    assert existing_asset.relative_path == "new/path.mp3"


def test_run_voice_import_file_dry_run_reports_failed_rows_without_writing(tmp_path: Path):
    manifest_path = tmp_path / "voice_manifest.jsonl"
    manifest_path.write_text(
        '{"status":"generated","entry_type":"word","entry_id":"word_bank","word":"bank","language":"en","content_scope":"word","source_text":"bank","locale":"en-US","voice_role":"female","provider":"google","family":"neural2","voice_id":"en-US-Neural2-C","profile_key":"word","audio_format":"mp3","storage_kind":"local","storage_base":"/tmp/voice","relative_path":"bank.mp3","source_text_hash":"hash"}\n',
        encoding="utf-8",
    )

    with patch("tools.lexicon.voice_import_db._ensure_backend_path"), \
         patch("tools.lexicon.voice_import_db.load_voice_manifest_rows", return_value=[json.loads(manifest_path.read_text(encoding='utf-8').strip())]), \
         patch("tools.lexicon.voice_import_db._dry_run_voice_manifest_rows", return_value={"row_count": 1, "failed_rows": 1, "skipped_rows": 0, "dry_run": True}):
        summary = run_voice_import_file(manifest_path, dry_run=True)

    assert summary["dry_run"] is True
    assert summary["failed_rows"] == 1


def test_run_voice_import_file_continue_mode_reports_row_level_failures(tmp_path: Path):
    manifest_rows = [
        {"status": "generated", "entry_type": "word", "entry_id": "word_bank", "word": "bank", "language": "en", "content_scope": "word", "source_text": "bank", "locale": "en-US", "voice_role": "female", "provider": "google", "family": "neural2", "voice_id": "en-US-Neural2-C", "profile_key": "word", "audio_format": "mp3", "storage_kind": "local", "storage_base": "/tmp/voice", "relative_path": "bank.mp3", "source_text_hash": "hash-1"},
        {"status": "generated", "entry_type": "word", "entry_id": "word_harbor", "word": "harbor", "language": "en", "content_scope": "word", "source_text": "harbor", "locale": "en-US", "voice_role": "female", "provider": "google", "family": "neural2", "voice_id": "en-US-Neural2-C", "profile_key": "word", "audio_format": "mp3", "storage_kind": "local", "storage_base": "/tmp/voice", "relative_path": "harbor.mp3", "source_text_hash": "hash-2"},
    ]
    manifest_path = tmp_path / "voice_manifest.jsonl"
    manifest_path.write_text("".join(f"{__import__('json').dumps(row)}\n" for row in manifest_rows), encoding="utf-8")

    session = MagicMock()
    session_cm = MagicMock()
    session_cm.__enter__.return_value = session
    session_cm.__exit__.return_value = None

    calls: list[str] = []

    def fake_import_rows(_session, rows, **kwargs):
        calls.append(rows[0]["entry_id"])
        if rows[0]["entry_id"] == "word_bank":
            raise RuntimeError("duplicate voice asset")
        return SimpleNamespace(created_assets=1, updated_assets=0, skipped_rows=0, missing_words=0, missing_meanings=0, missing_examples=0, failed_rows=0)

    with patch("tools.lexicon.voice_import_db._ensure_backend_path"), \
         patch("tools.lexicon.voice_import_db.load_voice_manifest_rows", return_value=manifest_rows), \
         patch("tools.lexicon.voice_import_db.create_engine"), \
         patch("tools.lexicon.voice_import_db.Session", return_value=session_cm), \
         patch("tools.lexicon.voice_import_db.get_settings", return_value=SimpleNamespace(database_url_sync="postgresql://test")), \
         patch("tools.lexicon.voice_import_db.import_voice_manifest_rows", side_effect=fake_import_rows):
        summary = run_voice_import_file(manifest_path, error_mode="continue")

    assert calls == ["word_bank", "word_harbor"]
    assert summary["created_assets"] == 1
    assert summary["failed_rows"] == 1
