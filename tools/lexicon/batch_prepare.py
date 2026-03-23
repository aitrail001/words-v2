"""Batch request preparation helpers for lexicon offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Iterable

from tools.lexicon.batch_ledger import append_jsonl_rows, build_batch_custom_id, build_batch_job_rows, load_jsonl_rows, parse_batch_custom_id, write_jsonl_rows
from tools.lexicon.enrich import build_phrase_enrichment_prompt
from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.models import LexemeRecord
from tools.lexicon.schemas.phrase_enrichment_schema import build_phrase_enrichment_response_schema


def _response_text_format(response_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "json_schema",
        "name": str(response_schema["name"]),
        "schema": response_schema["schema"],
        "strict": bool(response_schema.get("strict", True)),
    }


def _build_phrase_request_input(row: dict[str, Any]) -> str:
    try:
        lexeme = LexemeRecord(**row)
    except TypeError:
        display_form = str(row.get("display_form") or row.get("normalized_form") or row.get("entry_id") or "phrase").strip()
        phrase_kind = str(row.get("phrase_kind") or "phrase").strip() or "phrase"
        return (
            "You are enriching a learner-facing English phrase entry.\n"
            f"Display form: {display_form}\n"
            f"Phrase kind: {phrase_kind}\n"
            "Return structured learner-friendly phrase senses."
        )
    return build_phrase_enrichment_prompt(lexeme=lexeme)


def build_batch_request_rows(
    *,
    snapshot_id: str,
    model: str,
    prompt_version: str,
    rows: Iterable[dict[str, Any]],
    progress_callback: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    request_rows: list[dict[str, Any]] = []
    source_rows = list(rows)
    total_rows = len(source_rows)
    for index, row in enumerate(source_rows, start=1):
        entry_kind = str(row.get("entry_kind") or "word").strip().lower()
        entry_id = str(row.get("entry_id") or "").strip()
        if not entry_id:
            continue
        custom_id = build_batch_custom_id(
            entry_kind=entry_kind,
            snapshot_id=snapshot_id,
            entry_id=entry_id,
            attempt=1,
        )
        request_rows.append(
            {
                "custom_id": custom_id,
                "method": "POST",
                "url": "/responses",
                "body": (
                    {
                        "entry_kind": entry_kind,
                        "entry_id": entry_id,
                        "snapshot_id": snapshot_id,
                        "model": model,
                        "prompt_version": prompt_version,
                        "source_row": dict(row),
                        "input": _build_phrase_request_input(dict(row)),
                        "text": {"format": _response_text_format(build_phrase_enrichment_response_schema())},
                    }
                    if entry_kind == "phrase"
                    else {
                    "entry_kind": entry_kind,
                    "entry_id": entry_id,
                    "snapshot_id": snapshot_id,
                    "model": model,
                    "prompt_version": prompt_version,
                    "source_row": dict(row),
                    }
                ),
            }
        )
        if progress_callback is not None:
            progress_callback(
                entry_id=entry_id,
                entry_kind=entry_kind,
                custom_id=custom_id,
                completed_items=index,
                total_items=total_rows,
                status="prepared",
            )
    return request_rows


def write_batch_request_rows(output_path: Path, rows: Iterable[dict[str, Any]]) -> Path:
    return write_jsonl(output_path, rows)


def build_retry_batch_request_rows(
    *,
    snapshot_id: str,
    model: str,
    prompt_version: str,
    request_rows: Iterable[dict[str, Any]],
    failed_custom_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    failed_custom_ids = failed_custom_ids or set()
    retry_rows: list[dict[str, Any]] = []
    for row in request_rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        if failed_custom_ids and custom_id not in failed_custom_ids:
            continue
        parsed = parse_batch_custom_id(custom_id)
        attempt = int(parsed["attempt"]) + 1
        retry_custom_id = build_batch_custom_id(
            entry_kind=str(parsed["entry_kind"]),
            snapshot_id=snapshot_id,
            entry_id=str(parsed["entry_id"]),
            attempt=attempt,
        )
        body = dict(row.get("body") or {})
        body["model"] = model
        body["prompt_version"] = prompt_version
        body["attempt"] = attempt
        retry_rows.append(
            {
                "custom_id": retry_custom_id,
                "method": "POST",
                "url": "/responses",
                "body": body,
            }
        )
    return retry_rows
