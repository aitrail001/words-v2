import uuid
from unittest.mock import MagicMock, patch

from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_job import LexiconJob
from app.tasks.lexicon_jobs import (
    process_compiled_review_bulk_job,
    run_lexicon_compiled_review_bulk_update,
    run_lexicon_compiled_materialize,
    run_lexicon_import_db,
    run_lexicon_jsonl_materialize,
)


class TestLexiconWorkerTasks:
    @staticmethod
    def _mock_session(session_cls, *execute_results):
        mock_db = MagicMock()
        mock_db.execute.side_effect = execute_results

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_db
        mock_session_cm.__exit__.return_value = None
        session_cls.return_value = mock_session_cm
        return mock_db

    @staticmethod
    def _job_result(job: LexiconJob):
        result = MagicMock()
        result.scalar_one_or_none.return_value = job
        return result

    @patch("app.tasks.lexicon_jobs._import_db_module")
    @patch("app.tasks.lexicon_jobs.Session")
    def test_import_db_task_updates_progress_and_completes(self, mock_session_cls, mock_import_module):
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            job_type="import_db",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={
                "input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
                "source_type": "lexicon_snapshot",
                "source_reference": "demo",
                "language": "en",
            },
        )
        mock_db = self._mock_session(mock_session_cls, self._job_result(job))

        def fake_run_import_file(path, *, progress_callback=None, **kwargs):
            progress_callback(row={"word": "bank"}, completed_rows=1, total_rows=2)
            progress_callback(row={"word": "harbor"}, completed_rows=2, total_rows=2)
            return {"created_words": 2}

        mock_import_module.return_value.run_import_file = fake_run_import_file

        result = run_lexicon_import_db(str(job.id))

        assert result["status"] == "completed"
        assert result["result_payload"]["created_words"] == 2
        assert job.status == "completed"
        assert job.progress_completed == 2
        assert job.progress_total == 2
        assert job.progress_current_label == "Importing 2/2: harbor"
        assert mock_db.commit.call_count >= 2

    @patch("app.tasks.lexicon_jobs._import_db_module")
    @patch("app.tasks.lexicon_jobs.Session")
    def test_import_db_task_exposes_preflight_and_skip_progress_labels(self, mock_session_cls, mock_import_module):
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            job_type="import_db",
            target_key="import_db:/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            request_payload={
                "input_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
                "source_type": "lexicon_snapshot",
                "source_reference": "demo",
                "language": "en",
                "row_summary": {"row_count": 2},
            },
        )
        mock_db = self._mock_session(mock_session_cls, self._job_result(job))

        def fake_run_import_file(path, *, preflight_progress_callback=None, progress_callback=None, **kwargs):
            assert preflight_progress_callback is not None
            assert progress_callback is not None
            preflight_progress_callback({"word": "fuss over", "_progress_label": "Validating 1/2"}, 1, 2)
            progress_callback({"word": "bank", "_progress_label": "Skipping existing word: bank"}, 1, 2)
            progress_callback({"word": "harbor"}, 2, 2)
            return {"skipped_words": 1, "created_words": 1, "failed_rows": 0}

        mock_import_module.return_value.run_import_file = fake_run_import_file

        result = run_lexicon_import_db(str(job.id))

        assert result["status"] == "completed"
        assert result["result_payload"]["skipped_words"] == 1
        assert result["result_payload"]["created_words"] == 1
        assert job.status == "completed"
        assert job.progress_completed == 2
        assert job.progress_total == 2
        assert job.progress_current_label == "Importing 2/2: harbor"
        assert mock_db.commit.call_count >= 3

    @patch("app.tasks.lexicon_jobs.materialize_jsonl_review_outputs")
    @patch("app.tasks.lexicon_jobs.Session")
    def test_jsonl_materialize_task_completes_with_result_payload(self, mock_session_cls, mock_materialize):
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            job_type="jsonl_materialize",
            target_key="jsonl_materialize:/app/data/lexicon/snapshots/demo/reviewed",
            request_payload={
                "artifact_path": "/app/data/lexicon/snapshots/demo/words.enriched.jsonl",
                "decisions_path": "/app/data/lexicon/snapshots/demo/reviewed/review.decisions.jsonl",
                "output_dir": "/app/data/lexicon/snapshots/demo/reviewed",
            },
        )
        self._mock_session(mock_session_cls, self._job_result(job))
        mock_materialize.return_value = {
            "approved_output_path": "/app/data/lexicon/snapshots/demo/reviewed/approved.jsonl",
            "rejected_output_path": "/app/data/lexicon/snapshots/demo/reviewed/rejected.jsonl",
            "regenerate_output_path": "/app/data/lexicon/snapshots/demo/reviewed/regenerate.jsonl",
            "decisions_output_path": "/app/data/lexicon/snapshots/demo/reviewed/review.decisions.jsonl",
            "approved_count": 1,
            "rejected_count": 0,
            "regenerate_count": 0,
            "decision_count": 1,
            "artifact_sha256": "a" * 64,
        }

        result = run_lexicon_jsonl_materialize(str(job.id))

        assert result["status"] == "completed"
        assert result["result_payload"]["approved_output_path"].endswith("approved.jsonl")
        assert job.status == "completed"

    @patch("app.tasks.lexicon_jobs.materialize_compiled_review_batch")
    @patch("app.tasks.lexicon_jobs.Session")
    def test_compiled_materialize_task_marks_job_failed(self, mock_session_cls, mock_materialize):
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            job_type="compiled_materialize",
            target_key="compiled_materialize:batch:demo:output:/app/data/lexicon/snapshots/demo/reviewed",
            request_payload={
                "batch_id": str(uuid.uuid4()),
                "output_dir": "/app/data/lexicon/snapshots/demo/reviewed",
            },
        )
        self._mock_session(mock_session_cls, self._job_result(job))
        mock_materialize.side_effect = RuntimeError("write failed")

        result = run_lexicon_compiled_materialize(str(job.id))

        assert result["status"] == "failed"
        assert "write failed" in result["error"]
        assert job.status == "failed"
        assert job.error_message == "write failed"

    @patch("app.tasks.lexicon_jobs.process_compiled_review_bulk_job")
    @patch("app.tasks.lexicon_jobs.Session")
    def test_compiled_review_bulk_update_task_updates_progress_and_completes(self, mock_session_cls, mock_process_bulk):
        batch_id = uuid.uuid4()
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=uuid.uuid4(),
            job_type="compiled_review_bulk_update",
            target_key=f"compiled_review_bulk_update:{batch_id}:approved:all_pending",
            request_payload={
                "batch_id": str(batch_id),
                "review_status": "approved",
                "decision_reason": "bulk ready",
                "scope": "all_pending",
            },
        )
        mock_db = self._mock_session(mock_session_cls, self._job_result(job))

        def fake_process(db, *, job, batch_id, review_status, decision_reason, scope, chunk_size):
            assert review_status == "approved"
            assert decision_reason == "bulk ready"
            assert scope == "all_pending"
            assert chunk_size == 500
            job.progress_total = 3
            job.progress_completed = 3
            job.progress_current_label = "harbor"
            return {
                "batch_id": str(batch_id),
                "processed_count": 3,
                "approved_count": 3,
                "rejected_count": 0,
                "pending_count": 0,
                "failed_count": 0,
                "scope": "all_pending",
                "review_status": "approved",
            }

        mock_process_bulk.side_effect = fake_process

        result = run_lexicon_compiled_review_bulk_update(str(job.id))

        assert result["status"] == "completed"
        assert result["result_payload"]["processed_count"] == 3
        assert job.status == "completed"
        assert job.progress_total == 3
        assert job.progress_completed == 3
        assert job.progress_current_label == "harbor"
        assert mock_db.commit.call_count >= 2

    def test_process_compiled_review_bulk_job_reopens_reviewed_rows(self):
        batch_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        job = LexiconJob(
            id=uuid.uuid4(),
            created_by=actor_id,
            job_type="compiled_review_bulk_update",
            target_key=f"compiled_review_bulk_update:{batch_id}:pending:all_pending",
            request_payload={
                "batch_id": str(batch_id),
                "review_status": "pending",
                "scope": "all_pending",
            },
        )
        batch = LexiconArtifactReviewBatch(
            id=batch_id,
            artifact_family="word",
            artifact_filename="compiled.jsonl",
            artifact_sha256="a" * 64,
            artifact_row_count=3,
            compiled_schema_version="1.1.0",
            status="pending_review",
            total_items=3,
            pending_count=1,
            approved_count=1,
            rejected_count=1,
        )
        approved_item = LexiconArtifactReviewItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            entry_id="word:bank",
            entry_type="word",
            normalized_form="bank",
            display_text="bank",
            review_status="approved",
            import_eligible=True,
            regen_requested=False,
            review_priority=1,
            compiled_payload={},
            compiled_payload_sha256="b" * 64,
            search_text="bank",
        )
        rejected_item = LexiconArtifactReviewItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            entry_id="word:harbor",
            entry_type="word",
            normalized_form="harbor",
            display_text="harbor",
            review_status="rejected",
            import_eligible=False,
            regen_requested=True,
            review_priority=2,
            compiled_payload={},
            compiled_payload_sha256="c" * 64,
            search_text="harbor",
        )
        pending_item = LexiconArtifactReviewItem(
            id=uuid.uuid4(),
            batch_id=batch_id,
            entry_id="word:port",
            entry_type="word",
            normalized_form="port",
            display_text="port",
            review_status="pending",
            import_eligible=False,
            regen_requested=False,
            review_priority=3,
            compiled_payload={},
            compiled_payload_sha256="d" * 64,
            search_text="port",
        )

        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item, rejected_item]
        no_regen_request_result = MagicMock()
        no_regen_request_result.scalar_one_or_none.return_value = None
        db = MagicMock()
        db.execute.side_effect = [
            batch_result,
            items_result,
            no_regen_request_result,
            no_regen_request_result,
        ]

        result = process_compiled_review_bulk_job(
            db,
            job=job,
            batch_id=batch_id,
            review_status="pending",
            decision_reason="reopen",
            scope="all_pending",
            chunk_size=500,
        )

        assert result["processed_count"] == 2
        assert approved_item.review_status == "pending"
        assert rejected_item.review_status == "pending"
        assert pending_item.review_status == "pending"
        assert batch.pending_count == 3
        assert batch.approved_count == 0
        assert batch.rejected_count == 0
