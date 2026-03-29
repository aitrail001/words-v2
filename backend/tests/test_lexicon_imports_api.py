import json
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.user import User
from app.services import lexicon_import_jobs


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
                    "examples": [{"sentence": "She went to the bank.", "difficulty": "A1"}],
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
            json={
                "input_path": str(compiled_path),
                "source_type": "lexicon_snapshot",
                "conflict_mode": "skip",
                "error_mode": "continue",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert data["row_summary"]["row_count"] == 1
        assert data["row_summary"]["word_count"] == 1
        assert data["import_summary"]["dry_run"] == 1

    @pytest.mark.asyncio
    async def test_dry_run_surfaces_preflight_error_samples(self, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "phrases.approved.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())

        def fake_run_import_file(*args, error_samples_sink=None, **kwargs):
            if error_samples_sink is not None:
                error_samples_sink.append({"entry": "fuss over", "error": "usage_note must be a non-empty string"})
            return {"dry_run": True, "failed_rows": 1, "row_count": 1}

        monkeypatch.setattr("app.api.lexicon_imports._import_db_module", lambda: SimpleNamespace(
            load_compiled_rows=lambda path: _compiled_rows(),
            summarize_compiled_rows=lambda rows: {
                "row_count": len(rows),
                "word_count": len(rows),
                "phrase_count": 0,
                "reference_count": 0,
            },
            run_import_file=fake_run_import_file,
        ))

        response = await client.post(
            "/api/lexicon-imports/dry-run",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "input_path": str(compiled_path),
                "source_type": "lexicon_snapshot",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["import_summary"]["dry_run"] == 1
        assert data["import_summary"]["failed_rows"] == 1
        assert data["error_samples"] == [{"entry": "fuss over", "error": "usage_note must be a non-empty string"}]

    @pytest.mark.asyncio
    async def test_run_import_executes_import_file_as_background_job(self, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())

        def run_inline(target, *, name):
            target()

        monkeypatch.setattr(lexicon_import_jobs, "_start_job_thread", run_inline)
        monkeypatch.setattr("app.api.lexicon_imports._import_db_module", lambda: SimpleNamespace(
            load_compiled_rows=lambda path: _compiled_rows(),
            summarize_compiled_rows=lambda rows: {
                "row_count": len(rows),
                "word_count": len(rows),
                "phrase_count": 0,
                "reference_count": 0,
            },
            run_import_file=lambda *args, **kwargs: {"created_words": 1, "updated_words": 0},
        ))

        response = await client.post(
            "/api/lexicon-imports/run",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "input_path": str(compiled_path),
                "source_type": "lexicon_snapshot",
                "conflict_mode": "upsert",
                "error_mode": "continue",
            },
        )

        assert response.status_code == 202
        data = response.json()
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert data["status"] == "completed"
        assert data["completed_rows"] == 1
        assert data["remaining_rows"] == 0
        assert data["import_summary"]["created_words"] == 1
        assert data["conflict_mode"] == "upsert"
        assert data["error_mode"] == "continue"

        status_response = await client.get(
            f"/api/lexicon-imports/jobs/{data['id']}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "completed"

    @pytest.mark.asyncio
    async def test_run_import_job_reports_progress(self, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        rows = _compiled_rows() + [
            {
                **_compiled_rows()[0],
                "entry_id": "word:river-bank",
                "word": "river bank",
            }
        ]
        _write_jsonl(compiled_path, rows)

        def run_inline(target, *, name):
            target()

        def fake_run_import_file(path, *, rows, progress_callback=None, **kwargs):
            assert len(rows) == 2
            if progress_callback is not None:
                progress_callback(row=rows[0], completed_rows=1, total_rows=2)
                progress_callback(row=rows[1], completed_rows=2, total_rows=2)
            return {"created_words": 2, "updated_words": 0}

        monkeypatch.setattr(lexicon_import_jobs, "_start_job_thread", run_inline)
        monkeypatch.setattr("app.api.lexicon_imports._import_db_module", lambda: SimpleNamespace(
            load_compiled_rows=lambda path: rows,
            summarize_compiled_rows=lambda loaded_rows: {
                "row_count": len(loaded_rows),
                "word_count": len(loaded_rows),
                "phrase_count": 0,
                "reference_count": 0,
            },
            run_import_file=fake_run_import_file,
        ))

        response = await client.post(
            "/api/lexicon-imports/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"input_path": str(compiled_path), "source_type": "lexicon_snapshot"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["total_rows"] == 2
        assert data["completed_rows"] == 2
        assert data["current_entry"] == "river bank"

    @pytest.mark.asyncio
    async def test_run_import_job_fails_before_write_when_preflight_fails(self, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "phrases.approved.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())

        def run_inline(target, *, name):
            target()

        def fake_run_import_file(*args, **kwargs):
            raise RuntimeError("fuss over: sense 1 translations.zh-Hans.usage_note must be a non-empty string")

        monkeypatch.setattr(lexicon_import_jobs, "_start_job_thread", run_inline)
        monkeypatch.setattr("app.api.lexicon_imports._import_db_module", lambda: SimpleNamespace(
            load_compiled_rows=lambda path: _compiled_rows(),
            summarize_compiled_rows=lambda loaded_rows: {
                "row_count": len(loaded_rows),
                "word_count": len(loaded_rows),
                "phrase_count": 0,
                "reference_count": 0,
            },
            run_import_file=fake_run_import_file,
        ))

        response = await client.post(
            "/api/lexicon-imports/run",
            headers={"Authorization": f"Bearer {token}"},
            json={"input_path": str(compiled_path), "source_type": "lexicon_snapshot"},
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "failed"
        assert data["completed_rows"] == 0
        assert data["current_entry"] == "Failed before first row"
        assert "usage_note" in data["error_message"]

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
