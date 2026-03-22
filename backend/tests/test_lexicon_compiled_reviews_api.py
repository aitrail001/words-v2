import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_regeneration_request import LexiconRegenerationRequest
from app.models.user import User


def make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="compiled-reviewer@example.com", password_hash="hashed", role=role)


def make_batch(**overrides) -> LexiconArtifactReviewBatch:
    return LexiconArtifactReviewBatch(
        id=overrides.pop("id", uuid.uuid4()),
        artifact_family=overrides.pop("artifact_family", "compiled_words"),
        artifact_filename=overrides.pop("artifact_filename", "words.enriched.jsonl"),
        artifact_sha256=overrides.pop("artifact_sha256", "a" * 64),
        artifact_row_count=overrides.pop("artifact_row_count", 1),
        compiled_schema_version=overrides.pop("compiled_schema_version", "1.1.0"),
        snapshot_id=overrides.pop("snapshot_id", "snapshot-001"),
        source_type=overrides.pop("source_type", "lexicon_compiled_export"),
        source_reference=overrides.pop("source_reference", "snapshot-001"),
        status=overrides.pop("status", "pending_review"),
        total_items=overrides.pop("total_items", 1),
        pending_count=overrides.pop("pending_count", 1),
        approved_count=overrides.pop("approved_count", 0),
        rejected_count=overrides.pop("rejected_count", 0),
        created_by=overrides.pop("created_by", None),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        updated_at=overrides.pop("updated_at", datetime.now(timezone.utc)),
        completed_at=overrides.pop("completed_at", None),
        **overrides,
    )


def make_item(batch_id: uuid.UUID, **overrides) -> LexiconArtifactReviewItem:
    payload = overrides.pop(
        "compiled_payload",
        {
            "schema_version": "1.1.0",
            "entry_id": "word:bank",
            "entry_type": "word",
            "normalized_form": "bank",
            "source_provenance": [{"source": "snapshot"}],
            "entity_category": "general",
            "word": "bank",
            "part_of_speech": ["noun"],
            "cefr_level": "B1",
            "frequency_rank": 100,
            "forms": {"plural_forms": ["banks"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [
                {
                    "sense_id": "sense-bank-1",
                    "definition": "a financial institution",
                    "examples": [{"sentence": "She went to the bank.", "difficulty": "easy"}],
                    "translations": {
                        "zh-Hans": {"definition": "银行", "usage_note": "常见词义", "examples": ["她去了银行。"]},
                        "es": {"definition": "banco", "usage_note": "uso comun", "examples": ["Ella fue al banco."]},
                        "ar": {"definition": "بنك", "usage_note": "معنى شائع", "examples": ["ذهبت إلى البنك."]},
                        "pt-BR": {"definition": "banco", "usage_note": "uso comum", "examples": ["Ela foi ao banco."]},
                        "ja": {"definition": "銀行", "usage_note": "よくある意味", "examples": ["彼女は銀行に行った。"]},
                    },
                }
            ],
            "confusable_words": [],
            "generated_at": "2026-03-21T00:00:00Z",
        },
    )
    return LexiconArtifactReviewItem(
        id=overrides.pop("id", uuid.uuid4()),
        batch_id=batch_id,
        entry_id=overrides.pop("entry_id", "word:bank"),
        entry_type=overrides.pop("entry_type", "word"),
        normalized_form=overrides.pop("normalized_form", "bank"),
        display_text=overrides.pop("display_text", "bank"),
        entity_category=overrides.pop("entity_category", "general"),
        language=overrides.pop("language", "en"),
        frequency_rank=overrides.pop("frequency_rank", 100),
        cefr_level=overrides.pop("cefr_level", "B1"),
        review_status=overrides.pop("review_status", "pending"),
        review_priority=overrides.pop("review_priority", 100),
        validator_status=overrides.pop("validator_status", "warn"),
        validator_issues=overrides.pop("validator_issues", [{"code": "missing_usage_note"}]),
        qc_status=overrides.pop("qc_status", "fail"),
        qc_score=overrides.pop("qc_score", 0.4),
        qc_issues=overrides.pop("qc_issues", [{"code": "example_too_literal"}]),
        regen_requested=overrides.pop("regen_requested", False),
        import_eligible=overrides.pop("import_eligible", False),
        decision_reason=overrides.pop("decision_reason", None),
        reviewed_by=overrides.pop("reviewed_by", None),
        reviewed_at=overrides.pop("reviewed_at", None),
        compiled_payload=payload,
        compiled_payload_sha256=overrides.pop(
            "compiled_payload_sha256",
            hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest(),
        ),
        search_text=overrides.pop("search_text", "bank financial institution"),
        created_at=overrides.pop("created_at", datetime.now(timezone.utc)),
        updated_at=overrides.pop("updated_at", datetime.now(timezone.utc)),
        **overrides,
    )


def build_jsonl_bytes(*rows: dict) -> bytes:
    return "".join(json.dumps(row) + "\n" for row in rows).encode("utf-8")


class TestLexiconCompiledReviewApi:
    @pytest.mark.asyncio
    async def test_import_compiled_batch_success(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_batch_result = MagicMock()
        existing_batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_batch_result]

        row = make_item(uuid.uuid4()).compiled_payload

        response = await client.post(
            "/api/lexicon-compiled-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            data={"source_reference": "snapshot-001"},
            files={"file": ("words.enriched.jsonl", build_jsonl_bytes(row), "application/x-ndjson")},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["artifact_family"] == "compiled_words"
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert data["total_items"] == 1
        assert data["pending_count"] == 1
        assert data["approved_count"] == 0

    @pytest.mark.asyncio
    async def test_list_items_returns_compiled_metadata(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id)
        item = make_item(batch.id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.get(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/items",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["entry_id"] == "word:bank"
        assert data[0]["validator_status"] == "warn"
        assert data[0]["qc_status"] == "fail"
        assert data[0]["compiled_payload"]["word"] == "bank"

    @pytest.mark.asyncio
    async def test_patch_item_updates_decision(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=uuid.uuid4())
        item = make_item(batch.id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = item
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        regen_request_result = MagicMock()
        regen_request_result.scalar_one_or_none.return_value = None
        all_items_result = MagicMock()
        all_items_result.scalars.return_value.all.return_value = [item]
        mock_db.execute.side_effect = [user_result, item_result, batch_result, regen_request_result, all_items_result]

        response = await client.patch(
            f"/api/lexicon-compiled-reviews/items/{item.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"review_status": "approved", "decision_reason": "looks good"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["review_status"] == "approved"
        assert data["import_eligible"] is True
        assert data["regen_requested"] is False
        assert data["decision_reason"] == "looks good"
        assert data["reviewed_by"] == str(user_id)
        assert batch.approved_count == 1
        assert batch.pending_count == 0
        assert batch.status == "completed"

    @pytest.mark.asyncio
    async def test_export_approved_rows_returns_jsonl(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id)
        approved_item = make_item(batch.id, review_status="approved", import_eligible=True)
        rejected_item = make_item(batch.id, entry_id="phrase:break-a-leg", entry_type="phrase", display_text="break a leg", normalized_form="break a leg", review_status="rejected", regen_requested=True)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item, rejected_item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]

        response = await client.get(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/export/approved",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        lines = [json.loads(line) for line in response.text.splitlines()]
        assert len(lines) == 1
        assert lines[0]["entry_id"] == "word:bank"

    @pytest.mark.asyncio
    async def test_import_returns_existing_batch_for_duplicate_artifact_across_admins(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        existing_batch = make_batch(created_by=uuid.uuid4())

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_batch_result = MagicMock()
        existing_batch_result.scalar_one_or_none.return_value = existing_batch
        mock_db.execute.side_effect = [user_result, existing_batch_result]

        row = make_item(uuid.uuid4()).compiled_payload
        response = await client.post(
            "/api/lexicon-compiled-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            files={"file": ("words.enriched.jsonl", build_jsonl_bytes(row), "application/x-ndjson")},
        )

        assert response.status_code == 201
        assert response.json()["id"] == str(existing_batch.id)

    @pytest.mark.asyncio
    async def test_import_compiled_batch_by_path_success(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_batch_result = MagicMock()
        existing_batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_batch_result]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        snapshot_dir = tmp_path / "snapshot-001"
        snapshot_dir.mkdir()
        compiled_path = snapshot_dir / "words.enriched.jsonl"
        compiled_path.write_bytes(build_jsonl_bytes(make_item(uuid.uuid4()).compiled_payload))

        response = await client.post(
            "/api/lexicon-compiled-reviews/batches/import-by-path",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path), "source_reference": "snapshot-001"},
        )

        assert response.status_code == 201
        data = response.json()
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert data["artifact_family"] == "compiled_words"
        assert data["source_reference"] == "snapshot-001"

    @pytest.mark.asyncio
    async def test_import_compiled_batch_by_path_rejects_unsafe_paths(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        mock_db.execute.side_effect = [user_result]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        response = await client.post(
            "/api/lexicon-compiled-reviews/batches/import-by-path",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": "/tmp/not-allowed/words.enriched.jsonl"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Path must stay within the allowed roots"

    @pytest.mark.asyncio
    async def test_patch_rejected_item_creates_regeneration_request_and_decision_export(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=uuid.uuid4())
        item = make_item(batch.id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        item_result = MagicMock()
        item_result.scalar_one_or_none.return_value = item
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        regen_request_result = MagicMock()
        regen_request_result.scalar_one_or_none.return_value = None
        all_items_result = MagicMock()
        all_items_result.scalars.return_value.all.return_value = [item]
        mock_db.execute.side_effect = [user_result, item_result, batch_result, regen_request_result, all_items_result]

        patch_response = await client.patch(
            f"/api/lexicon-compiled-reviews/items/{item.id}",
            headers={"Authorization": f"Bearer {token}"},
            json={"review_status": "rejected", "decision_reason": "needs regeneration"},
        )

        assert patch_response.status_code == 200
        assert patch_response.json()["regen_requested"] is True
        added_regeneration_requests = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if call.args and isinstance(call.args[0], LexiconRegenerationRequest)
        ]
        assert len(added_regeneration_requests) == 1
        assert added_regeneration_requests[0].entry_id == "word:bank"
        assert batch.rejected_count == 1
        assert batch.pending_count == 0

        user_result_2 = MagicMock()
        user_result_2.scalar_one_or_none.return_value = user
        batch_result_2 = MagicMock()
        batch_result_2.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item]
        mock_db.execute.side_effect = [user_result_2, batch_result_2, items_result]

        export_response = await client.get(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/export/decisions",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert export_response.status_code == 200
        lines = [json.loads(line) for line in export_response.text.splitlines()]
        assert lines == [
            {
                "schema_version": "lexicon_review_decision.v1",
                "artifact_sha256": batch.artifact_sha256,
                "entry_id": "word:bank",
                "entry_type": "word",
                "decision": "rejected",
                "decision_reason": "needs regeneration",
                "compiled_payload_sha256": item.compiled_payload_sha256,
                "reviewed_by": str(user_id),
                "reviewed_at": item.reviewed_at.isoformat().replace("+00:00", "Z"),
            }
        ]
