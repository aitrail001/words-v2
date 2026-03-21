import uuid

from sqlalchemy import UniqueConstraint

from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_artifact_review_item_event import LexiconArtifactReviewItemEvent
from app.models.lexicon_regeneration_request import LexiconRegenerationRequest
from app.models.schema_names import LEXICON_SCHEMA


class TestLexiconArtifactReviewBatchModel:
    def test_batch_defaults(self):
        batch = LexiconArtifactReviewBatch(
            artifact_family="compiled_words",
            artifact_filename="words.enriched.jsonl",
            artifact_sha256="a" * 64,
            artifact_row_count=2,
            compiled_schema_version="1.1.0",
        )

        assert batch.status == "pending_review"
        assert batch.total_items == 0
        assert batch.pending_count == 0
        assert batch.approved_count == 0
        assert batch.rejected_count == 0

    def test_batch_has_artifact_hash_unique_constraint(self):
        constraints = [
            constraint
            for constraint in LexiconArtifactReviewBatch.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]

        assert any(
            constraint.name == "uq_lexicon_artifact_review_batch_sha256"
            and {column.name for column in constraint.columns} == {"artifact_sha256"}
            for constraint in constraints
        )


class TestLexiconArtifactReviewItemModel:
    def test_item_defaults(self):
        item = LexiconArtifactReviewItem(
            batch_id=uuid.uuid4(),
            entry_id="word:bank",
            entry_type="word",
            display_text="bank",
            language="en",
            compiled_payload={"entry_id": "word:bank"},
            compiled_payload_sha256="b" * 64,
            search_text="bank financial institution",
        )

        assert item.review_status == "pending"
        assert item.review_priority == 100
        assert item.regen_requested is False
        assert item.import_eligible is False
        assert item.reviewed_by is None
        assert item.reviewed_at is None

    def test_item_has_batch_entry_unique_constraint(self):
        constraints = [
            constraint
            for constraint in LexiconArtifactReviewItem.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]

        assert any(
            constraint.name == "uq_lexicon_artifact_review_item_batch_entry"
            and {column.name for column in constraint.columns} == {"batch_id", "entry_id"}
            for constraint in constraints
        )


class TestLexiconArtifactReviewEventModel:
    def test_event_defaults(self):
        event = LexiconArtifactReviewItemEvent(
            item_id=uuid.uuid4(),
            event_type="ingested",
        )

        assert event.from_status is None
        assert event.to_status is None
        assert event.reason is None


class TestLexiconRegenerationRequestModel:
    def test_request_defaults(self):
        request = LexiconRegenerationRequest(
            batch_id=uuid.uuid4(),
            item_id=uuid.uuid4(),
            entry_id="word:bank",
            entry_type="word",
            artifact_sha256="c" * 64,
            request_payload={"entry_id": "word:bank"},
        )

        assert request.request_status == "pending"
        assert request.request_reason is None

    def test_request_has_batch_item_unique_constraint(self):
        constraints = [
            constraint
            for constraint in LexiconRegenerationRequest.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]

        assert any(
            constraint.name == "uq_lexicon_regeneration_request_batch_item"
            and {column.name for column in constraint.columns} == {"batch_id", "item_id"}
            for constraint in constraints
        )


class TestLexiconCompiledReviewTables:
    def test_tables_use_lexicon_schema(self):
        assert LexiconArtifactReviewBatch.__table__.schema == LEXICON_SCHEMA
        assert LexiconArtifactReviewItem.__table__.schema == LEXICON_SCHEMA
        assert LexiconArtifactReviewItemEvent.__table__.schema == LEXICON_SCHEMA
        assert LexiconRegenerationRequest.__table__.schema == LEXICON_SCHEMA
