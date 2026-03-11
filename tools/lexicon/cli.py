from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tools.lexicon.benchmark_selection import run_selection_benchmark
from tools.lexicon.build_base import build_base_records, build_word_inventory, normalize_seed_words, write_base_snapshot
from tools.lexicon.compare_selection import compare_selection_artifacts
from tools.lexicon.compile_export import compile_snapshot
from tools.lexicon.enrich import run_enrichment
from tools.lexicon.ids import build_snapshot_id
from tools.lexicon.import_db import load_compiled_rows, run_import_file
from tools.lexicon.rerank import RERANK_CANDIDATE_SOURCES, run_rerank
from tools.lexicon.selection_review import prepare_review, score_selection_risk
from tools.lexicon.validate import validate_compiled_record, validate_snapshot_files
from tools.lexicon.wordfreq_provider import build_wordfreq_rank_provider
from tools.lexicon.wordfreq_utils import build_wordfreq_inventory_provider
from tools.lexicon.wordnet_provider import LexiconDependencyError, build_wordnet_sense_provider


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _load_build_base_providers():
    return build_wordfreq_rank_provider(), build_wordnet_sense_provider()


def _load_word_inventory_provider():
    return build_wordfreq_inventory_provider()


def _build_base_command(args: argparse.Namespace) -> int:
    try:
        rank_provider, sense_provider = _load_build_base_providers()
    except (LexiconDependencyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if args.top_words and args.rollout_stage:
        print('build-base accepts only one of --top-words or --rollout-stage', file=sys.stderr)
        return 2

    requested_top_words = args.top_words or args.rollout_stage
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
        source_label='wordnet-wordfreq',
    )
    result = build_base_records(
        words=words,
        snapshot_id=snapshot_id,
        created_at=_utc_now(),
        rank_provider=rank_provider,
        sense_provider=sense_provider,
        max_senses=args.max_senses,
    )
    payload = {
        'command': 'build-base',
        'snapshot_id': snapshot_id,
        'inventory_mode': inventory_mode,
        'words': [record.lemma for record in result.lexemes],
        'lexeme_count': len(result.lexemes),
        'sense_count': len(result.senses),
        'concept_count': len(result.concepts),
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


def _rerank_senses_command(args: argparse.Namespace) -> int:
    try:
        result = run_rerank(
            Path(args.snapshot_dir),
            output_path=Path(args.output) if args.output else None,
            provider_mode=args.provider_mode,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            candidate_limit=args.candidate_limit,
            candidate_source=args.candidate_source,
            words=args.words,
        )
    except (LexiconDependencyError, RuntimeError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'rerank-senses',
        'snapshot_dir': str(Path(args.snapshot_dir)),
        'output': str(result.output_path),
        'rerank_count': len(result.rows),
    }
    print(json.dumps(payload))
    return 0


def _compare_selection_command(args: argparse.Namespace) -> int:
    payload = compare_selection_artifacts(
        Path(args.snapshot_dir),
        Path(args.rerank_file),
        output_path=Path(args.output) if args.output else None,
    )
    payload = dict(payload)
    payload['command'] = 'compare-selection'
    if args.output:
        payload['output'] = str(Path(args.output))
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


def _score_selection_risk_command(args: argparse.Namespace) -> int:
    try:
        result = score_selection_risk(
            Path(args.snapshot_dir),
            output_path=Path(args.output) if args.output else None,
            candidate_limit=args.candidate_limit,
        )
    except (LexiconDependencyError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    risk_band_counts: dict[str, int] = {}
    for row in result.rows:
        band = str(row.get('risk_band') or '')
        if band:
            risk_band_counts[band] = risk_band_counts.get(band, 0) + 1
    payload = {
        'command': 'score-selection-risk',
        'snapshot_dir': str(Path(args.snapshot_dir)),
        'output': str(result.output_path),
        'decision_count': len(result.rows),
        'rerank_recommended_count': sum(1 for row in result.rows if bool(row.get('rerank_recommended')) or str(row.get('risk_band') or '') != 'deterministic_only'),
        'review_candidate_count': sum(1 for row in result.rows if row.get('risk_band') == 'rerank_and_review_candidate'),
        'risk_band_counts': risk_band_counts,
    }
    print(json.dumps(payload))
    return 0


def _prepare_review_command(args: argparse.Namespace) -> int:
    try:
        result = prepare_review(
            Path(args.snapshot_dir),
            decisions_path=Path(args.decisions),
            output_path=Path(args.output) if args.output else None,
            review_queue_output=Path(args.review_queue_output) if args.review_queue_output else None,
            provider_mode=args.provider_mode,
            model_name=args.model,
            reasoning_effort=args.reasoning_effort,
            candidate_limit=args.candidate_limit,
            candidate_source=args.candidate_source,
        )
    except (LexiconDependencyError, RuntimeError, ValueError, FileNotFoundError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    review_rows = list(getattr(result, 'review_rows', []))
    reranked_lexeme_count = getattr(result, 'reranked_lexeme_count', len(getattr(result, 'rerank_rows', [])))
    payload = {
        'command': 'prepare-review',
        'snapshot_dir': str(Path(args.snapshot_dir)),
        'decisions': str(Path(args.decisions)),
        'output': str(result.output_path),
        'decision_count': len(result.rows),
        'reranked_lexeme_count': reranked_lexeme_count,
        'review_required_count': sum(1 for row in result.rows if bool(row.get('review_required'))),
        'auto_accepted_count': sum(1 for row in result.rows if bool(row.get('auto_accepted'))),
        'review_count': len(review_rows),
    }
    if result.review_queue_output is not None:
        payload['review_queue_output'] = str(result.review_queue_output)
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
    if args.decision_filter:
        payload['decision_filter'] = args.decision_filter
    if args.decisions:
        payload['decisions'] = str(Path(args.decisions))
    print(json.dumps(payload))
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
        'sense_count': len(result.senses),
        'concept_count': len(result.concepts),
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
        sense_count = sum(len(row.get('senses') or []) for row in rows)
        example_count = sum(
            len(sense.get('examples') or [])
            for row in rows
            for sense in (row.get('senses') or [])
        )
        relation_count = sum(
            len(sense.get('synonyms') or []) + len(sense.get('antonyms') or []) + len(sense.get('collocations') or [])
            for row in rows
            for sense in (row.get('senses') or [])
        )
        payload = {
            'command': 'import-db',
            'dry_run': True,
            'row_count': len(rows),
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
    build_base.add_argument('--output-dir', help='optional output directory for normalized snapshot JSONL files')
    build_base.set_defaults(handler=_build_base_command)

    enrich = subparsers.add_parser('enrich', help='write learner-facing enrichment rows for a snapshot directory')
    enrich.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    enrich.add_argument('--output', help='optional output path for enrichments.jsonl')
    enrich.add_argument('--prompt-version', default='v1', help='prompt version tag for generated enrichment rows')
    enrich.add_argument('--provider-mode', choices=['auto', 'placeholder', 'openai_compatible', 'openai_compatible_node'], default='auto', help='enrichment provider mode')
    enrich.add_argument('--model', help='optional model override for this enrichment run')
    enrich.add_argument('--reasoning-effort', choices=['low', 'medium', 'high'], help='optional reasoning effort override for real endpoint runs')
    enrich.add_argument('--mode', choices=['per_sense', 'per_word'], default='per_sense', help='enrichment execution mode')
    enrich.add_argument('--max-concurrency', type=int, default=1, help='maximum parallel lexeme jobs for per_word enrichment mode')
    enrich.set_defaults(handler=_enrich_command)

    smoke_openai = subparsers.add_parser('smoke-openai-compatible', help='run a tiny real OpenAI-compatible smoke flow locally')
    smoke_openai.add_argument('--output-dir', required=True, help='directory to write the temporary smoke snapshot and compiled output')
    smoke_openai.add_argument('--snapshot-id', help='optional snapshot identifier override')
    smoke_openai.add_argument('--max-words', type=int, default=1, help='maximum number of seed words to include in the smoke run')
    smoke_openai.add_argument('--max-senses', type=int, default=2, help='maximum learner-visible senses per word for the smoke run')
    smoke_openai.add_argument('--prompt-version', default='v1', help='prompt version tag for generated enrichment rows')
    smoke_openai.add_argument('--provider-mode', choices=['openai_compatible', 'openai_compatible_node'], default='openai_compatible', help='real endpoint provider mode for the smoke run')
    smoke_openai.add_argument('--model', help='optional model override for this smoke run')
    smoke_openai.add_argument('--reasoning-effort', choices=['low', 'medium', 'high'], help='optional reasoning effort override for the smoke run')
    smoke_openai.add_argument('words', nargs='*', default=['run'], help='tiny seed words for the smoke run')
    smoke_openai.set_defaults(handler=_smoke_openai_compatible_command)

    rerank = subparsers.add_parser('rerank-senses', help='use an LLM to rerank grounded WordNet candidates for an existing snapshot')
    rerank.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    rerank.add_argument('--output', help='optional output path for sense_reranks.jsonl')
    rerank.add_argument('--provider-mode', choices=['auto', 'openai_compatible', 'openai_compatible_node'], default='auto', help='rerank provider mode')
    rerank.add_argument('--model', help='optional model override for this rerank run')
    rerank.add_argument('--reasoning-effort', choices=['low', 'medium', 'high'], help='optional reasoning effort override for rerank runs')
    rerank.add_argument('--candidate-limit', type=int, default=8, help='maximum WordNet candidates per lexeme to present to the rerank model')
    rerank.add_argument('--candidate-source', choices=RERANK_CANDIDATE_SOURCES, default='candidates', help='candidate pool to expose to the rerank model')
    rerank.add_argument('words', nargs='*', default=[], help='optional subset of lemmas to rerank')
    rerank.set_defaults(handler=_rerank_senses_command)

    compare_selection = subparsers.add_parser('compare-selection', help='compare deterministic snapshot selection against an LLM rerank artifact')
    compare_selection.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    compare_selection.add_argument('--rerank-file', required=True, help='path to a sense_reranks.jsonl file')
    compare_selection.add_argument('--output', help='optional output path for comparison JSON')
    compare_selection.set_defaults(handler=_compare_selection_command)

    benchmark_selection = subparsers.add_parser('benchmark-selection', help='build tuning/holdout benchmark snapshots and optional rerank comparisons')
    benchmark_selection.add_argument('--output-dir', required=True, help='directory to write benchmark artifacts')
    benchmark_selection.add_argument('--dataset', dest='datasets', action='append', choices=['tuning', 'holdout'], help='benchmark dataset to run; repeat to run multiple datasets')
    benchmark_selection.add_argument('--max-senses', type=int, default=6, help='maximum learner-visible senses per word for the deterministic baseline')
    benchmark_selection.add_argument('--with-rerank', action='store_true', help='run rerank and comparison after building the deterministic snapshot')
    benchmark_selection.add_argument('--provider-mode', choices=['auto', 'openai_compatible', 'openai_compatible_node'], default='auto', help='rerank provider mode for benchmark runs')
    benchmark_selection.add_argument('--model', help='optional model override for rerank benchmark runs')
    benchmark_selection.add_argument('--reasoning-effort', choices=['low', 'medium', 'high'], help='optional reasoning effort override for rerank benchmark runs')
    benchmark_selection.add_argument('--candidate-limit', type=int, default=8, help='maximum WordNet candidates per lexeme for the `candidates` rerank mode')
    benchmark_selection.add_argument('--candidate-source', dest='candidate_sources', action='append', choices=RERANK_CANDIDATE_SOURCES, help='rerank candidate source to compare; repeat to run multiple modes')
    benchmark_selection.set_defaults(handler=_benchmark_selection_command)

    score_selection = subparsers.add_parser('score-selection-risk', help='score deterministic selections and write selection_decisions.jsonl for a snapshot')
    score_selection.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    score_selection.add_argument('--output', help='optional output path for selection_decisions.jsonl')
    score_selection.add_argument('--candidate-limit', type=int, default=8, help='bounded WordNet candidate pool size to preserve for later rerank review')
    score_selection.set_defaults(handler=_score_selection_risk_command)

    prepare_review = subparsers.add_parser('prepare-review', help='rerank only risky lexemes and mark auto-accepted vs human-review-needed decisions')
    prepare_review.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    prepare_review.add_argument('--decisions', required=True, help='path to an existing selection_decisions.jsonl file')
    prepare_review.add_argument('--output', help='optional output path for updated selection_decisions.jsonl')
    prepare_review.add_argument('--review-queue-output', help='optional output path for flagged review_queue.jsonl')
    prepare_review.add_argument('--provider-mode', choices=['auto', 'openai_compatible', 'openai_compatible_node'], default='auto', help='rerank provider mode for review preparation runs')
    prepare_review.add_argument('--model', help='optional model override for rerank review preparation runs')
    prepare_review.add_argument('--reasoning-effort', choices=['low', 'medium', 'high'], help='optional reasoning effort override for rerank review preparation runs')
    prepare_review.add_argument('--candidate-limit', type=int, default=8, help='maximum WordNet candidates per lexeme for review preparation rerank runs')
    prepare_review.add_argument('--candidate-source', choices=RERANK_CANDIDATE_SOURCES, default='candidates', help='candidate pool to expose to the rerank model during review preparation')
    prepare_review.set_defaults(handler=_prepare_review_command)

    validate = subparsers.add_parser('validate', help='validate normalized or compiled lexicon outputs')
    validate_group = validate.add_mutually_exclusive_group(required=True)
    validate_group.add_argument('--snapshot-dir', help='directory containing normalized snapshot JSONL files')
    validate_group.add_argument('--compiled-input', '--compiled-path', dest='compiled_input', help='compiled learner JSONL file to validate')
    validate.set_defaults(handler=_validate_command)

    compile_export = subparsers.add_parser('compile-export', help='compile normalized snapshot records into learner JSONL')
    compile_export.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    compile_export.add_argument('--output', required=True, help='path to write compiled learner JSONL output')
    compile_export.add_argument('--decisions', help='optional selection_decisions.jsonl input for filtered compile runs')
    compile_export.add_argument('--decision-filter', choices=['mode_c_safe'], help='optional compile filter preset based on selection decisions')
    compile_export.set_defaults(handler=_compile_export_command)

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
