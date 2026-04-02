import uuid

from sqlalchemy import UniqueConstraint

from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.models.import_source_entry import ImportSourceEntry
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem


class TestImportSourceModel:
    def test_import_source_defaults(self):
        model = ImportSource(
            source_type="epub",
            source_hash_sha256="a" * 64,
            pipeline_version="pipeline-v1",
            lexicon_version="lexicon-v1",
        )

        assert model.status == "pending"
        assert model.matched_entry_count == 0
        assert model.title is None
        assert model.author is None


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


class TestWordListItemModel:
    def test_word_list_item_defaults(self):
        item = WordListItem(
            word_list_id=uuid.uuid4(),
            entry_type="word",
            entry_id=uuid.uuid4(),
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
            constraint.name == "uq_word_list_item_entry"
            and {column.name for column in constraint.columns} == {"word_list_id", "entry_type", "entry_id"}
            for constraint in constraints
        )


class TestImportSourceEntryModel:
    def test_import_source_entry_defaults(self):
        entry = ImportSourceEntry(
            import_source_id=uuid.uuid4(),
            entry_type="phrase",
            entry_id=uuid.uuid4(),
        )

        assert entry.frequency_count == 1
        assert entry.browse_rank_snapshot is None
        assert entry.normalization_method is None


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
        assert job.matched_entry_count == 0
        assert job.created_count == 0
        assert job.list_description is None
        assert job.error_message is None
