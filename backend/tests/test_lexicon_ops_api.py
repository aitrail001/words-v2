import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
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
