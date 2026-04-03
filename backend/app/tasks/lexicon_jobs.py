from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from celery.exceptions import Retry
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.models.lexicon_artifact_review_batch import LexiconArtifactReviewBatch
from app.models.lexicon_artifact_review_item import LexiconArtifactReviewItem
from app.models.lexicon_job import LexiconJob
from app.services.lexicon_compiled_reviews import materialize_compiled_review_batch
from app.services.lexicon_compiled_review_decisions import (
    BULK_REVIEW_CHUNK_SIZE,
    add_review_item_event,
    apply_review_decision,
    recalculate_batch_counts,
    upsert_regeneration_request_sync,
    utc_now,
)
from app.services.lexicon_jobs import (
    apply_lexicon_job_cancelled,
    apply_lexicon_job_completed,
    apply_lexicon_job_failed,
    apply_lexicon_job_progress,
    apply_lexicon_job_started,
)
from app.services.lexicon_jsonl_reviews import materialize_jsonl_review_outputs
from app.services.lexicon_tool_imports import import_lexicon_tool_module

settings = get_settings()
sync_engine = create_engine(settings.database_url_sync)
PROGRESS_COMMIT_CALLBACK_INTERVAL = 25
VOICE_IMPORT_LEXICAL_GROUP_CHUNK_SIZE = 100
IMPORT_DB_ROW_CHUNK_SIZE = 250
IMPORT_DB_COMMIT_BATCH_SIZE = 250
IMPORT_DB_EXECUTION_MODE = "continuation"
IMPORT_DB_SINGLE_TASK_PROGRESS_EMIT_EVERY = 250
IMPORT_DB_SINGLE_TASK_CANCEL_CHECK_SECONDS = 2.0
CANCEL_CHECK_INTERVAL = 25


class _JobCancelled(RuntimeError):
    pass


def _import_db_module() -> Any:
    return import_lexicon_tool_module("tools.lexicon.import_db")


def _voice_import_db_module() -> Any:
    return import_lexicon_tool_module("tools.lexicon.voice_import_db")


def _load_job(db: Session, job_id: str) -> LexiconJob:
    result = db.execute(select(LexiconJob).where(LexiconJob.id == uuid.UUID(job_id)))
    job = result.scalar_one_or_none()
    if job is None:
        raise RuntimeError("Lexicon job not found")
    return job


def _is_job_cancel_requested(db: Session, job_id: str) -> bool:
    result = db.execute(select(LexiconJob.status).where(LexiconJob.id == uuid.UUID(job_id)))
    status_value = result.scalar_one_or_none()
    return status_value == "cancel_requested"


def _set_job_progress_summary(
    job: LexiconJob,
    *,
    phase: str,
    total: int,
    validated: int,
    imported: int,
    skipped: int,
    failed: int,
) -> None:
    total_value = max(total, 0)
    validated_value = max(min(validated, total_value), 0)
    imported_value = max(imported, 0)
    skipped_value = max(skipped, 0)
    failed_value = max(failed, 0)
    payload = dict(job.request_payload or {})
    existing_summary = dict(payload.get("progress_summary") or {})
    previous_phase = str(existing_summary.get("phase") or "")
    previous_phase_started_at_ms = int(existing_summary.get("phase_started_at_ms") or 0)
    phase_started_at_ms = int(time.time() * 1000) if previous_phase != phase else previous_phase_started_at_ms
    if phase_started_at_ms <= 0:
        phase_started_at_ms = int(time.time() * 1000)
    payload["progress_summary"] = {
        "phase": phase,
        "phase_started_at_ms": phase_started_at_ms,
        "total": total_value,
        "validated": validated_value,
        "imported": imported_value,
        "skipped": skipped_value,
        "failed": failed_value,
        "to_validate": max(total_value - validated_value, 0),
        "to_import": max(total_value - imported_value - skipped_value - failed_value, 0),
    }
    job.request_payload = payload


def _set_job_progress_timing(
    job: LexiconJob,
    *,
    queue_wait_ms: int,
    elapsed_ms: int,
    validation_elapsed_ms: int,
    import_elapsed_ms: int,
    finalization_elapsed_ms: int = 0,
) -> None:
    resolved_elapsed_ms = max(elapsed_ms, 0)
    resolved_validation_elapsed_ms = max(validation_elapsed_ms, 0)
    resolved_import_elapsed_ms = max(import_elapsed_ms, 0)
    resolved_finalization_elapsed_ms = max(finalization_elapsed_ms, 0)
    orchestration_elapsed_ms = max(
        resolved_elapsed_ms
        - resolved_validation_elapsed_ms
        - resolved_import_elapsed_ms
        - resolved_finalization_elapsed_ms,
        0,
    )
    payload = dict(job.request_payload or {})
    payload["progress_timing"] = {
        "queue_wait_ms": max(queue_wait_ms, 0),
        "elapsed_ms": resolved_elapsed_ms,
        "validation_elapsed_ms": resolved_validation_elapsed_ms,
        "import_elapsed_ms": resolved_import_elapsed_ms,
        "finalization_elapsed_ms": resolved_finalization_elapsed_ms,
        "orchestration_elapsed_ms": orchestration_elapsed_ms,
    }
    job.request_payload = payload


def _job_queue_wait_ms(job: LexiconJob) -> int:
    if job.created_at is None or job.started_at is None:
        return 0
    return max(int((job.started_at - job.created_at).total_seconds() * 1000), 0)


class _ProgressCommitThrottle:
    def __init__(self, db: Session, *, callback_interval: int = PROGRESS_COMMIT_CALLBACK_INTERVAL) -> None:
        self._db = db
        self._callback_interval = max(callback_interval, 1)
        self._pending_callbacks = 0
        self._dirty = False
        self.flush_count = 0

    def record_update(self, *, callback: bool = False, force: bool = False) -> None:
        self._dirty = True
        if callback:
            self._pending_callbacks += 1
        if force or (callback and self._pending_callbacks >= self._callback_interval):
            self.flush()

    def flush(self) -> None:
        if not self._dirty:
            return
        self._db.commit()
        self.flush_count += 1
        self._dirty = False
        self._pending_callbacks = 0


def _voice_current_group_label(row: dict[str, Any]) -> str | None:
    for key in ("word", "display_form", "display_text", "normalized_form", "entry_id", "source_text"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    progress_label = str(row.get("_progress_label") or "").strip()
    return progress_label or None


def _voice_progress_delta(row: dict[str, Any]) -> tuple[int, int, int]:
    progress_label = str(row.get("_progress_label") or "").strip()
    if progress_label.startswith("Importing "):
        return 1, 0, 0
    if progress_label.startswith("Skipping "):
        return 0, 1, 0
    if progress_label.startswith("Failed "):
        return 0, 0, 1
    return 0, 0, 0


def _voice_result_progress_counts(result_payload: dict[str, Any]) -> tuple[int, int, int]:
    skipped_rows = int(result_payload.get("skipped_rows", 0))
    unresolved_rows = (
        int(result_payload.get("missing_words", 0))
        + int(result_payload.get("missing_meanings", 0))
        + int(result_payload.get("missing_examples", 0))
    )
    failed_rows = int(result_payload.get("failed_rows", 0)) + unresolved_rows
    imported_rows = int(result_payload.get("created_assets", 0)) + int(result_payload.get("updated_assets", 0))
    return imported_rows, skipped_rows, failed_rows


def _import_result_progress_counts(result_payload: dict[str, Any]) -> tuple[int, int, int]:
    skipped_rows = (
        int(result_payload.get("skipped_words", 0))
        + int(result_payload.get("skipped_phrases", 0))
        + int(result_payload.get("skipped_reference_entries", 0))
    )
    failed_rows = int(result_payload.get("failed_rows", 0))
    imported_rows = max(int(result_payload.get("processed_row_count", 0)) - skipped_rows - failed_rows, 0)
    return imported_rows, skipped_rows, failed_rows


def process_compiled_review_bulk_job(
    db: Session,
    *,
    job: LexiconJob,
    batch_id: uuid.UUID,
    review_status: str,
    decision_reason: str | None,
    scope: str,
    chunk_size: int,
) -> dict[str, Any]:
    batch = db.execute(
        select(LexiconArtifactReviewBatch).where(LexiconArtifactReviewBatch.id == batch_id)
    ).scalar_one_or_none()
    if batch is None:
        raise RuntimeError("Compiled review batch not found")
    if scope != "all_pending":
        raise RuntimeError("Unsupported compiled review bulk scope")

    target_status = "pending" if review_status in {"approved", "rejected"} else None
    items = list(
        db.execute(
            select(LexiconArtifactReviewItem)
            .where(
                LexiconArtifactReviewItem.batch_id == batch_id,
                (
                    LexiconArtifactReviewItem.review_status == target_status
                    if target_status is not None
                    else LexiconArtifactReviewItem.review_status != "pending"
                ),
            )
            .order_by(
                LexiconArtifactReviewItem.review_priority.asc(),
                LexiconArtifactReviewItem.display_text.asc(),
                LexiconArtifactReviewItem.id.asc(),
            )
        ).scalars().all()
    )
    total = len(items)
    reviewed_at = utc_now()
    processed_count = 0
    initial_total_items = batch.total_items
    approved_count = batch.approved_count
    rejected_count = batch.rejected_count

    if total == 0:
        apply_lexicon_job_progress(job, progress_completed=0, progress_total=0, current_label=None)
        recalculate_batch_counts(
            batch,
            total_items=initial_total_items,
            approved_count=approved_count,
            rejected_count=rejected_count,
            updated_at=reviewed_at,
        )
        return {
            "batch_id": str(batch_id),
            "processed_count": 0,
            "approved_count": batch.approved_count,
            "rejected_count": batch.rejected_count,
            "pending_count": batch.pending_count,
            "failed_count": 0,
            "scope": scope,
            "review_status": review_status,
        }

    for start in range(0, total, chunk_size):
        chunk = items[start:start + chunk_size]
        for item in chunk:
            previous_status = apply_review_decision(
                item,
                review_status=review_status,
                decision_reason=decision_reason,
                actor_user_id=job.created_by,
                reviewed_at=reviewed_at,
            )
            if previous_status == "approved":
                approved_count -= 1
            elif previous_status == "rejected":
                rejected_count -= 1

            if review_status == "approved":
                approved_count += 1
            elif review_status == "rejected":
                rejected_count += 1

            upsert_regeneration_request_sync(db=db, batch=batch, item=item, actor_user_id=job.created_by)
            db.add(add_review_item_event(
                item=item,
                previous_status=previous_status,
                review_status=review_status,
                actor_user_id=job.created_by,
                reason=decision_reason,
            ))
        processed_count += len(chunk)
        recalculate_batch_counts(
            batch,
            total_items=initial_total_items,
            approved_count=approved_count,
            rejected_count=rejected_count,
            updated_at=reviewed_at,
        )
        apply_lexicon_job_progress(
            job,
            progress_completed=processed_count,
            progress_total=total,
            current_label=chunk[-1].display_text if chunk else None,
        )
        db.commit()

    return {
        "batch_id": str(batch_id),
        "processed_count": processed_count,
        "approved_count": batch.approved_count,
        "rejected_count": batch.rejected_count,
        "pending_count": batch.pending_count,
        "failed_count": 0,
        "scope": scope,
        "review_status": review_status,
    }


@celery_app.task(bind=True, name="run_lexicon_import_db", max_retries=None)
def run_lexicon_import_db(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        if job.status == "cancel_requested":
            _set_job_progress_summary(
                job,
                phase="cancelled",
                total=job.progress_total,
                validated=job.progress_completed,
                imported=0,
                skipped=0,
                failed=0,
            )
            apply_lexicon_job_cancelled(job)
            db.commit()
            return {"status": "cancelled"}
        request_payload = dict(job.request_payload or {})
        requested_execution_mode = str(request_payload.get("import_execution_mode") or IMPORT_DB_EXECUTION_MODE).strip().lower()
        execution_mode = requested_execution_mode if requested_execution_mode in {"continuation", "single_task"} else IMPORT_DB_EXECUTION_MODE
        requested_chunk_rows = max(int(request_payload.get("import_row_chunk_size") or IMPORT_DB_ROW_CHUNK_SIZE), 1)
        requested_commit_rows = max(int(request_payload.get("import_row_commit_size") or IMPORT_DB_COMMIT_BATCH_SIZE), 1)
        commit_every_rows = min(requested_commit_rows, requested_chunk_rows)
        progress_emit_every = max(
            int(request_payload.get("import_progress_emit_every") or IMPORT_DB_SINGLE_TASK_PROGRESS_EMIT_EVERY),
            1,
        )
        cancel_check_seconds = max(
            float(request_payload.get("import_cancel_check_seconds") or IMPORT_DB_SINGLE_TASK_CANCEL_CHECK_SECONDS),
            0.2,
        )
        slice_row_count = requested_chunk_rows
        request_payload["import_execution_mode"] = execution_mode
        request_payload["import_row_chunk_size"] = requested_chunk_rows
        request_payload["import_row_commit_size"] = commit_every_rows
        request_payload["import_progress_emit_every"] = progress_emit_every
        request_payload["import_cancel_check_seconds"] = cancel_check_seconds
        request_payload["progress_commit_callback_interval"] = PROGRESS_COMMIT_CALLBACK_INTERVAL
        job.request_payload = request_payload
        import_db = _import_db_module()
        row_summary = dict(request_payload.get("row_summary") or {})
        total_rows = int(row_summary.get("row_count") or 0)
        row_cursor = max(int(request_payload.get("import_row_cursor") or 0), 0)
        is_continuation_slice = row_cursor > 0
        accumulator = dict(request_payload.get("import_accumulator") or {})
        observed_imported_rows, observed_skipped_rows, observed_failed_rows = _import_result_progress_counts(accumulator)
        worker_started_at = time.monotonic()
        validation_started_at = worker_started_at
        import_started_at: float | None = None
        queue_wait_ms = _job_queue_wait_ms(job)
        timing_payload = dict(request_payload.get("progress_timing") or {})
        base_elapsed_ms = max(int(timing_payload.get("elapsed_ms") or 0), 0)
        base_validation_elapsed_ms = max(int(timing_payload.get("validation_elapsed_ms") or 0), 0)
        base_import_elapsed_ms = max(int(timing_payload.get("import_elapsed_ms") or 0), 0)
        base_finalization_elapsed_ms = max(int(timing_payload.get("finalization_elapsed_ms") or 0), 0)
        finalization_started_at: float | None = None

        def _refresh_timing() -> None:
            now = time.monotonic()
            validation_finished_at = import_started_at if import_started_at is not None else now
            validation_elapsed_increment_ms = (
                0
                if is_continuation_slice
                else int((validation_finished_at - validation_started_at) * 1000)
            )
            finalization_elapsed_increment_ms = (
                int((now - finalization_started_at) * 1000)
                if finalization_started_at is not None
                else 0
            )
            _set_job_progress_timing(
                job,
                queue_wait_ms=queue_wait_ms,
                elapsed_ms=base_elapsed_ms + int((now - worker_started_at) * 1000),
                validation_elapsed_ms=base_validation_elapsed_ms + validation_elapsed_increment_ms,
                import_elapsed_ms=base_import_elapsed_ms + (
                    int((now - import_started_at) * 1000) if import_started_at is not None else 0
                ),
                finalization_elapsed_ms=base_finalization_elapsed_ms + finalization_elapsed_increment_ms,
            )

        def _mark_import_started() -> None:
            nonlocal import_started_at
            if import_started_at is None:
                import_started_at = time.monotonic()

        existing_progress_summary = dict(request_payload.get("progress_summary") or {})
        if row_cursor > 0 and existing_progress_summary:
            _set_job_progress_summary(
                job,
                phase="importing",
                total=total_rows,
                validated=int(existing_progress_summary.get("validated") or total_rows),
                imported=int(existing_progress_summary.get("imported") or observed_imported_rows),
                skipped=int(existing_progress_summary.get("skipped") or observed_skipped_rows),
                failed=int(existing_progress_summary.get("failed") or observed_failed_rows),
            )
        else:
            _set_job_progress_summary(
                job,
                phase="validating",
                total=total_rows,
                validated=0,
                imported=observed_imported_rows,
                skipped=observed_skipped_rows,
                failed=observed_failed_rows,
            )
        _refresh_timing()
        db.commit()
        progress_committer = _ProgressCommitThrottle(db)
        import_callback_count = 0
        preflight_callback_count = 0
        progress_update_count = 0
        cancel_query_count = 0
        cancel_skip_count = 0
        import_callback_elapsed_ms = 0
        preflight_callback_elapsed_ms = 0
        last_cancel_check_at = 0.0

        def _persist_perf_metrics() -> None:
            payload = dict(job.request_payload or {})
            payload["performance_metrics"] = {
                "execution_mode": execution_mode,
                "import_callback_count": import_callback_count,
                "preflight_callback_count": preflight_callback_count,
                "progress_update_count": progress_update_count,
                "progress_flush_count": progress_committer.flush_count,
                "cancel_query_count": cancel_query_count,
                "cancel_skip_count": cancel_skip_count,
                "import_callback_elapsed_ms": import_callback_elapsed_ms,
                "preflight_callback_elapsed_ms": preflight_callback_elapsed_ms,
            }
            job.request_payload = payload
        try:
            cancel_check_counter = 0

            def _raise_if_cancel_requested(*, force: bool = False) -> None:
                nonlocal cancel_check_counter
                nonlocal last_cancel_check_at
                nonlocal cancel_query_count
                nonlocal cancel_skip_count
                now = time.monotonic()
                if execution_mode == "single_task":
                    if not force and (now - last_cancel_check_at) < cancel_check_seconds:
                        cancel_skip_count += 1
                        return
                    last_cancel_check_at = now
                    cancel_query_count += 1
                    if _is_job_cancel_requested(db, job_id):
                        raise _JobCancelled("Import cancelled by user.")
                    return
                cancel_check_counter += 1
                if not force and cancel_check_counter % CANCEL_CHECK_INTERVAL != 0:
                    cancel_skip_count += 1
                    return
                cancel_query_count += 1
                if _is_job_cancel_requested(db, job_id):
                    raise _JobCancelled("Import cancelled by user.")

            def _row_label(row: dict[str, Any], *, default_prefix: str, completed_rows: int, total_rows: int) -> str | None:
                explicit_label = str(row.get("_progress_label") or "").strip()
                if default_prefix == "Importing" and explicit_label.startswith("Validating "):
                    explicit_label = ""
                if explicit_label:
                    entry_label = str(
                        row.get("display_form")
                        or row.get("display_text")
                        or row.get("word")
                        or row.get("normalized_form")
                        or row.get("entry_id")
                        or ""
                    ).strip()
                    return f"{explicit_label}: {entry_label}" if entry_label and entry_label not in explicit_label else explicit_label
                entry_label = str(
                    row.get("display_form")
                    or row.get("display_text")
                    or row.get("word")
                    or row.get("normalized_form")
                        or row.get("entry_id")
                        or ""
                    ).strip()
                if not entry_label:
                    return default_prefix
                return f"{default_prefix} {completed_rows}/{total_rows}: {entry_label}" if total_rows > 0 else f"{default_prefix}: {entry_label}"

            def _preflight_progress(row: dict[str, Any], completed_rows: int, total_rows: int) -> None:
                nonlocal preflight_callback_count
                nonlocal preflight_callback_elapsed_ms
                nonlocal progress_update_count
                started_at = time.monotonic()
                _raise_if_cancel_requested()
                preflight_callback_count += 1
                should_emit = (
                    execution_mode != "single_task"
                    or completed_rows == 1
                    or completed_rows >= total_rows
                    or completed_rows % progress_emit_every == 0
                )
                if should_emit:
                    _set_job_progress_summary(
                        job,
                        phase="validating",
                        total=total_rows,
                        validated=completed_rows,
                        imported=0,
                        skipped=0,
                        failed=0,
                    )
                    apply_lexicon_job_progress(
                        job,
                        progress_completed=completed_rows,
                        progress_total=total_rows,
                        current_label=_row_label(
                            row,
                            default_prefix="Validating",
                            completed_rows=completed_rows,
                            total_rows=total_rows,
                        ),
                    )
                    _refresh_timing()
                    _persist_perf_metrics()
                    progress_committer.record_update(callback=True)
                    progress_update_count += 1
                preflight_callback_elapsed_ms += int((time.monotonic() - started_at) * 1000)

            def _import_started() -> None:
                _raise_if_cancel_requested(force=True)
                _mark_import_started()
                _refresh_timing()
                _persist_perf_metrics()
                progress_committer.record_update(force=True)

            def _import_progress(row: dict[str, Any], completed_rows: int, total_rows: int) -> None:
                nonlocal observed_skipped_rows
                nonlocal import_callback_count
                nonlocal import_callback_elapsed_ms
                nonlocal progress_update_count
                started_at = time.monotonic()
                _raise_if_cancel_requested()
                import_callback_count += 1
                _mark_import_started()
                if str(row.get("_progress_label") or "").startswith("Skipping existing"):
                    observed_skipped_rows += 1
                should_emit = (
                    execution_mode != "single_task"
                    or completed_rows == 1
                    or completed_rows >= total_rows
                    or completed_rows % progress_emit_every == 0
                )
                if should_emit:
                    _set_job_progress_summary(
                        job,
                        phase="importing",
                        total=total_rows,
                        validated=total_rows,
                        imported=max(completed_rows - observed_skipped_rows, 0),
                        skipped=observed_skipped_rows,
                        failed=observed_failed_rows,
                    )
                    apply_lexicon_job_progress(
                        job,
                        progress_completed=completed_rows,
                        progress_total=total_rows,
                        current_label=_row_label(
                            row,
                            default_prefix="Importing",
                            completed_rows=completed_rows,
                            total_rows=total_rows,
                        ),
                    )
                    _refresh_timing()
                    _persist_perf_metrics()
                    progress_committer.record_update(callback=True)
                    progress_update_count += 1
                import_callback_elapsed_ms += int((time.monotonic() - started_at) * 1000)

            def _finalize_started() -> None:
                nonlocal finalization_started_at
                _raise_if_cancel_requested(force=True)
                _mark_import_started()
                if finalization_started_at is None:
                    finalization_started_at = time.monotonic()
                current_summary = dict((job.request_payload or {}).get("progress_summary") or {})
                skipped_value = int(current_summary.get("skipped") or observed_skipped_rows)
                failed_value = int(current_summary.get("failed") or observed_failed_rows)
                imported_value = max(total_rows - skipped_value - failed_value, 0)
                _set_job_progress_summary(
                    job,
                    phase="finalizing",
                    total=total_rows,
                    validated=total_rows,
                    imported=imported_value,
                    skipped=skipped_value,
                    failed=failed_value,
                )
                apply_lexicon_job_progress(
                    job,
                    progress_completed=total_rows,
                    progress_total=total_rows,
                    current_label="Rebuilding learner catalog projection",
                )
                _refresh_timing()
                _persist_perf_metrics()
                progress_committer.record_update(force=True)

            _raise_if_cancel_requested(force=True)
            result_payload = import_db.run_import_file(
                request_payload["input_path"],
                source_type=request_payload["source_type"],
                source_reference=request_payload.get("source_reference"),
                language=request_payload.get("language", "en"),
                conflict_mode=request_payload.get("conflict_mode"),
                error_mode=request_payload.get("error_mode", "fail_fast"),
                commit_every_rows=commit_every_rows,
                preflight_progress_callback=_preflight_progress,
                progress_callback=_import_progress,
                import_started_callback=_import_started,
                finalize_started_callback=_finalize_started,
                start_row_index=row_cursor if execution_mode == "continuation" else 0,
                max_row_count=slice_row_count if execution_mode == "continuation" else None,
            )
            if execution_mode == "continuation":
                for key in (
                    "created_words",
                    "updated_words",
                    "skipped_words",
                    "created_meanings",
                    "updated_meanings",
                    "created_examples",
                    "deleted_examples",
                    "created_relations",
                    "deleted_relations",
                    "created_translations",
                    "updated_translations",
                    "created_enrichment_jobs",
                    "reused_enrichment_jobs",
                    "created_enrichment_runs",
                    "reused_enrichment_runs",
                    "created_phrases",
                    "updated_phrases",
                    "skipped_phrases",
                    "created_reference_entries",
                    "updated_reference_entries",
                    "skipped_reference_entries",
                    "created_reference_localizations",
                    "updated_reference_localizations",
                    "failed_rows",
                ):
                    accumulator[key] = int(accumulator.get(key, 0)) + int(result_payload.get(key, 0))
                processed_row_count = int(result_payload.get("processed_row_count") or 0)
                next_row_index = int(result_payload.get("next_row_index") or row_cursor)
                total_row_count = int(result_payload.get("total_row_count") or total_rows)
                all_rows_completed = bool(result_payload.get("all_rows_completed", True))
                accumulator["processed_row_count"] = int(accumulator.get("processed_row_count", 0)) + processed_row_count
                latest_request_payload = dict(job.request_payload or {})
                latest_request_payload["import_accumulator"] = accumulator
                latest_request_payload["import_row_cursor"] = next_row_index
                latest_request_payload["import_row_chunk_size"] = slice_row_count
                latest_request_payload["import_row_commit_size"] = commit_every_rows
                latest_request_payload["import_execution_mode"] = execution_mode
                job.request_payload = latest_request_payload
                imported_rows, skipped_rows, failed_rows = _import_result_progress_counts(accumulator)
                phase = "completed" if all_rows_completed else "importing"
                _set_job_progress_summary(
                    job,
                    phase=phase,
                    total=total_row_count,
                    validated=total_rows,
                    imported=imported_rows,
                    skipped=skipped_rows,
                    failed=failed_rows,
                )
                _refresh_timing()
                _persist_perf_metrics()
                if not all_rows_completed:
                    if next_row_index <= row_cursor:
                        raise RuntimeError(
                            "Enrichment import continuation cursor did not advance "
                            f"(current={row_cursor}, next={next_row_index}, total_rows={total_row_count})."
                        )
                    _raise_if_cancel_requested(force=True)
                    progress_committer.record_update(force=True)
                    raise self.retry(countdown=0, max_retries=None)
                apply_lexicon_job_completed(job, result_payload=accumulator)
                progress_committer.record_update(force=True)
                return {"status": "completed", "result_payload": accumulator}
            total_row_count = int(result_payload.get("total_row_count") or total_rows)
            imported_rows, skipped_rows, failed_rows = _import_result_progress_counts(result_payload)
            _set_job_progress_summary(
                job,
                phase="completed",
                total=total_row_count,
                validated=total_row_count,
                imported=imported_rows,
                skipped=skipped_rows,
                failed=failed_rows,
            )
            _refresh_timing()
            _persist_perf_metrics()
            apply_lexicon_job_completed(job, result_payload=result_payload)
            progress_committer.record_update(force=True)
            return {"status": "completed", "result_payload": result_payload}
        except Retry:
            raise
        except _JobCancelled as exc:
            progress_summary = dict((job.request_payload or {}).get("progress_summary") or {})
            _set_job_progress_summary(
                job,
                phase="cancelled",
                total=int(progress_summary.get("total") or job.progress_total or 0),
                validated=int(progress_summary.get("validated") or job.progress_completed or 0),
                imported=int(progress_summary.get("imported") or 0),
                skipped=int(progress_summary.get("skipped") or 0),
                failed=int(progress_summary.get("failed") or 0),
            )
            _refresh_timing()
            _persist_perf_metrics()
            job.progress_current_label = "Cancelled"
            apply_lexicon_job_cancelled(job)
            progress_committer.record_update(force=True)
            return {"status": "cancelled", "message": str(exc)}
        except Exception as exc:
            progress_summary = dict((job.request_payload or {}).get("progress_summary") or {})
            _set_job_progress_summary(
                job,
                phase="failed",
                total=int(progress_summary.get("total") or job.progress_total or 0),
                validated=int(progress_summary.get("validated") or job.progress_completed or 0),
                imported=int(progress_summary.get("imported") or 0),
                skipped=int(progress_summary.get("skipped") or 0),
                failed=int(progress_summary.get("failed") or 0),
            )
            _refresh_timing()
            _persist_perf_metrics()
            apply_lexicon_job_failed(job, str(exc))
            progress_committer.record_update(force=True)
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_voice_import_db", max_retries=None)
def run_lexicon_voice_import_db(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        if job.status == "cancel_requested":
            _set_job_progress_summary(
                job,
                phase="cancelled",
                total=job.progress_total,
                validated=job.progress_completed,
                imported=0,
                skipped=0,
                failed=0,
            )
            apply_lexicon_job_cancelled(job)
            db.commit()
            return {"status": "cancelled"}
        request_payload = dict(job.request_payload or {})
        voice_import_db = _voice_import_db_module()
        row_summary = dict(request_payload.get("row_summary") or {})
        total_rows = int(row_summary.get("row_count") or 0)
        chunk_size = max(int(request_payload.get("voice_group_chunk_size") or VOICE_IMPORT_LEXICAL_GROUP_CHUNK_SIZE), 1)
        request_payload["voice_group_chunk_size"] = chunk_size
        request_payload["progress_commit_callback_interval"] = PROGRESS_COMMIT_CALLBACK_INTERVAL
        job.request_payload = request_payload
        group_cursor = max(int(request_payload.get("voice_group_cursor") or 0), 0)
        is_continuation_slice = group_cursor > 0
        accumulator = dict(request_payload.get("voice_import_accumulator") or {})
        observed_imported_rows, observed_skipped_rows, observed_failed_rows = _voice_result_progress_counts(accumulator)
        worker_started_at = time.monotonic()
        validation_started_at = worker_started_at
        import_started_at: float | None = None
        queue_wait_ms = _job_queue_wait_ms(job)
        timing_payload = dict(request_payload.get("progress_timing") or {})
        base_elapsed_ms = max(int(timing_payload.get("elapsed_ms") or 0), 0)
        base_validation_elapsed_ms = max(int(timing_payload.get("validation_elapsed_ms") or 0), 0)
        base_import_elapsed_ms = max(int(timing_payload.get("import_elapsed_ms") or 0), 0)

        def _refresh_timing() -> None:
            now = time.monotonic()
            validation_finished_at = import_started_at if import_started_at is not None else now
            validation_elapsed_increment_ms = (
                0
                if is_continuation_slice
                else int((validation_finished_at - validation_started_at) * 1000)
            )
            _set_job_progress_timing(
                job,
                queue_wait_ms=queue_wait_ms,
                elapsed_ms=base_elapsed_ms + int((now - worker_started_at) * 1000),
                validation_elapsed_ms=base_validation_elapsed_ms + validation_elapsed_increment_ms,
                import_elapsed_ms=base_import_elapsed_ms + (
                    int((now - import_started_at) * 1000) if import_started_at is not None else 0
                ),
            )

        def _mark_import_started() -> None:
            nonlocal import_started_at
            if import_started_at is None:
                import_started_at = time.monotonic()

        existing_progress_summary = dict(request_payload.get("progress_summary") or {})
        if group_cursor > 0 and existing_progress_summary:
            _set_job_progress_summary(
                job,
                phase="importing",
                total=total_rows,
                validated=int(existing_progress_summary.get("validated") or total_rows),
                imported=int(existing_progress_summary.get("imported") or observed_imported_rows),
                skipped=int(existing_progress_summary.get("skipped") or observed_skipped_rows),
                failed=int(existing_progress_summary.get("failed") or observed_failed_rows),
            )
        else:
            _set_job_progress_summary(
                job,
                phase="validating",
                total=total_rows,
                validated=0,
                imported=observed_imported_rows,
                skipped=observed_skipped_rows,
                failed=observed_failed_rows,
            )
        _refresh_timing()
        db.commit()
        progress_committer = _ProgressCommitThrottle(db)
        try:
            cancel_check_counter = 0

            def _raise_if_cancel_requested(*, force: bool = False) -> None:
                nonlocal cancel_check_counter
                cancel_check_counter += 1
                if not force and cancel_check_counter % CANCEL_CHECK_INTERVAL != 0:
                    return
                if _is_job_cancel_requested(db, job_id):
                    raise _JobCancelled("Voice import cancelled by user.")

            def _row_label(row: dict[str, Any], *, default_prefix: str, completed_rows: int, total_rows: int) -> str | None:
                explicit_label = str(row.get("_progress_label") or "").strip()
                if explicit_label:
                    entry_label = str(row.get("word") or row.get("source_text") or row.get("entry_id") or "").strip()
                    return f"{explicit_label}: {entry_label}" if entry_label and entry_label not in explicit_label else explicit_label
                entry_label = str(row.get("word") or row.get("source_text") or row.get("entry_id") or "").strip()
                if not entry_label:
                    return default_prefix
                return f"{default_prefix} {completed_rows}/{total_rows}: {entry_label}" if total_rows > 0 else f"{default_prefix}: {entry_label}"

            def _preflight_progress(row: dict[str, Any], completed_rows: int, total_rows: int) -> None:
                _raise_if_cancel_requested()
                _set_job_progress_summary(
                    job,
                    phase="validating",
                    total=total_rows,
                    validated=completed_rows,
                    imported=0,
                    skipped=0,
                    failed=0,
                )
                apply_lexicon_job_progress(
                    job,
                    progress_completed=completed_rows,
                    progress_total=total_rows,
                    current_label=_row_label(
                        row,
                        default_prefix="Validating",
                        completed_rows=completed_rows,
                        total_rows=total_rows,
                    ),
                )
                _refresh_timing()
                progress_committer.record_update(callback=True)

            def _import_started() -> None:
                _raise_if_cancel_requested(force=True)
                _mark_import_started()
                _refresh_timing()
                progress_committer.record_update(force=True)

            def _import_progress(row: dict[str, Any], completed_rows: int, total_rows: int) -> None:
                nonlocal observed_imported_rows, observed_skipped_rows, observed_failed_rows
                _raise_if_cancel_requested()
                _mark_import_started()
                imported_delta, skipped_delta, failed_delta = _voice_progress_delta(row)
                observed_imported_rows += imported_delta
                observed_skipped_rows += skipped_delta
                observed_failed_rows += failed_delta
                _set_job_progress_summary(
                    job,
                    phase="importing",
                    total=total_rows,
                    validated=total_rows,
                    imported=observed_imported_rows,
                    skipped=observed_skipped_rows,
                    failed=observed_failed_rows,
                )
                apply_lexicon_job_progress(
                    job,
                    progress_completed=completed_rows,
                    progress_total=total_rows,
                    current_label=_voice_current_group_label(row),
                )
                _refresh_timing()
                progress_committer.record_update(callback=True)

            _raise_if_cancel_requested(force=True)
            result_payload = voice_import_db.run_voice_import_file(
                request_payload["input_path"],
                language=request_payload.get("language", "en"),
                conflict_mode=request_payload.get("conflict_mode"),
                error_mode=request_payload.get("error_mode", "fail_fast"),
                preflight_progress_callback=_preflight_progress,
                progress_callback=_import_progress,
                import_started_callback=_import_started,
                start_group_index=group_cursor,
                max_group_count=chunk_size,
            )
            for key in (
                "created_assets",
                "updated_assets",
                "skipped_rows",
                "missing_words",
                "missing_meanings",
                "missing_examples",
                "failed_rows",
            ):
                accumulator[key] = int(accumulator.get(key, 0)) + int(result_payload.get(key, 0))
            next_group_index = int(result_payload.get("next_group_index") or group_cursor)
            all_groups_completed = bool(result_payload.get("all_groups_completed", True))
            total_group_count = int(result_payload.get("total_group_count") or 0)
            latest_request_payload = dict(job.request_payload or {})
            latest_request_payload["voice_import_accumulator"] = accumulator
            latest_request_payload["voice_group_cursor"] = next_group_index
            latest_request_payload["voice_group_chunk_size"] = chunk_size
            latest_request_payload["voice_total_group_count"] = total_group_count
            job.request_payload = latest_request_payload
            imported_rows, skipped_rows, failed_rows = _voice_result_progress_counts(accumulator)
            phase = "completed" if all_groups_completed else "importing"
            _set_job_progress_summary(
                job,
                phase=phase,
                total=total_rows,
                validated=total_rows,
                imported=imported_rows,
                skipped=skipped_rows,
                failed=failed_rows,
            )
            _refresh_timing()
            if not all_groups_completed:
                if next_group_index <= group_cursor:
                    raise RuntimeError(
                        "Voice import continuation cursor did not advance "
                        f"(current={group_cursor}, next={next_group_index}, total_groups={total_group_count})."
                    )
                _raise_if_cancel_requested(force=True)
                progress_committer.record_update(force=True)
                raise self.retry(countdown=0, max_retries=None)
            apply_lexicon_job_completed(job, result_payload=accumulator)
            progress_committer.record_update(force=True)
            return {"status": "completed", "result_payload": accumulator}
        except _JobCancelled as exc:
            progress_summary = dict((job.request_payload or {}).get("progress_summary") or {})
            _set_job_progress_summary(
                job,
                phase="cancelled",
                total=int(progress_summary.get("total") or job.progress_total or 0),
                validated=int(progress_summary.get("validated") or job.progress_completed or 0),
                imported=int(progress_summary.get("imported") or 0),
                skipped=int(progress_summary.get("skipped") or 0),
                failed=int(progress_summary.get("failed") or 0),
            )
            _refresh_timing()
            job.progress_current_label = "Cancelled"
            apply_lexicon_job_cancelled(job)
            progress_committer.record_update(force=True)
            return {"status": "cancelled", "message": str(exc)}
        except Retry:
            raise
        except Exception as exc:
            progress_summary = dict((job.request_payload or {}).get("progress_summary") or {})
            _set_job_progress_summary(
                job,
                phase="failed",
                total=int(progress_summary.get("total") or job.progress_total or 0),
                validated=int(progress_summary.get("validated") or job.progress_completed or 0),
                imported=int(progress_summary.get("imported") or 0),
                skipped=int(progress_summary.get("skipped") or 0),
                failed=int(progress_summary.get("failed") or 0),
            )
            _refresh_timing()
            apply_lexicon_job_failed(job, str(exc))
            progress_committer.record_update(force=True)
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_jsonl_materialize")
def run_lexicon_jsonl_materialize(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            result_payload = materialize_jsonl_review_outputs(
                artifact_path=Path(request_payload["artifact_path"]),
                decisions_path=Path(request_payload["decisions_path"]),
                output_dir=Path(request_payload["output_dir"]),
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_compiled_materialize")
def run_lexicon_compiled_materialize(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            result_payload = materialize_compiled_review_batch(
                db,
                batch_id=uuid.UUID(request_payload["batch_id"]),
                output_dir=Path(request_payload["output_dir"]),
                settings=settings,
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}


@celery_app.task(bind=True, name="run_lexicon_compiled_review_bulk_update")
def run_lexicon_compiled_review_bulk_update(self, job_id: str) -> dict[str, Any]:
    with Session(sync_engine) as db:
        job = _load_job(db, job_id)
        apply_lexicon_job_started(job)
        db.commit()
        try:
            request_payload = dict(job.request_payload or {})
            result_payload = process_compiled_review_bulk_job(
                db,
                job=job,
                batch_id=uuid.UUID(request_payload["batch_id"]),
                review_status=str(request_payload["review_status"]),
                decision_reason=request_payload.get("decision_reason"),
                scope=str(request_payload.get("scope") or "all_pending"),
                chunk_size=int(request_payload.get("chunk_size") or BULK_REVIEW_CHUNK_SIZE),
            )
            apply_lexicon_job_completed(job, result_payload=result_payload)
            db.commit()
            return {"status": "completed", "result_payload": result_payload}
        except Exception as exc:
            apply_lexicon_job_failed(job, str(exc))
            db.commit()
            return {"status": "failed", "error": str(exc)}
