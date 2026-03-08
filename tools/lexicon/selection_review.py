from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
import json

from tools.lexicon.enrich import read_snapshot_inputs
from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import LexemeRecord, SenseRecord
from tools.lexicon.rerank import run_rerank
from tools.lexicon.wordnet_provider import build_wordnet_sense_provider
from tools.lexicon.wordnet_utils import rank_learner_sense_candidates

_SCHEMA_VERSION = 'lexicon_selection_decision.v1'
_SUSPICIOUS_TAIL_FLAGS = {
    'sports',
    'institutional_legal',
    'religious_biblical',
    'geometry_technical',
    'event_geographic',
    'abstract_tail',
}
_SPORTS_KEYWORDS = {'football', 'sports', 'teammate', 'baseball', 'cricket', 'game', 'gambling', 'banker'}
_INSTITUTIONAL_KEYWORDS = {'court', 'law', 'legal', 'official', 'warrant', 'military', 'government', 'public office'}
_RELIGIOUS_KEYWORDS = {'gospel', 'apostle', 'saint', 'genesis', 'biblical', 'hebrew'}
_GEOMETRY_TECHNICAL_KEYWORDS = {'geometric', 'geometry', 'diacritics', 'technical', 'scientific', 'lathe'}
_EVENT_GEOGRAPHIC_KEYWORDS = {'tournament', 'season', 'fair', 'land', 'region', 'geographic', 'body of water'}
_ABSTRACT_KEYWORDS = {'abstraction', 'concept', 'state', 'quality', 'process', 'property', 'relation'}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


@dataclass(frozen=True)
class SelectionRiskRunResult:
    output_path: Path
    rows: list[dict[str, Any]]


@dataclass(frozen=True)
class PrepareReviewRunResult:
    output_path: Path
    rows: list[dict[str, Any]]
    review_queue_output: Path | None
    review_rows: list[dict[str, Any]]
    reranked_lexeme_count: int


def _normalize_gloss(value: Any) -> str:
    return str(value or '').lower()


def _label_drift_flag(query_lemma: str, label: str) -> bool:
    query = query_lemma.strip().lower()
    normalized_label = label.strip().lower()
    if not query or not normalized_label:
        return False
    return normalized_label != query and query not in normalized_label


def _candidate_flags(*, query_lemma: str, candidate: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    gloss = _normalize_gloss(candidate.get('canonical_gloss'))
    label = str(candidate.get('canonical_label') or '')
    if any(keyword in gloss for keyword in _SPORTS_KEYWORDS):
        flags.append('sports')
    if any(keyword in gloss for keyword in _INSTITUTIONAL_KEYWORDS):
        flags.append('institutional_legal')
    if any(keyword in gloss for keyword in _RELIGIOUS_KEYWORDS):
        flags.append('religious_biblical')
    if any(keyword in gloss for keyword in _GEOMETRY_TECHNICAL_KEYWORDS):
        flags.append('geometry_technical')
    if any(keyword in gloss for keyword in _EVENT_GEOGRAPHIC_KEYWORDS):
        flags.append('event_geographic')
    if any(keyword in gloss for keyword in _ABSTRACT_KEYWORDS):
        flags.append('abstract_tail')
    if _label_drift_flag(query_lemma, label):
        flags.append('label_drift')
    return flags


def _selected_senses_by_lexeme(senses: list[SenseRecord]) -> dict[str, list[SenseRecord]]:
    grouped: dict[str, list[SenseRecord]] = {}
    for sense in senses:
        grouped.setdefault(sense.lexeme_id, []).append(sense)
    for items in grouped.values():
        items.sort(key=lambda item: item.sense_order)
    return grouped


def _ranked_candidate_metadata(lemma: str, *, ranked_candidates: list[dict[str, Any]], selected_ids: set[str]) -> list[dict[str, Any]]:
    metadata: list[dict[str, Any]] = []
    for rank, item in enumerate(ranked_candidates, start=1):
        sense = dict(item['sense'])
        wn_synset_id = str(sense.get('wn_synset_id') or '')
        metadata.append(
            {
                'wn_synset_id': wn_synset_id,
                'part_of_speech': str(sense.get('part_of_speech') or 'noun'),
                'canonical_label': str(sense.get('canonical_label') or lemma),
                'canonical_gloss': str(sense.get('canonical_gloss') or ''),
                'lemma_count': int(sense.get('lemma_count') or 0),
                'query_lemma': str(sense.get('query_lemma') or lemma),
                'deterministic_score': float(item.get('score') or 0.0),
                'deterministic_rank': rank,
                'deterministic_selected': wn_synset_id in selected_ids,
                'rerank_exposed': False,
                'rerank_selected': False,
                'candidate_flags': _candidate_flags(query_lemma=lemma, candidate=sense),
            }
        )
    return metadata


def _cutoff_margin(ranked_candidates: list[dict[str, Any]], target_count: int) -> float | None:
    if target_count <= 0 or len(ranked_candidates) <= target_count:
        return None
    selected_last = float(ranked_candidates[target_count - 1].get('score') or 0.0)
    next_excluded = float(ranked_candidates[target_count].get('score') or 0.0)
    return selected_last - next_excluded


def _pos_competition_score(ranked_candidates: list[dict[str, Any]], target_count: int) -> tuple[int, list[str]]:
    if not ranked_candidates or target_count <= 0 or len(ranked_candidates) < 8 or target_count < 4:
        return 0, []
    cutoff_index = min(target_count - 1, len(ranked_candidates) - 1)
    cutoff_score = float(ranked_candidates[cutoff_index].get('score') or 0.0)
    near_candidates = ranked_candidates[: min(len(ranked_candidates), target_count + 2)]
    strong_pos = {item['pos'] for item in near_candidates if cutoff_score - float(item.get('score') or 0.0) <= 3.0}
    moderate_pos = {item['pos'] for item in near_candidates if cutoff_score - float(item.get('score') or 0.0) <= 6.0}
    if len(strong_pos) >= 2:
        return 2, ['multi_pos_competition_strong']
    if len(moderate_pos) >= 2:
        return 1, ['multi_pos_competition_moderate']
    return 0, []


def _tail_risk_score(candidate_metadata: list[dict[str, Any]], target_count: int) -> tuple[int, list[str]]:
    near_candidates = candidate_metadata[: min(len(candidate_metadata), target_count + 2)]
    present = []
    for flag in ['sports', 'institutional_legal', 'religious_biblical', 'geometry_technical', 'event_geographic', 'abstract_tail']:
        if any(flag in item.get('candidate_flags', []) for item in near_candidates):
            present.append(flag)
    return min(2, len(present)), [f'tail_risk:{flag}' for flag in present[:2]]


def _label_drift_score(candidate_metadata: list[dict[str, Any]], target_count: int) -> tuple[int, list[str]]:
    near_candidates = candidate_metadata[: min(len(candidate_metadata), target_count + 2)]
    if any('label_drift' in item.get('candidate_flags', []) for item in near_candidates):
        return 1, ['label_drift_near_cutoff']
    return 0, []


def _frequency_priority_score(wordfreq_rank: int) -> tuple[int, list[str]]:
    if int(wordfreq_rank or 0) > 0 and int(wordfreq_rank) <= 10000:
        return 1, ['high_frequency_priority']
    return 0, []


def _sense_breadth_score(available_count: int) -> tuple[int, list[str]]:
    if available_count >= 20:
        return 3, ['available_senses>=20']
    if available_count >= 12:
        return 2, ['available_senses>=12']
    if available_count >= 8:
        return 1, ['available_senses>=8']
    return 0, []


def _target_count_score(target_count: int) -> tuple[int, list[str]]:
    if target_count >= 8:
        return 2, ['deterministic_target_count=8']
    if target_count >= 6:
        return 1, ['deterministic_target_count=6']
    return 0, []


def _cutoff_margin_score(margin: float | None) -> tuple[int, list[str]]:
    if margin is None:
        return 0, []
    if margin <= 3.0:
        return 2, ['small_cutoff_margin']
    if margin <= 6.0:
        return 1, ['moderate_cutoff_margin']
    return 0, []


def _risk_band(score: int, *, reasons: list[str]) -> str:
    if score <= 2:
        return 'deterministic_only'
    if score <= 5:
        return 'rerank_recommended'
    escalation_signals = ('tail_risk:', 'label_drift', 'multi_pos_competition_')
    if any(any(reason.startswith(prefix) for prefix in escalation_signals) for reason in reasons):
        return 'rerank_and_review_candidate'
    return 'rerank_recommended'


def score_selection_risk(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    candidate_limit: int = 8,
    sense_provider=None,
) -> SelectionRiskRunResult:
    lexemes, senses = read_snapshot_inputs(snapshot_dir)
    effective_sense_provider = sense_provider or build_wordnet_sense_provider()
    selected_by_lexeme = _selected_senses_by_lexeme(senses)
    generated_at = _utc_now()
    generation_run_id = f'selection-review-{generated_at}'
    rows: list[dict[str, Any]] = []
    for lexeme in lexemes:
        selected_snapshot_senses = selected_by_lexeme.get(lexeme.lexeme_id, [])
        selected_ids = {str(sense.wn_synset_id) for sense in selected_snapshot_senses if sense.wn_synset_id}
        ranked_candidates = rank_learner_sense_candidates(effective_sense_provider(lexeme.lemma))
        candidate_metadata = _ranked_candidate_metadata(lexeme.lemma, ranked_candidates=ranked_candidates, selected_ids=selected_ids)
        available_count = len(candidate_metadata)
        target_count = len(selected_ids)
        margin = _cutoff_margin(ranked_candidates, target_count)

        risk_score = 0
        reasons: list[str] = []
        for points, new_reasons in (
            _sense_breadth_score(available_count),
            _target_count_score(target_count),
            _cutoff_margin_score(margin),
            _pos_competition_score(ranked_candidates, target_count),
            _tail_risk_score(candidate_metadata, target_count),
            _label_drift_score(candidate_metadata, target_count),
            _frequency_priority_score(lexeme.wordfreq_rank),
        ):
            risk_score += points
            reasons.extend(new_reasons)

        band = _risk_band(risk_score, reasons=reasons)
        rows.append(
            {
                'schema_version': _SCHEMA_VERSION,
                'snapshot_id': lexeme.snapshot_id,
                'lexeme_id': lexeme.lexeme_id,
                'lemma': lexeme.lemma,
                'language': lexeme.language,
                'wordfreq_rank': lexeme.wordfreq_rank,
                'available_wordnet_sense_count': available_count,
                'candidate_pool_count': min(max(1, candidate_limit), available_count) if available_count else 0,
                'deterministic_target_count': target_count,
                'deterministic_selected_wn_synset_ids': [sense.wn_synset_id for sense in selected_snapshot_senses if sense.wn_synset_id],
                'selection_risk_score': risk_score,
                'selection_risk_reasons': reasons,
                'risk_band': band,
                'generated_at': generated_at,
                'generation_run_id': generation_run_id,
                'rerank_recommended': band != 'deterministic_only',
                'rerank_candidate_source': 'candidates' if band != 'deterministic_only' else None,
                'rerank_candidate_limit': candidate_limit if band != 'deterministic_only' else None,
                'rerank_applied': False,
                'auto_accept_eligible': False,
                'auto_accepted': False,
                'review_required': False,
                'review_reasons': [],
                'deterministic_vs_rerank_changed': False,
                'deterministic_vs_rerank_reordered_only': False,
                'candidate_metadata': candidate_metadata,
            }
        )
    destination = output_path or snapshot_dir / 'selection_decisions.jsonl'
    write_jsonl(destination, rows)
    return SelectionRiskRunResult(output_path=destination, rows=rows)


def _selected_flags(candidate_metadata: list[dict[str, Any]], selected_ids: list[str]) -> set[str]:
    by_id = {str(item.get('wn_synset_id') or ''): item for item in candidate_metadata}
    flags: set[str] = set()
    for wn_synset_id in selected_ids:
        item = by_id.get(str(wn_synset_id))
        if not item:
            continue
        flags.update(item.get('candidate_flags', []))
    return flags


def _selected_pos(candidate_metadata: list[dict[str, Any]], selected_ids: list[str]) -> set[str]:
    by_id = {str(item.get('wn_synset_id') or ''): item for item in candidate_metadata}
    return {
        str(by_id[wn_synset_id].get('part_of_speech') or 'noun')
        for wn_synset_id in selected_ids
        if wn_synset_id in by_id
    }


def _update_candidate_metadata(candidate_metadata: list[dict[str, Any]], rerank_row: dict[str, Any]) -> list[dict[str, Any]]:
    exposed = {str(item) for item in rerank_row.get('candidate_wn_synset_ids') or []}
    selected = {str(item) for item in rerank_row.get('selected_wn_synset_ids') or []}
    updated: list[dict[str, Any]] = []
    for item in candidate_metadata:
        copy = dict(item)
        wn_synset_id = str(copy.get('wn_synset_id') or '')
        copy['rerank_exposed'] = wn_synset_id in exposed
        copy['rerank_selected'] = wn_synset_id in selected
        updated.append(copy)
    return updated


def prepare_review(
    snapshot_dir: Path,
    *,
    decisions_path: Path,
    output_path: Path | None = None,
    review_queue_output: Path | None = None,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    candidate_limit: int = 8,
    candidate_source: str = 'candidates',
    sense_provider=None,
    transport=None,
    runner=None,
) -> PrepareReviewRunResult:
    rows = read_jsonl(decisions_path)
    rerank_words = [str(row.get('lemma') or '') for row in rows if str(row.get('risk_band') or '') != 'deterministic_only']
    rerank_by_lemma: dict[str, dict[str, Any]] = {}
    reranked_lexeme_count = 0
    rerank_output_path = snapshot_dir / 'sense_reranks.review.jsonl'
    if rerank_words:
        rerank_result = run_rerank(
            snapshot_dir,
            output_path=rerank_output_path,
            provider_mode=provider_mode,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            candidate_limit=candidate_limit,
            candidate_source=candidate_source,
            words=rerank_words,
            sense_provider=sense_provider,
            transport=transport,
            runner=runner,
        )
        reranked_lexeme_count = len(rerank_result.rows)
        rerank_by_lemma = {str(row.get('lemma') or ''): row for row in rerank_result.rows}

    updated_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    for row in rows:
        lemma = str(row.get('lemma') or '')
        deterministic_ids = [str(item) for item in row.get('deterministic_selected_wn_synset_ids') or []]
        rerank_row = rerank_by_lemma.get(lemma)
        updated = dict(row)
        if rerank_row is None:
            updated.setdefault('rerank_applied', False)
            updated.setdefault('auto_accept_eligible', False)
            updated.setdefault('auto_accepted', False)
            updated.setdefault('review_required', False)
            updated.setdefault('review_reasons', [])
            updated_rows.append(updated)
            continue

        reranked_ids = [str(item) for item in rerank_row.get('selected_wn_synset_ids') or []]
        added = [item for item in reranked_ids if item not in deterministic_ids]
        dropped = [item for item in deterministic_ids if item not in reranked_ids]
        replacement_count = max(len(added), len(dropped))
        reordered_only = not added and not dropped and reranked_ids != deterministic_ids
        candidate_metadata = _update_candidate_metadata(list(updated.get('candidate_metadata') or []), rerank_row)

        target_count = int(updated.get('deterministic_target_count') or len(deterministic_ids))
        threshold = 2 if target_count <= 4 else 3
        deterministic_flags = _selected_flags(candidate_metadata, deterministic_ids)
        reranked_flags = _selected_flags(candidate_metadata, reranked_ids)
        suspicious_growth = len(reranked_flags & _SUSPICIOUS_TAIL_FLAGS) > len(deterministic_flags & _SUSPICIOUS_TAIL_FLAGS)
        label_drift_introduced = any(
            item.get('rerank_selected') and not item.get('deterministic_selected') and 'label_drift' in item.get('candidate_flags', [])
            for item in candidate_metadata
        )
        deterministic_pos = _selected_pos(candidate_metadata, deterministic_ids)
        reranked_pos = _selected_pos(candidate_metadata, reranked_ids)
        harmful_pos_collapse = len(deterministic_pos) > 1 and len(reranked_pos) == 1 and int(updated.get('available_wordnet_sense_count') or 0) >= 12

        auto_accept_eligible = (
            replacement_count <= threshold
            and not label_drift_introduced
            and not suspicious_growth
            and not harmful_pos_collapse
        )
        review_reasons: list[str] = []
        if replacement_count > threshold:
            review_reasons.append('replacement_count_exceeds_threshold')
        if label_drift_introduced:
            review_reasons.append('label_drift_introduced')
        if suspicious_growth:
            review_reasons.append('suspicious_tail_growth')
        if harmful_pos_collapse:
            review_reasons.append('harmful_pos_collapse')
        if int(updated.get('wordfreq_rank') or 0) <= 3000 and replacement_count > 1:
            review_reasons.append('high_frequency_substantial_change')
        if len(added) > max(1, target_count // 2):
            review_reasons.append('large_deterministic_rerank_disagreement')

        auto_accept_eligible = auto_accept_eligible and not any(
            reason in {'high_frequency_substantial_change', 'large_deterministic_rerank_disagreement'}
            for reason in review_reasons
        )

        updated.update(
            {
                'rerank_applied': True,
                'rerank_candidate_source': rerank_row.get('candidate_source') or candidate_source,
                'rerank_candidate_limit': candidate_limit if candidate_source == 'candidates' else None,
                'rerank_candidate_wn_synset_ids': [str(item) for item in rerank_row.get('candidate_wn_synset_ids') or []],
                'reranked_selected_wn_synset_ids': reranked_ids,
                'replacement_count': replacement_count,
                'auto_accept_eligible': auto_accept_eligible,
                'auto_accepted': auto_accept_eligible,
                'review_required': not auto_accept_eligible,
                'review_reasons': review_reasons,
                'deterministic_vs_rerank_changed': reranked_ids != deterministic_ids,
                'deterministic_vs_rerank_reordered_only': reordered_only,
                'candidate_metadata': candidate_metadata,
            }
        )
        if updated['review_required']:
            review_rows.append(updated)
        updated_rows.append(updated)

    destination = output_path or decisions_path
    write_jsonl(destination, updated_rows)
    queue_destination = None
    if review_queue_output is not None:
        queue_destination = write_jsonl(review_queue_output, review_rows)
    return PrepareReviewRunResult(
        output_path=destination,
        rows=updated_rows,
        review_queue_output=queue_destination,
        review_rows=review_rows,
        reranked_lexeme_count=reranked_lexeme_count,
    )
