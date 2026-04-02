import hashlib
import json
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.main import app
from app.api import lexicon_compiled_reviews
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
                    "examples": [{"sentence": "She went to the bank.", "difficulty": "A1"}],
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
    compiled_payload_sha256 = overrides.pop("compiled_payload_sha256", None)
    if compiled_payload_sha256 is None:
        compiled_payload_sha256 = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
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
        compiled_payload_sha256=compiled_payload_sha256,
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
    async def test_import_compiled_batch_sanitizes_control_characters_before_persist(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        existing_batch_result = MagicMock()
        existing_batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, existing_batch_result]

        row = make_item(uuid.uuid4()).compiled_payload
        row["senses"][0]["translations"]["es"]["definition"] = "da\x00nar o impedir"
        row["senses"][0]["translations"]["ar"]["examples"][0] = "\x00هذا الشكل"

        response = await client.post(
            "/api/lexicon-compiled-reviews/batches/import",
            headers={"Authorization": f"Bearer {token}"},
            data={"source_reference": "snapshot-001"},
            files={"file": ("words.enriched.jsonl", build_jsonl_bytes(row), "application/x-ndjson")},
        )

        assert response.status_code == 201
        persisted_items = [
            call.args[0]
            for call in mock_db.add.call_args_list
            if isinstance(call.args[0], LexiconArtifactReviewItem)
        ]
        assert len(persisted_items) == 1
        persisted_payload = persisted_items[0].compiled_payload
        assert persisted_payload["senses"][0]["translations"]["es"]["definition"] == "danar o impedir"
        assert persisted_payload["senses"][0]["translations"]["ar"]["examples"][0] == "هذا الشكل"

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
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        mock_db.execute.side_effect = [user_result, batch_result, count_result, items_result]

        response = await client.get(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/items",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 1
        assert data["limit"] == 50
        assert data["offset"] == 0
        assert data["has_more"] is False
        assert len(data["items"]) == 1
        assert data["items"][0]["entry_id"] == "word:bank"
        assert data["items"][0]["validator_status"] == "warn"
        assert data["items"][0]["qc_status"] == "fail"
        assert data["items"][0]["compiled_payload"]["word"] == "bank"

    @pytest.mark.asyncio
    async def test_list_items_supports_pagination_filters_and_search(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id, total_items=3, pending_count=1, approved_count=1, rejected_count=1)
        first = make_item(batch.id, id=uuid.uuid4(), entry_id="word:bank", display_text="bank", normalized_form="bank", review_status="pending")
        second = make_item(batch.id, id=uuid.uuid4(), entry_id="word:harbor", display_text="harbor", normalized_form="harbor", review_status="approved")

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [first, second]
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3
        mock_db.execute.side_effect = [user_result, batch_result, count_result, items_result]

        response = await client.get(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/items?limit=2&offset=1&status=approved&search=harbor",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 3
        assert data["limit"] == 2
        assert data["offset"] == 1
        assert data["has_more"] is False
        assert [item["entry_id"] for item in data["items"]] == ["word:bank", "word:harbor"]

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
        total_count_result = MagicMock()
        total_count_result.scalar_one.return_value = 1
        approved_count_result = MagicMock()
        approved_count_result.scalar_one.return_value = 1
        rejected_count_result = MagicMock()
        rejected_count_result.scalar_one.return_value = 0
        mock_db.execute.side_effect = [
            user_result,
            item_result,
            batch_result,
            regen_request_result,
            total_count_result,
            approved_count_result,
            rejected_count_result,
        ]

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
    async def test_materialize_writes_reviewed_outputs_under_snapshot_dir(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id, source_reference="snapshot-001")
        approved_item = make_item(batch.id, review_status="approved", import_eligible=True)
        rejected_item = make_item(
            batch.id,
            entry_id="phrase:break-a-leg",
            entry_type="phrase",
            display_text="break a leg",
            normalized_form="break a leg",
            review_status="rejected",
            regen_requested=True,
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item, rejected_item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))
        (tmp_path / "snapshot-001").mkdir()

        response = await client.post(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

        assert response.status_code == 200
        data = response.json()
        reviewed_dir = tmp_path / "snapshot-001" / "reviewed"
        assert data["approved_output_path"] == str(reviewed_dir / "approved.jsonl")
        assert data["decisions_output_path"] == str(reviewed_dir / "review.decisions.jsonl")
        assert (reviewed_dir / "approved.jsonl").exists()
        assert (reviewed_dir / "rejected.jsonl").exists()
        assert (reviewed_dir / "regenerate.jsonl").exists()

    @pytest.mark.asyncio
    async def test_materialize_normalizes_db_backed_payload_values_before_jsonl_write(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id, source_reference="snapshot-001")
        approved_item = make_item(
            batch.id,
            review_status="approved",
            import_eligible=True,
            compiled_payload_sha256="z" * 64,
            compiled_payload={
                **make_item(batch.id).compiled_payload,
                "generated_at": datetime(2026, 3, 21, 0, 0, tzinfo=timezone.utc),
                "debug_uuid": uuid.UUID("12345678-1234-5678-1234-567812345678"),
                "confidence_score": Decimal("0.75"),
            },
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))
        (tmp_path / "snapshot-001").mkdir()

        response = await client.post(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

        assert response.status_code == 200
        reviewed_dir = tmp_path / "snapshot-001" / "reviewed"
        approved_rows = [json.loads(line) for line in (reviewed_dir / "approved.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        assert approved_rows[0]["generated_at"] == "2026-03-21T00:00:00+00:00"
        assert approved_rows[0]["debug_uuid"] == "12345678-1234-5678-1234-567812345678"
        assert approved_rows[0]["confidence_score"] == 0.75

    @pytest.mark.asyncio
    async def test_materialize_returns_actionable_error_when_output_path_is_not_writable(
        self,
        client,
        mock_db,
        tmp_path: Path,
        monkeypatch,
    ):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id, source_reference="snapshot-001")
        approved_item = make_item(batch.id, review_status="approved", import_eligible=True)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [approved_item]
        mock_db.execute.side_effect = [user_result, batch_result, items_result]
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))
        reviewed_dir = tmp_path / "snapshot-001" / "reviewed"
        (tmp_path / "snapshot-001").mkdir()

        original_open = lexicon_compiled_reviews.Path.open

        def failing_open(path: Path, *args, **kwargs):
            if path == reviewed_dir / "review.decisions.jsonl" and kwargs.get("mode", args[0] if args else "r").startswith("w"):
                raise OSError(30, "Read-only file system")
            return original_open(path, *args, **kwargs)

        monkeypatch.setattr(lexicon_compiled_reviews.Path, "open", failing_open)

        response = await client.post(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == f"Output path is not writable: {reviewed_dir / 'review.decisions.jsonl'}"

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
    async def test_delete_batch_removes_review_staging_batch(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        mock_db.execute.side_effect = [user_result, batch_result]

        response = await client.delete(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 204
        mock_db.delete.assert_called_once_with(batch)
        mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_delete_batch_returns_404_when_missing(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = None
        mock_db.execute.side_effect = [user_result, batch_result]

        response = await client.delete(
            f"/api/lexicon-compiled-reviews/batches/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Compiled review batch not found"

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
        total_count_result = MagicMock()
        total_count_result.scalar_one.return_value = 1
        approved_count_result = MagicMock()
        approved_count_result.scalar_one.return_value = 0
        rejected_count_result = MagicMock()
        rejected_count_result.scalar_one.return_value = 1
        mock_db.execute.side_effect = [
            user_result,
            item_result,
            batch_result,
            regen_request_result,
            total_count_result,
            approved_count_result,
            rejected_count_result,
        ]

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

    @pytest.mark.asyncio
    async def test_bulk_patch_batch_updates_all_items_and_batch_counts(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        user = make_user(user_id)
        batch = make_batch(created_by=uuid.uuid4(), total_items=2, pending_count=2)
        item_one = make_item(batch.id)
        item_two = make_item(
            batch.id,
            id=uuid.uuid4(),
            entry_id="word:harbor",
            normalized_form="harbor",
            display_text="harbor",
            compiled_payload={**make_item(batch.id).compiled_payload, "entry_id": "word:harbor", "normalized_form": "harbor", "word": "harbor"},
        )

        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = user
        batch_result = MagicMock()
        batch_result.scalar_one_or_none.return_value = batch
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = [item_one, item_two]
        regen_request_result_one = MagicMock()
        regen_request_result_one.scalar_one_or_none.return_value = None
        regen_request_result_two = MagicMock()
        regen_request_result_two.scalar_one_or_none.return_value = None
        total_count_result = MagicMock()
        total_count_result.scalar_one.return_value = 2
        approved_count_result = MagicMock()
        approved_count_result.scalar_one.return_value = 2
        rejected_count_result = MagicMock()
        rejected_count_result.scalar_one.return_value = 0
        mock_db.execute.side_effect = [
            user_result,
            batch_result,
            items_result,
            regen_request_result_one,
            regen_request_result_two,
            total_count_result,
            approved_count_result,
            rejected_count_result,
        ]

        response = await client.post(
            f"/api/lexicon-compiled-reviews/batches/{batch.id}/bulk-update",
            headers={"Authorization": f"Bearer {token}"},
            json={"review_status": "approved", "decision_reason": "bulk ready"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["batch"]["approved_count"] == 2
        assert data["batch"]["pending_count"] == 0
        assert all(item["review_status"] == "approved" for item in data["items"])
        assert batch.status == "completed"
