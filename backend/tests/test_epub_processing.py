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


@patch("app.tasks.epub_processing._cleanup_uploaded_file")
@patch("app.tasks.epub_processing._release_import_source_lock")
@patch("app.tasks.epub_processing._acquire_import_source_lock")
@patch("app.tasks.epub_processing.upsert_import_source_entries_sync")
@patch("app.tasks.epub_processing.fetch_import_matcher_sync")
@patch("app.tasks.epub_processing.EpubTextExtractor")
@patch("app.tasks.epub_processing.get_or_create_import_source_sync")
@patch("app.tasks.epub_processing.Session")
def test_process_source_import_updates_live_progress_fields(
    mock_session_cls,
    mock_get_or_create_import_source_sync,
    mock_extractor_cls,
    mock_fetch_import_matcher_sync,
    mock_upsert_import_source_entries_sync,
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
    import_source.matched_entry_count = 0

    locked_source = MagicMock()
    locked_source.id = "source-1"
    locked_source.status = "pending"
    locked_source.matched_entry_count = 0

    job_result = MagicMock()
    job_result.scalar_one_or_none.return_value = job
    source_result = MagicMock()
    source_result.scalar_one.return_value = locked_source
    linked_jobs_result = MagicMock()
    linked_jobs_result.scalars.return_value.all.return_value = [job]

    mock_db = MagicMock()
    mock_db.execute.side_effect = [job_result, source_result, linked_jobs_result]
    mock_session_ctx = MagicMock()
    mock_session_ctx.__enter__.return_value = mock_db
    mock_session_ctx.__exit__.return_value = None
    mock_session_cls.return_value = mock_session_ctx
    mock_get_or_create_import_source_sync.return_value = import_source

    extractor = MagicMock()

    def extractor_side_effect(_file_path, *, progress_callback=None):
        if progress_callback is not None:
            progress_callback(MagicMock(completed=1, total=3, label="Extracting text 1/3"))
            progress_callback(MagicMock(completed=3, total=3, label="Extracting text 3/3"))
        return MagicMock(title="Book", author="Author", publisher="Press", language="en", source_identifier="id", published_year=2024, isbn="9781234567890"), ["one", "two", "three"]

    extractor.extract_metadata_and_chunks.side_effect = extractor_side_effect
    mock_extractor_cls.return_value = extractor

    matcher = MagicMock()

    def matcher_side_effect(chunks, *, progress_callback=None):
        assert chunks == ["one", "two", "three"]
        if progress_callback is not None:
            progress_callback(MagicMock(completed=2, total=3, matched_entries=5, label="Matching entries 2/3"))
            progress_callback(MagicMock(completed=3, total=3, matched_entries=7, label="Matching entries 3/3"))
        return [MagicMock()] * 7

    matcher.match_chunks_with_progress.side_effect = matcher_side_effect
    mock_fetch_import_matcher_sync.return_value = (matcher, {}, {})

    result = process_source_import(
        "00000000-0000-0000-0000-000000000001",
        "00000000-0000-0000-0000-000000000002",
        "/tmp/book.epub",
    )

    assert result == {"status": "completed", "matched_entry_count": 7}
    assert job.progress_stage == "completed"
    assert job.progress_current_label == "Import completed"
    assert job.progress_total == 7
    assert job.progress_completed == 7
    assert job.matched_entry_count == 7
    mock_upsert_import_source_entries_sync.assert_called_once()
    mock_cleanup.assert_called_once()
