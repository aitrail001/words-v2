from __future__ import annotations

import hashlib
from importlib import import_module
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import HTTPException, status

from app.core.config import Settings

DECISION_SCHEMA_VERSION = "lexicon_review_decision.v1"
ALLOWED_DECISIONS = {"approved", "rejected", "reopened"}
DECISIONS_FILENAME = "review.decisions.jsonl"
REVIEWED_DIRNAME = "reviewed"
APPROVED_FILENAME = "approved.jsonl"
REJECTED_FILENAME = "rejected.jsonl"
REGENERATE_FILENAME = "regenerate.jsonl"


def _import_review_prep_module() -> Any:
    try:
        return import_module("tools.lexicon.review_prep")
    except ModuleNotFoundError as exc:
        if not exc.name or not exc.name.startswith("tools"):
            raise
        repo_root = Path(__file__).resolve().parents[3]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))
        return import_module("tools.lexicon.review_prep")


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _artifact_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            text = line.strip()
            if not text:
                continue
            try:
                payload = json.loads(text)
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid JSONL at {path}:{line_number}: {exc.msg}") from exc
            if not isinstance(payload, dict):
                raise HTTPException(status_code=400, detail=f"JSONL row at {path}:{line_number} must be an object")
            rows.append(payload)
    return rows


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def _snapshot_root(settings: Settings) -> Path:
    root = Path(settings.lexicon_snapshot_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root


def _allowed_roots(settings: Settings) -> list[Path]:
    roots = [Path.cwd().resolve(), _snapshot_root(settings)]
    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def resolve_repo_local_path(raw_path: str, *, settings: Settings, allow_missing: bool = False) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()

    for root in _allowed_roots(settings):
        try:
            path.relative_to(root)
            break
        except ValueError:
            continue
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path must stay within the allowed roots",
        )

    if not allow_missing and not path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Path not found: {path}")
    return path


def default_decisions_path(artifact_path: Path) -> Path:
    return reviewed_output_dir(artifact_path) / DECISIONS_FILENAME


def reviewed_output_dir(artifact_path: Path) -> Path:
    return artifact_path.parent / REVIEWED_DIRNAME


def resolve_compiled_artifact_path(raw_path: str, *, settings: Settings) -> Path:
    path = resolve_repo_local_path(raw_path, settings=settings)
    if path.suffix != ".jsonl":
        raise HTTPException(status_code=400, detail="Artifact path must point to a .jsonl file")
    return path


def resolve_decisions_sidecar_path(
    artifact_path: Path,
    raw_path: str | None,
    *,
    settings: Settings,
) -> Path:
    candidate = default_decisions_path(artifact_path) if raw_path is None else resolve_repo_local_path(raw_path, settings=settings, allow_missing=True)
    if candidate.name != DECISIONS_FILENAME:
        raise HTTPException(status_code=400, detail=f"Decisions path must use the sidecar filename {DECISIONS_FILENAME}")
    reviewed_dir = reviewed_output_dir(artifact_path)
    try:
        candidate.parent.relative_to(reviewed_dir)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Decisions path must stay within the reviewed output directory") from exc
    return candidate


def resolve_output_dir_path(
    artifact_path: Path,
    raw_path: str | None,
    *,
    settings: Settings,
) -> Path | None:
    if raw_path is None:
        return reviewed_output_dir(artifact_path)
    candidate = resolve_repo_local_path(raw_path, settings=settings, allow_missing=True)
    try:
        candidate.relative_to(artifact_path.parent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Output directory must stay within the artifact directory") from exc
    return candidate


def build_materialized_review_outputs(session: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    decisions_by_id = {
        item["entry_id"]: {
            "entry_id": item["entry_id"],
            "entry_type": item["entry_type"],
            "decision": "reopened" if item["review_status"] == "pending" else item["review_status"],
            "decision_reason": item["decision_reason"],
            "reviewed_by": item["reviewed_by"],
            "reviewed_at": item["reviewed_at"],
            "compiled_payload_sha256": item["compiled_payload_sha256"],
        }
        for item in session["items"]
    }
    missing = sorted(entry_id for entry_id, row in decisions_by_id.items() if row["decision"] == "reopened")
    if missing:
        preview = ", ".join(missing[:10])
        raise HTTPException(status_code=400, detail=f"Missing review decisions for entry_ids: {preview}")

    approved_rows: list[dict[str, Any]] = []
    rejected_rows: list[dict[str, Any]] = []
    regenerate_rows: list[dict[str, Any]] = []
    finalized_decisions: list[dict[str, Any]] = []
    for item in session["items"]:
        decision = decisions_by_id[item["entry_id"]]
        finalized = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "artifact_sha256": session["artifact_sha256"],
            "entry_id": item["entry_id"],
            "entry_type": item["entry_type"],
            "decision": decision["decision"],
            "decision_reason": decision["decision_reason"],
            "compiled_payload_sha256": item["compiled_payload_sha256"],
            "reviewed_by": decision["reviewed_by"],
            "reviewed_at": decision["reviewed_at"],
        }
        finalized_decisions.append(finalized)
        if decision["decision"] == "approved":
            approved_rows.append(item["compiled_payload"])
            continue
        rejected_rows.append({**item["compiled_payload"], **finalized})
        if decision["decision"] == "rejected":
            regenerate_rows.append(
                {
                    "schema_version": DECISION_SCHEMA_VERSION,
                    "artifact_sha256": session["artifact_sha256"],
                    "entry_id": item["entry_id"],
                    "entry_type": item["entry_type"],
                    "normalized_form": item["normalized_form"],
                    "decision_reason": decision["decision_reason"],
                    "compiled_payload_sha256": item["compiled_payload_sha256"],
                }
            )
    return {
        "approved_rows": approved_rows,
        "rejected_rows": rejected_rows,
        "regenerate_rows": regenerate_rows,
        "finalized_decisions": finalized_decisions,
    }


def _display_text(row: dict[str, Any]) -> str:
    for key in ("display_form", "word", "normalized_form", "entry_id"):
        value = str(row.get(key) or "").strip()
        if value:
            return value
    return "unknown"

def _normalize_decision_rows(
    rows: list[dict[str, Any]],
    *,
    artifact_sha256: str,
    compiled_by_id: dict[str, dict[str, Any]],
    payload_sha_by_id: dict[str, str],
) -> dict[str, dict[str, Any]]:
    decisions_by_id: dict[str, dict[str, Any]] = {}
    for row in rows:
        entry_id = str(row.get("entry_id") or "").strip()
        entry_type = str(row.get("entry_type") or "").strip().lower()
        decision = str(row.get("decision") or "").strip().lower()
        if not entry_id:
            raise HTTPException(status_code=400, detail="Decision row entry_id is required")
        if entry_type not in {"word", "phrase", "reference"}:
            raise HTTPException(status_code=400, detail=f"Decision row entry_type is invalid for {entry_id}")
        if decision not in ALLOWED_DECISIONS:
            raise HTTPException(status_code=400, detail=f"Decision row value is invalid for {entry_id}")
        if entry_id in decisions_by_id:
            raise HTTPException(status_code=400, detail=f"Duplicate decision row for {entry_id}")
        if entry_id not in compiled_by_id:
            raise HTTPException(status_code=400, detail=f"Decision row references unknown entry_id {entry_id}")

        supplied_artifact_sha = str(row.get("artifact_sha256") or "").strip()
        if supplied_artifact_sha and supplied_artifact_sha != artifact_sha256:
            raise HTTPException(status_code=400, detail=f"Decision row artifact_sha256 mismatch for {entry_id}")

        supplied_payload_sha = str(row.get("compiled_payload_sha256") or "").strip()
        if supplied_payload_sha and supplied_payload_sha != payload_sha_by_id[entry_id]:
            raise HTTPException(status_code=400, detail=f"Decision row compiled_payload_sha256 mismatch for {entry_id}")

        decisions_by_id[entry_id] = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "artifact_sha256": artifact_sha256,
            "entry_id": entry_id,
            "entry_type": entry_type,
            "decision": decision,
            "decision_reason": row.get("decision_reason"),
            "compiled_payload_sha256": payload_sha_by_id[entry_id],
            "reviewed_by": row.get("reviewed_by"),
            "reviewed_at": row.get("reviewed_at"),
        }
    return decisions_by_id


def load_jsonl_review_session(
    *,
    artifact_path: Path,
    decisions_path: Path,
) -> dict[str, Any]:
    compiled_rows = _read_jsonl(artifact_path)
    if not compiled_rows:
        raise HTTPException(status_code=400, detail="Compiled artifact is empty")

    compiled_by_id: dict[str, dict[str, Any]] = {}
    payload_sha_by_id: dict[str, str] = {}
    items: list[dict[str, Any]] = []
    review_prep = _import_review_prep_module()
    prepared_rows = review_prep.build_review_prep_rows(compiled_rows, origin="realtime")
    for index, row in enumerate(compiled_rows, start=1):
        prepared = prepared_rows[index - 1]
        if prepared["reasons"]:
            raise HTTPException(
                status_code=400,
                detail=f"Compiled row {index} failed validation: {'; '.join(prepared['reasons'])}",
            )
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            raise HTTPException(status_code=400, detail=f"Compiled row {index} is missing entry_id")
        if entry_id in compiled_by_id:
            raise HTTPException(status_code=400, detail=f"Duplicate compiled entry_id in artifact: {entry_id}")
        compiled_by_id[entry_id] = row
        payload_sha_by_id[entry_id] = _payload_sha256(row)

    artifact_sha256 = _artifact_sha256(artifact_path)
    decision_rows = _read_jsonl(decisions_path) if decisions_path.exists() else []
    decisions_by_id = _normalize_decision_rows(
        decision_rows,
        artifact_sha256=artifact_sha256,
        compiled_by_id=compiled_by_id,
        payload_sha_by_id=payload_sha_by_id,
    )

    approved_count = 0
    rejected_count = 0
    for row, prepared in zip(compiled_rows, prepared_rows, strict=False):
        entry_id = str(row.get("entry_id") or "")
        decision = decisions_by_id.get(entry_id)
        review_status = "pending"
        if decision:
            if decision["decision"] == "approved":
                review_status = "approved"
                approved_count += 1
            elif decision["decision"] == "rejected":
                review_status = "rejected"
                rejected_count += 1
        items.append(
            {
                "entry_id": entry_id,
                "entry_type": str(row.get("entry_type") or "word"),
                "normalized_form": row.get("normalized_form"),
                "display_text": _display_text(row),
                "entity_category": row.get("entity_category"),
                "language": row.get("language") or "en",
                "frequency_rank": row.get("frequency_rank"),
                "cefr_level": row.get("cefr_level"),
                "review_priority": "warning" if prepared["warning_labels"] else "normal",
                "warning_count": prepared["warning_count"],
                "warning_labels": prepared["warning_labels"],
                "review_summary": prepared["review_summary"],
                "review_status": review_status,
                "decision_reason": decision.get("decision_reason") if decision else None,
                "reviewed_by": decision.get("reviewed_by") if decision else None,
                "reviewed_at": decision.get("reviewed_at") if decision else None,
                "compiled_payload": row,
                "compiled_payload_sha256": payload_sha_by_id[entry_id],
            }
        )

    total_items = len(compiled_rows)
    return {
        "artifact_filename": artifact_path.name,
        "artifact_path": str(artifact_path),
        "artifact_sha256": artifact_sha256,
        "decisions_path": str(decisions_path),
        "total_items": total_items,
        "pending_count": total_items - approved_count - rejected_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "items": items,
    }


def update_jsonl_review_decision(
    *,
    artifact_path: Path,
    decisions_path: Path,
    entry_id: str,
    review_status: str,
    decision_reason: str | None,
    reviewed_by: str,
) -> dict[str, Any]:
    if review_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid review_status")

    session = load_jsonl_review_session(artifact_path=artifact_path, decisions_path=decisions_path)
    items_by_id = {item["entry_id"]: item for item in session["items"]}
    if entry_id not in items_by_id:
        raise HTTPException(status_code=404, detail="Compiled review item not found")

    raw_rows = _read_jsonl(decisions_path) if decisions_path.exists() else []
    compiled_by_id = {item["entry_id"]: item["compiled_payload"] for item in session["items"]}
    payload_sha_by_id = {item["entry_id"]: item["compiled_payload_sha256"] for item in session["items"]}
    decisions_by_id = _normalize_decision_rows(
        raw_rows,
        artifact_sha256=session["artifact_sha256"],
        compiled_by_id=compiled_by_id,
        payload_sha_by_id=payload_sha_by_id,
    )

    decisions_by_id[entry_id] = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "artifact_sha256": session["artifact_sha256"],
        "entry_id": entry_id,
        "entry_type": items_by_id[entry_id]["entry_type"],
        "decision": "reopened" if review_status == "pending" else review_status,
        "decision_reason": decision_reason,
        "compiled_payload_sha256": payload_sha_by_id[entry_id],
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    ordered_rows = [decisions_by_id[key] for key in sorted(decisions_by_id)]
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(decisions_path, ordered_rows)

    refreshed = load_jsonl_review_session(artifact_path=artifact_path, decisions_path=decisions_path)
    return next(item for item in refreshed["items"] if item["entry_id"] == entry_id)


def materialize_jsonl_review_outputs(
    *,
    artifact_path: Path,
    decisions_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    approved_output_path = output_dir / APPROVED_FILENAME
    rejected_output_path = output_dir / REJECTED_FILENAME
    regenerate_output_path = output_dir / REGENERATE_FILENAME

    session = load_jsonl_review_session(artifact_path=artifact_path, decisions_path=decisions_path)
    outputs = build_materialized_review_outputs(session)
    approved_rows = outputs["approved_rows"]
    rejected_rows = outputs["rejected_rows"]
    regenerate_rows = outputs["regenerate_rows"]
    finalized_decisions = outputs["finalized_decisions"]

    _write_jsonl(decisions_path, finalized_decisions)
    _write_jsonl(approved_output_path, approved_rows)
    _write_jsonl(rejected_output_path, rejected_rows)
    _write_jsonl(regenerate_output_path, regenerate_rows)
    summary = {
        "artifact_sha256": session["artifact_sha256"],
        "decision_count": len(finalized_decisions),
        "approved_count": len(approved_rows),
        "rejected_count": len(rejected_rows),
        "regenerate_count": len(regenerate_rows),
    }
    return {
        **summary,
        "decisions_output_path": str(decisions_path),
        "approved_output_path": str(approved_output_path),
        "rejected_output_path": str(rejected_output_path),
        "regenerate_output_path": str(regenerate_output_path),
    }
