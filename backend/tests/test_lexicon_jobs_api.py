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
            },
        )

        assert response.status_code == 202
        assert response.json()["job_type"] == "import_db"
        mock_delay.assert_called_once()

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
