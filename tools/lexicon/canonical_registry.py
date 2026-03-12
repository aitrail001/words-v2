from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Optional

from tools.lexicon.jsonl_io import read_jsonl
from tools.lexicon.models import AmbiguousFormRecord, CanonicalEntryRecord, CanonicalVariantRecord
from tools.lexicon.wordfreq_utils import normalize_word_candidate

DbLookup = Callable[[str, str], Optional[dict[str, Any]]]


def load_canonical_entries(snapshot_dir: Path) -> list[CanonicalEntryRecord]:
    path = snapshot_dir / "canonical_entries.jsonl"
    if not path.exists():
        return []
    return [CanonicalEntryRecord(**row) for row in read_jsonl(path)]


def load_canonical_variants(snapshot_dir: Path) -> list[CanonicalVariantRecord]:
    path = snapshot_dir / "canonical_variants.jsonl"
    if not path.exists():
        return []
    return [CanonicalVariantRecord(**row) for row in read_jsonl(path)]


def load_ambiguous_forms(snapshot_dir: Path) -> list[AmbiguousFormRecord]:
    path = snapshot_dir / "ambiguous_forms.jsonl"
    if not path.exists():
        return []
    return [AmbiguousFormRecord(**row) for row in read_jsonl(path)]


def _lookup_payload(
    *,
    word: str,
    normalized_word: str,
    entry_id: str,
    canonical_form: str,
    decision: str,
    decision_reason: str,
    variant_type: str,
    linked_canonical_form: str | None,
    is_separately_learner_worthy: bool,
    source_forms: list[str],
    needs_adjudication: bool = False,
    candidate_forms: list[str] | None = None,
    ambiguity_reason: str | None = None,
) -> dict[str, Any]:
    payload = {
        "input_word": word,
        "normalized_word": normalized_word,
        "found": True,
        "entry_id": entry_id,
        "canonical_form": canonical_form,
        "decision": decision,
        "decision_reason": decision_reason,
        "variant_type": variant_type,
        "linked_canonical_form": linked_canonical_form,
        "is_separately_learner_worthy": is_separately_learner_worthy,
        "source_forms": source_forms,
        "needs_adjudication": needs_adjudication,
    }
    if candidate_forms is not None:
        payload["candidate_forms"] = list(candidate_forms)
    if ambiguity_reason is not None:
        payload["ambiguity_reason"] = ambiguity_reason
    return payload


def lookup_entry(snapshot_dir: Path, word: str) -> dict[str, Any] | None:
    normalized_word = normalize_word_candidate(word)
    if not normalized_word:
        return None

    entries = load_canonical_entries(snapshot_dir)
    variants = load_canonical_variants(snapshot_dir)
    ambiguous_forms = load_ambiguous_forms(snapshot_dir)
    entry_by_id = {entry.entry_id: entry for entry in entries}
    entry_by_form = {entry.canonical_form: entry for entry in entries}
    ambiguous_by_surface = {row.surface_form: row for row in ambiguous_forms}

    entry = entry_by_form.get(normalized_word)
    if entry is not None:
        return _lookup_payload(
            word=word,
            normalized_word=normalized_word,
            entry_id=entry.entry_id,
            canonical_form=entry.canonical_form,
            decision="direct_entry",
            decision_reason="word is already a canonical entry",
            variant_type="self",
            linked_canonical_form=entry.linked_canonical_form,
            is_separately_learner_worthy=True,
            source_forms=list(entry.source_forms or []),
        )

    matched_variant = next((variant for variant in variants if variant.surface_form == normalized_word), None)
    if matched_variant is None:
        matched_variant = next((variant for variant in variants if variant.canonical_form == normalized_word), None)

    if matched_variant is not None:
        entry = entry_by_id.get(matched_variant.entry_id) or entry_by_form.get(matched_variant.canonical_form)
        ambiguous_row = ambiguous_by_surface.get(matched_variant.surface_form)
        return _lookup_payload(
            word=word,
            normalized_word=normalized_word,
            entry_id=matched_variant.entry_id,
            canonical_form=matched_variant.canonical_form,
            decision=matched_variant.decision,
            decision_reason=matched_variant.decision_reason,
            variant_type=matched_variant.variant_type,
            linked_canonical_form=matched_variant.linked_canonical_form,
            is_separately_learner_worthy=matched_variant.is_separately_learner_worthy,
            source_forms=list(getattr(entry, "source_forms", []) or []),
            needs_adjudication=bool(matched_variant.needs_llm_adjudication),
            candidate_forms=list(ambiguous_row.candidate_forms) if ambiguous_row is not None else list(matched_variant.candidate_forms or []),
            ambiguity_reason=ambiguous_row.ambiguity_reason if ambiguous_row is not None else matched_variant.ambiguity_reason,
        )

    return {
        "input_word": word,
        "normalized_word": normalized_word,
        "found": False,
    }


def status_entry(
    snapshot_dir: Path,
    word: str,
    *,
    compiled_input: Path | None = None,
    db_lookup: DbLookup | None = None,
    language: str = "en",
) -> dict[str, Any] | None:
    lookup = lookup_entry(snapshot_dir, word)
    if not lookup or not lookup.get("found"):
        return lookup

    canonical_form = str(lookup["canonical_form"])

    lexemes_path = snapshot_dir / "lexemes.jsonl"
    senses_path = snapshot_dir / "senses.jsonl"
    enrichments_path = snapshot_dir / "enrichments.jsonl"

    lexemes = read_jsonl(lexemes_path) if lexemes_path.exists() else []
    senses = read_jsonl(senses_path) if senses_path.exists() else []
    enrichments = read_jsonl(enrichments_path) if enrichments_path.exists() else []

    lexeme = next((row for row in lexemes if row.get("lemma") == canonical_form), None)
    lexeme_id = lexeme.get("lexeme_id") if lexeme else None
    sense_ids = [row.get("sense_id") for row in senses if row.get("lexeme_id") == lexeme_id]
    enriched = any(row.get("sense_id") in sense_ids for row in enrichments)

    compiled = False
    compiled_path = compiled_input or (snapshot_dir / "words.enriched.jsonl")
    if compiled_path.exists():
        compiled = any(row.get("word") == canonical_form for row in read_jsonl(compiled_path))

    db_word = db_lookup(canonical_form, language) if db_lookup is not None else None

    return {
        **lookup,
        "base_built": lexeme is not None,
        "enriched": enriched,
        "compiled": compiled,
        "published": db_word is not None,
        "published_word": (db_word or {}).get("word"),
        "needs_adjudication": bool(lookup.get("needs_adjudication")),
        "candidate_forms": list(lookup.get("candidate_forms") or []),
        "ambiguity_reason": lookup.get("ambiguity_reason"),
    }
