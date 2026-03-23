import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.lexicon_job import LexiconJob
from app.services.lexicon_jobs import (
    ACTIVE_JOB_STATUSES,
    apply_lexicon_job_completed,
    apply_lexicon_job_failed,
    apply_lexicon_job_progress,
    apply_lexicon_job_started,
    create_or_reuse_lexicon_job,
    get_lexicon_job,
)


def _result_with(job):
    result = MagicMock()
    result.scalar_one_or_none.return_value = job
    return result


class TestLexiconJobsService:
    @pytest.mark.asyncio
    async def test_create_or_reuse_creates_new_job_when_no_active_target_match(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with(None))
        db.add = MagicMock()
        db.flush = AsyncMock()

        job, created = await create_or_reuse_lexicon_job(
            db,
            created_by=uuid.uuid4(),
            job_type="import_db",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={"input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"},
        )

        assert created is True
        assert job.status == "queued"
        assert job.progress_total == 0
        db.add.assert_called_once_with(job)
        db.flush.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_or_reuse_returns_existing_active_job(self):
        existing = LexiconJob(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            job_type="jsonl_materialize",
            status="running",
            target_key="jsonl_materialize:/app/data/lexicon/snapshots/demo/reviewed",
            request_payload={"output_dir": "/app/data/lexicon/snapshots/demo/reviewed"},
        )
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with(existing))
        db.add = MagicMock()
        db.flush = AsyncMock()

        job, created = await create_or_reuse_lexicon_job(
            db,
            created_by=uuid.uuid4(),
            job_type="jsonl_materialize",
            target_key="jsonl_materialize:/app/data/lexicon/snapshots/demo/reviewed",
            request_payload={"output_dir": "/app/data/lexicon/snapshots/demo/reviewed"},
        )

        assert created is False
        assert job is existing
        db.add.assert_not_called()
        db.flush.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_get_returns_none_when_missing(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_result_with(None))

        job = await get_lexicon_job(db, uuid.uuid4())

        assert job is None

    def test_apply_started_progress_completed_and_failed(self):
        job = LexiconJob(
            created_by=uuid.uuid4(),
            job_type="compiled_materialize",
            target_key="compiled_materialize:batch:1:output:/app/data/lexicon/snapshots/demo/reviewed",
            request_payload={"batch_id": "1"},
        )

        apply_lexicon_job_started(job)
        assert job.status == "running"
        assert job.started_at is not None

        apply_lexicon_job_progress(job, progress_completed=2, progress_total=5, current_label="bank")
        assert job.progress_completed == 2
        assert job.progress_total == 5
        assert job.progress_current_label == "bank"

        apply_lexicon_job_completed(job, result_payload={"approved_output_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"})
        assert job.status == "completed"
        assert job.result_payload == {"approved_output_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"}
        assert job.completed_at is not None
        assert job.progress_completed == 5

        failed = LexiconJob(
            created_by=uuid.uuid4(),
            job_type="import_db",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={"input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl"},
        )
        apply_lexicon_job_failed(failed, "queue error")
        assert failed.status == "failed"
        assert failed.error_message == "queue error"
        assert failed.completed_at is not None

    def test_active_statuses_are_only_queue_and_running(self):
        assert ACTIVE_JOB_STATUSES == {"queued", "running"}
