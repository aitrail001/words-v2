from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Iterable
import json
import statistics

from tools.lexicon.build_base import build_base_records, normalize_seed_words
from tools.lexicon.config import LexiconSettings
from tools.lexicon.enrich import (
    NodeOpenAICompatibleResponsesClient,
    OpenAICompatibleResponsesClient,
    _build_enrichment_record,
    _generate_validated_word_payload_with_stats,
)
from tools.lexicon.wordfreq_provider import build_wordfreq_rank_provider
from tools.lexicon.wordnet_provider import build_wordnet_sense_provider

BENCHMARKS_DIR = Path(__file__).resolve().parent / "benchmarks"
BUILTIN_ENRICHMENT_BENCHMARKS = {
    "default": BENCHMARKS_DIR / "enrichment_prompt_words.json",
    "curated_100": BENCHMARKS_DIR / "enrichment_prompt_words_100.json",
}
PromptMode = str
BenchmarkCaseRunner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class EnrichmentBenchmarkResult:
    output_dir: Path
    summary_path: Path
    payload: dict[str, Any]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _resolve_benchmark_path(dataset: str | Path) -> tuple[str, Path]:
    if isinstance(dataset, Path):
        return dataset.stem, dataset
    normalized = str(dataset).strip()
    if normalized in BUILTIN_ENRICHMENT_BENCHMARKS:
        return normalized, BUILTIN_ENRICHMENT_BENCHMARKS[normalized]
    path = Path(normalized)
    return path.stem, path


def load_enrichment_benchmark_words(dataset: str | Path) -> list[str]:
    dataset_name, path = _resolve_benchmark_path(dataset)
    if not path.exists():
        raise FileNotFoundError(f"Enrichment benchmark word list is missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Enrichment benchmark word list must be a JSON array: {path}")
    words = normalize_seed_words(str(item) for item in payload if str(item).strip())
    if not words:
        raise ValueError(f"Enrichment benchmark word list is empty: {path}")
    if dataset_name in BUILTIN_ENRICHMENT_BENCHMARKS and words != payload:
        path.write_text(json.dumps(words, indent=2) + "\n", encoding="utf-8")
    return words


def load_enrichment_benchmark_metadata(dataset: str | Path) -> dict[str, str]:
    dataset_name, path = _resolve_benchmark_path(dataset)
    if isinstance(dataset, Path):
        meta_path = path.with_suffix(".meta.json")
    else:
        if dataset_name in BUILTIN_ENRICHMENT_BENCHMARKS:
            meta_path = BUILTIN_ENRICHMENT_BENCHMARKS[dataset_name].with_suffix(".meta.json")
        else:
            meta_path = path.with_suffix(".meta.json")
    if not meta_path.exists():
        return {}
    payload = json.loads(meta_path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise ValueError(f"Enrichment benchmark metadata must be a JSON array: {meta_path}")
    rows: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        word = str(item.get("word") or "").strip().lower()
        category = str(item.get("category") or "").strip()
        if word and category:
            rows[word] = category
    return rows


def _lemma_from_sense_id(sense_id: str) -> str:
    parts = str(sense_id).split("_")
    if len(parts) >= 4 and parts[0] == "sn" and parts[1] == "lx":
        return "_".join(parts[2:-1]).lower()
    return ""


def _summarize_category_counts(words: list[str], metadata: dict[str, str]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in words:
        category = metadata.get(word)
        if not category:
            continue
        counts[category] = counts.get(category, 0) + 1
    return dict(sorted(counts.items()))


def _build_rubric_summary(*, rows: list[dict[str, Any]], metadata: dict[str, str], selected_sense_count: int, valid_response_count: int) -> dict[str, Any]:
    distinct_variant_rows = 0
    distinct_variant_linked_notes = 0
    entity_rows = 0
    entity_specific_notes = 0
    suspicious_generated_forms = 0

    for row in rows:
        lemma = _lemma_from_sense_id(str(row.get("sense_id") or ""))
        category = metadata.get(lemma)
        definition = str(row.get("definition") or "").lower()
        usage_note = str(row.get("usage_note") or "").lower()
        forms = dict(row.get("forms") or {})
        verb_forms = dict(forms.get("verb_forms") or {})

        if category == "distinct_variant":
            distinct_variant_rows += 1
            if any(marker in usage_note for marker in ("another form", "base word", "related to", "verb ")):
                distinct_variant_linked_notes += 1
        if category == "entity":
            entity_rows += 1
            if any(marker in (definition + " " + usage_note) for marker in ("proper noun", "capital city", "city", "brand", "organization", "place")):
                entity_specific_notes += 1
        if any(str(value).lower().endswith("inged") for value in verb_forms.values()):
            suspicious_generated_forms += 1

    return {
        "dropped_row_count": int(selected_sense_count - valid_response_count),
        "distinct_variant_rows": distinct_variant_rows,
        "distinct_variant_linked_note_hits": distinct_variant_linked_notes,
        "entity_rows": entity_rows,
        "entity_specific_note_hits": entity_specific_notes,
        "suspicious_generated_forms": suspicious_generated_forms,
    }


def _default_case_runner(
    *,
    lexemes,
    senses,
    output_path: Path,
    provider_mode: str,
    model_name: str,
    prompt_mode: str,
    settings: LexiconSettings,
    runner=None,
    transport=None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    if provider_mode == "openai_compatible_node":
        client = NodeOpenAICompatibleResponsesClient(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=model_name,
            runner=runner,
            timeout_seconds=settings.llm_timeout_seconds,
            reasoning_effort=reasoning_effort,
        )
    elif provider_mode == "openai_compatible":
        client = OpenAICompatibleResponsesClient(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=model_name,
            transport=transport,
            timeout_seconds=settings.llm_timeout_seconds,
            reasoning_effort=reasoning_effort,
        )
    else:
        raise ValueError(f"Unsupported provider mode for enrichment benchmark: {provider_mode}")

    senses_by_lexeme: dict[str, list[Any]] = {}
    for sense in senses:
        senses_by_lexeme.setdefault(sense.lexeme_id, []).append(sense)

    rows: list[dict[str, Any]] = []
    latencies: list[float] = []
    definition_lengths: list[int] = []
    usage_note_lengths: list[int] = []
    confidences: list[float] = []
    cefr_distribution: dict[str, int] = {}
    repair_count = 0
    retry_count = 0
    batch_started_at = perf_counter()

    for lexeme in lexemes:
        ordered_senses = sorted(senses_by_lexeme.get(lexeme.lexeme_id, []), key=lambda item: item.sense_order)
        started_at = perf_counter()
        response_rows, stats = _generate_validated_word_payload_with_stats(
            client=client,
            lexeme=lexeme,
            senses=ordered_senses,
            prompt_mode=prompt_mode,
        )
        elapsed = perf_counter() - started_at
        latencies.append(elapsed)
        repair_count += int(stats.get("repair_count") or 0)
        retry_count += int(stats.get("retry_count") or 0)

        sense_by_id = {sense.sense_id: sense for sense in ordered_senses}
        for response_row in response_rows:
            sense = sense_by_id[response_row["sense_id"]]
            record = _build_enrichment_record(
                lexeme=lexeme,
                sense=sense,
                response=response_row,
                model_name=model_name,
                prompt_version=f"benchmark-{prompt_mode}-v1",
                generation_run_id=f"benchmark-{model_name}-{prompt_mode}",
                review_status="draft",
                generated_at=_utc_now(),
            )
            definition_lengths.append(len(record.definition))
            usage_note_lengths.append(len(record.usage_note))
            confidences.append(record.confidence)
            cefr_distribution[record.cefr_level] = cefr_distribution.get(record.cefr_level, 0) + 1
            rows.append(record.to_dict())

    batch_duration = perf_counter() - batch_started_at
    payload = {
        "model_name": model_name,
        "prompt_mode": prompt_mode,
        "lexeme_count": len(lexemes),
        "selected_sense_count": sum(len(senses_by_lexeme.get(lexeme.lexeme_id, [])) for lexeme in lexemes),
        "valid_response_count": len(rows),
        "repair_count": repair_count,
        "retry_count": retry_count,
        "batch_duration_seconds": round(batch_duration, 3),
        "average_latency_seconds": round(statistics.mean(latencies), 3) if latencies else 0.0,
        "average_confidence": round(statistics.mean(confidences), 3) if confidences else 0.0,
        "average_definition_chars": round(statistics.mean(definition_lengths), 1) if definition_lengths else 0.0,
        "average_usage_note_chars": round(statistics.mean(usage_note_lengths), 1) if usage_note_lengths else 0.0,
        "cefr_distribution": dict(sorted(cefr_distribution.items())),
        "rows": rows,
    }
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def run_enrichment_benchmark(
    output_dir: Path,
    *,
    dataset: str | Path = "default",
    prompt_modes: Iterable[PromptMode] = ("grounded",),
    model_names: Iterable[str] = ("gpt-5.1-chat",),
    provider_mode: str = "openai_compatible_node",
    reasoning_effort: str | None = None,
    rank_provider=None,
    sense_provider=None,
    settings: LexiconSettings | None = None,
    run_case: BenchmarkCaseRunner | None = None,
    runner=None,
    transport=None,
) -> EnrichmentBenchmarkResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    generated_at = _utc_now()
    words = load_enrichment_benchmark_words(dataset)
    metadata = load_enrichment_benchmark_metadata(dataset)
    effective_rank_provider = rank_provider or build_wordfreq_rank_provider()
    effective_sense_provider = sense_provider or build_wordnet_sense_provider()
    effective_settings = settings or LexiconSettings.from_env()
    effective_run_case = run_case or _default_case_runner

    base_result = build_base_records(
        words=words,
        snapshot_id=f"benchmark-{datetime.now(timezone.utc).strftime('%Y%m%d')}-enrichment",
        created_at=generated_at,
        rank_provider=effective_rank_provider,
        sense_provider=effective_sense_provider,
        max_senses=6,
    )

    payload_runs: list[dict[str, Any]] = []
    resolved_prompt_modes = list(prompt_modes)
    resolved_models = list(model_names)
    for model_name in resolved_models:
        for prompt_mode in resolved_prompt_modes:
            case_output = output_dir / f"{model_name}.{prompt_mode}.json"
            case_payload = effective_run_case(
                lexemes=base_result.lexemes,
                senses=base_result.senses,
                output_path=case_output,
                provider_mode=provider_mode,
                model_name=model_name,
                prompt_mode=prompt_mode,
                settings=effective_settings,
                runner=runner,
                transport=transport,
                reasoning_effort=reasoning_effort,
            )
            case_payload["rubric_summary"] = _build_rubric_summary(
                rows=list(case_payload.get("rows") or []),
                metadata=metadata,
                selected_sense_count=int(case_payload.get("selected_sense_count") or 0),
                valid_response_count=int(case_payload.get("valid_response_count") or 0),
            )
            payload_runs.append(dict(case_payload))

    payload = {
        "generated_at": generated_at,
        "dataset": _resolve_benchmark_path(dataset)[0],
        "words": words,
        "category_counts": _summarize_category_counts(words, metadata),
        "prompt_modes": resolved_prompt_modes,
        "models": resolved_models,
        "output_dir": str(output_dir),
        "runs": payload_runs,
    }
    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return EnrichmentBenchmarkResult(output_dir=output_dir, summary_path=summary_path, payload=payload)
