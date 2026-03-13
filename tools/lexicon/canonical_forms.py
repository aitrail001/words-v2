from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Callable, Iterable, Optional

from tools.lexicon.wordfreq_utils import normalize_word_candidate, resolve_frequency_rank


CanonicalSenseProvider = Callable[[str], Iterable[dict[str, object]]]
RankProvider = Callable[[str], Optional[int]]

_IRREGULAR_BASES = {
    "gave": "give",
    "given": "give",
    "gone": "go",
    "went": "go",
    "better": "good",
    "best": "good",
    "worse": "bad",
    "worst": "bad",
    "left": "leave",
}

_KEEP_BOTH_LINKED = {
    "left",
    "better",
    "best",
    "worse",
    "worst",
    "given",
    "found",
}

_ALLOWED_ADJUDICATION_ACTIONS = {"collapse_to_canonical", "keep_separate", "keep_both_linked"}


@dataclass(frozen=True)
class CanonicalDecision:
    surface_form: str
    canonical_form: str
    decision: str
    decision_reason: str
    confidence: float
    variant_type: str
    linked_canonical_form: str | None = None
    is_separately_learner_worthy: bool = False
    candidate_forms: list[str] = field(default_factory=list)
    ambiguity_reason: str | None = None
    needs_llm_adjudication: bool = False
    sense_labels: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalizationResult:
    canonical_words: list[str]
    decisions: list[CanonicalDecision]


def _suffix_candidates(surface_form: str) -> list[str]:
    candidates: list[str] = []
    if len(surface_form) > 3 and surface_form.endswith("ies"):
        candidates.append(f"{surface_form[:-3]}y")
    if len(surface_form) > 3 and surface_form.endswith("es"):
        candidates.append(surface_form[:-2])
    # Avoid weak double-s chops like pass->pas or glass->glas.
    # Keep the broader -s fallback for ordinary plural/3sg forms like things->thing.
    if len(surface_form) > 2 and surface_form.endswith("s") and not surface_form.endswith("ss"):
        candidates.append(surface_form[:-1])
    if len(surface_form) > 4 and surface_form.endswith("ing"):
        stem = surface_form[:-3]
        candidates.append(stem)
        if stem:
            candidates.append(f"{stem}e")
    if len(surface_form) > 3 and surface_form.endswith("ed"):
        stem = surface_form[:-2]
        candidates.append(stem)
        if stem:
            candidates.append(f"{stem}e")
    if len(surface_form) > 3 and surface_form.endswith("er"):
        candidates.append(surface_form[:-2])
    if len(surface_form) > 4 and surface_form.endswith("est"):
        candidates.append(surface_form[:-3])

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        normalized_candidate = normalize_word_candidate(candidate)
        if not normalized_candidate or normalized_candidate == surface_form or normalized_candidate in seen:
            continue
        seen.add(normalized_candidate)
        normalized.append(normalized_candidate)
    return normalized


def _candidate_forms(surface_form: str, senses: list[dict[str, object]]) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = {surface_form}

    def add(candidate: str | None) -> None:
        normalized_candidate = normalize_word_candidate(candidate or "")
        if not normalized_candidate or normalized_candidate in seen:
            return
        seen.add(normalized_candidate)
        candidates.append(normalized_candidate)

    add(_IRREGULAR_BASES.get(surface_form))
    for candidate in _suffix_candidates(surface_form):
        add(candidate)
    for sense in senses:
        add(str(sense.get("canonical_label") or ""))

    return candidates


def _sense_labels_support_candidate(candidate: str, senses: list[dict[str, object]]) -> bool:
    for sense in senses:
        label = normalize_word_candidate(str(sense.get("canonical_label") or ""))
        if label == candidate:
            return True
        raw_label = str(sense.get("canonical_label") or "").strip().lower()
        if candidate in re.findall(r"[a-z]+", raw_label):
            return True
    return False


def _plural_suffix_candidates(surface_form: str) -> set[str]:
    candidates: set[str] = set()
    if len(surface_form) > 3 and surface_form.endswith("ies"):
        candidate = normalize_word_candidate(f"{surface_form[:-3]}y")
        if candidate:
            candidates.add(candidate)
    if len(surface_form) > 3 and surface_form.endswith("es"):
        candidate = normalize_word_candidate(surface_form[:-2])
        if candidate:
            candidates.add(candidate)
    if len(surface_form) > 2 and surface_form.endswith("s") and not surface_form.endswith("ss"):
        candidate = normalize_word_candidate(surface_form[:-1])
        if candidate:
            candidates.add(candidate)
    return candidates


def _apply_adjudication(surface_form: str, adjudication: dict[str, object], candidate_forms: list[str]) -> CanonicalDecision:
    selected_action = str(adjudication.get("selected_action") or "").strip()
    if selected_action not in _ALLOWED_ADJUDICATION_ACTIONS:
        raise RuntimeError(f"Invalid adjudication action for {surface_form}: {selected_action}")

    selected_canonical_form = normalize_word_candidate(str(adjudication.get("selected_canonical_form") or ""))
    if not selected_canonical_form or (selected_canonical_form != surface_form and selected_canonical_form not in candidate_forms):
        raise RuntimeError(
            f"Adjudication selected_canonical_form for {surface_form} must be the surface form or one of the candidate forms"
        )

    linked = adjudication.get("selected_linked_canonical_form")
    linked_canonical_form = normalize_word_candidate(str(linked)) if linked else None
    if linked_canonical_form and linked_canonical_form not in candidate_forms:
        raise RuntimeError(
            f"Adjudication selected_linked_canonical_form for {surface_form} must be null or one of the candidate forms"
        )

    if selected_action == "collapse_to_canonical":
        return CanonicalDecision(
            surface_form=surface_form,
            canonical_form=selected_canonical_form,
            linked_canonical_form=linked_canonical_form,
            decision=selected_action,
            decision_reason="operator/LLM adjudication override selected a canonical form",
            confidence=float(adjudication.get("confidence") or 0.8),
            variant_type="adjudicated",
            candidate_forms=candidate_forms,
        )
    if selected_action == "keep_both_linked":
        return CanonicalDecision(
            surface_form=surface_form,
            canonical_form=surface_form,
            linked_canonical_form=linked_canonical_form or selected_canonical_form,
            decision=selected_action,
            decision_reason="operator/LLM adjudication override kept the lexicalized surface form and linked it",
            confidence=float(adjudication.get("confidence") or 0.8),
            variant_type="lexicalized",
            is_separately_learner_worthy=True,
            candidate_forms=candidate_forms,
        )
    return CanonicalDecision(
        surface_form=surface_form,
        canonical_form=surface_form,
        decision="keep_separate",
        decision_reason="operator/LLM adjudication override kept the surface form separate",
        confidence=float(adjudication.get("confidence") or 0.8),
        variant_type="self",
        is_separately_learner_worthy=True,
        candidate_forms=candidate_forms,
    )


def canonicalize_words(
    *,
    words: Iterable[str],
    rank_provider: RankProvider,
    sense_provider: CanonicalSenseProvider,
    adjudications: dict[str, dict[str, object]] | None = None,
) -> CanonicalizationResult:
    normalized_words = [word for word in (normalize_word_candidate(raw_word) for raw_word in words) if word]
    sense_cache: dict[str, list[dict[str, object]]] = {}
    adjudication_map = adjudications or {}

    def get_senses(word: str) -> list[dict[str, object]]:
        if word not in sense_cache:
            sense_cache[word] = list(sense_provider(word))
        return sense_cache[word]

    canonical_words: list[str] = []
    canonical_seen: set[str] = set()
    decisions: list[CanonicalDecision] = []

    for surface_form in normalized_words:
        surface_senses = get_senses(surface_form)
        candidate_forms = _candidate_forms(surface_form, surface_senses)
        plural_suffix_candidates = _plural_suffix_candidates(surface_form)
        if plural_suffix_candidates:
            supported_suffix_candidates = {
                candidate
                for candidate in plural_suffix_candidates
                if _sense_labels_support_candidate(candidate, surface_senses)
                or _sense_labels_support_candidate(candidate, get_senses(candidate))
            }
            candidate_forms = [
                candidate
                for candidate in candidate_forms
                if candidate not in plural_suffix_candidates or candidate in supported_suffix_candidates
            ]
        surface_rank = resolve_frequency_rank(surface_form, rank_provider)
        surface_labels = sorted(
            {
                normalized
                for normalized in (
                    normalize_word_candidate(str(sense.get("canonical_label") or ""))
                    for sense in surface_senses
                )
                if normalized
            }
        )

        if surface_form in adjudication_map:
            decision = _apply_adjudication(surface_form, adjudication_map[surface_form], candidate_forms)
        elif not candidate_forms:
            decision = CanonicalDecision(
                surface_form=surface_form,
                canonical_form=surface_form,
                decision="keep_separate",
                decision_reason="no canonical alternative was found",
                confidence=0.55,
                variant_type="self",
                is_separately_learner_worthy=True,
                candidate_forms=candidate_forms,
                sense_labels=surface_labels,
            )
        else:
            scored_candidates: list[tuple[int, str, list[str], bool]] = []
            suffix_candidates = _suffix_candidates(surface_form)
            for candidate in candidate_forms:
                score = 0
                reasons: list[str] = []
                has_morphology_evidence = False
                candidate_rank = resolve_frequency_rank(candidate, rank_provider)
                if candidate_rank < surface_rank:
                    score += 3
                    reasons.append("candidate is more common in wordfreq")
                if candidate in surface_labels:
                    score += 4
                    reasons.append("WordNet canonical labels point to candidate")
                if _IRREGULAR_BASES.get(surface_form) == candidate:
                    score += 3
                    reasons.append("irregular-form map points to candidate")
                    has_morphology_evidence = True
                if candidate in suffix_candidates:
                    score += 2
                    reasons.append("suffix normalization points to candidate")
                    has_morphology_evidence = True
                scored_candidates.append((score, candidate, reasons, has_morphology_evidence))

            scored_candidates.sort(key=lambda item: (-item[0], resolve_frequency_rank(item[1], rank_provider), item[1]))
            best_score, best_candidate, best_reasons, best_has_morphology_evidence = scored_candidates[0]
            best_morphology_candidate = next((item for item in scored_candidates if item[3]), None)
            standalone_surface_labels = sum(1 for label in surface_labels if label == surface_form)
            candidate_label_matches = sum(1 for label in surface_labels if label == best_candidate)

            morph_score = None
            morph_candidate = None
            morph_reasons: list[str] = []
            morph_candidate_label_matches = 0
            if best_morphology_candidate is not None:
                morph_score, morph_candidate, morph_reasons, _ = best_morphology_candidate
                morph_candidate_label_matches = sum(1 for label in surface_labels if label == morph_candidate)

            if (
                morph_score is not None
                and morph_score >= 5
                and surface_form in _KEEP_BOTH_LINKED
                and morph_candidate_label_matches > 0
            ):
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=surface_form,
                    linked_canonical_form=morph_candidate,
                    decision="keep_both_linked",
                    decision_reason="surface form is learner-worthy on its own and also maps to a related base form",
                    confidence=0.9,
                    variant_type="lexicalized",
                    is_separately_learner_worthy=True,
                    candidate_forms=candidate_forms,
                    sense_labels=surface_labels,
                )
            elif (
                morph_score is not None
                and morph_score >= 5
                and morph_candidate != surface_form
                and standalone_surface_labels == 0
            ):
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=morph_candidate,
                    decision="collapse_to_canonical",
                    decision_reason=", ".join(morph_reasons) or "deterministic morphology selected a more suitable base form",
                    confidence=0.9,
                    variant_type="inflectional",
                    is_separately_learner_worthy=False,
                    candidate_forms=candidate_forms,
                    sense_labels=surface_labels,
                )
            elif (
                morph_score is not None
                and morph_candidate != surface_form
                and standalone_surface_labels > 0
                and morph_candidate_label_matches > 0
            ):
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=surface_form,
                    linked_canonical_form=morph_candidate,
                    decision="keep_both_linked",
                    decision_reason="surface form has standalone learner-worthy meaning and should stay linked rather than collapsed",
                    confidence=0.8,
                    variant_type="lexicalized",
                    is_separately_learner_worthy=True,
                    candidate_forms=candidate_forms,
                    sense_labels=surface_labels,
                )
            elif morph_score is not None and morph_candidate != surface_form and standalone_surface_labels > 0:
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=surface_form,
                    decision="keep_separate",
                    decision_reason="surface form has standalone learner-worthy meaning and morphology evidence alone is not enough to link it",
                    confidence=0.7,
                    variant_type="self",
                    is_separately_learner_worthy=True,
                    candidate_forms=candidate_forms,
                    sense_labels=surface_labels,
                )
            elif best_candidate != surface_form and not best_has_morphology_evidence:
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=surface_form,
                    decision="keep_separate",
                    decision_reason="semantic similarity alone is not enough to collapse to another headword",
                    confidence=0.7,
                    variant_type="self",
                    is_separately_learner_worthy=True,
                    candidate_forms=candidate_forms,
                    sense_labels=surface_labels,
                )
            else:
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=surface_form,
                    decision="unknown_needs_llm",
                    decision_reason="deterministic signals found candidate forms but no strong canonical winner",
                    confidence=0.45,
                    variant_type="ambiguous",
                    is_separately_learner_worthy=True,
                    candidate_forms=candidate_forms,
                    ambiguity_reason="candidate set exists but deterministic score stayed below the collapse threshold",
                    needs_llm_adjudication=True,
                    sense_labels=surface_labels,
                )

        if decision.canonical_form not in canonical_seen:
            canonical_seen.add(decision.canonical_form)
            canonical_words.append(decision.canonical_form)
        decisions.append(decision)

    return CanonicalizationResult(canonical_words=canonical_words, decisions=decisions)
