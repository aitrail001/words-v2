"""Batch output ingestion helpers for lexicon offline runs."""

from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Callable, Iterable

from tools.lexicon.batch_ledger import append_jsonl_rows, load_jsonl_rows
from tools.lexicon.compile_export import compile_word_result
from tools.lexicon.enrich import (
    _build_phrase_job_outcome,
    _build_word_job_outcome,
    _extract_output_text,
    _parse_json_payload_text,
    _validate_openai_compatible_phrase_payload,
    _validate_openai_compatible_word_payload,
)
from tools.lexicon.models import LexemeRecord
from tools.lexicon.review_prep import build_review_prep_rows


def _stable_hash(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return sha256(encoded).hexdigest()


def build_batch_result_rows(
    *,
    request_rows: Iterable[dict[str, Any]],
    output_rows: Iterable[dict[str, Any]],
    ingested_at: str,
) -> list[dict[str, Any]]:
    requests_by_custom_id = {
        str(row.get("custom_id") or "").strip(): dict(row)
        for row in request_rows
        if str(row.get("custom_id") or "").strip()
    }
    results: list[dict[str, Any]] = []
    for output_row in output_rows:
        custom_id = str(output_row.get("custom_id") or "").strip()
        if not custom_id:
            continue
        request_row = requests_by_custom_id.get(custom_id, {})
        response_payload = output_row.get("response")
        if response_payload is None:
            response_payload = output_row.get("body")
        error_payload = output_row.get("error") or output_row.get("response_error")
        has_error = error_payload is not None
        status = "failed" if has_error else "accepted"
        validation_status = "invalid" if has_error else "valid"
        qc_status = "pending" if not has_error else "needs_review"
        attempt = int(output_row.get("attempt") or request_row.get("attempt") or 1)
        result_row = {
            "custom_id": custom_id,
            "request_body": dict(request_row.get("body") or {}),
            "entry_id": output_row.get("entry_id") or request_row.get("entry_id") or dict(request_row.get("body") or {}).get("entry_id"),
            "entry_kind": output_row.get("entry_kind") or request_row.get("entry_kind") or dict(request_row.get("body") or {}).get("entry_kind"),
            "status": status,
            "validation_status": validation_status,
            "qc_status": qc_status,
            "attempt": attempt,
            "model": output_row.get("model") or request_row.get("body", {}).get("model"),
            "output_hash": _stable_hash(response_payload) if response_payload is not None else None,
            "error_class": error_payload.get("class") if isinstance(error_payload, dict) else None,
            "error_detail": error_payload.get("message") if isinstance(error_payload, dict) else error_payload,
            "ingested_at": ingested_at,
            "raw_output": dict(output_row),
        }
        results.append(result_row)
    return results


def split_batch_result_rows(result_rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    accepted_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    for row in result_rows:
        status = str(row.get("status") or "").strip().lower()
        if status == "accepted":
            accepted_rows.append(dict(row))
        else:
            failure_rows.append(dict(row))
    return accepted_rows, failure_rows


def _extract_batch_response_body(row: dict[str, Any]) -> dict[str, Any]:
    raw_output = dict(row.get("raw_output") or {})
    response_payload = raw_output.get("response")
    if isinstance(response_payload, dict):
        body = response_payload.get("body")
        if isinstance(body, dict):
            return body
        return response_payload
    body = raw_output.get("body")
    if isinstance(body, dict):
        return body
    raise RuntimeError("batch result row does not include a response body")


def _materialize_batch_word_row(row: dict[str, Any]) -> dict[str, Any] | None:
    request_body = dict(row.get("request_body") or {})
    source_row = dict(request_body.get("source_row") or {})
    if not source_row:
        raise RuntimeError("batch result row is missing request_body.source_row")
    lexeme = LexemeRecord(**source_row)
    response_body = _extract_batch_response_body(row)
    payload = _parse_json_payload_text(_extract_output_text(response_body))
    validated_payload = _validate_openai_compatible_word_payload(payload, lexeme=lexeme, senses=[])
    outcome = _build_word_job_outcome(
        lexeme=lexeme,
        response=validated_payload,
        model_name=str(row.get("model") or request_body.get("model") or ""),
        prompt_version=str(request_body.get("prompt_version") or ""),
        generation_run_id=str(row.get("custom_id") or ""),
        review_status="draft",
        generated_at=str(row.get("ingested_at") or ""),
    )
    compiled = compile_word_result(lexeme=lexeme, enrichments=outcome.records)
    if compiled is None:
        return None
    compiled_row = compiled.to_dict()
    review_row = build_review_prep_rows([compiled_row], origin="batch")[0]
    if str(review_row.get("verdict") or "").strip().lower() != "pass":
        messages = [
            *(str(item) for item in (review_row.get("reasons") or []) if str(item).strip()),
            *(str(item) for item in (review_row.get("warning_labels") or []) if str(item).strip()),
        ]
        raise RuntimeError("; ".join(messages or ["compiled QC failed"]))
    return compiled_row


def _materialize_batch_phrase_row(row: dict[str, Any]) -> dict[str, Any] | None:
    request_body = dict(row.get("request_body") or {})
    source_row = dict(request_body.get("source_row") or {})
    if not source_row:
        raise RuntimeError("batch result row is missing request_body.source_row")
    source_row.pop("entry_kind", None)
    display_form = str(
        source_row.get("display_form")
        or source_row.get("lemma")
        or source_row.get("normalized_form")
        or source_row.get("entry_id")
        or request_body.get("entry_id")
        or "phrase"
    ).strip()
    normalized_form = str(source_row.get("normalized_form") or display_form.lower()).strip().lower()
    source_row.setdefault("snapshot_id", str(source_row.get("snapshot_id") or request_body.get("snapshot_id") or ""))
    source_row.setdefault("lexeme_id", str(source_row.get("lexeme_id") or source_row.get("entry_id") or request_body.get("entry_id") or normalized_form))
    source_row.setdefault("lemma", display_form.lower())
    source_row.setdefault("language", "en")
    source_row.setdefault("wordfreq_rank", 0)
    source_row.setdefault("is_wordnet_backed", False)
    source_row.setdefault("source_refs", ["batch_prepare"])
    source_row.setdefault("created_at", str(source_row.get("created_at") or row.get("ingested_at") or ""))
    source_row.setdefault("entry_type", "phrase")
    source_row.setdefault("normalized_form", normalized_form)
    source_row.setdefault("display_form", display_form)
    source_row.setdefault("phrase_kind", str(source_row.get("phrase_kind") or "multiword_expression"))
    lexeme = LexemeRecord(**source_row)
    response_body = _extract_batch_response_body(row)
    payload = _parse_json_payload_text(_extract_output_text(response_body))
    validated_payload = _validate_openai_compatible_phrase_payload(payload)
    outcome = _build_phrase_job_outcome(
        lexeme=lexeme,
        response=validated_payload,
        model_name=str(row.get("model") or request_body.get("model") or ""),
        prompt_version=str(request_body.get("prompt_version") or ""),
        generation_run_id=str(row.get("custom_id") or ""),
        review_status="draft",
        generated_at=str(row.get("ingested_at") or ""),
    )
    compiled = compile_word_result(lexeme=lexeme, enrichments=outcome.records)
    if compiled is None:
        return None
    compiled_row = compiled.to_dict()
    review_row = build_review_prep_rows([compiled_row], origin="batch")[0]
    if str(review_row.get("verdict") or "").strip().lower() != "pass":
        messages = [
            *(str(item) for item in (review_row.get("reasons") or []) if str(item).strip()),
            *(str(item) for item in (review_row.get("warning_labels") or []) if str(item).strip()),
        ]
        raise RuntimeError("; ".join(messages or ["compiled QC failed"]))
    return compiled_row


def ingest_batch_outputs(
    snapshot_dir: Path,
    output_path: Path,
    *,
    request_path: Path | None = None,
    batch_output_path: Path,
    ingested_at: str,
    failure_output_path: Path | None = None,
    progress_callback: Callable[..., None] | None = None,
) -> list[dict[str, Any]]:
    request_rows = load_jsonl_rows(request_path or (snapshot_dir / "batch_requests.jsonl"))
    output_rows = load_jsonl_rows(batch_output_path)
    result_rows = build_batch_result_rows(
        request_rows=request_rows,
        output_rows=output_rows,
        ingested_at=ingested_at,
    )
    words_output_path = snapshot_dir / "words.enriched.jsonl"
    regenerate_output_path = snapshot_dir / "words.regenerate.jsonl"
    finalized_result_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    regenerate_rows: list[dict[str, Any]] = []
    total_rows = len(result_rows)
    for index, row in enumerate(result_rows, start=1):
        entry_kind = str(row.get("entry_kind") or "word").strip().lower()
        if entry_kind not in {"word", "phrase"}:
            finalized_result_rows.append(dict(row))
            if str(row.get("status") or "").strip().lower() != "accepted":
                failure_rows.append(dict(row))
            if progress_callback is not None:
                progress_callback(
                    entry_id=row.get("entry_id"),
                    entry_kind=entry_kind,
                    completed_items=index,
                    total_items=total_rows,
                    status=str(row.get("status") or "").strip().lower() or "unknown",
                )
            continue
        if str(row.get("status") or "").strip().lower() != "accepted":
            finalized_result_rows.append(dict(row))
            failure_rows.append(dict(row))
            if progress_callback is not None:
                progress_callback(
                    entry_id=row.get("entry_id"),
                    entry_kind=entry_kind,
                    completed_items=index,
                    total_items=total_rows,
                    status=str(row.get("status") or "").strip().lower() or "failed",
                )
            continue
        try:
            compiled_row = (
                _materialize_batch_phrase_row(row)
                if entry_kind == "phrase"
                else _materialize_batch_word_row(row)
            )
        except RuntimeError as exc:
            failed_row = dict(row)
            failed_row["status"] = "failed"
            failed_row["validation_status"] = "invalid"
            failed_row["qc_status"] = "needs_review"
            failed_row["error_detail"] = str(exc)
            finalized_result_rows.append(failed_row)
            failure_rows.append(failed_row)
            regenerate_rows.append(
                {
                    "custom_id": failed_row.get("custom_id"),
                    "entry_id": failed_row.get("entry_id"),
                    "entry_kind": failed_row.get("entry_kind"),
                    "failure_reason": str(exc),
                }
            )
            if progress_callback is not None:
                progress_callback(
                    entry_id=failed_row.get("entry_id"),
                    entry_kind=entry_kind,
                    completed_items=index,
                    total_items=total_rows,
                    status="failed",
                    error=str(exc),
                )
            continue
        finalized_result_rows.append(dict(row))
        if compiled_row is not None:
            append_jsonl_rows(words_output_path, [compiled_row])
        if progress_callback is not None:
            progress_callback(
                entry_id=row.get("entry_id"),
                entry_kind=entry_kind,
                completed_items=index,
                total_items=total_rows,
                status="accepted",
            )
    if finalized_result_rows:
        append_jsonl_rows(output_path, finalized_result_rows)
    if failure_output_path is not None and failure_rows:
        append_jsonl_rows(failure_output_path, failure_rows)
    if regenerate_rows:
        append_jsonl_rows(regenerate_output_path, regenerate_rows)
    return finalized_result_rows


def build_batch_output_summary(result_rows: Iterable[dict[str, Any]]) -> dict[str, int]:
    summary = {"total": 0, "accepted": 0, "failed": 0, "valid": 0, "invalid": 0, "pending": 0, "needs_review": 0}
    for row in result_rows:
        summary["total"] += 1
        for field in ("status", "validation_status", "qc_status"):
            value = str(row.get(field) or "").strip().lower()
            if value in summary:
                summary[value] += 1
    return summary
