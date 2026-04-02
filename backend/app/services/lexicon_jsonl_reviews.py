from __future__ import annotations

import hashlib
import json
from collections import OrderedDict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from fastapi import HTTPException, status

from app.core.config import Settings
from app.services.lexicon_tool_imports import import_lexicon_tool_module

DECISION_SCHEMA_VERSION = "lexicon_review_decision.v1"
ALLOWED_DECISIONS = {"approved", "rejected", "reopened"}
DECISIONS_FILENAME = "review.decisions.jsonl"
REVIEWED_DIRNAME = "reviewed"
APPROVED_FILENAME = "approved.jsonl"
REJECTED_FILENAME = "rejected.jsonl"
REGENERATE_FILENAME = "regenerate.jsonl"
_REVIEW_INDEX_CACHE_MAX_ENTRIES = 2


ReviewIndexRow = dict[str, Any]
ReviewIndex = dict[str, Any]


def _import_review_prep_module() -> Any:
    return import_lexicon_tool_module("tools.lexicon.review_prep")


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def _payload_sha256(payload: Any) -> str:
    return hashlib.sha256(_canonical_json_bytes(payload)).hexdigest()


def _artifact_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


_REVIEW_INDEX_CACHE: OrderedDict[tuple[str, int, int, str, int, int], ReviewIndex] = OrderedDict()


def _file_signature(path: Path) -> tuple[int, int]:
    if not path.exists():
        return (0, 0)
    stat_result = path.stat()
    return (stat_result.st_mtime_ns, stat_result.st_size)


def _review_index_cache_key(artifact_path: Path, decisions_path: Path) -> tuple[str, int, int, str, int, int]:
    artifact_mtime, artifact_size = _file_signature(artifact_path)
    decisions_mtime, decisions_size = _file_signature(decisions_path)
    return (
        str(artifact_path.resolve()),
        artifact_mtime,
        artifact_size,
        str(decisions_path.resolve()),
        decisions_mtime,
        decisions_size,
    )


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
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Output path is not writable: {path}",
        ) from exc


def _snapshot_root(settings: Settings) -> Path:
    root = Path(settings.lexicon_snapshot_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root


def _voice_root(settings: Settings) -> Path:
    root = Path(settings.lexicon_voice_root).expanduser()
    if not root.is_absolute():
        root = (Path.cwd() / root).resolve()
    return root


def _allowed_roots(settings: Settings, *, extra_roots: list[Path] | None = None) -> list[Path]:
    roots = [Path.cwd().resolve(), _snapshot_root(settings)]
    if extra_roots:
        roots.extend(extra_roots)
    unique_roots: list[Path] = []
    for root in roots:
        if root not in unique_roots:
            unique_roots.append(root)
    return unique_roots


def resolve_repo_local_path(
    raw_path: str,
    *,
    settings: Settings,
    allow_missing: bool = False,
    extra_roots: list[Path] | None = None,
) -> Path:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()

    for root in _allowed_roots(settings, extra_roots=extra_roots):
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


def resolve_voice_manifest_path(raw_path: str, *, settings: Settings, allow_missing: bool = False) -> Path:
    return resolve_repo_local_path(
        raw_path,
        settings=settings,
        allow_missing=allow_missing,
        extra_roots=[_voice_root(settings)],
    )


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


def _iter_jsonl(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    if not path.exists():
        return
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
            yield line_number, payload


def _decision_status_from_review_status(review_status: str) -> str:
    return "reopened" if review_status == "pending" else review_status


def _review_status_from_decision(decision: dict[str, Any] | None) -> str:
    if not decision:
        return "pending"
    if decision["decision"] == "approved":
        return "approved"
    if decision["decision"] == "rejected":
        return "rejected"
    return "pending"


def _load_decisions_index(
    *,
    decisions_path: Path,
    artifact_sha256: str,
) -> dict[str, dict[str, Any]]:
    rows = _read_jsonl(decisions_path) if decisions_path.exists() else []
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

        supplied_artifact_sha = str(row.get("artifact_sha256") or "").strip()
        if supplied_artifact_sha and supplied_artifact_sha != artifact_sha256:
            raise HTTPException(status_code=400, detail=f"Decision row artifact_sha256 mismatch for {entry_id}")

        decisions_by_id[entry_id] = {
            "schema_version": DECISION_SCHEMA_VERSION,
            "artifact_sha256": artifact_sha256,
            "entry_id": entry_id,
            "entry_type": entry_type,
            "decision": decision,
            "decision_reason": row.get("decision_reason"),
            "compiled_payload_sha256": str(row.get("compiled_payload_sha256") or "").strip() or None,
            "reviewed_by": row.get("reviewed_by"),
            "reviewed_at": row.get("reviewed_at"),
        }
    return decisions_by_id


def _prepare_review_index_row(
    row_number: int,
    row: dict[str, Any],
    *,
    decision: dict[str, Any] | None,
) -> ReviewIndexRow:
    review_prep = _import_review_prep_module()
    prepared = review_prep.build_review_prep_rows([row], origin="realtime")[0]
    if prepared["reasons"]:
        raise HTTPException(
            status_code=400,
            detail=f"Compiled row {row_number} failed validation: {'; '.join(prepared['reasons'])}",
        )
    entry_id = str(row.get("entry_id") or "").strip()
    if not entry_id:
        raise HTTPException(status_code=400, detail=f"Compiled row {row_number} is missing entry_id")
    payload_sha = _payload_sha256(row)
    if decision and decision.get("compiled_payload_sha256") and decision["compiled_payload_sha256"] != payload_sha:
        raise HTTPException(status_code=400, detail=f"Decision row compiled_payload_sha256 mismatch for {entry_id}")
    return {
        "row_number": row_number,
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
        "review_status": _review_status_from_decision(decision),
        "decision_reason": decision.get("decision_reason") if decision else None,
        "reviewed_by": decision.get("reviewed_by") if decision else None,
        "reviewed_at": decision.get("reviewed_at") if decision else None,
        "compiled_payload_sha256": payload_sha,
    }


def _build_review_index(
    *,
    artifact_path: Path,
    decisions_path: Path,
) -> ReviewIndex:
    artifact_sha256 = _artifact_sha256(artifact_path)
    decisions_by_id = _load_decisions_index(decisions_path=decisions_path, artifact_sha256=artifact_sha256)
    rows: list[ReviewIndexRow] = []
    entry_ids_seen: set[str] = set()
    approved_count = 0
    rejected_count = 0
    for row_number, row in _iter_jsonl(artifact_path):
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            raise HTTPException(status_code=400, detail=f"Compiled row {row_number} is missing entry_id")
        if entry_id in entry_ids_seen:
            raise HTTPException(status_code=400, detail=f"Duplicate compiled entry_id in artifact: {entry_id}")
        entry_ids_seen.add(entry_id)
        decision = decisions_by_id.get(entry_id)
        index_row = _prepare_review_index_row(row_number, row, decision=decision)
        if index_row["review_status"] == "approved":
            approved_count += 1
        elif index_row["review_status"] == "rejected":
            rejected_count += 1
        rows.append(index_row)

    if not rows:
        raise HTTPException(status_code=400, detail="Compiled artifact is empty")

    unknown_decisions = sorted(set(decisions_by_id.keys()) - entry_ids_seen)
    if unknown_decisions:
        preview = ", ".join(unknown_decisions[:10])
        raise HTTPException(status_code=400, detail=f"Decision row references unknown entry_id {preview}")

    index = {
        "artifact_filename": artifact_path.name,
        "artifact_path": str(artifact_path),
        "artifact_sha256": artifact_sha256,
        "decisions_path": str(decisions_path),
        "total_items": len(rows),
        "pending_count": len(rows) - approved_count - rejected_count,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "rows": rows,
        "rows_by_id": {row["entry_id"]: row for row in rows},
    }
    return index


def _get_review_index(
    *,
    artifact_path: Path,
    decisions_path: Path,
) -> ReviewIndex:
    cache_key = _review_index_cache_key(artifact_path, decisions_path)
    cached = _REVIEW_INDEX_CACHE.get(cache_key)
    if cached is not None:
        _REVIEW_INDEX_CACHE.move_to_end(cache_key)
        return cached
    built = _build_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    _REVIEW_INDEX_CACHE[cache_key] = built
    while len(_REVIEW_INDEX_CACHE) > _REVIEW_INDEX_CACHE_MAX_ENTRIES:
        _REVIEW_INDEX_CACHE.popitem(last=False)
    return built


def _matches_review_filters(
    row: ReviewIndexRow,
    *,
    search: str | None,
    review_status: str | None,
) -> bool:
    if review_status and review_status != "all" and row["review_status"] != review_status:
        return False
    normalized_search = (search or "").strip().lower()
    if not normalized_search:
        return True
    haystacks = [
        row["entry_id"],
        row["display_text"],
        row.get("normalized_form") or "",
        row["review_summary"].get("primary_definition") or "",
        *(row.get("warning_labels") or []),
    ]
    return any(normalized_search in str(value).lower() for value in haystacks)


def _review_sort_key(row: ReviewIndexRow) -> tuple[int, int, int, str]:
    pending_bucket = 0 if row["review_status"] == "pending" else 1
    frequency_rank = row["frequency_rank"] if isinstance(row["frequency_rank"], int) else 10**9
    return (-int(row["warning_count"] or 0), pending_bucket, frequency_rank, str(row["display_text"]).lower())


def _load_compiled_payloads_for_row_numbers(
    *,
    artifact_path: Path,
    row_numbers: set[int],
) -> dict[int, dict[str, Any]]:
    if not row_numbers:
        return {}
    payloads: dict[int, dict[str, Any]] = {}
    for row_number, row in _iter_jsonl(artifact_path):
        if row_number in row_numbers:
            payloads[row_number] = row
        if len(payloads) == len(row_numbers):
            break
    return payloads


def get_jsonl_review_session_summary(
    *,
    artifact_path: Path,
    decisions_path: Path,
) -> dict[str, Any]:
    index = _get_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    return {
        "artifact_filename": index["artifact_filename"],
        "artifact_path": index["artifact_path"],
        "artifact_sha256": index["artifact_sha256"],
        "decisions_path": index["decisions_path"],
        "total_items": index["total_items"],
        "pending_count": index["pending_count"],
        "approved_count": index["approved_count"],
        "rejected_count": index["rejected_count"],
    }


def browse_jsonl_review_items(
    *,
    artifact_path: Path,
    decisions_path: Path,
    limit: int,
    offset: int,
    search: str | None = None,
    review_status: str | None = None,
) -> dict[str, Any]:
    index = _get_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    filtered_rows = [row for row in index["rows"] if _matches_review_filters(row, search=search, review_status=review_status)]
    filtered_rows.sort(key=_review_sort_key)
    page_rows = filtered_rows[offset: offset + limit]
    payloads_by_row_number = _load_compiled_payloads_for_row_numbers(
        artifact_path=artifact_path,
        row_numbers={int(row["row_number"]) for row in page_rows},
    )
    items = [
        {
            **row,
            "compiled_payload": payloads_by_row_number.get(int(row["row_number"]), {}),
        }
        for row in page_rows
    ]
    return {
        **get_jsonl_review_session_summary(artifact_path=artifact_path, decisions_path=decisions_path),
        "items": items,
        "limit": limit,
        "offset": offset,
        "filtered_total": len(filtered_rows),
        "has_more": offset + limit < len(filtered_rows),
        "search": search.strip() if search else None,
        "review_status": review_status or "all",
    }


def _get_review_item_payload(
    *,
    artifact_path: Path,
    decisions_path: Path,
    entry_id: str,
) -> dict[str, Any]:
    index = _get_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    row = index["rows_by_id"].get(entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Compiled review item not found")
    payloads = _load_compiled_payloads_for_row_numbers(
        artifact_path=artifact_path,
        row_numbers={int(row["row_number"])},
    )
    return {
        **row,
        "compiled_payload": payloads.get(int(row["row_number"]), {}),
    }

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
    index = _get_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    payloads_by_row_number = _load_compiled_payloads_for_row_numbers(
        artifact_path=artifact_path,
        row_numbers={int(row["row_number"]) for row in index["rows"]},
    )
    items = [
        {
            **row,
            "compiled_payload": payloads_by_row_number.get(int(row["row_number"]), {}),
        }
        for row in index["rows"]
    ]
    return {
        "artifact_filename": index["artifact_filename"],
        "artifact_path": index["artifact_path"],
        "artifact_sha256": index["artifact_sha256"],
        "decisions_path": index["decisions_path"],
        "total_items": index["total_items"],
        "pending_count": index["pending_count"],
        "approved_count": index["approved_count"],
        "rejected_count": index["rejected_count"],
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
    index = _get_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    current_item = index["rows_by_id"].get(entry_id)
    if current_item is None:
        raise HTTPException(status_code=404, detail="Compiled review item not found")
    decisions_by_id = _load_decisions_index(decisions_path=decisions_path, artifact_sha256=index["artifact_sha256"])
    decisions_by_id[entry_id] = {
        "schema_version": DECISION_SCHEMA_VERSION,
        "artifact_sha256": index["artifact_sha256"],
        "entry_id": entry_id,
        "entry_type": current_item["entry_type"],
        "decision": _decision_status_from_review_status(review_status),
        "decision_reason": decision_reason,
        "compiled_payload_sha256": current_item["compiled_payload_sha256"],
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    ordered_rows = [decisions_by_id[key] for key in sorted(decisions_by_id)]
    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(decisions_path, ordered_rows)
    return _get_review_item_payload(artifact_path=artifact_path, decisions_path=decisions_path, entry_id=entry_id)


def bulk_update_jsonl_review_decisions(
    *,
    artifact_path: Path,
    decisions_path: Path,
    review_status: str,
    decision_reason: str | None,
    reviewed_by: str,
) -> dict[str, Any]:
    if review_status not in {"pending", "approved", "rejected"}:
        raise HTTPException(status_code=400, detail="Invalid review_status")
    index = _get_review_index(artifact_path=artifact_path, decisions_path=decisions_path)
    reviewed_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    ordered_rows: list[dict[str, Any]] = []
    for item in index["rows"]:
        ordered_rows.append(
            {
                "schema_version": DECISION_SCHEMA_VERSION,
                "artifact_sha256": index["artifact_sha256"],
                "entry_id": item["entry_id"],
                "entry_type": item["entry_type"],
                "decision": _decision_status_from_review_status(review_status),
                "decision_reason": decision_reason,
                "compiled_payload_sha256": item["compiled_payload_sha256"],
                "reviewed_by": reviewed_by,
                "reviewed_at": reviewed_at,
            }
        )

    decisions_path.parent.mkdir(parents=True, exist_ok=True)
    _write_jsonl(decisions_path, ordered_rows)
    return get_jsonl_review_session_summary(artifact_path=artifact_path, decisions_path=decisions_path)


def materialize_jsonl_review_outputs(
    *,
    artifact_path: Path,
    decisions_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Output directory is not writable: {output_dir}",
        ) from exc
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
