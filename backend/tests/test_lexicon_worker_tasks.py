import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.models.lexicon_job import LexiconJob
from app.tasks.lexicon_jobs import (
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
        assert job.progress_current_label == "harbor"
        assert mock_db.commit.call_count >= 2

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
