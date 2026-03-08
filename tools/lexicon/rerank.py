from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from tools.lexicon.config import LexiconSettings
from tools.lexicon.enrich import NodeOpenAICompatibleResponsesClient, OpenAICompatibleResponsesClient, read_snapshot_inputs
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.models import LexemeRecord, SenseRecord
from tools.lexicon.wordnet_provider import build_wordnet_sense_provider
from tools.lexicon.wordnet_utils import rank_learner_sense_candidates

RERANK_CANDIDATE_SOURCES = ('selected_only', 'candidates', 'full_wordnet')


@dataclass(frozen=True)
class RerankRunResult:
    output_path: Path
    rows: list[dict[str, Any]]


_SYSTEM_PROMPT = (
    "You are choosing learner-priority English WordNet senses. "
    "Only choose from the provided wn_synset_id candidates. "
    "Prefer everyday, general, learner-useful meanings over obscure, specialized, or tail meanings. "
    "Return only JSON."
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def build_rerank_prompt(*, lemma: str, target_count: int, candidates: list[dict[str, Any]]) -> str:
    payload = [
        {
            'wn_synset_id': candidate['wn_synset_id'],
            'part_of_speech': candidate['part_of_speech'],
            'canonical_gloss': candidate['canonical_gloss'],
            'lemma_count': int(candidate.get('lemma_count') or 0),
        }
        for candidate in candidates
    ]
    schema_hint = {'selected_wn_synset_ids': ['example.v.01']}
    return (
        f"Choose exactly {target_count} learner-priority senses for the English word '{lemma}'.\n"
        "You must choose only from the provided candidates and preserve your preferred order.\n"
        "Prefer broad, everyday, learner-useful meanings over specialized or obscure ones.\n"
        f"Candidates: {json.dumps(payload)}\n"
        f"Return JSON only with this schema: {json.dumps(schema_hint)}"
    )


def validate_rerank_selection(response: dict[str, Any], *, candidate_ids: set[str], target_count: int) -> list[str]:
    if not isinstance(response, dict):
        raise RuntimeError('OpenAI-compatible endpoint returned a non-object rerank payload')
    selected = response.get('selected_wn_synset_ids')
    if not isinstance(selected, list) or not selected:
        raise RuntimeError("OpenAI-compatible rerank payload field 'selected_wn_synset_ids' must be a non-empty list")
    normalized: list[str] = []
    seen: set[str] = set()
    for index, item in enumerate(selected):
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"OpenAI-compatible rerank payload field 'selected_wn_synset_ids[{index}]' must be a non-empty string")
        wn_synset_id = item.strip()
        if wn_synset_id in seen:
            raise RuntimeError('OpenAI-compatible rerank payload must not contain duplicate wn_synset_ids')
        if wn_synset_id not in candidate_ids:
            raise RuntimeError(f"OpenAI-compatible rerank payload selected unknown wn_synset_id '{wn_synset_id}'")
        seen.add(wn_synset_id)
        normalized.append(wn_synset_id)
    if len(normalized) != target_count:
        raise RuntimeError(f'OpenAI-compatible rerank payload must choose exactly {target_count} wn_synset_ids')
    return normalized


def _build_client(*, settings: LexiconSettings, provider_mode: str, model_name: str | None = None, reasoning_effort: str | None = None, transport=None, runner=None):
    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for rerank-senses')
    if not effective_model_name:
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for rerank-senses')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for rerank-senses')
    if provider_mode == 'auto':
        provider_mode = 'openai_compatible_node' if settings.llm_transport == 'node' else 'openai_compatible'
    if provider_mode == 'openai_compatible_node':
        return NodeOpenAICompatibleResponsesClient(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=str(effective_model_name),
            runner=runner,
            reasoning_effort=effective_reasoning_effort,
        ), str(effective_model_name)
    if provider_mode == 'openai_compatible':
        return OpenAICompatibleResponsesClient(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=str(effective_model_name),
            transport=transport,
            reasoning_effort=effective_reasoning_effort,
        ), str(effective_model_name)
    raise ValueError(f'Unsupported provider mode for rerank-senses: {provider_mode}')


def _normalize_provider_candidates(canonical_senses: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = rank_learner_sense_candidates(canonical_senses)
    return [dict(item['sense']) for item in ranked if item['sense'].get('wn_synset_id')]


def _candidate_senses_for_lemma(lemma: str, *, candidate_limit: int, sense_provider) -> list[dict[str, Any]]:
    ranked = _normalize_provider_candidates(sense_provider(lemma))
    return ranked[:max(1, candidate_limit)]


def _snapshot_selected_candidates(selected_snapshot_senses: list[SenseRecord]) -> list[dict[str, Any]]:
    ordered = sorted(selected_snapshot_senses, key=lambda item: item.sense_order)
    candidates: list[dict[str, Any]] = []
    for sense in ordered:
        if not sense.wn_synset_id:
            continue
        candidates.append(
            {
                'wn_synset_id': str(sense.wn_synset_id),
                'part_of_speech': sense.part_of_speech,
                'canonical_gloss': sense.canonical_gloss,
                'lemma_count': 0,
            }
        )
    return candidates


def _full_wordnet_candidates(lemma: str, *, sense_provider) -> list[dict[str, Any]]:
    return _normalize_provider_candidates(sense_provider(lemma))


def _resolve_candidate_senses(
    *,
    lexeme: LexemeRecord,
    selected_snapshot_senses: list[SenseRecord],
    candidate_source: str,
    candidate_limit: int,
    sense_provider,
) -> list[dict[str, Any]]:
    if candidate_source == 'selected_only':
        return _snapshot_selected_candidates(selected_snapshot_senses)
    if candidate_source == 'candidates':
        return _candidate_senses_for_lemma(lexeme.lemma, candidate_limit=candidate_limit, sense_provider=sense_provider)
    if candidate_source == 'full_wordnet':
        return _full_wordnet_candidates(lexeme.lemma, sense_provider=sense_provider)
    raise ValueError(f'Unsupported rerank candidate source: {candidate_source}')


def run_rerank(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    settings: LexiconSettings | None = None,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    prompt_version: str = 'rerank-v1',
    candidate_limit: int = 8,
    candidate_source: str = 'candidates',
    words: list[str] | None = None,
    sense_provider=None,
    transport=None,
    runner=None,
) -> RerankRunResult:
    if candidate_source not in RERANK_CANDIDATE_SOURCES:
        raise ValueError(
            f"Unsupported rerank candidate source: {candidate_source}. Expected one of: {', '.join(RERANK_CANDIDATE_SOURCES)}"
        )

    effective_settings = settings or LexiconSettings.from_env()
    effective_sense_provider = sense_provider
    if candidate_source != 'selected_only' and effective_sense_provider is None:
        effective_sense_provider = build_wordnet_sense_provider()
    client, effective_model_name = _build_client(
        settings=effective_settings,
        provider_mode=provider_mode,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        transport=transport,
        runner=runner,
    )
    lexemes, senses = read_snapshot_inputs(snapshot_dir)
    selected_words = {word.strip().lower() for word in (words or []) if word.strip()}
    selected_senses_by_lexeme: dict[str, list[SenseRecord]] = {}
    selected_count_by_lexeme: dict[str, int] = {}
    for sense in senses:
        selected_senses_by_lexeme.setdefault(sense.lexeme_id, []).append(sense)
        if sense.wn_synset_id:
            selected_count_by_lexeme[sense.lexeme_id] = selected_count_by_lexeme.get(sense.lexeme_id, 0) + 1

    rows: list[dict[str, Any]] = []
    generated_at = _utc_now()
    generation_run_id = f'rerank-{generated_at}'
    for lexeme in lexemes:
        if selected_words and lexeme.lemma not in selected_words:
            continue
        candidates = _resolve_candidate_senses(
            lexeme=lexeme,
            selected_snapshot_senses=selected_senses_by_lexeme.get(lexeme.lexeme_id, []),
            candidate_source=candidate_source,
            candidate_limit=candidate_limit,
            sense_provider=effective_sense_provider,
        )
        if not candidates:
            continue
        target_count = min(selected_count_by_lexeme.get(lexeme.lexeme_id, 0) or len(candidates), len(candidates))
        if target_count <= 0:
            continue
        prompt = build_rerank_prompt(lemma=lexeme.lemma, target_count=target_count, candidates=candidates)
        response = client.generate_json(prompt)
        candidate_ids = {str(candidate['wn_synset_id']) for candidate in candidates if candidate.get('wn_synset_id')}
        selected_ids = validate_rerank_selection(response, candidate_ids=candidate_ids, target_count=target_count)
        rows.append({
            'snapshot_id': lexeme.snapshot_id,
            'lexeme_id': lexeme.lexeme_id,
            'lemma': lexeme.lemma,
            'candidate_source': candidate_source,
            'candidate_count': len(candidates),
            'candidate_limit': candidate_limit if candidate_source == 'candidates' else None,
            'candidate_wn_synset_ids': [str(candidate['wn_synset_id']) for candidate in candidates if candidate.get('wn_synset_id')],
            'selected_wn_synset_ids': selected_ids,
            'model_name': effective_model_name,
            'prompt_version': prompt_version,
            'generation_run_id': generation_run_id,
            'generated_at': generated_at,
        })

    destination = output_path or snapshot_dir / 'sense_reranks.jsonl'
    write_jsonl(destination, rows)
    return RerankRunResult(output_path=destination, rows=rows)
