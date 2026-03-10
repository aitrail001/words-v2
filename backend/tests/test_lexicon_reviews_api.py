import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.core.security import create_access_token
from app.models.lexicon_review_batch import LexiconReviewBatch
from app.models.lexicon_review_item import LexiconReviewItem
from app.models.user import User
from app.models.word import Word
from app.models.meaning import Meaning


def make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="reviewer@example.com", password_hash="hashed", role=role)


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
        total_items=overrides.pop("total_items", 2),
        review_required_count=overrides.pop("review_required_count", 1),
        auto_accepted_count=overrides.pop("auto_accepted_count", 1),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        started_at=overrides.pop("started_at", datetime.now(timezone.utc)),
        completed_at=overrides.pop("completed_at", datetime.now(timezone.utc)),
        **overrides,
    )


def make_item(batch_id: uuid.UUID, reviewer_id: uuid.UUID | None = None, **overrides) -> LexiconReviewItem:
    return LexiconReviewItem(
        id=overrides.pop("id", uuid.uuid4()),
        batch_id=batch_id,
        lexeme_id=overrides.pop("lexeme_id", "lx_bank"),
        lemma=overrides.pop("lemma", "bank"),
        language=overrides.pop("language", "en"),
        wordfreq_rank=overrides.pop("wordfreq_rank", 1234),
        risk_band=overrides.pop("risk_band", "rerank_and_review_candidate"),
        selection_risk_score=overrides.pop("selection_risk_score", 6),
        deterministic_selected_wn_synset_ids=overrides.pop("deterministic_selected_wn_synset_ids", ["bank.n.01"]),
        reranked_selected_wn_synset_ids=overrides.pop("reranked_selected_wn_synset_ids", ["bank.n.01"]),
        candidate_metadata=overrides.pop("candidate_metadata", [{"wn_synset_id": "bank.n.01", "canonical_label": "bank", "canonical_gloss": "a financial institution", "part_of_speech": "noun", "selection_score": 9.7, "selection_reason": "common concrete noun"}]),
        auto_accepted=overrides.pop("auto_accepted", False),
        review_required=overrides.pop("review_required", True),
        review_status=overrides.pop("review_status", "pending"),
        review_override_wn_synset_ids=overrides.pop("review_override_wn_synset_ids", None),
        review_comment=overrides.pop("review_comment", None),
        reviewed_by=overrides.pop("reviewed_by", reviewer_id),
        reviewed_at=overrides.pop("reviewed_at", None),
        row_payload=overrides.pop(
            "row_payload",
            {
                "schema_version": "lexicon_selection_decision.v1",
                "snapshot_id": "snapshot-001",
                "lexeme_id": "lx_bank",
                "lemma": "bank",
                "language": "en",
                "risk_band": "rerank_and_review_candidate",
                "selection_risk_score": 6,
                "deterministic_selected_wn_synset_ids": ["bank.n.01"],
                "candidate_metadata": [{"wn_synset_id": "bank.n.01", "canonical_label": "bank", "canonical_gloss": "a financial institution", "part_of_speech": "noun", "selection_score": 9.7, "selection_reason": "common concrete noun"}],
                "generated_at": "2026-03-08T00:00:00Z",
                "generation_run_id": "selection-review-2026-03-08T00:00:00Z",
            },
        ),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        **overrides,
    )


def build_jsonl_bytes(*rows: dict) -> bytes:
    return "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")


class TestLexiconReviewBatchAdminAccess:
    @pytest.mark.asyncio
    async def test_import_requires_admin_role(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id, role="user")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        row = {
            "schema_version": "lexicon_selection_decision.v1",
            "snapshot_id": "snapshot-001",
            "lexeme_id": "lx_bank",
            "lemma": "bank",
            "language": "en",
            "risk_band": "rerank_and_review_candidate",
            "selection_risk_score": 6,
            "deterministic_selected_wn_synset_ids": ["bank.n.01"],
            "candidate_metadata": [{"wn_synset_id": "bank.n.01"}],
            "review_required": True,
            "auto_accepted": False,
            "generated_at": "2026-03-08T00:00:00Z",
            "generation_run_id": "selection-review-2026-03-08T00:00:00Z",
        }

        response = await client.post(
            "/api/lexicon-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("selection_decisions.jsonl", build_jsonl_bytes(row), "application/x-ndjson")},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    @pytest.mark.asyncio
    async def test_list_batches_requires_admin_role(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id, role="user")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        response = await client.get(
            "/api/lexicon-reviews/batches",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    @pytest.mark.asyncio
    async def test_patch_item_requires_admin_role(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id, role="user")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        response = await client.patch(
            f"/api/lexicon-reviews/items/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
            json={"review_status": "approved"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    @pytest.mark.asyncio
    async def test_publish_preview_requires_admin_role(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id, role="user")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{uuid.uuid4()}/publish-preview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"

    @pytest.mark.asyncio
    async def test_publish_requires_admin_role(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id, role="user")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]

        response = await client.post(
            f"/api/lexicon-reviews/batches/{uuid.uuid4()}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"


class TestImportLexiconReviewBatch:
    @pytest.mark.asyncio
    async def test_import_batch_success(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_result]

        row = {
            "schema_version": "lexicon_selection_decision.v1",
            "snapshot_id": "snapshot-001",
            "lexeme_id": "lx_bank",
            "lemma": "bank",
            "language": "en",
            "risk_band": "rerank_and_review_candidate",
            "selection_risk_score": 6,
            "deterministic_selected_wn_synset_ids": ["bank.n.01"],
            "candidate_metadata": [{"wn_synset_id": "bank.n.01"}],
            "review_required": True,
            "auto_accepted": False,
            "generated_at": "2026-03-08T00:00:00Z",
            "generation_run_id": "selection-review-2026-03-08T00:00:00Z",
        }

        response = await client.post(
            "/api/lexicon-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            data={"source_type": "lexicon_selection_decisions", "source_reference": "demo-ref"},
            files={"file": ("selection_decisions.jsonl", build_jsonl_bytes(row), "application/x-ndjson")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["user_id"] == str(user_id)
        assert data["status"] == "imported"
        assert data["total_items"] == 1
        assert data["review_required_count"] == 1
        assert data["auto_accepted_count"] == 0
        assert data["snapshot_id"] == "snapshot-001"

    @pytest.mark.asyncio
    async def test_import_batch_duplicate_imported_returns_existing(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        existing_batch = make_batch(user_id, status="imported")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = existing_batch
        mock_db.execute.side_effect = [user_result, existing_result]

        row = {
            "schema_version": "lexicon_selection_decision.v1",
            "snapshot_id": "snapshot-001",
            "lexeme_id": "lx_bank",
            "lemma": "bank",
            "language": "en",
            "risk_band": "rerank_and_review_candidate",
            "selection_risk_score": 6,
            "deterministic_selected_wn_synset_ids": ["bank.n.01"],
            "candidate_metadata": [{"wn_synset_id": "bank.n.01"}],
            "generated_at": "2026-03-08T00:00:00Z",
            "generation_run_id": "selection-review-2026-03-08T00:00:00Z",
        }

        response = await client.post(
            "/api/lexicon-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("selection_decisions.jsonl", build_jsonl_bytes(row), "application/x-ndjson")},
        )

        assert response.status_code == 200
        assert response.json()["id"] == str(existing_batch.id)

    @pytest.mark.asyncio
    async def test_import_batch_requires_jsonl_file(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.return_value = user_result

        response = await client.post(
            "/api/lexicon-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("selection_decisions.txt", b"not-jsonl", "text/plain")},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Only .jsonl files are supported"

    @pytest.mark.asyncio
    async def test_import_batch_rejects_missing_required_fields(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_result = MagicMock()
        existing_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_result]

        bad_row = {"schema_version": "lexicon_selection_decision.v1", "lemma": "bank"}
        response = await client.post(
            "/api/lexicon-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("selection_decisions.jsonl", build_jsonl_bytes(bad_row), "application/x-ndjson")},
        )

        assert response.status_code == 400
        assert "missing required fields" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_import_batch_requires_auth(self, client):
        response = await client.post(
            "/api/lexicon-reviews/batches/import",
            files={"file": ("selection_decisions.jsonl", b"", "application/x-ndjson")},
        )
        assert response.status_code == 401


class TestLexiconReviewBatchReadApi:
    @pytest.mark.asyncio
    async def test_list_batches(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batches_result = MagicMock()
        batches_result.scalars.return_value.all.return_value = [batch]
        mock_db.execute.side_effect = [user_result, batches_result]

        response = await client.get(
            "/api/lexicon-reviews/batches",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["id"] == str(batch.id)

    @pytest.mark.asyncio
    async def test_get_batch_detail_returns_404_for_non_owned_batch(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, batch_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch_id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Lexicon review batch not found"

    @pytest.mark.asyncio
    async def test_get_batch_items_filters_results(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id)
        item = make_item(batch.id, review_status="pending", review_required=True)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch.id}/items?review_status=pending&review_required=true",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["lemma"] == "bank"
        assert data[0]["review_status"] == "pending"
        assert data[0]["selected_source"] == "reranked"
        assert data[0]["selected_wn_synset_ids"] == ["bank.n.01"]
        assert data[0]["candidate_entries"][0]["definition"] == "a financial institution"
        assert data[0]["candidate_entries"][0]["deterministic_selected"] is True

    @pytest.mark.asyncio
    async def test_list_batch_items_supports_legacy_candidate_metadata_fields(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id)
        item = make_item(
            batch.id,
            review_status="pending",
            review_required=True,
            candidate_metadata=[
                {
                    "wn_synset_id": "bank.n.01",
                    "label": "bank",
                    "gloss": "a place that keeps money",
                    "part_of_speech": "noun",
                }
            ],
            deterministic_selected_wn_synset_ids=["bank.n.01"],
            reranked_selected_wn_synset_ids=None,
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch.id}/items",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data[0]["selected_source"] == "deterministic"
        assert data[0]["candidate_entries"][0]["canonical_label"] == "bank"
        assert data[0]["candidate_entries"][0]["gloss"] == "a place that keeps money"
        assert data[0]["candidate_entries"][0]["definition"] == "a place that keeps money"


class TestLexiconReviewItemUpdateApi:
    @pytest.mark.asyncio
    async def test_patch_item_review_decision(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id)
        item = make_item(batch.id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = item
        mock_db.execute.side_effect = [user_result, item_result]

        response = await client.patch(
            f"/api/lexicon-reviews/items/{item.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "review_status": "approved",
                "review_comment": "Looks good",
                "review_override_wn_synset_ids": ["bank.n.01", "bank.v.01"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["review_status"] == "approved"
        assert data["review_comment"] == "Looks good"
        assert data["review_override_wn_synset_ids"] == ["bank.n.01", "bank.v.01"]
        assert data["selected_source"] == "review_override"
        assert data["selected_wn_synset_ids"] == ["bank.n.01", "bank.v.01"]
        assert data["candidate_entries"][0]["definition"] == "a financial institution"
        assert data["reviewed_by"] == str(user_id)
        assert data["reviewed_at"] is not None


class TestLexiconReviewBatchPublishApi:
    @pytest.mark.asyncio
    async def test_publish_batch_publishes_approved_items_to_words_and_meanings(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id, status="reviewing")
        approved_item = make_item(
            batch.id,
            review_status="approved",
            deterministic_selected_wn_synset_ids=["bank.n.01"],
            reranked_selected_wn_synset_ids=["bank.v.01", "bank.n.01"],
            candidate_metadata=[
                {"wn_synset_id": "bank.v.01", "canonical_gloss": "to rely on something", "part_of_speech": "verb"},
                {"wn_synset_id": "bank.n.01", "canonical_gloss": "the land beside a river", "part_of_speech": "noun"},
            ],
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item]
        word_lookup_result = MagicMock()
        word_lookup_result.scalar_one_or_none.return_value = None
        existing_meanings_result = MagicMock()
        existing_meanings_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [user_result, batch_result, items_result, word_lookup_result, existing_meanings_result]

        def fake_flush():
            for call in mock_db.add.call_args_list:
                obj = call.args[0]
                if isinstance(obj, Word) and getattr(obj, "id", None) is None:
                    obj.id = uuid.uuid4()

        mock_db.flush.side_effect = fake_flush

        response = await client.post(
            f"/api/lexicon-reviews/batches/{batch.id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"] == str(batch.id)
        assert data["published_item_count"] == 1
        assert data["published_word_count"] == 1
        assert data["created_meaning_count"] == 2
        assert batch.status == "published"
        assert isinstance(batch.import_metadata, dict)
        added_objects = [call.args[0] for call in mock_db.add.call_args_list]
        added_words = [obj for obj in added_objects if isinstance(obj, Word)]
        added_meanings = [obj for obj in added_objects if isinstance(obj, Meaning)]
        assert len(added_words) == 1
        assert added_words[0].word == "bank"
        assert added_words[0].source_type == "lexicon_review_publish"
        assert len(added_meanings) == 2
        assert [meaning.definition for meaning in added_meanings] == ["to rely on something", "the land beside a river"]
        assert [meaning.part_of_speech for meaning in added_meanings] == ["verb", "noun"]

    @pytest.mark.asyncio
    async def test_publish_batch_replaces_lexicon_meanings_but_keeps_other_sources(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id, status="reviewing")
        approved_item = make_item(
            batch.id,
            review_status="approved",
            candidate_metadata=[
                {"wn_synset_id": "bank.n.01", "canonical_gloss": "the land beside a river", "part_of_speech": "noun"},
            ],
        )
        word = Word(id=uuid.uuid4(), word="bank", language="en")
        lexicon_meaning = Meaning(
            id=uuid.uuid4(),
            word_id=word.id,
            definition="old lexicon definition",
            part_of_speech="noun",
            order_index=0,
            source="lexicon_review_publish",
            source_reference="lexicon_review_batch:old-batch:lx_bank:0",
        )
        manual_meaning = Meaning(
            id=uuid.uuid4(),
            word_id=word.id,
            definition="manual definition",
            part_of_speech="noun",
            order_index=1,
            source="manual",
            source_reference="manual:1",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item]
        word_lookup_result = MagicMock()
        word_lookup_result.scalar_one_or_none.return_value = word
        existing_meanings_result = MagicMock()
        existing_meanings_result.scalars.return_value.all.return_value = [lexicon_meaning, manual_meaning]
        mock_db.execute.side_effect = [user_result, batch_result, items_result, word_lookup_result, existing_meanings_result]

        response = await client.post(
            f"/api/lexicon-reviews/batches/{batch.id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["updated_word_count"] == 1
        assert data["replaced_meaning_count"] == 1
        deleted_objects = [call.args[0] for call in mock_db.delete.call_args_list]
        assert deleted_objects == [lexicon_meaning]
        assert manual_meaning not in deleted_objects

    @pytest.mark.asyncio
    async def test_publish_batch_rejects_when_no_items_are_publishable(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id, status="reviewing")
        pending_item = make_item(batch.id, review_status="pending")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [pending_item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.post(
            f"/api/lexicon-reviews/batches/{batch.id}/publish",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "No approved lexicon review items are publishable"

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


class TestLexiconReviewBatchPublishPreviewApi:
    @pytest.mark.asyncio
    async def test_publish_preview_summarizes_publish_impact(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id, status="reviewing")
        approved_item = make_item(
            batch.id,
            review_status="approved",
            candidate_metadata=[
                {"wn_synset_id": "bank.n.01", "canonical_gloss": "a financial institution", "part_of_speech": "noun"},
                {"wn_synset_id": "bank.v.01", "canonical_gloss": "to deposit money", "part_of_speech": "verb"},
            ],
            reranked_selected_wn_synset_ids=["bank.n.01", "bank.v.01"],
        )
        existing_word = Word(id=uuid.uuid4(), word="bank", language="en")
        existing_lexicon_meaning = Meaning(
            id=uuid.uuid4(),
            word_id=existing_word.id,
            definition="old definition",
            part_of_speech="noun",
            order_index=0,
            source="lexicon_review_publish",
            source_reference="lexicon_review_batch:old:lx_bank:0",
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item]
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = existing_word
        meanings_result = MagicMock()
        meanings_result.scalars.return_value.all.return_value = [existing_lexicon_meaning]
        mock_db.execute.side_effect = [user_result, batch_result, items_result, word_result, meanings_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch.id}/publish-preview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["batch_id"] == str(batch.id)
        assert data["publishable_item_count"] == 1
        assert data["created_word_count"] == 0
        assert data["updated_word_count"] == 1
        assert data["replaced_meaning_count"] == 1
        assert data["created_meaning_count"] == 2
        assert data["skipped_item_count"] == 0
        assert len(data["items"]) == 1
        assert data["items"][0]["action"] == "update_word"
        assert data["items"][0]["existing_lexicon_meaning_count"] == 1
        assert data["items"][0]["new_meaning_count"] == 2
        mock_db.add.assert_not_called()
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_publish_preview_supports_legacy_gloss_metadata(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id, status="reviewing")
        approved_item = make_item(
            batch.id,
            review_status="approved",
            candidate_metadata=[
                {"wn_synset_id": "bank.n.01", "gloss": "a place that keeps money", "part_of_speech": "noun"},
            ],
            deterministic_selected_wn_synset_ids=["bank.n.01"],
            reranked_selected_wn_synset_ids=None,
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item]
        word_result = MagicMock()
        word_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, batch_result, items_result, word_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch.id}/publish-preview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["publishable_item_count"] == 1
        assert data["created_meaning_count"] == 1
        assert data["items"][0]["selected_synset_ids"] == ["bank.n.01"]

    @pytest.mark.asyncio
    async def test_publish_preview_returns_400_when_no_items_are_publishable(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(user_id, status="reviewing")
        pending_item = make_item(batch.id, review_status="pending")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [pending_item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch.id}/publish-preview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "No approved lexicon review items are publishable"

    @pytest.mark.asyncio
    async def test_publish_preview_returns_404_for_non_owned_batch(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch_id = uuid.uuid4()

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, batch_result]

        response = await client.get(
            f"/api/lexicon-reviews/batches/{batch_id}/publish-preview",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Lexicon review batch not found"
