from unittest.mock import MagicMock, patch

from app.tasks.epub_processing import process_source_import


@patch("app.tasks.epub_processing._cleanup_uploaded_file")
@patch("app.tasks.epub_processing.Session")
def test_process_source_import_missing_job_returns_failed(mock_session_cls, mock_cleanup):
    mock_db = MagicMock()
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__.return_value = mock_db
    mock_session_ctx.__exit__.return_value = None
    mock_session_cls.return_value = mock_session_ctx

    result = process_source_import("00000000-0000-0000-0000-000000000001", "00000000-0000-0000-0000-000000000002", "/tmp/book.epub")

    assert result["status"] == "failed"
    mock_cleanup.assert_called_once()


@patch("app.tasks.epub_processing._cleanup_uploaded_file")
@patch("app.tasks.epub_processing._release_import_source_lock")
@patch("app.tasks.epub_processing._acquire_import_source_lock")
@patch("app.tasks.epub_processing.get_or_create_import_source_sync")
@patch("app.tasks.epub_processing.Session")
def test_process_source_import_reuses_completed_source_after_lock(
    mock_session_cls,
    mock_get_or_create_import_source_sync,
    mock_acquire_lock,
    mock_release_lock,
    mock_cleanup,
):
    job = MagicMock()
    job.id = "job-1"
    job.source_hash = "a" * 64
    job.completed_at = None

    import_source = MagicMock()
    import_source.id = "source-1"
    import_source.status = "pending"
    import_source.matched_entry_count = 4
    completed_source = MagicMock()
    completed_source.id = "source-1"
    completed_source.status = "completed"
    completed_source.matched_entry_count = 4

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    source_result = MagicMock()
    source_result.scalar_one.return_value = completed_source

    mock_db = MagicMock()
    mock_db.execute.side_effect = [job_result, source_result]
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__.return_value = mock_db
    mock_session_ctx.__exit__.return_value = None
    mock_session_cls.return_value = mock_session_ctx
    mock_get_or_create_import_source_sync.return_value = import_source

    result = process_source_import(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "/tmp/book.epub",
    )

    assert result == {"status": "completed", "matched_entry_count": 4}
    mock_acquire_lock.assert_called_once_with(mock_db, "source-1")
    mock_release_lock.assert_called_once_with(mock_db, "source-1")
    mock_cleanup.assert_called_once()
