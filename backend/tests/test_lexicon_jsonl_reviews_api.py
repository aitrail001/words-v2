import json
import uuid
from pathlib import Path

import pytest

from app.core.config import Settings, get_settings
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


def make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="jsonl-reviewer@example.com", password_hash="hashed", role=role)


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _compiled_rows() -> list[dict]:
    return [
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
            "phonetics": {
                "us": {"ipa": "/bæŋk/", "confidence": 0.99},
                "uk": {"ipa": "/bæŋk/", "confidence": 0.98},
                "au": {"ipa": "/bæŋk/", "confidence": 0.97},
            },
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
            "snapshot_id": "snapshot-001",
        },
        {
            "schema_version": "1.1.0",
            "entry_id": "phrase:break-a-leg",
            "entry_type": "phrase",
            "normalized_form": "break a leg",
            "source_provenance": [{"source": "snapshot"}],
            "entity_category": "general",
            "word": "break a leg",
            "part_of_speech": ["idiom"],
            "cefr_level": "B1",
            "frequency_rank": 5000,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [{"sense_id": "phrase-1", "definition": "good luck", "examples": [{"sentence": "Break a leg tonight.", "difficulty": "easy"}]}],
            "confusable_words": [],
            "generated_at": "2026-03-21T00:00:00Z",
            "display_form": "break a leg",
            "phrase_kind": "idiom",
            "snapshot_id": "snapshot-001",
        },
    ]


def _compiled_rows_with_warning() -> list[dict]:
    rows = _compiled_rows()
    rows[1]["source_provenance"] = []
    rows[1]["senses"] = [{"sense_id": "phrase-1", "definition": "good luck", "examples": []}]
    return rows


def _invalid_compiled_word_row() -> dict:
    row = _compiled_rows()[0]
    row["senses"] = []
    return row


def _compiled_reference_row() -> dict:
    return {
        "schema_version": "1.1.0",
        "entry_id": "rf_australia",
        "entry_type": "reference",
        "normalized_form": "australia",
        "source_provenance": [{"source": "reference_seed"}],
        "entity_category": "general",
        "word": "Australia",
        "part_of_speech": [],
        "cefr_level": "B1",
        "frequency_rank": 0,
        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
        "senses": [],
        "confusable_words": [],
        "generated_at": "2026-03-20T00:00:00Z",
        "reference_type": "country",
        "display_form": "Australia",
        "translation_mode": "localized",
        "brief_description": "A country in the Southern Hemisphere.",
        "pronunciation": "/ɔˈstreɪliə/",
        "localized_display_form": {"es": "Australia"},
        "localized_brief_description": {"es": "País del hemisferio sur."},
        "learner_tip": "Stress is on STRAY.",
        "localizations": [{"locale": "es", "display_form": "Australia", "translation_mode": "localized"}],
    }


def _compiled_reference_row_with_warning() -> dict:
    row = _compiled_reference_row()
    row["localizations"] = []
    return row


class TestLexiconJsonlReviewsApi:
    @pytest.mark.asyncio
    async def test_load_reads_compiled_rows_and_existing_decisions(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        decisions_path = tmp_path / "reviewed" / "review.decisions.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())
        _write_jsonl(
            decisions_path,
            [
                {
                    "schema_version": "lexicon_review_decision.v1",
                    "entry_id": "word:bank",
                    "entry_type": "word",
                    "decision": "approved",
                    "decision_reason": "ready",
                    "reviewed_by": str(user_id),
                    "reviewed_at": "2026-03-21T01:00:00Z",
                }
            ],
        )

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path), "decisions_path": str(decisions_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_filename"] == "words.enriched.jsonl"
        assert data["total_items"] == 2
        assert data["approved_count"] == 1
        assert data["pending_count"] == 1
        assert data["items"][0]["entry_id"] == "word:bank"
        assert data["items"][0]["review_status"] == "approved"
        assert data["items"][0]["decision_reason"] == "ready"
        assert data["items"][1]["entry_id"] == "phrase:break-a-leg"
        assert data["items"][1]["review_status"] == "pending"

    @pytest.mark.asyncio
    async def test_load_accepts_valid_reference_compiled_row(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "references.enriched.jsonl"
        _write_jsonl(compiled_path, [_compiled_reference_row()])

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["artifact_filename"] == "references.enriched.jsonl"
        assert data["total_items"] == 1
        assert data["pending_count"] == 1
        assert data["items"][0]["entry_id"] == "rf_australia"
        assert data["items"][0]["entry_type"] == "reference"
        assert data["items"][0]["review_status"] == "pending"

    @pytest.mark.asyncio
    async def test_load_includes_triage_warnings_and_reviewer_summary(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        _write_jsonl(compiled_path, _compiled_rows_with_warning())

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["warning_count"] == 0
        assert data["items"][0]["review_priority"] == "normal"
        assert data["items"][0]["review_summary"]["sense_count"] == 1
        assert data["items"][0]["review_summary"]["provenance_sources"] == ["snapshot"]
        assert data["items"][0]["review_summary"]["primary_definition"] == "a financial institution"

        assert data["items"][1]["warning_count"] == 2
        assert data["items"][1]["review_priority"] == "warning"
        assert data["items"][1]["warning_labels"] == ["missing_source_provenance", "missing_examples"]
        assert data["items"][1]["review_summary"]["sense_count"] == 1
        assert data["items"][1]["review_summary"]["primary_definition"] == "good luck"
        assert data["items"][1]["review_summary"]["provenance_sources"] == []

    @pytest.mark.asyncio
    async def test_load_reference_rows_use_shared_warning_labels(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "references.enriched.jsonl"
        _write_jsonl(compiled_path, [_compiled_reference_row_with_warning()])

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["items"][0]["entry_type"] == "reference"
        assert data["items"][0]["review_priority"] == "warning"
        assert data["items"][0]["warning_labels"] == ["missing_localizations"]
        assert data["items"][0]["review_summary"]["primary_definition"] is None

    @pytest.mark.asyncio
    async def test_load_rejects_invalid_compiled_word_rows(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        _write_jsonl(compiled_path, [_invalid_compiled_word_row()])

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path)},
        )

        assert response.status_code == 400
        assert "senses must be a non-empty list" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_item_writes_sidecar_decision_row(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        decisions_path = tmp_path / "reviewed" / "review.decisions.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())

        response = await client.patch(
            "/api/lexicon-jsonl-reviews/items/word:bank",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "artifact_path": str(compiled_path),
                "decisions_path": str(decisions_path),
                "review_status": "approved",
                "decision_reason": "ready for import",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["entry_id"] == "word:bank"
        assert data["review_status"] == "approved"
        assert data["decision_reason"] == "ready for import"

        persisted_rows = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(persisted_rows) == 1
        assert persisted_rows[0]["entry_id"] == "word:bank"
        assert persisted_rows[0]["decision"] == "approved"
        assert persisted_rows[0]["decision_reason"] == "ready for import"

    @pytest.mark.asyncio
    async def test_patch_item_can_reopen_existing_sidecar_decision(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        decisions_path = tmp_path / "reviewed" / "review.decisions.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())
        _write_jsonl(
            decisions_path,
            [
                {"entry_id": "word:bank", "entry_type": "word", "decision": "approved", "decision_reason": "ready"},
            ],
        )

        response = await client.patch(
            "/api/lexicon-jsonl-reviews/items/word:bank",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "artifact_path": str(compiled_path),
                "decisions_path": str(decisions_path),
                "review_status": "pending",
                "decision_reason": "needs another look",
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["review_status"] == "pending"
        assert data["decision_reason"] == "needs another look"

        persisted_rows = [json.loads(line) for line in decisions_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        assert len(persisted_rows) == 1
        assert persisted_rows[0]["decision"] == "reopened"
        assert persisted_rows[0]["decision_reason"] == "needs another look"

    @pytest.mark.asyncio
    async def test_materialize_writes_outputs_via_review_materialize(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        decisions_path = tmp_path / "reviewed" / "review.decisions.jsonl"
        output_dir = tmp_path / "reviewed"
        _write_jsonl(compiled_path, _compiled_rows())
        _write_jsonl(
            decisions_path,
            [
                {"entry_id": "word:bank", "entry_type": "word", "decision": "approved"},
                {"entry_id": "phrase:break-a-leg", "entry_type": "phrase", "decision": "rejected", "decision_reason": "regen"},
            ],
        )

        response = await client.post(
            "/api/lexicon-jsonl-reviews/materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "artifact_path": str(compiled_path),
                "decisions_path": str(decisions_path),
                "output_dir": str(output_dir),
            },
        )

        assert response.status_code == 200
        data = response.json()
        assert data["approved_count"] == 1
        assert data["rejected_count"] == 1
        assert data["regenerate_count"] == 1
        assert data["approved_output_path"] == str(output_dir / "approved.jsonl")
        assert (output_dir / "approved.jsonl").exists()
        assert (output_dir / "rejected.jsonl").exists()
        assert (output_dir / "regenerate.jsonl").exists()

    @pytest.mark.asyncio
    async def test_load_rejects_paths_outside_allowed_roots(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path / "safe-root"))

        outside_path = tmp_path / "outside.jsonl"
        _write_jsonl(outside_path, _compiled_rows())

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(outside_path)},
        )

        assert response.status_code == 400
        assert "allowed roots" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_patch_rejects_non_sidecar_decisions_path_within_allowed_roots(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        compiled_path = tmp_path / "words.enriched.jsonl"
        dangerous_target = tmp_path / "README.md"
        _write_jsonl(compiled_path, _compiled_rows())
        dangerous_target.write_text("do not overwrite", encoding="utf-8")

        response = await client.patch(
            "/api/lexicon-jsonl-reviews/items/word:bank",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "artifact_path": str(compiled_path),
                "decisions_path": str(dangerous_target),
                "review_status": "approved",
                "decision_reason": "ready",
            },
        )

        assert response.status_code == 400
        assert "sidecar filename" in response.json()["detail"]
        assert dangerous_target.read_text(encoding="utf-8") == "do not overwrite"

    @pytest.mark.asyncio
    async def test_materialize_rejects_output_dir_outside_artifact_directory(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        artifact_dir = tmp_path / "snapshot"
        artifact_dir.mkdir()
        compiled_path = artifact_dir / "words.enriched.jsonl"
        decisions_path = artifact_dir / "reviewed" / "review.decisions.jsonl"
        outside_output_dir = tmp_path / "other-output"
        _write_jsonl(compiled_path, _compiled_rows())
        _write_jsonl(decisions_path, [{"entry_id": "word:bank", "entry_type": "word", "decision": "approved"}])

        response = await client.post(
            "/api/lexicon-jsonl-reviews/materialize",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "artifact_path": str(compiled_path),
                "decisions_path": str(decisions_path),
                "output_dir": str(outside_output_dir),
            },
        )

        assert response.status_code == 400
        assert "artifact directory" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_load_defaults_decisions_and_output_to_reviewed_dir(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        artifact_dir = tmp_path / "snapshot"
        artifact_dir.mkdir()
        compiled_path = artifact_dir / "words.enriched.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())

        response = await client.post(
            "/api/lexicon-jsonl-reviews/load",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path)},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["decisions_path"] == str(artifact_dir / "reviewed" / "review.decisions.jsonl")
        assert data["output_dir"] == str(artifact_dir / "reviewed")

    @pytest.mark.asyncio
    async def test_download_returns_reviewed_outputs_without_materializing(self, client, mock_db, tmp_path: Path):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        mock_db.execute.return_value.scalar_one_or_none.return_value = make_user(user_id)
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(tmp_path))

        artifact_dir = tmp_path / "snapshot"
        artifact_dir.mkdir()
        compiled_path = artifact_dir / "words.enriched.jsonl"
        decisions_path = artifact_dir / "reviewed" / "review.decisions.jsonl"
        _write_jsonl(compiled_path, _compiled_rows())
        _write_jsonl(
            decisions_path,
            [
                {"entry_id": "word:bank", "entry_type": "word", "decision": "approved"},
                {"entry_id": "phrase:break-a-leg", "entry_type": "phrase", "decision": "rejected", "decision_reason": "regen"},
            ],
        )

        response = await client.post(
            "/api/lexicon-jsonl-reviews/download/approved",
            headers={"Authorization": f"Bearer {token}"},
            json={"artifact_path": str(compiled_path), "decisions_path": str(decisions_path)},
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("application/x-ndjson")
        rows = [json.loads(line) for line in response.text.splitlines() if line.strip()]
        assert len(rows) == 1
        assert rows[0]["entry_id"] == "word:bank"
