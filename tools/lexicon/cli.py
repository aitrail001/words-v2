from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from tools.lexicon.build_base import build_base_records, write_base_snapshot
from tools.lexicon.compile_export import compile_snapshot
from tools.lexicon.enrich import run_enrichment
from tools.lexicon.ids import build_snapshot_id
from tools.lexicon.import_db import load_compiled_rows, run_import_file
from tools.lexicon.validate import validate_compiled_record, validate_snapshot_files
from tools.lexicon.wordfreq_provider import build_wordfreq_rank_provider
from tools.lexicon.wordnet_provider import LexiconDependencyError, build_wordnet_sense_provider


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _load_build_base_providers():
    return build_wordfreq_rank_provider(), build_wordnet_sense_provider()


def _build_base_command(args: argparse.Namespace) -> int:
    try:
        rank_provider, sense_provider = _load_build_base_providers()
    except (LexiconDependencyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2

    snapshot_id = args.snapshot_id or build_snapshot_id(
        date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
        source_label='wordnet-wordfreq',
    )
    result = build_base_records(
        words=args.words,
        snapshot_id=snapshot_id,
        created_at=_utc_now(),
        rank_provider=rank_provider,
        sense_provider=sense_provider,
        max_senses=args.max_senses,
    )
    payload = {
        'command': 'build-base',
        'snapshot_id': snapshot_id,
        'words': [record.lemma for record in result.lexemes],
        'lexeme_count': len(result.lexemes),
        'sense_count': len(result.senses),
        'concept_count': len(result.concepts),
    }
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
        )
    except (LexiconDependencyError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    payload = {
        'command': 'enrich',
        'snapshot_dir': str(Path(args.snapshot_dir)),
        'output': str(result.output_path),
        'enrichment_count': len(result.enrichments),
    }
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
    compiled = compile_snapshot(Path(args.snapshot_dir), Path(args.output))
    payload = {
        'command': 'compile-export',
        'compiled_count': len(compiled),
        'output': str(Path(args.output)),
    }
    print(json.dumps(payload))
    return 0


def _smoke_openai_compatible_command(args: argparse.Namespace) -> int:
    try:
        rank_provider, sense_provider = _load_build_base_providers()
        snapshot_id = args.snapshot_id or build_snapshot_id(
            date_stamp=datetime.now(timezone.utc).strftime('%Y%m%d'),
            source_label='openai-compatible-smoke',
        )
        result = build_base_records(
            words=args.words,
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
        'words': [record.lemma for record in result.lexemes],
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
        payload = {
            'command': 'import-db',
            'dry_run': True,
            'row_count': len(rows),
            'sense_count': sum(len(row.get('senses') or []) for row in rows),
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
    build_base.add_argument('words', nargs='+', help='seed words to normalize and process')
    build_base.add_argument('--snapshot-id', help='optional snapshot identifier override')
    build_base.add_argument('--max-senses', type=int, default=4, help='maximum learner-visible senses per word')
    build_base.add_argument('--output-dir', help='optional output directory for normalized snapshot JSONL files')
    build_base.set_defaults(handler=_build_base_command)

    enrich = subparsers.add_parser('enrich', help='write learner-facing enrichment rows for a snapshot directory')
    enrich.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    enrich.add_argument('--output', help='optional output path for enrichments.jsonl')
    enrich.add_argument('--prompt-version', default='v1', help='prompt version tag for generated enrichment rows')
    enrich.add_argument('--provider-mode', choices=['auto', 'placeholder', 'openai_compatible', 'openai_compatible_node'], default='auto', help='enrichment provider mode')
    enrich.set_defaults(handler=_enrich_command)

    smoke_openai = subparsers.add_parser('smoke-openai-compatible', help='run a tiny real OpenAI-compatible smoke flow locally')
    smoke_openai.add_argument('--output-dir', required=True, help='directory to write the temporary smoke snapshot and compiled output')
    smoke_openai.add_argument('--snapshot-id', help='optional snapshot identifier override')
    smoke_openai.add_argument('--max-senses', type=int, default=4, help='maximum learner-visible senses per word')
    smoke_openai.add_argument('--prompt-version', default='v1', help='prompt version tag for generated enrichment rows')
    smoke_openai.add_argument('--provider-mode', choices=['openai_compatible', 'openai_compatible_node'], default='openai_compatible', help='real endpoint provider mode for the smoke run')
    smoke_openai.add_argument('words', nargs='*', default=['run', 'set'], help='tiny seed words for the smoke run')
    smoke_openai.set_defaults(handler=_smoke_openai_compatible_command)

    validate = subparsers.add_parser('validate', help='validate normalized or compiled lexicon outputs')
    validate_group = validate.add_mutually_exclusive_group(required=True)
    validate_group.add_argument('--snapshot-dir', help='directory containing normalized snapshot JSONL files')
    validate_group.add_argument('--compiled-input', '--compiled-path', dest='compiled_input', help='compiled learner JSONL file to validate')
    validate.set_defaults(handler=_validate_command)

    compile_export = subparsers.add_parser('compile-export', help='compile normalized snapshot records into learner JSONL')
    compile_export.add_argument('--snapshot-dir', required=True, help='directory containing normalized snapshot JSONL files')
    compile_export.add_argument('--output', required=True, help='path to write compiled learner JSONL output')
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
