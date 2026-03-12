from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from tools.lexicon.jsonl_io import read_jsonl
from tools.lexicon.models import CanonicalEntryRecord, CanonicalVariantRecord
from tools.lexicon.wordfreq_utils import normalize_word_candidate

DbLookup = Callable[[str, str], dict[str, Any] | None]


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


def lookup_entry(snapshot_dir: Path, word: str) -> dict[str, Any] | None:
    normalized_word = normalize_word_candidate(word)
    if not normalized_word:
        return None

    entries = load_canonical_entries(snapshot_dir)
    variants = load_canonical_variants(snapshot_dir)
    entry_by_id = {entry.entry_id: entry for entry in entries}
    entry_by_form = {entry.canonical_form: entry for entry in entries}

    matched_variant = next(
        (
            variant
            for variant in variants
            if variant.surface_form == normalized_word or variant.canonical_form == normalized_word
        ),
        None,
    )

    if matched_variant is not None:
        entry = entry_by_id.get(matched_variant.entry_id) or entry_by_form.get(matched_variant.canonical_form)
        return {
            "input_word": word,
            "normalized_word": normalized_word,
            "found": True,
            "entry_id": matched_variant.entry_id,
            "canonical_form": matched_variant.canonical_form,
            "decision": matched_variant.decision,
            "decision_reason": matched_variant.decision_reason,
            "variant_type": matched_variant.variant_type,
            "linked_canonical_form": matched_variant.linked_canonical_form,
            "is_separately_learner_worthy": matched_variant.is_separately_learner_worthy,
            "source_forms": list(getattr(entry, "source_forms", []) or []),
        }

    entry = entry_by_form.get(normalized_word)
    if entry is None:
        return {
            "input_word": word,
            "normalized_word": normalized_word,
            "found": False,
        }

    return {
        "input_word": word,
        "normalized_word": normalized_word,
        "found": True,
        "entry_id": entry.entry_id,
        "canonical_form": entry.canonical_form,
        "decision": "direct_entry",
        "decision_reason": "word is already a canonical entry",
        "variant_type": "self",
        "linked_canonical_form": entry.linked_canonical_form,
        "is_separately_learner_worthy": True,
        "source_forms": list(entry.source_forms or []),
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
    }
