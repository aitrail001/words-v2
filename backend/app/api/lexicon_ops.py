from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.auth import get_current_admin_user
from app.core.config import Settings, get_settings
from app.models.user import User

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


def _resolve_root(settings: Settings) -> Path:
    root = Path(settings.lexicon_snapshot_root).expanduser()
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
