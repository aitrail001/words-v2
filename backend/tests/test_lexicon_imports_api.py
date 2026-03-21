import json
import uuid
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


def make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="import-admin@example.com", password_hash="hashed", role=role)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _compiled_rows() -> list[dict]:
    return [
        {
            "schema_version": "1.1.0",
            "entry_id": "word:bank",
            "entry_type": "word",
            "normalized_form": "bank",
            "source_provenance": [{"source": "snapshot"}],
            "entity_category": "general",
            "word": "bank",
            "part_of_speech": ["noun"],
            "cefr_level": "B1",
            "frequency_rank": 100,
            "forms": {"plural_forms": ["banks"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [
                {
                    "sense_id": "sense-bank-1",
                    "definition": "a financial institution",
                    "examples": [{"sentence": "She went to the bank.", "difficulty": "easy"}],
                    "translations": {},
                }
            ],
            "confusable_words": [],
            "generated_at": "2026-03-21T00:00:00Z",
        }
    ]


class TestLexiconImportsApi:
    @pytest.mark.asyncio
    async def test_dry_run_summarizes_compiled_rows(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())

        response = await client.post(
            "/api/lexicon-imports/dry-run",
            headers={"Authorization": f"Bearer {token}"},
            json={"input_path": str(compiled_path), "source_type": "lexicon_snapshot"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert data["row_summary"]["row_count"] == 1
        assert data["row_summary"]["word_count"] == 1

    @pytest.mark.asyncio
    async def test_run_import_executes_import_file(self, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())
        monkeypatch.setattr(
            "app.api.lexicon_imports.run_import_file",
            lambda *args, **kwargs: {"created_words": 1, "updated_words": 0},
        )

        response = await client.post(
            "/api/lexicon-imports/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"input_path": str(compiled_path), "source_type": "lexicon_snapshot"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert "import_summary" in data

    @pytest.mark.asyncio
    async def test_import_rejects_paths_outside_allowed_roots(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        response = await client.post(
            "/api/lexicon-imports/dry-run",
            headers={"Authorization": f"Bearer {token}"},
            json={"input_path": "/tmp/not-allowed/words.enriched.jsonl", "source_type": "lexicon_snapshot"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Path must stay within the allowed roots"
