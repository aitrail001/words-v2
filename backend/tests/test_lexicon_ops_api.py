import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.database import get_db
from app.core.redis import get_redis
from app.core.security import create_access_token
from app.main import app
from app.models.user import User


def _make_user(user_id: uuid.UUID, role: str = "admin") -> User:
    return User(id=user_id, email="ops@example.com", password_hash="hashed", role=role)


def _write_jsonl(path, rows: list[dict]) -> None:
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
        _write_jsonl(words_1000 / "senses.jsonl", [{"snapshot_id": "lexicon-20260312-wordnet-wordfreq", "sense_id": "sn_bank_1"}])
        _write_jsonl(words_1000 / "ambiguous_forms.jsonl", [{"surface_form": "ringed"}])
        _write_jsonl(words_1000 / "words.enriched.jsonl", [{"word": "bank", "senses": []}])

        demo = snapshot_root_env / "demo"
        demo.mkdir()
        _write_jsonl(
            demo / "lexemes.jsonl",
            [{"snapshot_id": "lexicon-20260311-wordnet-wordfreq", "lexeme_id": "lx_run", "lemma": "run"}],
        )
        _write_jsonl(demo / "selection_decisions.jsonl", [{"lexeme_id": "lx_run", "risk_band": "deterministic_only"}])

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
        assert words_item["artifact_counts"]["senses"] == 1
        assert words_item["artifact_counts"]["compiled_words"] == 1
        assert words_item["artifact_counts"]["ambiguous_forms"] == 1
        assert words_item["has_compiled_export"] is True
        assert words_item["has_ambiguous_forms"] is True

        demo_item = by_snapshot["demo"]
        assert demo_item["artifact_counts"]["selection_decisions"] == 1
        assert demo_item["has_selection_decisions"] is True
        assert demo_item["has_enrichments"] is False


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
