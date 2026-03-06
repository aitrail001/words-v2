import uuid

from sqlalchemy import UniqueConstraint

from app.models.book import Book
from app.models.import_job import ImportJob
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem


class TestBookModel:
    def test_book_defaults(self):
        user_id = uuid.uuid4()
        book = Book(
            content_hash="a" * 64,
            uploaded_by=user_id,
        )

        assert book.content_hash == "a" * 64
        assert book.uploaded_by == user_id
        assert book.language == "en"
        assert book.title is None
        assert book.author is None
        assert book.word_count is None
        assert book.file_path is None


class TestWordListModel:
    def test_word_list_defaults(self):
        list_model = WordList(
            user_id=uuid.uuid4(),
            name="My Import List",
        )

        assert list_model.name == "My Import List"
        assert list_model.source_type is None
        assert list_model.source_reference is None
        assert list_model.description is None
        assert list_model.book_id is None


class TestWordListItemModel:
    def test_word_list_item_defaults(self):
        item = WordListItem(
            word_list_id=uuid.uuid4(),
            word_id=uuid.uuid4(),
        )

        assert item.frequency_count == 1
        assert item.context_sentence is None
        assert item.variation_data is None

    def test_word_list_item_unique_constraint(self):
        constraints = [
            constraint
            for constraint in WordListItem.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]

        assert any(
            constraint.name == "uq_word_list_item_word"
            and {column.name for column in constraint.columns} == {"word_list_id", "word_id"}
            for constraint in constraints
        )


class TestImportJobModel:
    def test_import_job_defaults(self):
        job = ImportJob(
            user_id=uuid.uuid4(),
            source_filename="book.epub",
            source_hash="b" * 64,
            list_name="Book Import",
        )

        assert job.status == "queued"
        assert job.total_items == 0
        assert job.processed_items == 0
        assert job.created_count == 0
        assert job.skipped_count == 0
        assert job.not_found_count == 0
        assert job.error_count == 0
        assert job.list_description is None
        assert job.error_message is None
        assert job.not_found_words is None

    def test_import_job_status_values(self):
        for status in ["queued", "processing", "completed", "failed"]:
            job = ImportJob(
                user_id=uuid.uuid4(),
                source_filename="book.epub",
                source_hash="c" * 64,
                list_name="Book Import",
                status=status,
            )

            assert job.status == status
