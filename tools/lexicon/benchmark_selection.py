from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from tools.lexicon.build_base import build_base_records, normalize_seed_words, write_base_snapshot
from tools.lexicon.compare_selection import compare_selection_artifacts
from tools.lexicon.ids import build_snapshot_id
from tools.lexicon.rerank import RERANK_CANDIDATE_SOURCES, run_rerank
from tools.lexicon.wordfreq_provider import build_wordfreq_rank_provider
from tools.lexicon.wordnet_provider import build_wordnet_sense_provider

BENCHMARKS_DIR = Path(__file__).resolve().parent / 'benchmarks'
BUILTIN_BENCHMARKS = {
    'tuning': BENCHMARKS_DIR / 'tuning_words.json',
    'holdout': BENCHMARKS_DIR / 'holdout_words.json',
}


@dataclass(frozen=True)
class BenchmarkSelectionRunResult:
    output_dir: Path
    summary_path: Path
    payload: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def default_benchmark_names() -> list[str]:
    return list(BUILTIN_BENCHMARKS)


def _resolve_benchmark_path(dataset: str | Path) -> tuple[str, Path]:
    if isinstance(dataset, Path):
        return dataset.stem, dataset
    normalized = str(dataset).strip()
    if normalized in BUILTIN_BENCHMARKS:
        return normalized, BUILTIN_BENCHMARKS[normalized]
    path = Path(normalized)
    return path.stem, path


def load_benchmark_words(dataset: str | Path) -> list[str]:
    dataset_name, path = _resolve_benchmark_path(dataset)
    if not path.exists():
        raise FileNotFoundError(f'Benchmark word list is missing: {path}')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, list):
        raise ValueError(f'Benchmark word list must be a JSON array: {path}')
    words = normalize_seed_words(str(item) for item in payload if str(item).strip())
    if not words:
        raise ValueError(f'Benchmark word list is empty: {path}')
    if dataset_name in BUILTIN_BENCHMARKS and words != payload:
        # keep built-in artifacts normalized and auditable
        path.write_text(json.dumps(words, indent=2) + '\n', encoding='utf-8')
    return words


def run_selection_benchmark(
    output_dir: Path,
    *,
    datasets: Iterable[str | Path] | None = None,
    max_senses: int = 6,
    with_rerank: bool = False,
    candidate_sources: Iterable[str] | None = None,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    candidate_limit: int = 8,
    rank_provider=None,
    sense_provider=None,
    rerank_sense_provider=None,
    transport=None,
    runner=None,
) -> BenchmarkSelectionRunResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _utc_now()
    date_stamp = datetime.now(timezone.utc).strftime('%Y%m%d')
    dataset_specs = list(datasets or default_benchmark_names())
    resolved_candidate_sources = list(candidate_sources or (['candidates'] if with_rerank else []))
    for candidate_source in resolved_candidate_sources:
        if candidate_source not in RERANK_CANDIDATE_SOURCES:
            raise ValueError(
                f"Unsupported rerank candidate source: {candidate_source}. Expected one of: {', '.join(RERANK_CANDIDATE_SOURCES)}"
            )

    effective_rank_provider = rank_provider or build_wordfreq_rank_provider()
    effective_sense_provider = sense_provider or build_wordnet_sense_provider()
    effective_rerank_sense_provider = rerank_sense_provider or effective_sense_provider

    dataset_payloads: list[dict[str, Any]] = []
    for dataset_spec in dataset_specs:
        dataset_name, _ = _resolve_benchmark_path(dataset_spec)
        words = load_benchmark_words(dataset_spec)
        snapshot_id = build_snapshot_id(date_stamp=date_stamp, source_label=f'benchmark-{dataset_name}-wordnet-wordfreq')
        dataset_dir = output_dir / dataset_name
        result = build_base_records(
            words=words,
            snapshot_id=snapshot_id,
            created_at=generated_at,
            rank_provider=effective_rank_provider,
            sense_provider=effective_sense_provider,
            max_senses=max_senses,
        )
        write_base_snapshot(dataset_dir, result)

        dataset_payload: dict[str, Any] = {
            'dataset': dataset_name,
            'words': words,
            'snapshot_id': snapshot_id,
            'snapshot_dir': str(dataset_dir),
            'lexeme_count': len(result.lexemes),
            'sense_count': len(result.senses),
            'concept_count': len(result.concepts),
            'rerank_runs': [],
        }

        if with_rerank:
            for candidate_source in resolved_candidate_sources:
                rerank_output = dataset_dir / f'sense_reranks.{candidate_source}.jsonl'
                compare_output = dataset_dir / f'comparison.{candidate_source}.json'
                rerank_result = run_rerank(
                    dataset_dir,
                    output_path=rerank_output,
                    provider_mode=provider_mode,
                    model_name=model_name,
                    reasoning_effort=reasoning_effort,
                    candidate_limit=candidate_limit,
                    candidate_source=candidate_source,
                    words=words,
                    sense_provider=effective_rerank_sense_provider,
                    transport=transport,
                    runner=runner,
                )
                comparison = compare_selection_artifacts(dataset_dir, rerank_result.output_path, output_path=compare_output)
                dataset_payload['rerank_runs'].append(
                    {
                        'candidate_source': candidate_source,
                        'rerank_output': str(rerank_result.output_path),
                        'rerank_count': len(rerank_result.rows),
                        'comparison_output': str(compare_output),
                        'compared_lexeme_count': comparison['compared_lexeme_count'],
                        'changed_lexeme_count': comparison['changed_lexeme_count'],
                    }
                )

        dataset_payloads.append(dataset_payload)

    payload = {
        'generated_at': generated_at,
        'output_dir': str(output_dir),
        'datasets': dataset_payloads,
    }
    summary_path = output_dir / 'summary.json'
    summary_path.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    return BenchmarkSelectionRunResult(output_dir=output_dir, summary_path=summary_path, payload=payload)
