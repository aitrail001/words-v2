from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.core.database import get_db
from app.models.lexicon_voice_asset import LexiconVoiceAsset
from app.models.lexicon_voice_storage_policy import LexiconVoiceStoragePolicy
from app.models.meaning import Meaning
from app.models.meaning_example import MeaningExample
from app.models.user import User
from app.models.word import Word

router = APIRouter()

_SNAPSHOT_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_EXPECTED_ARTIFACT_FILES: tuple[str, ...] = (
    "lexemes.jsonl",
    "canonical_entries.jsonl",
    "canonical_variants.jsonl",
    "generation_status.jsonl",
    "ambiguous_forms.jsonl",
    "form_adjudications.jsonl",
    "enrichments.jsonl",
    "enrich.checkpoint.jsonl",
    "enrich.failures.jsonl",
    "words.enriched.jsonl",
    "phrases.enriched.jsonl",
    "references.enriched.jsonl",
    "reviewed/approved.jsonl",
    "reviewed/rejected.jsonl",
    "reviewed/regenerate.jsonl",
    "reviewed/review.decisions.jsonl",
)
_COUNTED_ARTIFACT_FILES: dict[str, str] = {
    "lexemes": "lexemes.jsonl",
    "enrichments": "enrichments.jsonl",
    "compiled_words": "words.enriched.jsonl",
    "compiled_phrases": "phrases.enriched.jsonl",
    "compiled_references": "references.enriched.jsonl",
    "approved_rows": "reviewed/approved.jsonl",
    "rejected_rows": "reviewed/rejected.jsonl",
    "regenerate_rows": "reviewed/regenerate.jsonl",
    "review_decisions": "reviewed/review.decisions.jsonl",
    "ambiguous_forms": "ambiguous_forms.jsonl",
    "form_adjudications": "form_adjudications.jsonl",
}
_SNAPSHOT_ID_FILES: tuple[str, ...] = (
    "lexemes.jsonl",
    "generation_status.jsonl",
    "enrichments.jsonl",
)


class LexiconSnapshotArtifactResponse(BaseModel):
    file_name: str
    exists: bool
    size_bytes: int | None
    modified_at: datetime | None
    row_count: int | None
    read_error: str | None


class LexiconSnapshotSummaryResponse(BaseModel):
    snapshot: str
    snapshot_path: str
    snapshot_id: str | None
    updated_at: datetime
    artifact_counts: dict[str, int]
    has_enrichments: bool
    has_compiled_export: bool
    has_ambiguous_forms: bool
    workflow_stage: str
    recommended_action: str
    preferred_review_artifact_path: str | None
    preferred_import_artifact_path: str | None
    outside_portal_steps: list[str]


class LexiconSnapshotDetailResponse(LexiconSnapshotSummaryResponse):
    artifacts: list[LexiconSnapshotArtifactResponse]


class VoiceStorageRewriteRequest(BaseModel):
    source_reference: str | None = None
    policy_ids: list[str] | None = None
    provider: str | None = None
    family: str | None = None
    locale: str | None = None
    storage_kind: str
    storage_base: str
    fallback_storage_kind: str | None = None
    fallback_storage_base: str | None = None
    dry_run: bool = False


class VoiceStorageRewriteResponse(BaseModel):
    matched_count: int
    updated_count: int
    dry_run: bool
    storage_kind: str
    storage_base: str
    fallback_storage_kind: str | None
    fallback_storage_base: str | None


class VoiceStorageSummaryGroupResponse(BaseModel):
    storage_kind: str
    storage_base: str
    asset_count: int


class VoiceStorageSummaryResponse(BaseModel):
    source_reference: str
    asset_count: int
    groups: list[VoiceStorageSummaryGroupResponse]


class VoiceStoragePolicyResponse(BaseModel):
    id: str
    policy_key: str
    content_scope: str
    primary_storage_kind: str
    primary_storage_base: str
    fallback_storage_kind: str | None
    fallback_storage_base: str | None
    asset_count: int


class LexiconVoiceRunSummaryResponse(BaseModel):
    run_name: str
    run_path: str
    updated_at: datetime
    planned_count: int
    generated_count: int
    existing_count: int
    failed_count: int


class LexiconVoiceRunDetailResponse(LexiconVoiceRunSummaryResponse):
    locale_counts: dict[str, int]
    voice_role_counts: dict[str, int]
    content_scope_counts: dict[str, int]
    source_references: list[str]
    artifacts: dict[str, str]
    latest_manifest_rows: list[dict[str, object]]
    latest_error_rows: list[dict[str, object]]


def _resolve_root(settings: Settings) -> Path:
    root = Path(settings.lexicon_snapshot_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root


def _resolve_voice_root(settings: Settings) -> Path:
    root = Path(settings.lexicon_voice_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root


def _is_safe_snapshot_name(name: str) -> bool:
    return bool(_SNAPSHOT_NAME_RE.fullmatch(name)) and name not in {".", ".."}


def _safe_snapshot_path(root: Path, snapshot_name: str) -> Path:
    if not _is_safe_snapshot_name(snapshot_name):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid snapshot identifier",
        )
    snapshot_path = (root / snapshot_name).resolve()
    try:
        snapshot_path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid snapshot identifier",
        ) from exc
    return snapshot_path


def _count_jsonl_rows(path: Path) -> tuple[int | None, str | None]:
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                text = line.strip()
                if not text:
                    continue
                json.loads(text)
                count += 1
        return count, None
    except (OSError, json.JSONDecodeError) as exc:
        message = f"{exc.__class__.__name__}"
        if isinstance(exc, json.JSONDecodeError):
            message = f"{message} at line {line_number}"
        return None, message


def _artifact_response(snapshot_dir: Path, file_name: str) -> LexiconSnapshotArtifactResponse:
    path = snapshot_dir / file_name
    if not path.exists() or not path.is_file():
        return LexiconSnapshotArtifactResponse(
            file_name=file_name,
            exists=False,
            size_bytes=None,
            modified_at=None,
            row_count=None,
            read_error=None,
        )

    stat_result = path.stat()
    row_count = None
    read_error = None
    if path.suffix == ".jsonl":
        row_count, read_error = _count_jsonl_rows(path)
    return LexiconSnapshotArtifactResponse(
        file_name=file_name,
        exists=True,
        size_bytes=stat_result.st_size,
        modified_at=datetime.fromtimestamp(stat_result.st_mtime, tz=timezone.utc),
        row_count=row_count,
        read_error=read_error,
    )


def _infer_snapshot_id(snapshot_dir: Path) -> str | None:
    for file_name in _SNAPSHOT_ID_FILES:
        path = snapshot_dir / file_name
        if not path.exists() or not path.is_file():
            continue
        try:
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    text = line.strip()
                    if not text:
                        continue
                    payload = json.loads(text)
                    if isinstance(payload, dict):
                        value = payload.get("snapshot_id")
                        snapshot_id = str(value).strip() if value is not None else ""
                        if snapshot_id:
                            return snapshot_id
                    break
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _snapshot_updated_at(snapshot_dir: Path) -> datetime:
    latest = snapshot_dir.stat().st_mtime
    for child in snapshot_dir.rglob("*"):
        if child.is_file():
            latest = max(latest, child.stat().st_mtime)
    return datetime.fromtimestamp(latest, tz=timezone.utc)


def _artifact_counts(snapshot_dir: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for key, file_name in _COUNTED_ARTIFACT_FILES.items():
        path = snapshot_dir / file_name
        if not path.exists() or not path.is_file():
            counts[key] = 0
            continue
        row_count, _ = _count_jsonl_rows(path)
        counts[key] = row_count or 0
    return counts


def _count_status_rows(path: Path, status: str) -> int:
    if not path.exists() or not path.is_file():
        return 0
    count = 0
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, dict) and str(payload.get("status") or "").strip().lower() == status:
                    count += 1
    except (OSError, json.JSONDecodeError):
        return 0
    return count


def _voice_run_summary(run_dir: Path) -> LexiconVoiceRunSummaryResponse:
    plan_path = run_dir / "voice_plan.jsonl"
    manifest_path = run_dir / "voice_manifest.jsonl"
    errors_path = run_dir / "voice_errors.jsonl"
    latest = run_dir.stat().st_mtime
    for path in (plan_path, manifest_path, errors_path):
        if path.exists() and path.is_file():
            latest = max(latest, path.stat().st_mtime)
    planned_count, _ = _count_jsonl_rows(plan_path) if plan_path.exists() else (0, None)
    failed_count, _ = _count_jsonl_rows(errors_path) if errors_path.exists() else (0, None)
    return LexiconVoiceRunSummaryResponse(
        run_name=run_dir.name,
        run_path=str(run_dir),
        updated_at=datetime.fromtimestamp(latest, tz=timezone.utc),
        planned_count=planned_count or 0,
        generated_count=_count_status_rows(manifest_path, "generated"),
        existing_count=_count_status_rows(manifest_path, "existing"),
        failed_count=failed_count or 0,
    )


def _latest_jsonl_rows(path: Path, limit: int = 5) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, dict):
                    rows.append(dict(payload))
    except (OSError, json.JSONDecodeError):
        return []
    return rows[-limit:]


def _jsonl_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists() or not path.is_file():
        return []
    rows: list[dict[str, object]] = []
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                text = line.strip()
                if not text:
                    continue
                payload = json.loads(text)
                if isinstance(payload, dict):
                    rows.append(dict(payload))
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def _count_field(rows: list[dict[str, object]], field_name: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(field_name) or "").strip()
        if not value:
            continue
        counts[value] = counts.get(value, 0) + 1
    return counts


def _snapshot_summary(snapshot_dir: Path) -> LexiconSnapshotSummaryResponse:
    counts = _artifact_counts(snapshot_dir)
    preferred_review_artifact = _preferred_review_artifact_path(snapshot_dir)
    preferred_import_artifact = _preferred_import_artifact_path(snapshot_dir)
    workflow_stage, recommended_action, outside_portal_steps = _workflow_metadata(
        snapshot_dir,
        counts=counts,
        preferred_review_artifact=preferred_review_artifact,
        preferred_import_artifact=preferred_import_artifact,
    )
    return LexiconSnapshotSummaryResponse(
        snapshot=snapshot_dir.name,
        snapshot_path=str(snapshot_dir),
        snapshot_id=_infer_snapshot_id(snapshot_dir),
        updated_at=_snapshot_updated_at(snapshot_dir),
        artifact_counts=counts,
        has_enrichments=(snapshot_dir / "enrichments.jsonl").exists(),
        has_compiled_export=preferred_review_artifact is not None,
        has_ambiguous_forms=counts.get("ambiguous_forms", 0) > 0,
        workflow_stage=workflow_stage,
        recommended_action=recommended_action,
        preferred_review_artifact_path=str(preferred_review_artifact) if preferred_review_artifact else None,
        preferred_import_artifact_path=str(preferred_import_artifact) if preferred_import_artifact else None,
        outside_portal_steps=outside_portal_steps,
    )


def _preferred_review_artifact_path(snapshot_dir: Path) -> Path | None:
    for file_name in (
        "words.enriched.jsonl",
        "phrases.enriched.jsonl",
        "references.enriched.jsonl",
    ):
        candidate = snapshot_dir / file_name
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def _preferred_import_artifact_path(snapshot_dir: Path) -> Path | None:
    approved_path = snapshot_dir / "reviewed" / "approved.jsonl"
    if approved_path.exists() and approved_path.is_file():
        return approved_path
    return None


def _workflow_metadata(
    snapshot_dir: Path,
    *,
    counts: dict[str, int],
    preferred_review_artifact: Path | None,
    preferred_import_artifact: Path | None,
) -> tuple[str, str, list[str]]:
    snapshot_path = str(snapshot_dir)
    if preferred_import_artifact is not None:
        return (
            "approved_ready_for_import",
            "open_import_db",
            [
                f"Run import-db with {preferred_import_artifact}",
                f"Verify the imported rows in DB Inspector after import-db completes for snapshot_path {snapshot_path}",
            ],
        )
    if preferred_review_artifact is not None:
        return (
            "compiled_ready_for_review",
            "open_compiled_review",
            [
                f"Review {preferred_review_artifact} in Compiled Review or JSONL Review",
                f"Materialize or export reviewed/approved.jsonl under snapshot_path {snapshot_path} before import-db",
            ],
        )
    if counts.get("lexemes", 0) > 0 or counts.get("enrichments", 0) > 0:
        return (
            "base_artifacts",
            "run_enrich",
            [
                f"Run enrich from snapshot_path {snapshot_path} to produce words.enriched.jsonl",
                f"Review compiled artifacts and materialize reviewed/approved.jsonl under snapshot_path {snapshot_path} before import-db",
            ],
        )
    return (
        "snapshot_missing_artifacts",
        "run_build_base",
        [
            f"Run build-base and enrich before using snapshot_path {snapshot_path}",
        ],
    )


def _voice_storage_rewrite_query(*, source_reference: str, provider: str | None, family: str | None, locale: str | None) -> Select[tuple[LexiconVoiceAsset]]:
    word_direct = Word.__table__.alias("word_direct")
    meaning_parent = Meaning.__table__.alias("meaning_parent")
    meaning_word = Word.__table__.alias("meaning_word")
    example_parent = MeaningExample.__table__.alias("example_parent")
    example_meaning = Meaning.__table__.alias("example_meaning")
    example_word = Word.__table__.alias("example_word")

    query = (
        select(LexiconVoiceAsset)
        .outerjoin(word_direct, LexiconVoiceAsset.word_id == word_direct.c.id)
        .outerjoin(meaning_parent, LexiconVoiceAsset.meaning_id == meaning_parent.c.id)
        .outerjoin(meaning_word, meaning_parent.c.word_id == meaning_word.c.id)
        .outerjoin(example_parent, LexiconVoiceAsset.meaning_example_id == example_parent.c.id)
        .outerjoin(example_meaning, example_parent.c.meaning_id == example_meaning.c.id)
        .outerjoin(example_word, example_meaning.c.word_id == example_word.c.id)
        .options(selectinload(LexiconVoiceAsset.storage_policy))
        .where(
            or_(
                word_direct.c.source_reference == source_reference,
                meaning_word.c.source_reference == source_reference,
                example_word.c.source_reference == source_reference,
            )
        )
        .order_by(LexiconVoiceAsset.created_at.asc())
    )
    if provider:
        query = query.where(LexiconVoiceAsset.provider == provider)
    if family:
        query = query.where(LexiconVoiceAsset.family == family)
    if locale:
        query = query.where(LexiconVoiceAsset.locale == locale)
    return query


@router.get("/snapshots", response_model=list[LexiconSnapshotSummaryResponse])
async def list_lexicon_snapshots(
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> list[LexiconSnapshotSummaryResponse]:
    root = _resolve_root(settings)
    if not root.exists():
        return []
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configured lexicon snapshot root is not a directory",
        )

    snapshots = [entry for entry in root.iterdir() if entry.is_dir() and not entry.name.startswith(".")]
    summaries = [_snapshot_summary(snapshot_dir) for snapshot_dir in snapshots]
    summaries.sort(key=lambda item: item.updated_at, reverse=True)
    return summaries


@router.get("/snapshots/{snapshot_name}", response_model=LexiconSnapshotDetailResponse)
async def get_lexicon_snapshot_detail(
    snapshot_name: str,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconSnapshotDetailResponse:
    root = _resolve_root(settings)
    if not root.exists() or not root.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    snapshot_dir = _safe_snapshot_path(root, snapshot_name)
    if not snapshot_dir.exists() or not snapshot_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Snapshot not found")

    expected_set = set(_EXPECTED_ARTIFACT_FILES)
    extra_files = sorted(
        str(path.relative_to(snapshot_dir))
        for path in snapshot_dir.rglob("*")
        if path.is_file()
        and str(path.relative_to(snapshot_dir)) not in expected_set
        and path.suffix in {".jsonl", ".json"}
    )
    artifact_names = [*_EXPECTED_ARTIFACT_FILES, *extra_files]
    artifacts = [_artifact_response(snapshot_dir, artifact_name) for artifact_name in artifact_names]

    summary = _snapshot_summary(snapshot_dir)
    return LexiconSnapshotDetailResponse(
        **summary.model_dump(),
        artifacts=artifacts,
    )


@router.post("/voice-storage/rewrite", response_model=VoiceStorageRewriteResponse)
async def rewrite_voice_storage(
    payload: VoiceStorageRewriteRequest,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> VoiceStorageRewriteResponse:
    source_reference = payload.source_reference.strip() if payload.source_reference else ""
    policy_ids = [value.strip() for value in (payload.policy_ids or []) if value and value.strip()]
    storage_kind = payload.storage_kind.strip()
    storage_base = payload.storage_base.strip()
    fallback_storage_kind = payload.fallback_storage_kind.strip() if payload.fallback_storage_kind else ""
    fallback_storage_base = payload.fallback_storage_base.strip() if payload.fallback_storage_base else ""
    provider = payload.provider.strip() if payload.provider else ""
    family = payload.family.strip() if payload.family else ""
    locale = payload.locale.strip() if payload.locale else ""

    if not source_reference and not policy_ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="policy_ids or source_reference is required")
    if not storage_kind:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="storage_kind is required")
    if not storage_base:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="storage_base is required")
    if fallback_storage_kind and not fallback_storage_base:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fallback_storage_base is required")
    if fallback_storage_base and not fallback_storage_kind:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="fallback_storage_kind is required")

    if policy_ids:
        result = await db.execute(
            select(LexiconVoiceStoragePolicy).where(
                LexiconVoiceStoragePolicy.id.in_([value for value in policy_ids])
            )
        )
        policies = list(result.scalars().all())
        matched_count = len(policies)
    else:
        result = await db.execute(
            _voice_storage_rewrite_query(
                source_reference=source_reference,
                provider=provider or None,
                family=family or None,
                locale=locale or None,
            )
        )
        assets = list(result.scalars().all())
        policy_ids = [str(value) for value in {asset.storage_policy_id for asset in assets}]
        matched_count = len(assets)
        policies = []
    if not payload.dry_run:
        if policy_ids:
            if not policies:
                policy_result = await db.execute(
                    select(LexiconVoiceStoragePolicy).where(LexiconVoiceStoragePolicy.id.in_(policy_ids))
                )
                policies = list(policy_result.scalars().all())
            for policy in policies:
                policy.primary_storage_kind = storage_kind
                policy.primary_storage_base = storage_base
                policy.fallback_storage_kind = fallback_storage_kind or None
                policy.fallback_storage_base = fallback_storage_base or None
        await db.commit()

    return VoiceStorageRewriteResponse(
        matched_count=matched_count,
        updated_count=0 if payload.dry_run else matched_count,
        dry_run=payload.dry_run,
        storage_kind=storage_kind,
        storage_base=storage_base,
        fallback_storage_kind=fallback_storage_kind or None,
        fallback_storage_base=fallback_storage_base or None,
    )


@router.get("/voice-storage/summary", response_model=VoiceStorageSummaryResponse)
async def get_voice_storage_summary(
    source_reference: str,
    provider: str | None = None,
    family: str | None = None,
    locale: str | None = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> VoiceStorageSummaryResponse:
    normalized_source_reference = source_reference.strip()
    if not normalized_source_reference:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_reference is required")

    result = await db.execute(
        _voice_storage_rewrite_query(
            source_reference=normalized_source_reference,
            provider=provider.strip() if provider else None,
            family=family.strip() if family else None,
            locale=locale.strip() if locale else None,
        )
    )
    assets = list(result.scalars().all())
    grouped: dict[tuple[str, str], int] = {}
    for asset in assets:
        key = (
            str(asset.storage_policy.primary_storage_kind),
            str(asset.storage_policy.primary_storage_base),
        )
        grouped[key] = grouped.get(key, 0) + 1
    groups = [
        VoiceStorageSummaryGroupResponse(
            storage_kind=storage_kind,
            storage_base=storage_base,
            asset_count=count,
        )
        for (storage_kind, storage_base), count in sorted(grouped.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    ]
    return VoiceStorageSummaryResponse(
        source_reference=normalized_source_reference,
        asset_count=len(assets),
        groups=groups,
    )

@router.get("/voice-storage/policies", response_model=list[VoiceStoragePolicyResponse])
async def list_voice_storage_policies(
    source_reference: str | None = None,
    _: User = Depends(get_current_admin_user),
    db: AsyncSession = Depends(get_db),
) -> list[VoiceStoragePolicyResponse]:
    query = (
        select(LexiconVoiceStoragePolicy)
        .where(
            LexiconVoiceStoragePolicy.policy_key.in_(["word_default", "definition_default", "example_default"])
        )
        .order_by(
            LexiconVoiceStoragePolicy.content_scope.asc(),
            LexiconVoiceStoragePolicy.policy_key.asc(),
        )
    )
    result = await db.execute(query)
    policies = list(result.scalars().all())
    count_by_policy_id: dict[object, int] = {}
    if policies:
        counts_result = await db.execute(
            select(
                LexiconVoiceAsset.storage_policy_id,
                func.count(LexiconVoiceAsset.id),
            )
            .where(LexiconVoiceAsset.storage_policy_id.in_([policy.id for policy in policies]))
            .group_by(LexiconVoiceAsset.storage_policy_id)
        )
        count_by_policy_id = {
            policy_id: int(asset_count)
            for policy_id, asset_count in counts_result.all()
        }
    return [
        VoiceStoragePolicyResponse(
            id=str(policy.id),
            policy_key=policy.policy_key,
            content_scope=policy.content_scope,
            primary_storage_kind=policy.primary_storage_kind,
            primary_storage_base=policy.primary_storage_base,
            fallback_storage_kind=policy.fallback_storage_kind,
            fallback_storage_base=policy.fallback_storage_base,
            asset_count=count_by_policy_id.get(policy.id, 0),
        )
        for policy in policies
    ]


@router.get("/voice-runs", response_model=list[LexiconVoiceRunSummaryResponse])
async def list_voice_runs(
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> list[LexiconVoiceRunSummaryResponse]:
    root = _resolve_voice_root(settings)
    if not root.exists():
        return []
    if not root.is_dir():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Configured lexicon voice root is not a directory",
        )

    runs = [
        _voice_run_summary(entry)
        for entry in root.iterdir()
        if entry.is_dir() and not entry.name.startswith(".")
    ]
    runs.sort(key=lambda item: item.updated_at, reverse=True)
    return runs


@router.get("/voice-runs/{run_name}", response_model=LexiconVoiceRunDetailResponse)
async def get_voice_run_detail(
    run_name: str,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
) -> LexiconVoiceRunDetailResponse:
    if not _is_safe_snapshot_name(run_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run identifier")
    root = _resolve_voice_root(settings)
    run_dir = (root / run_name).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run identifier") from exc
    if not run_dir.exists() or not run_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice run not found")
    summary = _voice_run_summary(run_dir)
    manifest_rows = _jsonl_rows(run_dir / "voice_manifest.jsonl")
    error_rows = _jsonl_rows(run_dir / "voice_errors.jsonl")
    combined_rows = [*manifest_rows, *error_rows]
    return LexiconVoiceRunDetailResponse(
        **summary.model_dump(),
        locale_counts=_count_field(combined_rows, "locale"),
        voice_role_counts=_count_field(combined_rows, "voice_role"),
        content_scope_counts=_count_field(combined_rows, "content_scope"),
        source_references=sorted({str(row.get("source_reference") or "").strip() for row in combined_rows if str(row.get("source_reference") or "").strip()}),
        artifacts={
            "voice_plan_url": f"/api/lexicon-ops/voice-runs/{run_name}/artifacts/voice_plan.jsonl",
            "voice_manifest_url": f"/api/lexicon-ops/voice-runs/{run_name}/artifacts/voice_manifest.jsonl",
            "voice_errors_url": f"/api/lexicon-ops/voice-runs/{run_name}/artifacts/voice_errors.jsonl",
        },
        latest_manifest_rows=manifest_rows[-5:],
        latest_error_rows=error_rows[-5:],
    )


@router.get("/voice-runs/{run_name}/artifacts/{artifact_name}")
async def get_voice_run_artifact(
    run_name: str,
    artifact_name: str,
    _: User = Depends(get_current_admin_user),
    settings: Settings = Depends(get_settings),
):
    if not _is_safe_snapshot_name(run_name):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run identifier")
    allowed_artifacts = {"voice_plan.jsonl", "voice_manifest.jsonl", "voice_errors.jsonl"}
    if artifact_name not in allowed_artifacts:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice run artifact not found")
    root = _resolve_voice_root(settings)
    run_dir = (root / run_name).resolve()
    try:
        run_dir.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid run identifier") from exc
    artifact_path = (run_dir / artifact_name).resolve()
    try:
        artifact_path.relative_to(run_dir)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid artifact path") from exc
    if not artifact_path.exists() or not artifact_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice run artifact not found")
    return FileResponse(artifact_path, media_type="application/json", filename=artifact_name)
