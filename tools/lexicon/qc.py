"""QC helpers for lexicon offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.batch_ledger import load_jsonl_rows, write_jsonl_rows
from tools.lexicon.overrides import apply_manual_overrides, load_manual_overrides


def build_qc_verdict_rows(
    *,
    result_rows: Iterable[dict[str, Any]],
    reviewed_at: str,
    judge_model: str = "gpt-5-mini",
    prompt_version: str = "v1",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    verdict_rows: list[dict[str, Any]] = []
    for row in result_rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        status = str(row.get("status") or "").strip().lower()
        validation_status = str(row.get("validation_status") or "").strip().lower()
        pass_qc = status == "accepted" and validation_status == "valid"
        verdict_row = {
            "custom_id": custom_id,
            "entry_kind": row.get("entry_kind"),
            "entry_id": row.get("entry_id"),
            "verdict": "pass" if pass_qc else "fail",
            "confidence": 1.0 if pass_qc else 0.0,
            "reasons": [] if pass_qc else [f"status={status or 'unknown'}", f"validation_status={validation_status or 'unknown'}"],
            "review_notes": None if pass_qc else row.get("error_detail"),
            "model_name": judge_model,
            "prompt_version": prompt_version,
            "reviewed_at": reviewed_at,
        }
        verdict_rows.append(verdict_row)

    if overrides:
        verdict_rows = apply_manual_overrides(verdict_rows, overrides)
    return verdict_rows


def build_review_queue_rows(verdict_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    queue_rows: list[dict[str, Any]] = []
    for row in verdict_rows:
        verdict = str(row.get("verdict") or "").strip().lower()
        if verdict == "pass":
            continue
        queue_rows.append(
            {
                "custom_id": row.get("custom_id"),
                "entry_kind": row.get("entry_kind"),
                "entry_id": row.get("entry_id"),
                "review_status": "needs_review",
                "review_notes": row.get("review_notes"),
            }
        )
    return queue_rows


def run_batch_qc(
    *,
    snapshot_dir: Path,
    results_path: Path | None = None,
    qc_output_path: Path | None = None,
    review_queue_output_path: Path | None = None,
    overrides_path: Path | None = None,
    reviewed_at: str,
    judge_model: str = "gpt-5-mini",
    prompt_version: str = "v1",
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    result_rows = load_jsonl_rows(results_path or (snapshot_dir / "batch_results.jsonl"))
    overrides = load_manual_overrides(overrides_path) if overrides_path else {}
    verdict_rows = build_qc_verdict_rows(
        result_rows=result_rows,
        reviewed_at=reviewed_at,
        judge_model=judge_model,
        prompt_version=prompt_version,
        overrides=overrides,
    )
    write_jsonl_rows(qc_output_path or (snapshot_dir / "batch_qc.jsonl"), verdict_rows)
    review_queue_rows = build_review_queue_rows(verdict_rows)
    if review_queue_output_path is not None:
        write_jsonl_rows(review_queue_output_path, review_queue_rows)
    return verdict_rows, review_queue_rows


def run_review_apply(
    *,
    snapshot_dir: Path,
    qc_input_path: Path | None = None,
    qc_output_path: Path | None = None,
    review_queue_output_path: Path | None = None,
    overrides_path: Path | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    verdict_rows = load_jsonl_rows(qc_input_path or (snapshot_dir / "batch_qc.jsonl"))
    overrides = load_manual_overrides(overrides_path) if overrides_path else {}
    if overrides:
        verdict_rows = apply_manual_overrides(verdict_rows, overrides)
    write_jsonl_rows(qc_output_path or (snapshot_dir / "batch_qc.jsonl"), verdict_rows)
    review_queue_rows = build_review_queue_rows(verdict_rows)
    if review_queue_output_path is not None:
        write_jsonl_rows(review_queue_output_path, review_queue_rows)
    return verdict_rows, review_queue_rows
