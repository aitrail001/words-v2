import uuid

from sqlalchemy import UniqueConstraint

from app.models.lexicon_review_batch import LexiconReviewBatch
from app.models.lexicon_review_item import LexiconReviewItem


class TestLexiconReviewBatchModel:
    def test_batch_defaults(self):
        batch = LexiconReviewBatch(
            user_id=uuid.uuid4(),
            source_filename="selection_decisions.jsonl",
            source_hash="a" * 64,
        )
        assert batch.status == "importing"
        assert batch.total_items == 0
        assert batch.review_required_count == 0
        assert batch.auto_accepted_count == 0
        assert batch.error_message is None

    def test_batch_has_user_hash_unique_constraint(self):
        constraints = [
            constraint
            for constraint in LexiconReviewBatch.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert any(
            constraint.name == "uq_lexicon_review_batch_user_hash"
            and {column.name for column in constraint.columns} == {"user_id", "source_hash"}
            for constraint in constraints
        )


class TestLexiconReviewItemModel:
    def test_item_defaults(self):
        item = LexiconReviewItem(
            batch_id=uuid.uuid4(),
            lexeme_id="lx_bank",
            lemma="bank",
            language="en",
            risk_band="rerank_and_review_candidate",
            selection_risk_score=6,
            deterministic_selected_wn_synset_ids=["bank.n.01"],
            candidate_metadata=[{"wn_synset_id": "bank.n.01"}],
            row_payload={"lexeme_id": "lx_bank"},
        )
        assert item.review_status == "pending"
        assert item.auto_accepted is False
        assert item.review_required is False
        assert item.reviewed_by is None
        assert item.reviewed_at is None

    def test_item_has_batch_lexeme_unique_constraint(self):
        constraints = [
            constraint
            for constraint in LexiconReviewItem.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert any(
            constraint.name == "uq_lexicon_review_item_batch_lexeme"
            and {column.name for column in constraint.columns} == {"batch_id", "lexeme_id"}
            for constraint in constraints
        )
