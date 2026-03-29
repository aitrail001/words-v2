import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.dialects import postgresql

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.api.lexicon_ops import _voice_storage_rewrite_query
from app.main import app
from app.models.user import User


def _make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="ops@example.com", password_hash="hashed", role=role)


def _write_jsonl(path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.execute = AsyncMock()
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.set = AsyncMock(return_value=True)
    return r


@pytest.fixture
async def client(mock_db, mock_redis):
    async def override_get_db():
        yield mock_db

    def override_get_redis():
        return mock_redis

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_redis] = override_get_redis

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


@pytest.fixture
def snapshot_root_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "snapshots"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LEXICON_SNAPSHOT_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


@pytest.fixture
def voice_root_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "voice"
    root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("LEXICON_VOICE_ROOT", str(root))
    get_settings.cache_clear()
    yield root
    get_settings.cache_clear()


def _mock_authenticated_user(mock_db, user: User) -> None:
    user_result = MagicMock()
    user_result.scalar_one_or_none.return_value = user
    mock_db.execute.side_effect = [user_result]


class TestLexiconOpsAdminAccess:
    @pytest.mark.asyncio
    async def test_list_snapshots_requires_admin(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id, role="user"))

        response = await client.get(
            "/api/lexicon-ops/snapshots",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 403
        assert response.json()["detail"] == "Admin access required"


class TestLexiconOpsSnapshotListing:
    @pytest.mark.asyncio
    async def test_list_snapshots_returns_empty_when_root_missing(self, client, mock_db, monkeypatch):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        missing_root = "/tmp/lexicon-ops-missing-root-do-not-create"
        monkeypatch.setenv("LEXICON_SNAPSHOT_ROOT", missing_root)
        get_settings.cache_clear()

        response = await client.get(
            "/api/lexicon-ops/snapshots",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert response.json() == []

    @pytest.mark.asyncio
    async def test_list_snapshots_returns_counts_and_flags(self, client, mock_db, snapshot_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        words_1000 = snapshot_root_env / "words-1000"
        words_1000.mkdir()
        _write_jsonl(
            words_1000 / "lexemes.jsonl",
            [{"snapshot_id": "lexicon-20260312-wordnet-wordfreq", "lexeme_id": "lx_bank", "lemma": "bank"}],
        )
        _write_jsonl(words_1000 / "ambiguous_forms.jsonl", [{"surface_form": "ringed"}])
        _write_jsonl(words_1000 / "words.enriched.jsonl", [{"word": "bank", "senses": []}])

        demo = snapshot_root_env / "demo"
        demo.mkdir()
        _write_jsonl(
            demo / "lexemes.jsonl",
            [{"snapshot_id": "lexicon-20260311-wordnet-wordfreq", "lexeme_id": "lx_run", "lemma": "run"}],
        )
        response = await client.get(
            "/api/lexicon-ops/snapshots",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        by_snapshot = {item["snapshot"]: item for item in payload}
        assert set(by_snapshot.keys()) == {"words-1000", "demo"}

        words_item = by_snapshot["words-1000"]
        assert words_item["snapshot_id"] == "lexicon-20260312-wordnet-wordfreq"
        assert words_item["artifact_counts"]["lexemes"] == 1
        assert words_item["artifact_counts"]["compiled_words"] == 1
        assert words_item["artifact_counts"]["ambiguous_forms"] == 1
        assert words_item["has_compiled_export"] is True
        assert words_item["has_ambiguous_forms"] is True

        demo_item = by_snapshot["demo"]
        assert demo_item["has_enrichments"] is False

    @pytest.mark.asyncio
    async def test_list_snapshots_includes_workflow_metadata(self, client, mock_db, snapshot_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        base_only = snapshot_root_env / "base-only"
        base_only.mkdir()
        _write_jsonl(
            base_only / "lexemes.jsonl",
            [{"snapshot_id": "snapshot-base", "lexeme_id": "lx_bank", "lemma": "bank"}],
        )

        compiled_ready = snapshot_root_env / "compiled-ready"
        compiled_ready.mkdir()
        _write_jsonl(
            compiled_ready / "words.enriched.jsonl",
            [{"entry_id": "word:bank", "entry_type": "word", "word": "bank", "senses": []}],
        )

        approved_ready = snapshot_root_env / "approved-ready"
        approved_ready.mkdir()
        _write_jsonl(
            approved_ready / "words.enriched.jsonl",
            [{"entry_id": "word:run", "entry_type": "word", "word": "run", "senses": []}],
        )
        _write_jsonl(
            approved_ready / "reviewed" / "approved.jsonl",
            [{"entry_id": "word:run", "entry_type": "word", "word": "run", "senses": []}],
        )

        response = await client.get(
            "/api/lexicon-ops/snapshots",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        by_snapshot = {item["snapshot"]: item for item in response.json()}

        base_item = by_snapshot["base-only"]
        assert base_item["workflow_stage"] == "base_artifacts"
        assert base_item["recommended_action"] == "run_enrich"
        assert base_item["preferred_review_artifact_path"] is None
        assert base_item["preferred_import_artifact_path"] is None
        assert any("enrich" in step for step in base_item["outside_portal_steps"])

        compiled_item = by_snapshot["compiled-ready"]
        assert compiled_item["workflow_stage"] == "compiled_ready_for_review"
        assert compiled_item["recommended_action"] == "open_compiled_review"
        assert compiled_item["preferred_review_artifact_path"] == str(compiled_ready / "words.enriched.jsonl")
        assert compiled_item["preferred_import_artifact_path"] is None
        assert any("reviewed/approved.jsonl" in step for step in compiled_item["outside_portal_steps"])

        approved_item = by_snapshot["approved-ready"]
        assert approved_item["workflow_stage"] == "approved_ready_for_import"
        assert approved_item["recommended_action"] == "open_import_db"
        assert approved_item["preferred_review_artifact_path"] == str(approved_ready / "words.enriched.jsonl")
        assert approved_item["preferred_import_artifact_path"] == str(approved_ready / "reviewed" / "approved.jsonl")
        assert any("import-db" in step for step in approved_item["outside_portal_steps"])


class TestLexiconOpsSnapshotDetail:
    @pytest.mark.asyncio
    async def test_get_snapshot_detail_returns_artifacts(self, client, mock_db, snapshot_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        snapshot_dir = snapshot_root_env / "words-1000"
        snapshot_dir.mkdir()
        _write_jsonl(
            snapshot_dir / "lexemes.jsonl",
            [{"snapshot_id": "lexicon-20260312-wordnet-wordfreq", "lexeme_id": "lx_bank", "lemma": "bank"}],
        )
        _write_jsonl(snapshot_dir / "senses.jsonl", [{"snapshot_id": "lexicon-20260312-wordnet-wordfreq", "sense_id": "sn_bank_1"}])
        _write_jsonl(snapshot_dir / "enrichments.jsonl", [{"snapshot_id": "lexicon-20260312-wordnet-wordfreq", "sense_id": "sn_bank_1"}])
        _write_jsonl(snapshot_dir / "words.enriched.jsonl", [{"word": "bank", "senses": []}])
        (snapshot_dir / "notes.json").write_text("{}", encoding="utf-8")

        response = await client.get(
            "/api/lexicon-ops/snapshots/words-1000",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["snapshot"] == "words-1000"
        assert payload["snapshot_id"] == "lexicon-20260312-wordnet-wordfreq"
        assert payload["artifact_counts"]["lexemes"] == 1
        assert payload["artifact_counts"]["enrichments"] == 1
        assert payload["artifact_counts"]["compiled_words"] == 1
        assert payload["has_enrichments"] is True
        assert payload["has_compiled_export"] is True

        artifacts = {artifact["file_name"]: artifact for artifact in payload["artifacts"]}
        assert artifacts["lexemes.jsonl"]["exists"] is True
        assert artifacts["lexemes.jsonl"]["row_count"] == 1
        assert artifacts["notes.json"]["exists"] is True
        assert artifacts["notes.json"]["row_count"] is None

    @pytest.mark.asyncio
    async def test_get_snapshot_detail_includes_workflow_metadata(self, client, mock_db, snapshot_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))
        app.dependency_overrides[get_settings] = lambda: Settings(environment="test", lexicon_snapshot_root=str(snapshot_root_env))

        snapshot_dir = snapshot_root_env / "approved-ready"
        snapshot_dir.mkdir()
        _write_jsonl(
            snapshot_dir / "words.enriched.jsonl",
            [{"entry_id": "word:run", "entry_type": "word", "word": "run", "senses": []}],
        )
        _write_jsonl(
            snapshot_dir / "reviewed" / "approved.jsonl",
            [{"entry_id": "word:run", "entry_type": "word", "word": "run", "senses": []}],
        )

        response = await client.get(
            "/api/lexicon-ops/snapshots/approved-ready",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["workflow_stage"] == "approved_ready_for_import"
        assert payload["recommended_action"] == "open_import_db"
        assert payload["preferred_review_artifact_path"] == str(snapshot_dir / "words.enriched.jsonl")
        assert payload["preferred_import_artifact_path"] == str(snapshot_dir / "reviewed" / "approved.jsonl")
        assert any("import-db" in step for step in payload["outside_portal_steps"])

    @pytest.mark.asyncio
    async def test_get_snapshot_detail_rejects_invalid_snapshot_identifier(self, client, mock_db, snapshot_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        response = await client.get(
            "/api/lexicon-ops/snapshots/not*valid",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "Invalid snapshot identifier"

    @pytest.mark.asyncio
    async def test_get_snapshot_detail_not_found(self, client, mock_db, snapshot_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        response = await client.get(
            "/api/lexicon-ops/snapshots/does-not-exist",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 404
        assert response.json()["detail"] == "Snapshot not found"


class TestLexiconVoiceStorageRewrite:
    def test_voice_storage_rewrite_query_applies_optional_filters(self):
        statement = _voice_storage_rewrite_query(
            source_reference="snapshot-001",
            provider="google",
            family="neural2",
            locale="en-US",
        )

        compiled = str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        )

        assert "google" in compiled
        assert "neural2" in compiled
        assert "en-US" in compiled
        assert "snapshot-001" in compiled

    @pytest.mark.asyncio
    async def test_rewrite_voice_storage_updates_matching_assets(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _make_user(user_id)

        matched_result = MagicMock()
        matched_result.scalars.return_value.all.return_value = [
            SimpleNamespace(
                id=uuid.uuid4(),
                storage_policy_id=uuid.uuid4(),
                created_at="2026-03-29T00:00:00Z",
            ),
            SimpleNamespace(
                id=uuid.uuid4(),
                storage_policy_id=uuid.uuid4(),
                created_at="2026-03-29T00:00:01Z",
            ),
        ]
        target_root_result = MagicMock()
        target_root_result.scalar_one_or_none.return_value = None
        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = [
            SimpleNamespace(id=matched_result.scalars.return_value.all.return_value[0].storage_policy_id),
            SimpleNamespace(id=matched_result.scalars.return_value.all.return_value[1].storage_policy_id),
        ]
        mock_db.execute.side_effect = [user_result, matched_result, target_root_result, policy_result]

        response = await client.post(
            "/api/lexicon-ops/voice-storage/rewrite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "source_reference": "snapshot-001",
                "storage_kind": "s3",
                "storage_base": "https://cdn.example.com/voice",
                "dry_run": False,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["matched_count"] == 2
        assert payload["updated_count"] == 2
        assert payload["dry_run"] is False
        assert payload["storage_kind"] == "s3"
        assert payload["storage_base"] == "https://cdn.example.com/voice"
        assert mock_db.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_rewrite_voice_storage_updates_selected_policies(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _make_user(user_id)

        policy_a = SimpleNamespace(id=uuid.uuid4(), primary_storage_kind="local", primary_storage_base="/tmp/a", fallback_storage_kind=None, fallback_storage_base=None)
        policy_b = SimpleNamespace(id=uuid.uuid4(), primary_storage_kind="local", primary_storage_base="/tmp/b", fallback_storage_kind=None, fallback_storage_base=None)
        policy_result = MagicMock()
        policy_result.scalars.return_value.all.return_value = [policy_a, policy_b]
        mock_db.execute.side_effect = [user_result, policy_result]

        response = await client.post(
            "/api/lexicon-ops/voice-storage/rewrite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "policy_ids": [str(policy_a.id), str(policy_b.id)],
                "storage_kind": "http",
                "storage_base": "https://cdn.example.com/voice",
                "dry_run": False,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["matched_count"] == 2
        assert payload["updated_count"] == 2
        assert policy_a.primary_storage_kind == "http"
        assert policy_a.primary_storage_base == "https://cdn.example.com/voice"
        assert policy_b.primary_storage_kind == "http"
        assert policy_b.primary_storage_base == "https://cdn.example.com/voice"
        assert mock_db.commit.await_count == 1

    @pytest.mark.asyncio
    async def test_rewrite_voice_storage_dry_run_does_not_commit(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _make_user(user_id)

        matched_result = MagicMock()
        matched_result.scalars.return_value.all.return_value = []
        mock_db.execute.side_effect = [user_result, matched_result]

        response = await client.post(
            "/api/lexicon-ops/voice-storage/rewrite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "source_reference": "snapshot-001",
                "storage_kind": "s3",
                "storage_base": "https://cdn.example.com/voice",
                "dry_run": True,
            },
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["matched_count"] == 0
        assert payload["updated_count"] == 0
        assert payload["dry_run"] is True
        assert mock_db.commit.await_count == 0

    @pytest.mark.asyncio
    async def test_rewrite_voice_storage_requires_scope(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        response = await client.post(
            "/api/lexicon-ops/voice-storage/rewrite",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "storage_kind": "s3",
                "storage_base": "https://cdn.example.com/voice",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"] == "policy_ids or source_reference is required"

    @pytest.mark.asyncio
    async def test_voice_storage_summary_returns_grouped_current_config(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _make_user(user_id)

        matched_result = MagicMock()
        matched_result.scalars.return_value.all.return_value = [
            SimpleNamespace(storage_policy=SimpleNamespace(primary_storage_kind="local", primary_storage_base="/tmp/voice-a")),
            SimpleNamespace(storage_policy=SimpleNamespace(primary_storage_kind="local", primary_storage_base="/tmp/voice-a")),
            SimpleNamespace(storage_policy=SimpleNamespace(primary_storage_kind="s3", primary_storage_base="https://cdn.example.com/voice")),
        ]
        mock_db.execute.side_effect = [user_result, matched_result]

        response = await client.get(
            "/api/lexicon-ops/voice-storage/summary?source_reference=snapshot-001",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["source_reference"] == "snapshot-001"
        assert payload["asset_count"] == 3
        assert payload["groups"] == [
            {"storage_kind": "local", "storage_base": "/tmp/voice-a", "asset_count": 2},
            {"storage_kind": "s3", "storage_base": "https://cdn.example.com/voice", "asset_count": 1},
        ]

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_voice_storage_policies_returns_policy_config(self, client, mock_db):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))
        user_result = MagicMock()
        user_result.scalar_one_or_none.return_value = _make_user(user_id)

        policies_result = MagicMock()
        policies_result.scalars.return_value.all.return_value = [
            SimpleNamespace(
                id=uuid.uuid4(),
                policy_key="word_default",
                content_scope="word",
                primary_storage_kind="local",
                primary_storage_base="/tmp/voice-a",
                fallback_storage_kind=None,
                fallback_storage_base=None,
                voice_assets=[object(), object()],
            ),
        ]
        mock_db.execute.side_effect = [user_result, policies_result]

        response = await client.get(
            "/api/lexicon-ops/voice-storage/policies?source_reference=snapshot-001",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload == [
            {
                "id": payload[0]["id"],
                "policy_key": "word_default",
                "content_scope": "word",
                "primary_storage_kind": "local",
                "primary_storage_base": "/tmp/voice-a",
                "fallback_storage_kind": None,
                "fallback_storage_base": None,
                "asset_count": 2,
            }
        ]


class TestLexiconVoiceRuns:
    @pytest.mark.asyncio
    async def test_list_voice_runs_returns_ledger_summary(self, client, mock_db, voice_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        run_dir = voice_root_env / "voice-roundtrip"
        run_dir.mkdir()
        _write_jsonl(run_dir / "voice_plan.jsonl", [{"unit_id": "1"}, {"unit_id": "2"}, {"unit_id": "3"}])
        _write_jsonl(run_dir / "voice_manifest.jsonl", [{"status": "generated"}, {"status": "existing"}])
        _write_jsonl(run_dir / "voice_errors.jsonl", [{"status": "failed"}])

        response = await client.get(
            "/api/lexicon-ops/voice-runs",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert len(payload) == 1
        assert payload[0]["run_name"] == "voice-roundtrip"
        assert payload[0]["planned_count"] == 3
        assert payload[0]["generated_count"] == 1
        assert payload[0]["existing_count"] == 1
        assert payload[0]["failed_count"] == 1

    @pytest.mark.asyncio
    async def test_get_voice_run_detail_returns_latest_rows(self, client, mock_db, voice_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        run_dir = voice_root_env / "voice-roundtrip"
        run_dir.mkdir()
        _write_jsonl(run_dir / "voice_plan.jsonl", [{"unit_id": "1"}, {"unit_id": "2"}])
        _write_jsonl(
            run_dir / "voice_manifest.jsonl",
            [
                {"status": "generated", "locale": "en-US", "voice_role": "female", "content_scope": "word", "source_reference": "voice-roundtrip"},
                {"status": "existing", "locale": "en-GB", "voice_role": "male", "content_scope": "definition", "source_reference": "voice-roundtrip"},
            ],
        )
        _write_jsonl(run_dir / "voice_errors.jsonl", [{"status": "failed", "generation_error": "boom", "locale": "en-US", "voice_role": "female", "content_scope": "example", "source_reference": "voice-roundtrip"}])

        response = await client.get(
            "/api/lexicon-ops/voice-runs/voice-roundtrip",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["run_name"] == "voice-roundtrip"
        assert payload["planned_count"] == 2
        assert payload["generated_count"] == 1
        assert payload["existing_count"] == 1
        assert payload["failed_count"] == 1
        assert payload["locale_counts"] == {"en-US": 2, "en-GB": 1}
        assert payload["voice_role_counts"] == {"female": 2, "male": 1}
        assert payload["content_scope_counts"] == {"word": 1, "definition": 1, "example": 1}
        assert payload["source_references"] == ["voice-roundtrip"]
        assert payload["artifacts"]["voice_plan_url"].endswith("/api/lexicon-ops/voice-runs/voice-roundtrip/artifacts/voice_plan.jsonl")
        assert len(payload["latest_manifest_rows"]) == 2
        assert len(payload["latest_error_rows"]) == 1

    @pytest.mark.asyncio
    async def test_get_voice_run_artifact_serves_jsonl_file(self, client, mock_db, voice_root_env):
        user_id = uuid.uuid4()
        token = create_access_token(subject=str(user_id))
        _mock_authenticated_user(mock_db, _make_user(user_id))

        run_dir = voice_root_env / "voice-roundtrip"
        run_dir.mkdir()
        _write_jsonl(run_dir / "voice_manifest.jsonl", [{"status": "generated"}])

        response = await client.get(
            "/api/lexicon-ops/voice-runs/voice-roundtrip/artifacts/voice_manifest.jsonl",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert response.status_code == 200
        assert '"status": "generated"' in response.text
