from __future__ import annotations

from dataclasses import dataclass, field, replace
from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Callable, Iterable, Optional

from tools.lexicon.wordfreq_utils import normalize_word_candidate, resolve_frequency_rank


CanonicalSenseProvider = Callable[[str], Iterable[dict[str, object]]]
RankProvider = Callable[[str], Optional[int]]

_ALLOWED_ADJUDICATION_ACTIONS = {"collapse_to_canonical", "keep_separate", "keep_both_linked"}
_CANONICAL_ANOMALIES_PATH = Path(__file__).resolve().parent / "data" / "canonical_anomalies.json"
_CANONICAL_RULE_SETS_PATH = Path(__file__).resolve().parent / "data" / "canonical_rule_sets.json"
_IRREGULAR_FORM_OVERRIDES_PATH = Path(__file__).resolve().parent / "data" / "irregular_form_overrides.json"
_IRREGULAR_VERB_FORMS_PATH = Path(__file__).resolve().parent / "data" / "irregular_verb_forms.json"


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


@lru_cache(maxsize=1)
def _load_canonical_anomaly_overrides() -> dict[str, dict[str, dict[str, str]]]:
    if not _CANONICAL_ANOMALIES_PATH.exists():
        return {
            "force_keep_separate": {},
            "force_collapse_to_canonical": {},
        }
    payload = json.loads(_CANONICAL_ANOMALIES_PATH.read_text(encoding="utf-8"))
    return {
        "force_keep_separate": dict(payload.get("force_keep_separate") or {}),
        "force_collapse_to_canonical": dict(payload.get("force_collapse_to_canonical") or {}),
    }


@lru_cache(maxsize=1)
def _load_canonical_rule_sets() -> dict[str, list[str]]:
    if not _CANONICAL_RULE_SETS_PATH.exists():
        return {
            "apostrophe_s_contraction_stems": [],
            "keep_both_linked_forms": [],
        }
    payload = json.loads(_CANONICAL_RULE_SETS_PATH.read_text(encoding="utf-8"))
    return {
        "apostrophe_s_contraction_stems": sorted(
            {
                normalize_word_candidate(str(stem))
                for stem in (payload.get("apostrophe_s_contraction_stems") or [])
                if normalize_word_candidate(str(stem))
            }
        ),
        "keep_both_linked_forms": sorted(
            {
                normalize_word_candidate(str(stem))
                for stem in (payload.get("keep_both_linked_forms") or [])
                if normalize_word_candidate(str(stem))
            }
        ),
    }


def _normalize_irregular_payload(
    payload: dict[str, object],
    *,
    default_reason: str,
) -> dict[str, dict[str, dict[str, str]]]:
    buckets: dict[str, dict[str, dict[str, str]]] = {
        "collapse_to_canonical": {},
        "keep_both_linked": {},
    }
    if "forms" in payload:
        forms = dict(payload.get("forms") or {})
        for surface_form, metadata in forms.items():
            normalized_surface = normalize_word_candidate(str(surface_form))
            normalized_canonical = normalize_word_candidate(str(dict(metadata).get("canonical_form") or ""))
            if not normalized_surface or not normalized_canonical:
                continue
            buckets["collapse_to_canonical"][normalized_surface] = {
                "canonical_form": normalized_canonical,
                "reason": str(dict(metadata).get("reason") or default_reason),
            }
        return buckets

    for bucket_name in buckets:
        bucket = dict(payload.get(bucket_name) or {})
        for surface_form, metadata in bucket.items():
            normalized_surface = normalize_word_candidate(str(surface_form))
            normalized_canonical = normalize_word_candidate(str(dict(metadata).get("canonical_form") or ""))
            if not normalized_surface or not normalized_canonical:
                continue
            buckets[bucket_name][normalized_surface] = {
                "canonical_form": normalized_canonical,
                "reason": str(dict(metadata).get("reason") or default_reason),
            }
    return buckets


@lru_cache(maxsize=1)
def _load_irregular_form_overrides() -> dict[str, dict[str, dict[str, str]]]:
    if not _IRREGULAR_FORM_OVERRIDES_PATH.exists():
        return {
            "collapse_to_canonical": {},
            "keep_both_linked": {},
        }
    payload = json.loads(_IRREGULAR_FORM_OVERRIDES_PATH.read_text(encoding="utf-8"))
    return _normalize_irregular_payload(payload, default_reason="irregular_form")


@lru_cache(maxsize=1)
def _load_irregular_verb_forms() -> dict[str, dict[str, dict[str, str]]]:
    if not _IRREGULAR_VERB_FORMS_PATH.exists():
        return {
            "collapse_to_canonical": {},
            "keep_both_linked": {},
        }
    payload = json.loads(_IRREGULAR_VERB_FORMS_PATH.read_text(encoding="utf-8"))
    return _normalize_irregular_payload(payload, default_reason="irregular_verb_form")


@lru_cache(maxsize=1)
def _load_irregular_bases() -> dict[str, str]:
    bases: dict[str, str] = {}
    for source in (_load_irregular_form_overrides(), _load_irregular_verb_forms()):
        for bucket in source.values():
            for surface_form, metadata in bucket.items():
                canonical_form = normalize_word_candidate(str(metadata.get("canonical_form") or ""))
                if canonical_form:
                    bases[surface_form] = canonical_form
    return bases


def _lookup_irregular_override(surface_form: str) -> tuple[str, dict[str, str]] | None:
    for source in (_load_irregular_form_overrides(), _load_irregular_verb_forms()):
        for action in ("collapse_to_canonical", "keep_both_linked"):
            metadata = source.get(action, {}).get(surface_form)
            if metadata is not None:
                return action, metadata
    return None


def _resolve_explicit_canonical_form(surface_form: str) -> str:
    current = surface_form
    seen: set[str] = set()
    anomaly_overrides = _load_canonical_anomaly_overrides()

    while current not in seen:
        seen.add(current)
        irregular_override = _lookup_irregular_override(current)
        if irregular_override is not None and irregular_override[0] == "collapse_to_canonical":
            next_form = normalize_word_candidate(str(irregular_override[1].get("canonical_form") or ""))
            if next_form and next_form != current:
                current = next_form
                continue

        anomaly_override = dict(anomaly_overrides.get("force_collapse_to_canonical") or {}).get(current)
        next_form = normalize_word_candidate(str((anomaly_override or {}).get("canonical_form") or ""))
        if next_form and next_form != current:
            current = next_form
            continue

        break

    return current


def _apply_canonical_anomaly_override(
    *,
    surface_form: str,
    candidate_forms: list[str],
    sense_labels: list[str],
    overrides: dict[str, dict[str, dict[str, str]]],
) -> CanonicalDecision | None:
    force_keep_separate = overrides.get("force_keep_separate", {})
    if surface_form in force_keep_separate:
        reason = str(force_keep_separate[surface_form].get("reason") or "anomaly_override")
        return CanonicalDecision(
            surface_form=surface_form,
            canonical_form=surface_form,
            decision="keep_separate",
            decision_reason=f"canonical anomaly override forced keep_separate ({reason})",
            confidence=0.99,
            variant_type="anomaly_override",
            is_separately_learner_worthy=True,
            candidate_forms=candidate_forms,
            sense_labels=sense_labels,
        )

    force_collapse = overrides.get("force_collapse_to_canonical", {})
    if surface_form in force_collapse:
        canonical_form = normalize_word_candidate(str(force_collapse[surface_form].get("canonical_form") or ""))
        if not canonical_form or canonical_form not in candidate_forms:
            raise RuntimeError(
                f"canonical anomaly override for {surface_form} must point to one of the deterministic candidate forms"
            )
        reason = str(force_collapse[surface_form].get("reason") or "anomaly_override")
        return CanonicalDecision(
            surface_form=surface_form,
            canonical_form=canonical_form,
            decision="collapse_to_canonical",
            decision_reason=f"canonical anomaly override forced collapse_to_canonical ({reason})",
            confidence=0.99,
            variant_type="anomaly_override",
            is_separately_learner_worthy=False,
            candidate_forms=candidate_forms,
            sense_labels=sense_labels,
        )

    return None


def _apply_irregular_override(
    *,
    surface_form: str,
    candidate_forms: list[str],
    sense_labels: list[str],
) -> CanonicalDecision | None:
    override = _lookup_irregular_override(surface_form)
    if override is None:
        return None

    action, metadata = override
    canonical_form = normalize_word_candidate(str(metadata.get("canonical_form") or ""))
    if not canonical_form or canonical_form not in candidate_forms:
        raise RuntimeError(
            f"irregular override for {surface_form} must point to one of the deterministic candidate forms"
        )

    reason = str(metadata.get("reason") or "irregular_form_override")
    if action == "collapse_to_canonical":
        return CanonicalDecision(
            surface_form=surface_form,
            canonical_form=canonical_form,
            decision="collapse_to_canonical",
            decision_reason=f"irregular-form override forced collapse_to_canonical ({reason})",
            confidence=0.99,
            variant_type="inflectional",
            is_separately_learner_worthy=False,
            candidate_forms=candidate_forms,
            sense_labels=sense_labels,
        )

    return CanonicalDecision(
        surface_form=surface_form,
        canonical_form=surface_form,
        linked_canonical_form=canonical_form,
        decision="keep_both_linked",
        decision_reason=f"irregular-form override forced keep_both_linked ({reason})",
        confidence=0.99,
        variant_type="lexicalized",
        is_separately_learner_worthy=True,
        candidate_forms=candidate_forms,
        sense_labels=sense_labels,
    )


def _suffix_candidates(surface_form: str) -> list[str]:
    candidates: list[str] = []
    apostrophe_s_contraction_stems = set(_load_canonical_rule_sets().get("apostrophe_s_contraction_stems") or [])
    if len(surface_form) > 3 and surface_form.endswith("'s"):
        base = normalize_word_candidate(surface_form[:-2])
        if base and base not in apostrophe_s_contraction_stems:
            candidates.append(base)
    if len(surface_form) > 3 and surface_form.endswith("s'"):
        candidates.append(surface_form[:-1])
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
    irregular_bases = _load_irregular_bases()

    def add(candidate: str | None) -> None:
        normalized_candidate = normalize_word_candidate(candidate or "")
        if not normalized_candidate or normalized_candidate in seen:
            return
        seen.add(normalized_candidate)
        candidates.append(normalized_candidate)

    add(irregular_bases.get(surface_form))
    for irregular_surface, irregular_base in irregular_bases.items():
        if surface_form.endswith(irregular_surface) and len(surface_form) > len(irregular_surface):
            add(f"{surface_form[:-len(irregular_surface)]}{irregular_base}")
    for candidate in _suffix_candidates(surface_form):
        add(candidate)
        add(irregular_bases.get(candidate))
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


def _non_plural_suffix_candidates(surface_form: str) -> set[str]:
    return set(_suffix_candidates(surface_form)) - _plural_suffix_candidates(surface_form)


def _possessive_suffix_candidates(surface_form: str) -> set[str]:
    candidates: set[str] = set()
    apostrophe_s_contraction_stems = set(_load_canonical_rule_sets().get("apostrophe_s_contraction_stems") or [])
    irregular_bases = _load_irregular_bases()
    if len(surface_form) > 3 and surface_form.endswith("'s"):
        base = normalize_word_candidate(surface_form[:-2])
        if base and base not in apostrophe_s_contraction_stems:
            candidates.add(base)
            irregular_base = irregular_bases.get(base)
            if irregular_base:
                candidates.add(irregular_base)
    if len(surface_form) > 3 and surface_form.endswith("s'"):
        base = normalize_word_candidate(surface_form[:-1])
        if base:
            candidates.add(base)
            irregular_base = irregular_bases.get(base)
            if irregular_base:
                candidates.add(irregular_base)
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
    anomaly_overrides = _load_canonical_anomaly_overrides()
    irregular_bases = _load_irregular_bases()
    keep_both_linked_forms = set(_load_canonical_rule_sets().get("keep_both_linked_forms") or [])
    keep_both_linked_forms.update(_load_irregular_form_overrides().get("keep_both_linked", {}).keys())
    keep_both_linked_forms.update(_load_irregular_verb_forms().get("keep_both_linked", {}).keys())

    def get_senses(word: str) -> list[dict[str, object]]:
        if word not in sense_cache:
            sense_cache[word] = list(sense_provider(word))
        return sense_cache[word]

    canonical_words: list[str] = []
    canonical_seen: set[str] = set()
    decisions: list[CanonicalDecision] = []

    for surface_form in normalized_words:
        surface_senses = get_senses(surface_form)
        raw_candidate_forms = _candidate_forms(surface_form, surface_senses)
        candidate_forms = list(raw_candidate_forms)
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
        non_plural_suffix_candidates = _non_plural_suffix_candidates(surface_form)
        possessive_suffix_candidates = _possessive_suffix_candidates(surface_form)
        if non_plural_suffix_candidates:
            filtered_candidates: list[str] = []
            for candidate in candidate_forms:
                if candidate not in non_plural_suffix_candidates:
                    filtered_candidates.append(candidate)
                    continue
                if candidate in possessive_suffix_candidates:
                    filtered_candidates.append(candidate)
                    continue
                candidate_rank = resolve_frequency_rank(candidate, rank_provider)
                if (
                    _sense_labels_support_candidate(candidate, surface_senses)
                    or _sense_labels_support_candidate(candidate, get_senses(candidate))
                    or (candidate_rank < 999_999 and candidate_rank <= surface_rank)
                ):
                    filtered_candidates.append(candidate)
            candidate_forms = filtered_candidates
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
        anomaly_override = _apply_canonical_anomaly_override(
            surface_form=surface_form,
            candidate_forms=list(dict.fromkeys(candidate_forms + raw_candidate_forms)),
            sense_labels=surface_labels,
            overrides=anomaly_overrides,
        )
        irregular_override = _apply_irregular_override(
            surface_form=surface_form,
            candidate_forms=candidate_forms,
            sense_labels=surface_labels,
        )

        if surface_form in adjudication_map:
            decision = _apply_adjudication(surface_form, adjudication_map[surface_form], candidate_forms)
        elif anomaly_override is not None:
            decision = anomaly_override
        elif irregular_override is not None:
            decision = irregular_override
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
                if irregular_bases.get(surface_form) == candidate:
                    score += 3
                    reasons.append("irregular-form map points to candidate")
                    has_morphology_evidence = True
                if candidate in suffix_candidates:
                    score += 2
                    reasons.append("suffix normalization points to candidate")
                    has_morphology_evidence = True
                if candidate in possessive_suffix_candidates:
                    score += 4
                    reasons.append("possessive normalization points to candidate")
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
                and morph_candidate is not None
                and morph_candidate in possessive_suffix_candidates
                and morph_candidate != surface_form
            ):
                decision = CanonicalDecision(
                    surface_form=surface_form,
                    canonical_form=morph_candidate,
                    decision="collapse_to_canonical",
                    decision_reason=", ".join(morph_reasons) or "possessive normalization selected the base form",
                    confidence=0.92,
                    variant_type="inflectional",
                    is_separately_learner_worthy=False,
                    candidate_forms=candidate_forms,
                    sense_labels=surface_labels,
                )
            elif (
                morph_score is not None
                and morph_score >= 5
                and _lookup_irregular_override(surface_form) is not None
                and _lookup_irregular_override(surface_form)[0] == "keep_both_linked"
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
                and morph_candidate not in plural_suffix_candidates
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

        if decision.decision == "collapse_to_canonical":
            resolved_canonical_form = _resolve_explicit_canonical_form(decision.canonical_form)
            if resolved_canonical_form != decision.canonical_form:
                decision = replace(decision, canonical_form=resolved_canonical_form)

        if decision.canonical_form not in canonical_seen:
            canonical_seen.add(decision.canonical_form)
            canonical_words.append(decision.canonical_form)
        decisions.append(decision)

    return CanonicalizationResult(canonical_words=canonical_words, decisions=decisions)
