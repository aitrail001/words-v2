from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from tools.lexicon.import_db import (
    ImportSummary,
    _default_models,
    _default_phrase_models,
    _default_source_reference,
    _increment,
    _iter_row_batches,
    _rebuild_learner_catalog_projection,
    import_compiled_rows,
    iter_compiled_rows,
)


def _iter_source_rows(path: str | Path, rows: list[dict[str, Any]] | None) -> Iterable[dict[str, Any]]:
    if rows is not None:
        yield from rows
        return
    yield from iter_compiled_rows(path)


def _copy_rows_into_temp_stage(session: Any, source_rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    connection = session.connection()
    connection.exec_driver_sql(
        """
        CREATE TEMP TABLE lexicon_stage_compiled_rows (
            line_number integer NOT NULL,
            raw_line text NOT NULL,
            payload jsonb
        ) ON COMMIT DROP
        """
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter="\t", lineterminator="\n", quoting=csv.QUOTE_MINIMAL)
    for row_count, row in enumerate(source_rows, start=1):
        writer.writerow([row_count, json.dumps(row, ensure_ascii=False)])
    buffer.seek(0)

    dbapi_connection = connection.connection
    cursor = dbapi_connection.cursor()
    try:
        cursor.copy_expert(
            "COPY lexicon_stage_compiled_rows (line_number, raw_line) FROM STDIN WITH (FORMAT csv, DELIMITER E'\\t')",
            buffer,
        )
    finally:
        cursor.close()

    connection.exec_driver_sql("UPDATE lexicon_stage_compiled_rows SET payload = raw_line::jsonb")
    result = connection.exec_driver_sql(
        "SELECT payload::text FROM lexicon_stage_compiled_rows ORDER BY line_number ASC"
    )
    return [json.loads(payload_text) for (payload_text,) in result.fetchall()]


def merge_staged_word_rows(
    session: Any,
    rows: list[dict[str, Any]],
    *,
    source_type: str,
    source_reference: str,
    language: str,
    progress_callback: Optional[Callable[[dict[str, Any], int, int], None]] = None,
    on_conflict: str = "upsert",
) -> ImportSummary:
    return import_compiled_rows(
        session,
        rows,
        source_type=source_type,
        source_reference=source_reference,
        language=language,
        rebuild_learner_catalog=False,
        progress_callback=progress_callback,
        on_conflict=on_conflict,
    )


def run_staging_import_file(
    path: str | Path,
    *,
    source_type: str,
    source_reference: str | None = None,
    language: str = "en",
    rows: list[dict[str, Any]] | None = None,
    commit_every_rows: int | None = 250,
    progress_callback: Optional[Callable[..., None]] = None,
    on_conflict: str = "upsert",
) -> dict[str, int]:
    from sqlalchemy.engine.create import create_engine
    from sqlalchemy.orm.session import Session

    from app.core.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    effective_source_reference = source_reference or _default_source_reference(path)
    aggregate_summary = ImportSummary()

    with Session(engine) as session:
        staged_rows = _copy_rows_into_temp_stage(session, _iter_source_rows(path, rows))
        total_rows = len(staged_rows)
        word_rows = [row for row in staged_rows if str(row.get("entry_type") or "word").strip().lower() in {"", "word"}]
        other_rows = [row for row in staged_rows if str(row.get("entry_type") or "word").strip().lower() not in {"", "word"}]

        if word_rows:
            word_summary = merge_staged_word_rows(
                session,
                word_rows,
                source_type=source_type,
                source_reference=effective_source_reference,
                language=language,
                progress_callback=(
                    (lambda row, completed_rows, total_word_rows, offset=0: progress_callback(
                        row=row,
                        completed_rows=completed_rows,
                        total_rows=total_rows,
                    ))
                    if progress_callback is not None
                    else None
                ),
                on_conflict=on_conflict,
            )
            aggregate_summary = _increment(aggregate_summary, **word_summary.__dict__)
            session.commit()

        if other_rows:
            batch_size = commit_every_rows if commit_every_rows is not None and commit_every_rows > 0 else len(other_rows) or 1
            completed_other_rows = len(word_rows)
            for batch in _iter_row_batches(other_rows, batch_size):
                batch_summary = import_compiled_rows(
                    session,
                    batch,
                    source_type=source_type,
                    source_reference=effective_source_reference,
                    language=language,
                    rebuild_learner_catalog=False,
                    progress_callback=(
                        (lambda row, batch_completed_rows, _batch_total_rows, base_completed_rows=completed_other_rows: progress_callback(
                            row=row,
                            completed_rows=base_completed_rows + batch_completed_rows,
                            total_rows=total_rows,
                        ))
                        if progress_callback is not None
                        else None
                    ),
                    on_conflict=on_conflict,
                )
                aggregate_summary = _increment(aggregate_summary, **batch_summary.__dict__)
                completed_other_rows += len(batch)
                session.commit()

        if aggregate_summary != ImportSummary():
            (
                word_model,
                _meaning_model,
                _meaning_metadata_model,
                _meaning_example_model,
                _word_relation_model,
                _lexicon_enrichment_job_model,
                _lexicon_enrichment_run_model,
                _translation_model,
                _translation_example_model,
                _word_confusable_model,
                _word_form_model,
                _word_part_of_speech_model,
                learner_catalog_entry_model,
            ) = _default_models()
            phrase_model = _default_phrase_models()[0]
            _rebuild_learner_catalog_projection(
                session,
                learner_catalog_entry_model=learner_catalog_entry_model,
                word_model=word_model,
                phrase_model=phrase_model,
            )
            session.commit()

    return aggregate_summary.__dict__
