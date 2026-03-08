import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.security import create_access_token
from app.models.lexicon_review_batch import LexiconReviewBatch
from app.models.lexicon_review_item import LexiconReviewItem
from app.models.meaning import Meaning
from app.models.user import User
from app.models.word import Word


def make_user(user_id: uuid.UUID) -> User:
    return User(id=user_id, email="publisher@example.com", password_hash="hashed")


def make_batch(user_id: uuid.UUID, **overrides) -> LexiconReviewBatch:
    return LexiconReviewBatch(
        id=overrides.pop("id", uuid.uuid4()),
        user_id=user_id,
        status=overrides.pop("status", "imported"),
        source_filename=overrides.pop("source_filename", "selection_decisions.jsonl"),
        source_hash=overrides.pop("source_hash", "a" * 64),
        source_type=overrides.pop("source_type", "lexicon_selection_decisions"),
        source_reference=overrides.pop("source_reference", "demo-batch"),
        snapshot_id=overrides.pop("snapshot_id", "snapshot-001"),
        total_items=overrides.pop("total_items", 1),
        review_required_count=overrides.pop("review_required_count", 0),
        auto_accepted_count=overrides.pop("auto_accepted_count", 1),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        started_at=overrides.pop("started_at", datetime.now(timezone.utc)),
        completed_at=overrides.pop("completed_at", datetime.now(timezone.utc)),
        import_metadata=overrides.pop("import_metadata", {}),
        **overrides,
    )


def make_item(batch_id: uuid.UUID, **overrides) -> LexiconReviewItem:
    return LexiconReviewItem(
        id=overrides.pop("id", uuid.uuid4()),
        batch_id=batch_id,
        lexeme_id=overrides.pop("lexeme_id", "lx_bank"),
        lemma=overrides.pop("lemma", "bank"),
        language=overrides.pop("language", "en"),
        wordfreq_rank=overrides.pop("wordfreq_rank", 1234),
        risk_band=overrides.pop("risk_band", "rerank_recommended"),
        selection_risk_score=overrides.pop("selection_risk_score", 4),
        deterministic_selected_wn_synset_ids=overrides.pop("deterministic_selected_wn_synset_ids", ["bank.n.01"]),
        reranked_selected_wn_synset_ids=overrides.pop("reranked_selected_wn_synset_ids", ["bank.n.01", "bank.v.01"]),
        candidate_metadata=overrides.pop(
            "candidate_metadata",
            [
                {
                    "wn_synset_id": "bank.n.01",
                    "part_of_speech": "noun",
                    "canonical_label": "bank",
                    "canonical_gloss": "a financial institution that accepts deposits",
                },
                {
                    "wn_synset_id": "bank.v.01",
                    "part_of_speech": "verb",
                    "canonical_label": "bank",
                    "canonical_gloss": "to deposit money in a bank",
                },
            ],
        ),
        auto_accepted=overrides.pop("auto_accepted", True),
        review_required=overrides.pop("review_required", False),
        review_status=overrides.pop("review_status", "approved"),
        review_override_wn_synset_ids=overrides.pop("review_override_wn_synset_ids", None),
        review_comment=overrides.pop("review_comment", None),
        reviewed_by=overrides.pop("reviewed_by", None),
        reviewed_at=overrides.pop("reviewed_at", None),
        row_payload=overrides.pop("row_payload", {"lexeme_id": "lx_bank"}),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        **overrides,
    )


class TestPublishLexiconReviewBatch:
    @pytest.mark.asyncio
    async def test_publish_batch_success_replaces_lexicon_meanings_and_preserves_others(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id)
        item = make_item(batch.id)

        existing_word = Word(
            id=uuid.uuid4(),
            word="bank",
            language="en",
            frequency_rank=9999,
            source_type="manual",
            source_reference="manual-seed",
        )
        existing_lexicon_meaning = Meaning(
            id=uuid.uuid4(),
            word_id=existing_word.id,
            definition="old lexicon definition",
            part_of_speech="noun",
            order_index=0,
            source="lexicon_review_publish",
            source_reference="lexicon_review_batch:old:bank.n.01",
        )
        existing_manual_meaning = Meaning(
            id=uuid.uuid4(),
            word_id=existing_word.id,
            definition="manual meaning",
            part_of_speech="noun",
            order_index=9,
            source="manual",
            source_reference="manual-entry",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = existing_word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [existing_lexicon_meaning, existing_manual_meaning]
        mock_db.execute.side_effect = [user_result, batch_result, items_result, word_result, meanings_result]

        response = await client.post(
            f"/api/lexicon-reviews/batches/{batch.id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"] == str(batch.id)
        assert data["status"] == "published"
        assert data["published_item_count"] == 1
        assert data["updated_word_count"] == 1
        assert data["published_word_count"] == 0
        assert data["replaced_meaning_count"] == 1
        assert data["created_meaning_count"] == 2
        assert batch.status == "published"
        assert batch.completed_at is not None
        assert batch.import_metadata["publish_summary"]["published_item_count"] == 1
        assert batch.import_metadata["publish_summary"]["created_meaning_count"] == 2
        assert existing_word.source_type == "lexicon_review_publish"
        assert existing_word.source_reference == f"lexicon_review_batch:{batch.id}"
        mock_db.delete.assert_awaited_once_with(existing_lexicon_meaning)
        added_meanings = [call.args[0] for call in mock_db.add.call_args_list if isinstance(call.args[0], Meaning)]
        assert len(added_meanings) == 2
        assert [meaning.definition for meaning in added_meanings] == [
            "a financial institution that accepts deposits",
            "to deposit money in a bank",
        ]
        assert all(meaning.source == "lexicon_review_publish" for meaning in added_meanings)
        assert all(meaning.word_id == existing_word.id for meaning in added_meanings)

    @pytest.mark.asyncio
    async def test_publish_batch_returns_404_for_non_owned_batch(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, batch_result]

        response = await client.post(
            f"/api/lexicon-reviews/batches/{batch_id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Lexicon review batch not found"

    @pytest.mark.asyncio
    async def test_publish_batch_returns_400_when_no_approved_items_are_publishable(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.post(
            f"/api/lexicon-reviews/batches/{batch.id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "No approved lexicon review items are publishable"
