from __future__ import annotations

from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any
import json
import re

from tools.lexicon.jsonl_io import read_jsonl

_CANONICAL_RULE_SETS_PATH = Path(__file__).resolve().parent / "data" / "canonical_rule_sets.json"


def _load_by_key(path: Path, key: str) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for row in read_jsonl(path):
        rows[str(row[key])] = row
    return rows


@lru_cache(maxsize=1)
def _load_canonical_rule_sets() -> dict[str, list[str]]:
    if not _CANONICAL_RULE_SETS_PATH.exists():
        return {"apostrophe_s_contraction_stems": []}
    payload = json.loads(_CANONICAL_RULE_SETS_PATH.read_text(encoding="utf-8"))
    return {
        "apostrophe_s_contraction_stems": sorted(
            {
                str(stem).strip().lower()
                for stem in (payload.get("apostrophe_s_contraction_stems") or [])
                if str(stem).strip()
            }
        )
    }


def _plural_suffix_candidates(surface_form: str) -> set[str]:
    candidates: set[str] = set()
    if len(surface_form) > 3 and surface_form.endswith("ies"):
        candidates.add(f"{surface_form[:-3]}y")
    if len(surface_form) > 3 and surface_form.endswith("es"):
        candidates.add(surface_form[:-2])
    if len(surface_form) > 2 and surface_form.endswith("s") and not surface_form.endswith("ss"):
        candidates.add(surface_form[:-1])
    return candidates


def _non_plural_suffix_candidates(surface_form: str) -> set[str]:
    candidates: set[str] = set()
    apostrophe_s_contraction_stems = set(_load_canonical_rule_sets().get("apostrophe_s_contraction_stems") or [])
    if len(surface_form) > 3 and surface_form.endswith("'s"):
        base = surface_form[:-2]
        if base and base not in apostrophe_s_contraction_stems:
            candidates.add(base)
    if len(surface_form) > 3 and surface_form.endswith("s'"):
        candidates.add(surface_form[:-1])
    if len(surface_form) > 4 and surface_form.endswith("ing"):
        stem = surface_form[:-3]
        candidates.update({stem, f"{stem}e"})
    if len(surface_form) > 3 and surface_form.endswith("ed"):
        stem = surface_form[:-2]
        candidates.update({stem, f"{stem}e"})
    if len(surface_form) > 3 and surface_form.endswith("er"):
        candidates.add(surface_form[:-2])
    if len(surface_form) > 4 and surface_form.endswith("est"):
        candidates.add(surface_form[:-3])
    return {candidate for candidate in candidates if candidate and candidate != surface_form}


def _is_common_contraction(lemma: str) -> bool:
    apostrophe_s_contraction_stems = set(_load_canonical_rule_sets().get("apostrophe_s_contraction_stems") or [])
    if re.fullmatch(r"[a-z]+n't", lemma):
        return True
    if re.fullmatch(r"[a-z]+'(re|ve|ll|d|m)", lemma):
        return True
    if lemma.endswith("'s") and lemma[:-2] in apostrophe_s_contraction_stems:
        return True
    return False


def _risk_buckets(*, lexeme: dict[str, Any], variant: dict[str, Any] | None, entry: dict[str, Any] | None) -> list[str]:
    lemma = str(lexeme["lemma"])
    rank = int(lexeme["wordfreq_rank"])
    is_wordnet_backed = bool(lexeme["is_wordnet_backed"])
    entity_category = str(lexeme.get("entity_category") or "general")
    candidate_forms = list((variant or {}).get("candidate_forms") or [])
    decision = str((variant or {}).get("decision") or "")
    variant_type = str((variant or {}).get("variant_type") or "")
    source_forms = list((entry or {}).get("source_forms") or [lemma])
    candidate_set = {str(candidate) for candidate in candidate_forms}
    plural_morph_candidates = sorted(candidate_set.intersection(_plural_suffix_candidates(lemma)))
    non_plural_morph_candidates = sorted(candidate_set.intersection(_non_plural_suffix_candidates(lemma)))

    buckets: list[str] = []

    if not is_wordnet_backed and candidate_forms:
        buckets.append("no_wordnet_backing")
    if "'" in lemma or "-" in lemma:
        buckets.append("punctuation_token")
    if _is_common_contraction(lemma):
        buckets.append("common_contraction")
    if lemma.endswith(("'s", "s'")) and non_plural_morph_candidates:
        buckets.append("possessive_surface_form")
    if "'" in lemma and not _is_common_contraction(lemma) and "possessive_surface_form" not in buckets:
        buckets.append("apostrophe_name_or_abbreviation_candidate")
    if "-" in lemma:
        buckets.append("hyphenated_surface_form")
    if decision == "keep_both_linked":
        buckets.append("linked_variant")
    if plural_morph_candidates:
        buckets.append("plural_morph_candidate")
    if non_plural_morph_candidates:
        buckets.append("derived_morph_candidate")
    if decision == "keep_separate" and plural_morph_candidates:
        buckets.append("lexicalized_plural_candidate")
    if (
        decision == "keep_separate"
        and non_plural_morph_candidates
        and lemma.endswith(("ed", "ing", "est"))
        and "possessive_surface_form" not in buckets
    ):
        buckets.append("derived_form_candidate")
    if candidate_forms and any(len(candidate) <= 4 for candidate in candidate_forms):
        buckets.append("short_candidate_tail")
    if candidate_forms and all(candidate.isalpha() for candidate in candidate_forms):
        buckets.append("morph_candidate_present")
    if len(source_forms) > 1:
        buckets.append("multi_source_form")
    if entity_category != "general":
        buckets.append("non_general_entity")
    if not is_wordnet_backed and rank >= 300_000 and candidate_forms:
        buckets.append("name_brand_place_like_candidate")

    # Keep rows explicit even if they look safe.
    if not buckets:
        buckets.append("baseline_safe")
    return buckets


def build_audit_inventory(snapshot_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lexemes = [row for row in read_jsonl(snapshot_dir / "lexemes.jsonl")]
    variants_by_surface = _load_by_key(snapshot_dir / "canonical_variants.jsonl", "surface_form")
    entries_by_form = _load_by_key(snapshot_dir / "canonical_entries.jsonl", "canonical_form")

    audit_rows: list[dict[str, Any]] = []
    bucket_counts: Counter[str] = Counter()

    for lexeme in lexemes:
        lemma = str(lexeme["lemma"])
        variant = variants_by_surface.get(lemma)
        entry = entries_by_form.get(lemma)
        buckets = _risk_buckets(lexeme=lexeme, variant=variant, entry=entry)
        variant_type = str((variant or {}).get("variant_type") or "")
        candidate_set = {str(candidate) for candidate in ((variant or {}).get("candidate_forms") or [])}
        plural_morph_candidates = sorted(candidate_set.intersection(_plural_suffix_candidates(lemma)))
        non_plural_morph_candidates = sorted(candidate_set.intersection(_non_plural_suffix_candidates(lemma)))
        bucket_counts.update(buckets)
        audit_rows.append(
            {
                "lemma": lemma,
                "wordfreq_rank": int(lexeme["wordfreq_rank"]),
                "is_wordnet_backed": bool(lexeme["is_wordnet_backed"]),
                "decision": (variant or {}).get("decision"),
                "variant_type": variant_type,
                "canonical_form": (variant or {}).get("canonical_form"),
                "linked_canonical_form": (variant or {}).get("linked_canonical_form"),
                "candidate_forms": list((variant or {}).get("candidate_forms") or []),
                "plural_morph_candidates": plural_morph_candidates,
                "non_plural_morph_candidates": non_plural_morph_candidates,
                "source_forms": list((entry or {}).get("source_forms") or [lemma]),
                "is_variant_with_distinct_meanings": bool(lexeme.get("is_variant_with_distinct_meanings") or False),
                "variant_base_form": lexeme.get("variant_base_form"),
                "variant_relationship": lexeme.get("variant_relationship"),
                "entity_category": str(lexeme.get("entity_category") or "general"),
                "risk_buckets": buckets,
            }
        )

    review_priority_buckets = {
        "apostrophe_name_or_abbreviation_candidate",
        "derived_form_candidate",
        "lexicalized_plural_candidate",
        "name_brand_place_like_candidate",
        "non_general_entity",
        "possessive_surface_form",
    }
    suspicious_rows = [row for row in audit_rows if review_priority_buckets.intersection(row["risk_buckets"])]
    entity_category_counts: Counter[str] = Counter(
        str(row.get("entity_category") or "general") for row in audit_rows if str(row.get("entity_category") or "general") != "general"
    )
    summary = {
        "snapshot_dir": str(snapshot_dir),
        "lexeme_count": len(audit_rows),
        "suspicious_count": len(suspicious_rows),
        "review_priority_buckets": sorted(review_priority_buckets),
        "entity_category_counts": dict(sorted(entity_category_counts.items())),
        "bucket_counts": dict(sorted(bucket_counts.items())),
    }
    return audit_rows, summary


def main() -> int:
    snapshot_dir = Path("data/lexicon/snapshots/words-30000-20260314-main-real")
    audit_dir = Path("data/lexicon/audits")
    audit_dir.mkdir(parents=True, exist_ok=True)

    rows, summary = build_audit_inventory(snapshot_dir)
    audit_path = audit_dir / "words-30000-20260314-main-real.audit.json"
    summary_path = audit_dir / "words-30000-20260314-main-real.audit.summary.json"
    audit_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
