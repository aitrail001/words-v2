from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import uuid

from tools.lexicon.voice_import_db import import_voice_manifest_rows


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
