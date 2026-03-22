"""QC helpers for lexicon offline runs."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

from tools.lexicon.batch_ledger import load_jsonl_rows, write_jsonl_rows
from tools.lexicon.overrides import apply_manual_overrides, load_manual_overrides
from tools.lexicon.review_prep import build_review_prep_rows, build_review_queue_rows as build_shared_review_queue_rows


def build_qc_verdict_rows(
    *,
    result_rows: Iterable[dict[str, Any]],
    reviewed_at: str,
    judge_model: str = "gpt-5-mini",
    prompt_version: str = "v1",
    overrides: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    qc_input_rows: list[dict[str, Any]] = []
    for row in result_rows:
        custom_id = str(row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        qc_input_rows.append(dict(row))

    verdict_rows = build_review_prep_rows(qc_input_rows, origin="batch")
    for verdict_row in verdict_rows:
        verdict_row["model_name"] = judge_model
        verdict_row["prompt_version"] = prompt_version
        verdict_row["reviewed_at"] = reviewed_at

    if overrides:
        verdict_rows = apply_manual_overrides(verdict_rows, overrides)
    return verdict_rows


def build_review_queue_rows(verdict_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return build_shared_review_queue_rows(verdict_rows)


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
