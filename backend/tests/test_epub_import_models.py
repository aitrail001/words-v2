import uuid
from datetime import datetime

import pytest

from app.models.epub_import import EpubImport


class TestEpubImportModel:
    def test_import_has_required_fields(self):
        user_id = uuid.uuid4()
        epub_import = EpubImport(
            user_id=user_id,
            filename="book.epub",
            file_hash="abc123",
        )
        assert epub_import.user_id == user_id
        assert epub_import.filename == "book.epub"
        assert epub_import.file_hash == "abc123"
        assert epub_import.status == "pending"
        assert epub_import.total_words == 0
        assert epub_import.processed_words == 0
        assert epub_import.error_message is None
        assert epub_import.started_at is None
        assert epub_import.completed_at is None

    def test_import_status_defaults_to_pending(self):
        epub_import = EpubImport(
            user_id=uuid.uuid4(),
            filename="test.epub",
            file_hash="hash123",
        )
        assert epub_import.status == "pending"

    def test_import_status_values(self):
        for status in ["pending", "processing", "completed", "failed"]:
            epub_import = EpubImport(
                user_id=uuid.uuid4(),
                filename="test.epub",
                file_hash="hash",
                status=status,
            )
            assert epub_import.status == status

    def test_import_with_progress(self):
        epub_import = EpubImport(
            user_id=uuid.uuid4(),
            filename="test.epub",
            file_hash="hash",
            status="processing",
            total_words=1000,
            processed_words=500,
        )
        assert epub_import.total_words == 1000
        assert epub_import.processed_words == 500

    def test_import_with_error(self):
        epub_import = EpubImport(
            user_id=uuid.uuid4(),
            filename="test.epub",
            file_hash="hash",
            status="failed",
            error_message="Invalid ePub format",
        )
        assert epub_import.status == "failed"
        assert epub_import.error_message == "Invalid ePub format"

    def test_import_timestamps(self):
        started = datetime.now()
        completed = datetime.now()
        epub_import = EpubImport(
            user_id=uuid.uuid4(),
            filename="test.epub",
            file_hash="hash",
            started_at=started,
            completed_at=completed,
        )
        assert epub_import.started_at == started
        assert epub_import.completed_at == completed
