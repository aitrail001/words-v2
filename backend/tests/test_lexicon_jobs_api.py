import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_job import LexiconJob
from app.models.user import User


def make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="lexicon-admin@example.com", password_hash="hashed", role=role)


def _result_with(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


class TestLexiconJobsApi:
    @pytest.mark.asyncio
    @patch("app.api.lexicon_jobs.run_lexicon_import_db.delay")
    async def test_create_import_db_job(self, mock_delay, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(None)]
        mock_db.flush = pytest.importorskip("unittest.mock").AsyncMock()

        async def fake_refresh(job):
            job.id = uuid.uuid4()

        mock_db.refresh = pytest.importorskip("unittest.mock").AsyncMock(side_effect=fake_refresh)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "approved.jsonl"
        compiled_path.write_text('{"entry_id":"word:bank","entry_type":"word","word":"bank"}\n', encoding="utf-8")
        monkeypatch.setattr("app.api.lexicon_jobs._import_db_module", lambda: SimpleNamespace(
            load_compiled_rows=lambda path: [{"entry_id": "word:bank", "entry_type": "word", "word": "bank"}],
            summarize_compiled_rows=lambda rows: {"row_count": 1, "word_count": 1, "phrase_count": 0, "reference_count": 0},
        ))

        response = await client.post(
            "/api/lexicon-jobs/import-db",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "input_path": str(compiled_path),
                "source_type": "lexicon_snapshot",
                "source_reference": "demo",
                "language": "en",
                "conflict_mode": "upsert",
                "error_mode": "continue",
            },
        )

        assert response.status_code == 202
        assert response.json()["job_type"] == "import_db"
        assert response.json()["request_payload"]["conflict_mode"] == "upsert"
        assert response.json()["request_payload"]["error_mode"] == "continue"
        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    @patch("app.api.lexicon_jobs.run_lexicon_voice_import_db.delay")
    async def test_create_voice_import_db_job(self, mock_delay, client, mock_db, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(None)]
        mock_db.flush = pytest.importorskip("unittest.mock").AsyncMock()

        async def fake_refresh(job):
            job.id = uuid.uuid4()

        mock_db.refresh = pytest.importorskip("unittest.mock").AsyncMock(side_effect=fake_refresh)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        manifest_path = tmp_path / "voice_manifest.jsonl"
        manifest_path.write_text('{"status":"generated","entry_type":"word","entry_id":"word:bank","word":"bank"}\n', encoding="utf-8")
        monkeypatch.setattr("app.api.lexicon_jobs._voice_import_db_module", lambda: SimpleNamespace(
            load_voice_manifest_rows=lambda path: [{"status": "generated", "entry_type": "word", "entry_id": "word:bank", "word": "bank"}],
            summarize_voice_manifest_rows=lambda rows: {"row_count": 1, "generated_count": 1, "existing_count": 0, "failed_count": 0},
        ))

        response = await client.post(
            "/api/lexicon-jobs/voice-import-db",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "input_path": str(manifest_path),
                "source_type": "voice_manifest",
                "language": "en",
                "conflict_mode": "skip",
                "error_mode": "continue",
            },
        )

        assert response.status_code == 202
        assert response.json()["job_type"] == "voice_import_db"
        assert response.json()["request_payload"]["conflict_mode"] == "skip"
        assert response.json()["request_payload"]["row_summary"]["generated_count"] == 1
        mock_delay.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_voice_import_db_job_rejects_directory_input(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.side_effect = [_result_with(make_user(user_id))]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        manifest_dir = tmp_path / "voice-run-dir"
        manifest_dir.mkdir()

        response = await client.post(
            "/api/lexicon-jobs/voice-import-db",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "input_path": str(manifest_dir),
                "source_type": "voice_manifest",
                "language": "en",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Voice import input must be a .jsonl file, not a directory"

    @pytest.mark.asyncio
    @patch("app.api.lexicon_jobs.run_lexicon_jsonl_materialize.delay")
    async def test_create_jsonl_materialize_reuses_active_job(self, mock_delay, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        existing = LexiconJob(
            id=uuid.uuid4(),
            created_by=user_id,
            job_type="jsonl_materialize",
            status="running",
            target_key=f"jsonl_materialize:{tmp_path / 'reviewed'}",
            request_payload={"output_dir": str(tmp_path / "reviewed")},
        )
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(existing)]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        artifact_path = tmp_path / "words.enriched.jsonl"
        artifact_path.write_text('{"entry_id":"word:bank","entry_type":"word","word":"bank"}\n', encoding="utf-8")

        response = await client.post(
            "/api/lexicon-jobs/jsonl-materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "artifact_path": str(artifact_path),
                "output_dir": str(tmp_path / "reviewed"),
            },
        )

        assert response.status_code == 202
        assert response.json()["id"] == str(existing.id)
        mock_delay.assert_not_called()

    @pytest.mark.asyncio
    @patch("app.api.lexicon_jobs.run_lexicon_compiled_materialize.delay", side_effect=RuntimeError("queue down"))
    async def test_create_compiled_materialize_returns_503_when_queue_unavailable(self, _mock_delay, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(None)]
        mock_db.flush = pytest.importorskip("unittest.mock").AsyncMock()
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        response = await client.post(
            "/api/lexicon-jobs/compiled-materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(uuid.uuid4()),
                "output_dir": str(tmp_path / "reviewed"),
            },
        )

        assert response.status_code == 503
        assert response.json()["detail"] == "Lexicon job queue is unavailable"

    @pytest.mark.asyncio
    async def test_get_lexicon_job_status(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=user_id,
            job_type="import_db",
            status="completed",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={"input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"},
            result_payload={"created_words": 1},
        )
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(job)]

        response = await client.get(
            f"/api/lexicon-jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "completed"
        assert response.json()["result_payload"]["created_words"] == 1

    @pytest.mark.asyncio
    async def test_get_lexicon_job_status_exposes_phase_aware_progress_summary(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=user_id,
            job_type="import_db",
            status="running",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={
                "input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
                "row_summary": {"row_count": 10},
                "progress_summary": {
                    "phase": "importing",
                    "total": 10,
                    "validated": 10,
                    "imported": 3,
                    "skipped": 2,
                    "failed": 1,
                    "to_validate": 0,
                    "to_import": 4,
                },
            },
            result_payload=None,
            progress_total=10,
            progress_completed=6,
            progress_current_label="Importing 6/10: harbor",
        )
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(job)]

        response = await client.get(
            f"/api/lexicon-jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["progress_summary"] == {
            "phase": "importing",
            "total": 10,
            "validated": 10,
            "imported": 3,
            "skipped": 2,
            "failed": 1,
            "to_validate": 0,
            "to_import": 4,
        }

    @pytest.mark.asyncio
    async def test_list_lexicon_jobs_filters_and_limits(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        recent_job = LexiconJob(
            id=uuid.uuid4(),
            created_by=user_id,
            job_type="import_db",
            status="failed",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={"input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"},
            result_payload={"failed_rows": 1},
            error_message="usage_note must be a non-empty string",
        )
        jobs_result = MagicMock()
        jobs_result.scalars.return_value.all.return_value = [recent_job]
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), jobs_result]

        response = await client.get(
            "/api/lexicon-jobs?job_type=import_db&limit=6",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["status"] == "failed"
        assert "usage_note" in data[0]["error_message"]

    @pytest.mark.asyncio
    async def test_get_failed_import_db_job_exposes_first_row_failure_details(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=user_id,
            job_type="import_db",
            status="failed",
            target_key="import_db:/app/data/lexicon/snapshots/phrases/reviewed/approved.jsonl",
            request_payload={"input_path": "/app/data/lexicon/snapshots/phrases/reviewed/approved.jsonl"},
            result_payload=None,
            progress_total=0,
            progress_completed=0,
            progress_current_label=None,
            error_message="sense 2 translations.zh-Hans.usage_note must be a non-empty string",
        )
        mock_db.execute.side_effect = [_result_with(make_user(user_id)), _result_with(job)]

        response = await client.get(
            f"/api/lexicon-jobs/{job.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json()["status"] == "failed"
        assert response.json()["progress_current_label"] == "Failed before first row"
        assert "usage_note" in response.json()["error_message"]

    @pytest.mark.asyncio
    @patch("app.api.lexicon_jobs.run_lexicon_compiled_review_bulk_update.delay")
    async def test_create_compiled_review_bulk_update_job(self, mock_delay, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        batch_id = uuid.uuid4()
        mock_db.execute.side_effect = [
            _result_with(make_user(user_id)),
            _result_with(
                LexiconArtifactReviewBatch(
                    id=batch_id,
                    artifact_family="compiled_words",
                    artifact_filename="words.enriched.jsonl",
                    artifact_sha256="a" * 64,
                    artifact_row_count=2,
                    compiled_schema_version="1.1.0",
                    snapshot_id="snapshot-001",
                    source_type="lexicon_compiled_export",
                    source_reference="snapshot-001",
                    status="pending_review",
                    total_items=2,
                    pending_count=2,
                    approved_count=0,
                    rejected_count=0,
                )
            ),
            _result_with(None),
        ]
        mock_db.flush = pytest.importorskip("unittest.mock").AsyncMock()

        async def fake_refresh(job):
            job.id = uuid.uuid4()

        mock_db.refresh = pytest.importorskip("unittest.mock").AsyncMock(side_effect=fake_refresh)

        response = await client.post(
            "/api/lexicon-jobs/compiled-review-bulk-update",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "batch_id": str(batch_id),
                "review_status": "approved",
                "decision_reason": "bulk ready",
                "scope": "all_pending",
            },
        )

        assert response.status_code == 202
        assert response.json()["job_type"] == "compiled_review_bulk_update"
        mock_delay.assert_called_once()
