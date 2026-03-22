from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tools.lexicon.benchmark_selection import run_selection_benchmark
from tools.lexicon.enrichment_benchmark import run_enrichment_benchmark
from tools.lexicon.build_base import build_base_records, build_word_inventory, normalize_seed_words, write_base_snapshot
from tools.lexicon.canonical_registry import lookup_entry, status_entry
from tools.lexicon.batch_prepare import build_batch_request_rows, build_retry_batch_request_rows, write_batch_request_rows
from tools.lexicon.batch_ledger import (
    BatchArtifactPaths,
    append_jsonl_rows,
    build_batch_job_rows,
    load_jsonl_rows,
    summarize_batch_jobs,
    write_jsonl_rows,
)
from tools.lexicon.batch_ingest import build_batch_output_summary, build_batch_result_rows, ingest_batch_outputs
from tools.lexicon.batch_client import BatchClient
from tools.lexicon.form_adjudication import adjudicate_forms, load_adjudications
from tools.lexicon.compile_export import compile_snapshot
from tools.lexicon.enrich import run_enrichment
from tools.lexicon.ids import build_snapshot_id
from tools.lexicon.inventory import load_seed_rows
from tools.lexicon.import_db import _ensure_backend_path, load_compiled_rows, run_import_file, summarize_compiled_rows
from tools.lexicon.rerank import RERANK_CANDIDATE_SOURCES
from tools.lexicon.phrase_pipeline import build_phrase_snapshot_rows, write_phrase_snapshot
from tools.lexicon.reference_pipeline import build_reference_snapshot_rows, write_reference_snapshot
from tools.lexicon.qc import run_batch_qc, run_review_apply
from tools.lexicon.review_materialize import materialize_review_outputs
from tools.lexicon.validate import validate_compiled_record, validate_snapshot_files
from tools.lexicon.policy_data import excluded_canonical_forms
from tools.lexicon.wordfreq_provider import build_wordfreq_rank_provider
from tools.lexicon.wordfreq_utils import build_wordfreq_inventory_provider
from tools.lexicon.wordnet_provider import LexiconDependencyError, build_wordnet_sense_provider

_REASONING_EFFORT_CHOICES = ['none', 'low', 'medium', 'high']


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _resolve_existing_db_url(explicit_database_url: str | None) -> str | None:
    if explicit_database_url:
        return explicit_database_url
    env_sync_url = os.getenv('DATABASE_URL_SYNC')
    if env_sync_url:
        return env_sync_url
    return None


def _load_existing_db_words(words: Sequence[str], language: str = 'en', database_url: str | None = None) -> set[str]:
    normalized_words = [str(word).strip() for word in words if str(word).strip()]
    if not normalized_words:
        return set()

    try:
        _ensure_backend_path()
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session
        from app.core.config import get_settings
        from app.models.word import Word

        settings = get_settings()
        engine = create_engine(database_url or settings.database_url_sync)
        try:
            with Session(engine) as session:
                rows = session.execute(
                    select(Word.word).where(
                        Word.word.in_(normalized_words),
                        Word.language == language,
                    )
                ).scalars().all()
                return {str(row) for row in rows}
        finally:
            engine.dispose()
    except Exception as exc:  # pragma: no cover - error path exercised via CLI wrapper tests
        raise RuntimeError(f'Database existing-word check failed: {exc}') from exc


def _load_build_base_providers():
    return build_wordfreq_rank_provider(), build_wordnet_sense_provider()


def _load_word_inventory_provider():
    return build_wordfreq_inventory_provider()


def _build_base_command(args: argparse.Namespace) -> int:
    if args.top_words and args.rollout_stage:
        print('build-base accepts only one of --top-words or --rollout-stage', file=sys.stderr)
        return 2

    requested_top_words = args.top_words or args.rollout_stage
    try:
        rank_provider, sense_provider = _load_build_base_providers()
    except (LexiconDependencyError, RuntimeError) as exc:
        if requested_top_words is None:
            print(str(exc), file=sys.stderr)
            return 2
        rank_provider = build_wordfreq_rank_provider()
        sense_provider = lambda word: []
    if requested_top_words is not None:
        sense_provider = lambda word: []

    inventory_mode = 'seed_words'
    words = list(args.words)
    if requested_top_words is not None:
        try:
            inventory_provider = _load_word_inventory_provider()
        except (LexiconDependencyError, RuntimeError) as exc:
            print(str(exc), file=sys.stderr)
            return 2
        words = build_word_inventory(limit=int(requested_top_words), inventory_provider=inventory_provider)
        inventory_mode = 'top_words'

    if not words:
        print('build-base requires seed words or --top-words/--rollout-stage', file=sys.stderr)
        return 2

    snapshot_id = args.snapshot_id or build_snapshot_id(
        date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
        source_label='wordfreq-only' if requested_top_words is not None else 'wordnet-wordfreq',
    )
    adjudications_path = getattr(args, 'adjudications', None)
    adjudications = load_adjudications(Path(adjudications_path)) if adjudications_path else None
    existing_canonical_words_lookup = None
    existing_db_url = None
    policy_tail_exclusions = excluded_canonical_forms() if requested_top_words is not None else set()
    if not args.rerun_existing:
        existing_db_url = _resolve_existing_db_url(args.database_url)
        if existing_db_url:
            def existing_canonical_words_lookup(canonical_words: list[str]) -> set[str]:
                return _load_existing_db_words(
                    canonical_words,
                    language='en',
                    database_url=existing_db_url,
                )

    try:
        result = build_base_records(
            words=words,
            snapshot_id=snapshot_id,
            created_at=_utc_now(),
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=args.max_senses,
            adjudications=adjudications,
            existing_canonical_words_lookup=existing_canonical_words_lookup,
            excluded_canonical_words=policy_tail_exclusions,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'build-base',
        'snapshot_id': snapshot_id,
        'inventory_mode': inventory_mode,
        'words': [record.lemma for record in result.lexemes],
        'lexeme_count': len(result.lexemes),
        'ambiguous_form_count': len(result.ambiguous_forms),
        'skip_existing_db': existing_canonical_words_lookup is not None,
        'skipped_existing_db_count': len(result.skipped_existing_canonical_words),
        'tail_exclusion_count': len(getattr(result, 'excluded_tail_canonical_words', [])),
    }
    if requested_top_words is not None:
        payload['requested_top_words'] = int(requested_top_words)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        written = write_base_snapshot(output_dir, result)
        payload['output_dir'] = str(output_dir)
        payload['written_files'] = {key: str(value) for key, value in written.items()}
    print(json.dumps(payload))
    return 0


def _enrich_command(args: argparse.Namespace) -> int:
    try:
        result = run_enrichment(
            Path(args.snapshot_dir),
            prompt_version=args.prompt_version,
            output_path=Path(args.output) if args.output else None,
            provider_mode=args.provider_mode,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            mode=args.mode,
            max_concurrency=args.max_concurrency,
            resume=args.resume,
            checkpoint_path=Path(args.checkpoint_path) if args.checkpoint_path else None,
            failures_output=Path(args.failures_output) if args.failures_output else None,
            max_failures=args.max_failures,
            request_delay_seconds=args.request_delay_seconds,
            max_new_completed_lexemes=args.max_new_completed_lexemes,
        )
    except (LexiconDependencyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'enrich',
        'snapshot_dir': str(Path(args.snapshot_dir)),
        'output': str(result.output_path),
        'mode': result.mode,
        'lexeme_count': result.lexeme_count,
        'enrichment_count': len(result.enrichments),
    }
    print(json.dumps(payload))
    return 0


def _benchmark_selection_command(args: argparse.Namespace) -> int:
    try:
        result = run_selection_benchmark(
            Path(args.output_dir),
            datasets=args.datasets or None,
            max_senses=args.max_senses,
            with_rerank=args.with_rerank,
            candidate_sources=args.candidate_sources or None,
            provider_mode=args.provider_mode,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            candidate_limit=args.candidate_limit,
        )
    except (LexiconDependencyError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = dict(result.payload)
    payload['command'] = 'benchmark-selection'
    payload['summary'] = str(result.summary_path)
    print(json.dumps(payload))
    return 0


def _benchmark_enrichment_command(args: argparse.Namespace) -> int:
    try:
        result = run_enrichment_benchmark(
            Path(args.output_dir),
            dataset=args.dataset,
            prompt_modes=args.prompt_modes or ["grounded"],
            model_names=args.models or ["gpt-5.1-chat"],
            provider_mode=args.provider_mode,
            reasoning_effort=args.reasoning_effort,
        )
    except (LexiconDependencyError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = dict(result.payload)
    payload["command"] = "benchmark-enrichment"
    payload["summary"] = str(result.summary_path)
    print(json.dumps(payload))
    return 0


def _detect_ambiguous_forms_command(args: argparse.Namespace) -> int:
    try:
        rank_provider, sense_provider = _load_build_base_providers()
    except (LexiconDependencyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if not args.words:
        print('detect-ambiguous-forms requires at least one word', file=sys.stderr)
        return 2

    result = build_base_records(
        words=args.words,
        snapshot_id=args.snapshot_id or build_snapshot_id(
            date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
            source_label='ambiguous-forms',
        ),
        created_at=_utc_now(),
        rank_provider=rank_provider,
        sense_provider=sense_provider,
        max_senses=args.max_senses,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload_text = '\n'.join(json.dumps(row.to_dict()) for row in result.ambiguous_forms)
    output_path.write_text(payload_text + ('\n' if payload_text else ''), encoding='utf-8')
    print(json.dumps({
        'command': 'detect-ambiguous-forms',
        'output': str(output_path),
        'ambiguous_count': len(result.ambiguous_forms),
        'words': [row.surface_form for row in result.ambiguous_forms],
    }))
    return 0


def _adjudicate_forms_command(args: argparse.Namespace) -> int:
    try:
        result = adjudicate_forms(
            args.input,
            output_path=args.output,
            provider_mode=args.provider_mode,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
        )
    except (LexiconDependencyError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps({
        'command': 'adjudicate-forms',
        'input': str(Path(args.input)),
        'output': str(result.output_path),
        'adjudication_count': len(result.rows),
    }))
    return 0


def _lookup_entry_command(args: argparse.Namespace) -> int:
    payload = lookup_entry(Path(args.snapshot_dir), args.word)
    if payload is None:
        print(json.dumps({"command": "lookup-entry", "input_word": args.word, "found": False}))
        return 0
    payload = dict(payload)
    payload["command"] = "lookup-entry"
    print(json.dumps(payload))
    return 0


def _db_word_lookup(word: str, language: str) -> dict[str, object] | None:
    _ensure_backend_path()
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session
    from app.core.config import get_settings
    from app.models.word import Word

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    with Session(engine) as session:
        row = session.execute(select(Word).where(Word.word == word, Word.language == language)).scalar_one_or_none()
        if row is None:
            return None
        return {"word": row.word, "language": row.language, "id": str(row.id)}


def _status_entry_command(args: argparse.Namespace) -> int:
    payload = status_entry(
        Path(args.snapshot_dir),
        args.word,
        compiled_input=Path(args.compiled_input) if args.compiled_input else None,
        db_lookup=_db_word_lookup if args.check_db else None,
        language=args.language,
    )
    if payload is None:
        print(json.dumps({"command": "status-entry", "input_word": args.word, "found": False}))
        return 0
    payload = dict(payload)
    payload["command"] = "status-entry"
    print(json.dumps(payload))
    return 0


def _validate_command(args: argparse.Namespace) -> int:
    if args.snapshot_dir:
        errors = validate_snapshot_files(Path(args.snapshot_dir))
        payload = {
            'command': 'validate',
            'scope': 'snapshot',
            'error_count': len(errors),
            'errors': errors,
        }
        print(json.dumps(payload))
        return 0

    rows = load_compiled_rows(Path(args.compiled_input))
    errors: list[str] = []
    for index, row in enumerate(rows, start=1):
        for error in validate_compiled_record(row):
            errors.append(f'row {index}: {error}')
    payload = {
        'command': 'validate',
        'scope': 'compiled',
        'error_count': len(errors),
        'errors': errors,
    }
    print(json.dumps(payload))
    return 0


def _compile_export_command(args: argparse.Namespace) -> int:
    try:
        compiled = compile_snapshot(
            Path(args.snapshot_dir),
            Path(args.output),
            decisions_path=Path(args.decisions) if args.decisions else None,
            decision_filter=args.decision_filter,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'compile-export',
        'compiled_count': len(compiled),
        'output': str(Path(args.output)),
    }
    print(json.dumps(payload))
    return 0


def _phrase_build_base_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    try:
        rows = build_phrase_snapshot_rows(
            phrases=load_seed_rows(input_path),
            snapshot_id=args.snapshot_id or build_snapshot_id(
                date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
                source_label='phrase-seeds',
            ),
            created_at=_utc_now(),
        )
        output_path = write_phrase_snapshot(output_dir, rows)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'phrase-build-base',
        'input': str(input_path),
        'output_dir': str(output_dir),
        'output': str(output_path),
        'snapshot_id': args.snapshot_id or None,
        'phrase_count': len(rows),
    }
    print(json.dumps(payload))
    return 0


def _reference_build_base_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    try:
        rows = build_reference_snapshot_rows(
            references=load_seed_rows(input_path),
            snapshot_id=args.snapshot_id or build_snapshot_id(
                date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
                source_label='reference-seeds',
            ),
            created_at=_utc_now(),
        )
        output_path = write_reference_snapshot(output_dir, rows)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'reference-build-base',
        'input': str(input_path),
        'output_dir': str(output_dir),
        'output': str(output_path),
        'snapshot_id': args.snapshot_id or None,
        'reference_count': len(rows),
    }
    print(json.dumps(payload))
    return 0


def _batch_prepare_command(args: argparse.Namespace) -> int:
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    try:
        rows = build_batch_request_rows(
            snapshot_id=args.snapshot_id or build_snapshot_id(
                date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
                source_label='batch-input',
            ),
            model=args.model,
            prompt_version=args.prompt_version,
            rows=load_seed_rows(input_path),
        )
        output_path = write_batch_request_rows(output_dir / "batch_requests.jsonl", rows)
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'batch-prepare',
        'input': str(input_path),
        'output_dir': str(output_dir),
        'output': str(output_path),
        'snapshot_id': args.snapshot_id or None,
        'model': args.model,
        'prompt_version': args.prompt_version,
        'request_count': len(rows),
    }
    print(json.dumps(payload))
    return 0


def _batch_submit_command(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    paths = BatchArtifactPaths.from_snapshot_dir(snapshot_dir)
    request_rows = load_jsonl_rows(paths.batch_requests_path)
    if not request_rows:
        print(f'No batch requests found at {paths.batch_requests_path}', file=sys.stderr)
        return 2
    batch_id = args.batch_id or f"batch-{snapshot_dir.name}"
    input_file_id = args.input_file_id or f"input-{snapshot_dir.name}"
    job_rows = build_batch_job_rows(
        batch_id=batch_id,
        input_file_id=input_file_id,
        request_rows=request_rows,
        status=args.status,
        created_at=_utc_now(),
    )
    write_jsonl_rows(paths.batch_jobs_path, job_rows)
    payload = {
        'command': 'batch-submit',
        'snapshot_dir': str(snapshot_dir),
        'batch_id': batch_id,
        'input_file_id': input_file_id,
        'request_count': len(request_rows),
        'job_count': len(job_rows),
        'status': args.status,
    }
    print(json.dumps(payload))
    return 0


def _batch_status_command(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    paths = BatchArtifactPaths.from_snapshot_dir(snapshot_dir)
    job_rows = load_jsonl_rows(paths.batch_jobs_path)
    result_rows = load_jsonl_rows(paths.snapshot_dir / 'batch_results.jsonl')
    qc_rows = load_jsonl_rows(paths.snapshot_dir / 'batch_qc.jsonl')
    payload = {
        'command': 'batch-status',
        'snapshot_dir': str(snapshot_dir),
        'jobs': summarize_batch_jobs(job_rows),
        'results': build_batch_output_summary(result_rows),
        'qc_count': len(qc_rows),
    }
    if args.batch_id:
        payload['batch_id'] = args.batch_id
    print(json.dumps(payload))
    return 0


def _batch_ingest_command(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    paths = BatchArtifactPaths.from_snapshot_dir(snapshot_dir)
    output_path = Path(args.input)
    results_path = Path(args.output) if args.output else (snapshot_dir / 'batch_results.jsonl')
    failure_path = snapshot_dir / 'enrich.failures.jsonl'
    result_rows = ingest_batch_outputs(
        snapshot_dir=snapshot_dir,
        output_path=results_path,
        request_path=paths.batch_requests_path,
        batch_output_path=output_path,
        ingested_at=_utc_now(),
        failure_output_path=failure_path,
    )
    if args.update_jobs:
        job_rows = load_jsonl_rows(paths.batch_jobs_path)
        updated_jobs = []
        status_by_custom_id = {row['custom_id']: row['status'] for row in result_rows if row.get('custom_id')}
        for job_row in job_rows:
            custom_id = str(job_row.get('custom_id') or '').strip()
            if custom_id in status_by_custom_id:
                job_row = dict(job_row)
                job_row['status'] = 'completed' if status_by_custom_id[custom_id] == 'accepted' else 'failed'
                job_row['updated_at'] = _utc_now()
            updated_jobs.append(job_row)
        write_jsonl_rows(paths.batch_jobs_path, updated_jobs)
    payload = {
        'command': 'batch-ingest',
        'snapshot_dir': str(snapshot_dir),
        'input': str(output_path),
        'output': str(results_path),
        'failures_output': str(failure_path),
        'accepted_output': str(snapshot_dir / 'words.enriched.jsonl'),
        'regenerate_output': str(snapshot_dir / 'words.regenerate.jsonl'),
        'result_count': len(result_rows),
    }
    print(json.dumps(payload))
    return 0


def _batch_retry_command(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    paths = BatchArtifactPaths.from_snapshot_dir(snapshot_dir)
    request_rows = load_jsonl_rows(paths.batch_requests_path)
    result_rows = load_jsonl_rows(Path(args.results) if args.results else (snapshot_dir / 'batch_results.jsonl'))
    failed_custom_ids = set()
    if args.failed_custom_ids:
        failed_custom_ids = {
            line.strip()
            for line in Path(args.failed_custom_ids).read_text(encoding='utf-8').splitlines()
            if line.strip()
        }
    for row in result_rows:
        if str(row.get('status') or '').strip().lower() != 'accepted':
            custom_id = str(row.get('custom_id') or '').strip()
            if custom_id:
                failed_custom_ids.add(custom_id)
    retry_rows = build_retry_batch_request_rows(
        snapshot_id=args.snapshot_id or build_snapshot_id(
            date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
            source_label='batch-retry',
        ),
        model=args.model,
        prompt_version=args.prompt_version,
        request_rows=request_rows,
        failed_custom_ids=failed_custom_ids or None,
    )
    if args.mode == 'escalate-model' and args.model == 'gpt-5-mini':
        for row in retry_rows:
            row['body']['model'] = 'gpt-5.4'
    retry_requests_path = paths.snapshot_dir / 'batch_requests.retry.jsonl'
    write_jsonl_rows(retry_requests_path, retry_rows)
    if retry_rows:
        append_jsonl_rows(paths.batch_requests_path, retry_rows)
    payload = {
        'command': 'batch-retry',
        'snapshot_dir': str(snapshot_dir),
        'mode': args.mode,
        'retry_count': len(retry_rows),
        'output': str(retry_requests_path),
    }
    print(json.dumps(payload))
    return 0


def _batch_qc_command(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    qc_output_path = Path(args.output) if args.output else (snapshot_dir / 'batch_qc.jsonl')
    review_queue_output_path = Path(args.review_queue_output) if args.review_queue_output else (snapshot_dir / 'enrichment_review_queue.jsonl')
    verdict_rows, review_queue_rows = run_batch_qc(
        snapshot_dir=snapshot_dir,
        results_path=Path(args.results) if args.results else None,
        qc_output_path=qc_output_path,
        review_queue_output_path=review_queue_output_path,
        overrides_path=Path(args.overrides) if args.overrides else None,
        reviewed_at=_utc_now(),
        judge_model=args.judge_model,
        prompt_version=args.prompt_version,
    )
    payload = {
        'command': 'batch-qc',
        'snapshot_dir': str(snapshot_dir),
        'output': str(qc_output_path),
        'review_queue_output': str(review_queue_output_path),
        'verdict_count': len(verdict_rows),
        'review_queue_count': len(review_queue_rows),
    }
    print(json.dumps(payload))
    return 0


def _review_apply_command(args: argparse.Namespace) -> int:
    snapshot_dir = Path(args.snapshot_dir)
    qc_output_path = Path(args.output) if args.output else (snapshot_dir / 'batch_qc.jsonl')
    review_queue_output_path = Path(args.review_queue_output) if args.review_queue_output else (snapshot_dir / 'enrichment_review_queue.jsonl')
    verdict_rows, review_queue_rows = run_review_apply(
        snapshot_dir=snapshot_dir,
        qc_input_path=Path(args.input) if args.input else None,
        qc_output_path=qc_output_path,
        review_queue_output_path=review_queue_output_path,
        overrides_path=Path(args.overrides) if args.overrides else None,
    )
    payload = {
        'command': 'review-apply',
        'snapshot_dir': str(snapshot_dir),
        'output': str(qc_output_path),
        'review_queue_output': str(review_queue_output_path),
        'verdict_count': len(verdict_rows),
        'review_queue_count': len(review_queue_rows),
    }
    print(json.dumps(payload))
    return 0


def _review_materialize_command(args: argparse.Namespace) -> int:
    try:
        payload = materialize_review_outputs(
            compiled_path=Path(args.compiled_input),
            decisions_input_path=Path(args.decisions_input),
            approved_output_path=Path(args.approved_output),
            rejected_output_path=Path(args.rejected_output),
            regenerate_output_path=Path(args.regenerate_output),
        )
    except (RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    result = {
        'command': 'review-materialize',
        'compiled_input': str(Path(args.compiled_input)),
        'decisions_input': str(Path(args.decisions_input)),
        'approved_output': str(Path(args.approved_output)),
        'rejected_output': str(Path(args.rejected_output)),
        'regenerate_output': str(Path(args.regenerate_output)),
    }
    result.update(payload)
    print(json.dumps(result))
    return 0


def _smoke_openai_compatible_command(args: argparse.Namespace) -> int:
    try:
        rank_provider, sense_provider = _load_build_base_providers()
        requested_words = normalize_seed_words(args.words)
        bounded_words = requested_words[:max(1, int(args.max_words))]
        snapshot_id = args.snapshot_id or build_snapshot_id(
            date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
            source_label='openai-compatible-smoke',
        )
        result = build_base_records(
            words=bounded_words,
            snapshot_id=snapshot_id,
            created_at=_utc_now(),
            rank_provider=rank_provider,
            sense_provider=sense_provider,
            max_senses=args.max_senses,
        )
        output_dir = Path(args.output_dir)
        written = write_base_snapshot(output_dir, result)
        enrichment_result = run_enrichment(
            output_dir,
            prompt_version=args.prompt_version,
            provider_mode=args.provider_mode,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            mode='per_word',
        )
        errors = validate_snapshot_files(output_dir)
        if errors:
            print(json.dumps({
                'command': 'smoke-openai-compatible',
                'snapshot_id': snapshot_id,
                'output_dir': str(output_dir),
                'error_count': len(errors),
                'errors': errors,
            }))
            return 2
        compiled_output = output_dir / 'words.enriched.jsonl'
        if enrichment_result.output_path.name == 'words.enriched.jsonl':
            compiled = load_compiled_rows(enrichment_result.output_path)
        else:
            compiled = compile_snapshot(output_dir, compiled_output)
    except (LexiconDependencyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    payload = {
        'command': 'smoke-openai-compatible',
        'snapshot_id': snapshot_id,
        'output_dir': str(output_dir),
        'requested_words': requested_words,
        'words': [record.lemma for record in result.lexemes],
        'max_words': int(args.max_words),
        'max_senses': int(args.max_senses),
        'lexeme_count': len(result.lexemes),
        'enrichment_count': len(enrichment_result.enrichments),
        'compiled_count': len(compiled),
        'compiled_output': str(compiled_output),
        'written_files': {key: str(value) for key, value in written.items()},
    }
    print(json.dumps(payload))
    return 0


def _import_db_command(args: argparse.Namespace) -> int:
    rows = load_compiled_rows(Path(args.input))
    if args.dry_run:
        counts = summarize_compiled_rows(rows)
        sense_count = sum(len(row.get('senses') or []) for row in rows if str(row.get('entry_type') or 'word') == 'word')
        example_count = sum(
            len(sense.get('examples') or [])
            for row in rows
            if str(row.get('entry_type') or 'word') == 'word'
            for sense in (row.get('senses') or [])
        )
        relation_count = sum(
            len(sense.get('synonyms') or []) + len(sense.get('antonyms') or []) + len(sense.get('collocations') or [])
            for row in rows
            if str(row.get('entry_type') or 'word') == 'word'
            for sense in (row.get('senses') or [])
        )
        payload = {
            'command': 'import-db',
            'dry_run': True,
            **counts,
            'sense_count': sense_count,
            'example_count': example_count,
            'relation_count': relation_count,
        }
        print(json.dumps(payload))
        return 0

    summary = run_import_file(
        Path(args.input),
        source_type=args.source_type,
        source_reference=args.source_reference,
        language=args.language,
    )
    payload = {
        'command': 'import-db',
        'dry_run': False,
        'summary': summary,
    }
    print(json.dumps(payload))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='python -m tools.lexicon.cli')
    subparsers = parser.add_subparsers(dest='command', required=True)

    build_base = subparsers.add_parser('build-base', help='build normalized base records for a bounded word list')
    build_base.add_argument('words', nargs='*', help='seed words to normalize and process')
    build_base.add_argument('--top-words', type=int, help='build a bounded top-N common-word inventory from wordfreq')
    build_base.add_argument('--rollout-stage', type=int, choices=[100, 1000, 5000, 30000], help='named staged rollout size alias for top common words')
    build_base.add_argument('--snapshot-id', help='optional snapshot identifier override')
    build_base.add_argument('--max-senses', type=int, default=8, help='maximum learner-visible senses per word; adaptive selection typically keeps 4, 6, or 8')
    build_base.add_argument('--adjudications', help='optional form_adjudications.jsonl file to apply as canonicalization overrides')
    build_base.add_argument('--database-url', help='optional sync database URL override for existing-word skip checks')
    build_base.add_argument('--rerun-existing', action='store_true', help='include canonical words even if they already exist in the DB')
    build_base.add_argument('--output-dir', help='optional output directory for normalized snapshot JSONL files')
    build_base.set_defaults(handler=_build_base_command)

    enrich = subparsers.add_parser('enrich', help='write learner-facing enrichment rows for a snapshot directory')
    enrich.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    enrich.add_argument('--output', help='optional output path for realtime `words.enriched.jsonl` or legacy per-sense `enrichments.jsonl`')
    enrich.add_argument('--prompt-version', default='v1', help='prompt version tag for generated enrichment rows')
    enrich.add_argument('--provider-mode', choices=['auto', 'placeholder', 'openai_compatible', 'openai_compatible_node'], default='auto', help='enrichment provider mode')
    enrich.add_argument('--model', help='optional model override for this enrichment run')
    enrich.add_argument('--reasoning-effort', choices=_REASONING_EFFORT_CHOICES, help='optional reasoning effort override for real endpoint runs')
    enrich.add_argument('--mode', choices=['per_sense', 'per_word'], default='per_word', help='enrichment execution mode')
    enrich.add_argument('--max-concurrency', type=int, default=1, help='maximum parallel lexeme jobs for per_word enrichment mode')
    enrich.add_argument('--resume', action='store_true', help='resume a prior per_word enrichment run using the checkpoint file')
    enrich.add_argument('--checkpoint-path', help='optional override path for the per_word checkpoint JSONL file')
    enrich.add_argument('--failures-output', help='optional override path for the per_word failures JSONL file')
    enrich.add_argument('--max-failures', type=int, help='stop submitting new per_word jobs after this many lexeme failures')
    enrich.add_argument('--request-delay-seconds', type=float, default=1.0, help='delay between per_word request starts in seconds')
    enrich.add_argument('--max-new-completed-lexemes', type=int, help='stop after this many newly completed per_word lexemes in the current invocation')
    enrich.set_defaults(handler=_enrich_command)

    smoke_openai = subparsers.add_parser('smoke-openai-compatible', help='run a tiny real OpenAI-compatible smoke flow locally')
    smoke_openai.add_argument('--output-dir', required=True, help='directory to write the temporary smoke snapshot and compiled output')
    smoke_openai.add_argument('--snapshot-id', help='optional snapshot identifier override')
    smoke_openai.add_argument('--max-words', type=int, default=1, help='maximum number of seed words to include in the smoke run')
    smoke_openai.add_argument('--max-senses', type=int, default=2, help='maximum learner-visible senses per word for the smoke run')
    smoke_openai.add_argument('--prompt-version', default='v1', help='prompt version tag for generated enrichment rows')
    smoke_openai.add_argument('--provider-mode', choices=['openai_compatible', 'openai_compatible_node'], default='openai_compatible', help='real endpoint provider mode for the smoke run')
    smoke_openai.add_argument('--model', help='optional model override for this smoke run')
    smoke_openai.add_argument('--reasoning-effort', choices=_REASONING_EFFORT_CHOICES, help='optional reasoning effort override for the smoke run')
    smoke_openai.add_argument('words', nargs='*', default=['run'], help='tiny seed words for the smoke run')
    smoke_openai.set_defaults(handler=_smoke_openai_compatible_command)

    benchmark_selection = subparsers.add_parser('benchmark-selection', help='build tuning/holdout benchmark snapshots and optional rerank comparisons')
    benchmark_selection.add_argument('--output-dir', required=True, help='directory to write benchmark artifacts')
    benchmark_selection.add_argument('--dataset', dest='datasets', action='append', choices=['tuning', 'holdout'], help='benchmark dataset to run; repeat to run multiple datasets')
    benchmark_selection.add_argument('--max-senses', type=int, default=6, help='maximum learner-visible senses per word for the deterministic baseline')
    benchmark_selection.add_argument('--with-rerank', action='store_true', help='run rerank and comparison after building the deterministic snapshot')
    benchmark_selection.add_argument('--provider-mode', choices=['auto', 'openai_compatible', 'openai_compatible_node'], default='auto', help='rerank provider mode for benchmark runs')
    benchmark_selection.add_argument('--model', help='optional model override for rerank benchmark runs')
    benchmark_selection.add_argument('--reasoning-effort', choices=_REASONING_EFFORT_CHOICES, help='optional reasoning effort override for rerank benchmark runs')
    benchmark_selection.add_argument('--candidate-limit', type=int, default=8, help='maximum WordNet candidates per lexeme for the `candidates` rerank mode')
    benchmark_selection.add_argument('--candidate-source', dest='candidate_sources', action='append', choices=RERANK_CANDIDATE_SOURCES, help='rerank candidate source to compare; repeat to run multiple modes')
    benchmark_selection.set_defaults(handler=_benchmark_selection_command)

    benchmark_enrichment = subparsers.add_parser('benchmark-enrichment', help='run live lexicon enrichment prompt/model benchmarks')
    benchmark_enrichment.add_argument('--output-dir', required=True, help='directory to write benchmark artifacts')
    benchmark_enrichment.add_argument('--dataset', default='default', help='benchmark dataset name or JSON file path')
    benchmark_enrichment.add_argument('--prompt-mode', dest='prompt_modes', action='append', choices=['grounded', 'word_only'], help='prompt mode to compare; repeat to run multiple modes')
    benchmark_enrichment.add_argument('--model', dest='models', action='append', help='model to compare; repeat to run multiple models')
    benchmark_enrichment.add_argument('--provider-mode', choices=['openai_compatible', 'openai_compatible_node'], default='openai_compatible_node', help='enrichment provider mode for benchmark runs')
    benchmark_enrichment.add_argument('--reasoning-effort', choices=_REASONING_EFFORT_CHOICES, help='optional reasoning effort override for models that support it')
    benchmark_enrichment.set_defaults(handler=_benchmark_enrichment_command)

    phrase_build_base = subparsers.add_parser('phrase-build-base', help='build normalized phrase snapshot rows from a JSONL seed file')
    phrase_build_base.add_argument('--input', required=True, help='JSONL seed file containing phrase rows')
    phrase_build_base.add_argument('--output-dir', required=True, help='directory to write phrase snapshot JSONL output')
    phrase_build_base.add_argument('--snapshot-id', help='optional snapshot identifier override')
    phrase_build_base.set_defaults(handler=_phrase_build_base_command)

    reference_build_base = subparsers.add_parser('reference-build-base', help='build normalized reference snapshot rows from a JSONL seed file')
    reference_build_base.add_argument('--input', required=True, help='JSONL seed file containing reference rows')
    reference_build_base.add_argument('--output-dir', required=True, help='directory to write reference snapshot JSONL output')
    reference_build_base.add_argument('--snapshot-id', help='optional snapshot identifier override')
    reference_build_base.set_defaults(handler=_reference_build_base_command)

    batch_prepare = subparsers.add_parser('batch-prepare', help='build deterministic batch request rows from a JSONL seed file')
    batch_prepare.add_argument('--input', required=True, help='JSONL seed file containing normalized entry rows')
    batch_prepare.add_argument('--output-dir', required=True, help='directory to write batch request JSONL output')
    batch_prepare.add_argument('--snapshot-id', help='optional snapshot identifier override')
    batch_prepare.add_argument('--model', default='gpt-5-mini', help='batch generation model to record in request bodies')
    batch_prepare.add_argument('--prompt-version', default='v1', help='prompt version tag to record in request bodies')
    batch_prepare.set_defaults(handler=_batch_prepare_command)

    batch_submit = subparsers.add_parser('batch-submit', help='submit prepared batch requests')
    batch_submit.add_argument('--snapshot-dir', required=True, help='snapshot directory containing batch_requests.jsonl')
    batch_submit.add_argument('--batch-id', help='optional batch job identifier override')
    batch_submit.add_argument('--input-file-id', help='optional input file identifier override')
    batch_submit.add_argument('--status', default='submitted', choices=['submitted', 'completed', 'failed', 'pending'], help='initial batch status to record')
    batch_submit.set_defaults(handler=_batch_submit_command)

    batch_status = subparsers.add_parser('batch-status', help='check prepared or submitted batch status')
    batch_status.add_argument('--snapshot-dir', required=True, help='snapshot directory containing batch ledgers')
    batch_status.add_argument('--batch-id', help='optional batch job identifier filter')
    batch_status.set_defaults(handler=_batch_status_command)

    batch_ingest = subparsers.add_parser('batch-ingest', help='ingest completed batch outputs')
    batch_ingest.add_argument('--snapshot-dir', required=True, help='snapshot directory containing batch_requests.jsonl')
    batch_ingest.add_argument('--input', required=True, help='batch output JSONL file to ingest')
    batch_ingest.add_argument('--output', help='optional override path for batch_results.jsonl')
    batch_ingest.add_argument('--update-jobs', action='store_true', default=True, help='update batch_jobs.jsonl statuses after ingest')
    batch_ingest.set_defaults(handler=_batch_ingest_command)

    batch_retry = subparsers.add_parser('batch-retry', help='prepare retry requests for failed batch items')
    batch_retry.add_argument('--snapshot-dir', required=True, help='snapshot directory containing batch ledgers')
    batch_retry.add_argument('--results', help='optional override path for batch_results.jsonl')
    batch_retry.add_argument('--failed-custom-ids', help='optional newline-delimited list of failed custom_ids to retry')
    batch_retry.add_argument('--snapshot-id', help='optional snapshot identifier override for retry lineage')
    batch_retry.add_argument('--model', default='gpt-5-mini', help='model to record in retry requests')
    batch_retry.add_argument('--prompt-version', default='v1', help='prompt version to record in retry requests')
    batch_retry.add_argument('--mode', choices=['repair', 'regenerate', 'escalate-model'], default='repair', help='retry mode to use when preparing requests')
    batch_retry.set_defaults(handler=_batch_retry_command)

    batch_qc = subparsers.add_parser('batch-qc', help='run QC over ingested batch outputs')
    batch_qc.add_argument('--snapshot-dir', required=True, help='snapshot directory containing batch_results.jsonl')
    batch_qc.add_argument('--results', help='optional override path for batch_results.jsonl')
    batch_qc.add_argument('--output', help='optional override path for batch_qc.jsonl')
    batch_qc.add_argument('--review-queue-output', help='optional override path for enrichment_review_queue.jsonl')
    batch_qc.add_argument('--overrides', help='optional manual overrides JSONL path')
    batch_qc.add_argument('--judge-model', default='gpt-5-mini', help='model name to record in QC rows')
    batch_qc.add_argument('--prompt-version', default='v1', help='prompt version to record in QC rows')
    batch_qc.set_defaults(handler=_batch_qc_command)

    review_apply = subparsers.add_parser('review-apply', help='apply manual overrides to an existing QC verdict file')
    review_apply.add_argument('--snapshot-dir', required=True, help='snapshot directory containing batch_qc.jsonl')
    review_apply.add_argument('--input', help='optional override path for batch_qc.jsonl')
    review_apply.add_argument('--output', help='optional override path for batch_qc.jsonl after overrides are applied')
    review_apply.add_argument('--review-queue-output', help='optional override path for enrichment_review_queue.jsonl')
    review_apply.add_argument('--overrides', help='optional manual overrides JSONL path')
    review_apply.set_defaults(handler=_review_apply_command)

    review_materialize = subparsers.add_parser('review-materialize', help='materialize approved/rejected/regenerate artifacts from compiled learner JSONL and review decisions')
    review_materialize.add_argument('--compiled-input', required=True, help='compiled learner JSONL input path')
    review_materialize.add_argument('--decisions-input', required=True, help='review decisions JSONL input path')
    review_materialize.add_argument('--approved-output', required=True, help='path to write approved compiled rows')
    review_materialize.add_argument('--rejected-output', required=True, help='path to write rejected overlay rows')
    review_materialize.add_argument('--regenerate-output', required=True, help='path to write regeneration request rows')
    review_materialize.set_defaults(handler=_review_materialize_command)

    detect_ambiguous = subparsers.add_parser('detect-ambiguous-forms', help='emit ambiguous canonicalization cases for optional LLM adjudication')
    detect_ambiguous.add_argument('--output', required=True, help='path to write ambiguous_forms.jsonl')
    detect_ambiguous.add_argument('--snapshot-id', help='optional snapshot identifier for the detection run')
    detect_ambiguous.add_argument('--max-senses', type=int, default=8, help='maximum learner senses to preserve while building the temporary snapshot context')
    detect_ambiguous.add_argument('words', nargs='+', help='surface forms to analyze')
    detect_ambiguous.set_defaults(handler=_detect_ambiguous_forms_command)

    adjudicate_forms_parser = subparsers.add_parser('adjudicate-forms', help='run bounded LLM adjudication over ambiguous surface-form rows')
    adjudicate_forms_parser.add_argument('--input', required=True, help='ambiguous_forms.jsonl input path')
    adjudicate_forms_parser.add_argument('--output', required=True, help='path to write form_adjudications.jsonl')
    adjudicate_forms_parser.add_argument('--provider-mode', choices=['auto', 'placeholder', 'openai_compatible', 'openai_compatible_node'], default='auto', help='adjudication provider mode')
    adjudicate_forms_parser.add_argument('--model', help='optional model override for adjudication')
    adjudicate_forms_parser.add_argument('--reasoning-effort', choices=_REASONING_EFFORT_CHOICES, help='optional reasoning effort override for adjudication')
    adjudicate_forms_parser.set_defaults(handler=_adjudicate_forms_command)

    lookup_entry_parser = subparsers.add_parser('lookup-entry', help='resolve a surface form to its canonical lexicon entry within a snapshot')
    lookup_entry_parser.add_argument('--snapshot-dir', required=True, help='directory containing canonical snapshot JSONL files')
    lookup_entry_parser.add_argument('word', help='surface form or canonical word to look up')
    lookup_entry_parser.set_defaults(handler=_lookup_entry_command)

    status_entry_parser = subparsers.add_parser('status-entry', help='report canonical/build/enrich/compile status for a word within a snapshot and optionally the DB')
    status_entry_parser.add_argument('--snapshot-dir', required=True, help='directory containing canonical snapshot JSONL files')
    status_entry_parser.add_argument('--compiled-input', help='optional compiled learner JSONL path; defaults to <snapshot-dir>/words.enriched.jsonl when present')
    status_entry_parser.add_argument('--check-db', action='store_true', help='also query the configured local DB for the canonical word')
    status_entry_parser.add_argument('--language', default='en', help='language code for DB status checks')
    status_entry_parser.add_argument('word', help='surface form or canonical word to inspect')
    status_entry_parser.set_defaults(handler=_status_entry_command)

    validate = subparsers.add_parser('validate', help='validate normalized or compiled lexicon outputs')
    validate_group = validate.add_mutually_exclusive_group(required=True)
    validate_group.add_argument('--snapshot-dir', help='directory containing normalized snapshot JSONL files')
    validate_group.add_argument('--compiled-input', '--compiled-path', dest='compiled_input', help='compiled learner JSONL file to validate')
    validate.set_defaults(handler=_validate_command)

    import_db = subparsers.add_parser('import-db', help='load compiled learner JSONL for local DB import workflows')
    import_db.add_argument('--input', required=True, help='compiled learner JSONL input path')
    import_db.add_argument('--dry-run', action='store_true', help='show import summary without opening a DB session')
    import_db.add_argument('--source-type', default='lexicon_snapshot', help='source type to stamp onto imported rows')
    import_db.add_argument('--source-reference', help='source reference to stamp onto imported rows')
    import_db.add_argument('--language', default='en', help='language code for imported words')
    import_db.set_defaults(handler=_import_db_command)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    return int(args.handler(args))


if __name__ == '__main__':
    raise SystemExit(main())
