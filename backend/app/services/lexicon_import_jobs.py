from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock, Thread
from typing import Any, Callable
import uuid


@dataclass
class LexiconImportJobState:
    id: str
    artifact_filename: str
    input_path: str
    source_type: str
    source_reference: str | None
    language: str
    status: str
    row_summary: dict[str, int]
    import_summary: dict[str, int] | None
    total_rows: int
    completed_rows: int
    remaining_rows: int
    current_entry: str | None
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


_jobs: dict[str, LexiconImportJobState] = {}
_job_lock = Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _entry_label(row: dict[str, Any]) -> str | None:
    for key in ("display_form", "display_text", "word", "normalized_form", "entry_id"):
        value = row.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def get_lexicon_import_job(job_id: str) -> LexiconImportJobState | None:
    with _job_lock:
        return _jobs.get(job_id)


def create_lexicon_import_job(
    *,
    input_path: Path,
    source_type: str,
    source_reference: str | None,
    language: str,
    rows: list[dict[str, Any]],
    import_runner: Callable[..., dict[str, int]],
    row_summary: dict[str, int],
) -> LexiconImportJobState:
    job_id = str(uuid.uuid4())
    state = LexiconImportJobState(
        id=job_id,
        artifact_filename=input_path.name,
        input_path=str(input_path),
        source_type=source_type,
        source_reference=source_reference,
        language=language,
        status="queued",
        row_summary=dict(row_summary),
        import_summary=None,
        total_rows=len(rows),
        completed_rows=0,
        remaining_rows=len(rows),
        current_entry=None,
        error_message=None,
        created_at=_now_iso(),
        started_at=None,
        completed_at=None,
    )
    with _job_lock:
        _jobs[job_id] = state

    def progress_callback(*, row: dict[str, Any], completed_rows: int, total_rows: int) -> None:
        with _job_lock:
            current = _jobs.get(job_id)
            if current is None:
                return
            current.status = "running"
            current.started_at = current.started_at or _now_iso()
            current.current_entry = _entry_label(row)
            current.completed_rows = completed_rows
            current.total_rows = total_rows
            current.remaining_rows = max(0, total_rows - completed_rows)

    def run_job() -> None:
        with _job_lock:
            current = _jobs[job_id]
            current.status = "running"
            current.started_at = current.started_at or _now_iso()
        try:
            import_summary = import_runner(
                input_path,
                source_type=source_type,
                source_reference=source_reference,
                language=language,
                rows=rows,
                progress_callback=progress_callback,
            )
            with _job_lock:
                current = _jobs[job_id]
                current.status = "completed"
                current.import_summary = import_summary
                current.completed_rows = current.total_rows
                current.remaining_rows = 0
                current.completed_at = _now_iso()
        except Exception as exc:  # pragma: no cover - exercised via API tests
            with _job_lock:
                current = _jobs[job_id]
                current.status = "failed"
                current.error_message = str(exc)
                current.completed_at = _now_iso()

    _start_job_thread(run_job, name=f"lexicon-import-{job_id}")
    return state


def serialize_lexicon_import_job(job: LexiconImportJobState) -> dict[str, Any]:
    return asdict(job)


def _start_job_thread(target: Callable[[], None], *, name: str) -> None:
    thread = Thread(target=target, name=name, daemon=True)
    thread.start()
