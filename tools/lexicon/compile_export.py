from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import CompiledWordRecord, EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord


COMPILED_SCHEMA_VERSION = "1.1.0"
_ALLOWED_DECISION_FILTERS = {"mode_c_safe"}


def compile_words(
    lexemes: list[LexemeRecord],
    senses: list[SenseRecord],
    enrichments: list[EnrichmentRecord],
) -> list[CompiledWordRecord]:
    senses_by_lexeme: dict[str, list[SenseRecord]] = defaultdict(list)
    sense_by_id: dict[str, SenseRecord] = {}
    for sense in senses:
        senses_by_lexeme[sense.lexeme_id].append(sense)
        sense_by_id[sense.sense_id] = sense

    enrichments_by_lexeme: dict[str, list[EnrichmentRecord]] = defaultdict(list)
    for enrichment in enrichments:
        source_sense = sense_by_id.get(enrichment.sense_id)
        lexeme_id = enrichment.lexeme_id or (source_sense.lexeme_id if source_sense is not None else None)
        if lexeme_id:
            enrichments_by_lexeme[lexeme_id].append(enrichment)

    compiled: list[CompiledWordRecord] = []
    for lexeme in lexemes:
        ordered_enrichments = sorted(
            enrichments_by_lexeme.get(lexeme.lexeme_id, []),
            key=lambda item: (item.sense_order, item.sense_id),
        )
        compiled_senses: list[dict] = []
        top_level_pos: list[str] = []
        top_level_forms = None
        top_level_confusables = None
        top_level_cefr = None
        generated_at = None

        for enrichment in ordered_enrichments:
            source_sense = sense_by_id.get(enrichment.sense_id)
            part_of_speech = enrichment.part_of_speech or (source_sense.part_of_speech if source_sense is not None else None)
            if part_of_speech and part_of_speech not in top_level_pos:
                top_level_pos.append(part_of_speech)
            if top_level_forms is None:
                top_level_forms = enrichment.forms
            if top_level_confusables is None:
                top_level_confusables = enrichment.confusable_words
            if top_level_cefr is None:
                top_level_cefr = enrichment.cefr_level
            if generated_at is None:
                generated_at = enrichment.generated_at
            compiled_senses.append(
                {
                    "sense_id": enrichment.sense_id,
                    "wn_synset_id": source_sense.wn_synset_id if source_sense is not None else None,
                    "pos": part_of_speech,
                    "sense_kind": enrichment.sense_kind,
                    "decision": enrichment.decision,
                    "base_word": enrichment.base_word,
                    "primary_domain": enrichment.primary_domain,
                    "secondary_domains": enrichment.secondary_domains,
                    "register": enrichment.register,
                    "definition": enrichment.definition,
                    "examples": [example.to_dict() for example in enrichment.examples],
                    "synonyms": enrichment.synonyms,
                    "antonyms": enrichment.antonyms,
                    "collocations": enrichment.collocations,
                    "grammar_patterns": enrichment.grammar_patterns,
                    "usage_note": enrichment.usage_note,
                    "enrichment_id": enrichment.enrichment_id,
                    "generation_run_id": enrichment.generation_run_id,
                    "model_name": enrichment.model_name,
                    "prompt_version": enrichment.prompt_version,
                    "confidence": enrichment.confidence,
                    "generated_at": enrichment.generated_at,
                    "translations": enrichment.translations or {},
                }
            )

        if not compiled_senses:
            continue

        compiled.append(
            CompiledWordRecord(
                schema_version=COMPILED_SCHEMA_VERSION,
                entry_id=lexeme.entry_id,
                entry_type=lexeme.entry_type,
                normalized_form=lexeme.normalized_form,
                source_provenance=lexeme.source_provenance,
                entity_category=lexeme.entity_category,
                word=lexeme.lemma,
                part_of_speech=top_level_pos,
                cefr_level=top_level_cefr or "B1",
                frequency_rank=lexeme.wordfreq_rank,
                forms=top_level_forms or {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                senses=compiled_senses,
                confusable_words=top_level_confusables or [],
                generated_at=generated_at or lexeme.created_at,
            )
        )

    return compiled


def _load_lexemes(path: Path) -> list[LexemeRecord]:
    return [LexemeRecord(**row) for row in read_jsonl(path)]


def _load_senses(path: Path) -> list[SenseRecord]:
    return [SenseRecord(**row) for row in read_jsonl(path)]


def _load_enrichments(path: Path) -> list[EnrichmentRecord]:
    records: list[EnrichmentRecord] = []
    for row in read_jsonl(path):
        examples = [SenseExample(**example) for example in row.get("examples", [])]
        row = dict(row)
        row["examples"] = examples
        records.append(EnrichmentRecord(**row))
    return records


def _load_decisions(path: Path) -> list[dict[str, object]]:
    return [dict(row) for row in read_jsonl(path)]


def _coerce_decision_bool(value: object, *, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"", "0", "false", "no", "n", "off"}:
            return False
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
    raise ValueError(f"Selection decision field '{field_name}' must be a boolean-like value")


def _allowed_lexeme_ids_from_decisions(
    decisions: list[dict[str, object]],
    *,
    decision_filter: str,
    snapshot_lexeme_ids: set[str],
) -> set[str]:
    if decision_filter not in _ALLOWED_DECISION_FILTERS:
        raise ValueError(f"Unsupported decision filter: {decision_filter}")

    decision_lexeme_ids = {str(row.get("lexeme_id") or "") for row in decisions}
    unknown = sorted(lexeme_id for lexeme_id in decision_lexeme_ids if lexeme_id and lexeme_id not in snapshot_lexeme_ids)
    if unknown:
        raise ValueError(f"Selection decisions reference lexeme_ids not present in snapshot: {unknown[:10]}")

    if decision_filter == "mode_c_safe":
        allowed: set[str] = set()
        for row in decisions:
            lexeme_id = str(row.get("lexeme_id") or "")
            if not lexeme_id:
                continue
            risk_band = str(row.get("risk_band") or "")
            auto_accepted = _coerce_decision_bool(row.get("auto_accepted"), field_name="auto_accepted")
            review_required = _coerce_decision_bool(row.get("review_required"), field_name="review_required")
            if review_required:
                continue
            if risk_band == "deterministic_only" or auto_accepted:
                allowed.add(lexeme_id)
        return allowed

    raise ValueError(f"Unsupported decision filter: {decision_filter}")


def compile_snapshot(
    snapshot_dir: Path,
    output_path: Path,
    *,
    decisions_path: Path | None = None,
    decision_filter: str | None = None,
) -> list[CompiledWordRecord]:
    lexemes = _load_lexemes(snapshot_dir / "lexemes.jsonl")
    senses = _load_senses(snapshot_dir / "senses.jsonl")
    enrichments = _load_enrichments(snapshot_dir / "enrichments.jsonl")

    if decisions_path is not None and decision_filter is None:
        raise ValueError("--decisions requires --decision-filter")

    if decision_filter is not None:
        if decisions_path is None:
            raise ValueError("--decision-filter requires --decisions")
        decisions = _load_decisions(decisions_path)
        allowed_lexeme_ids = _allowed_lexeme_ids_from_decisions(
            decisions,
            decision_filter=decision_filter,
            snapshot_lexeme_ids={lexeme.lexeme_id for lexeme in lexemes},
        )
        if not allowed_lexeme_ids:
            raise ValueError(f"Decision filter '{decision_filter}' produced zero lexemes")
        lexemes = [lexeme for lexeme in lexemes if lexeme.lexeme_id in allowed_lexeme_ids]
        allowed_sense_ids = {sense.sense_id for sense in senses if sense.lexeme_id in allowed_lexeme_ids}
        senses = [sense for sense in senses if sense.lexeme_id in allowed_lexeme_ids]
        enrichments = [enrichment for enrichment in enrichments if enrichment.sense_id in allowed_sense_ids]

    compiled = compile_words(lexemes, senses, enrichments)
    write_jsonl(output_path, [record.to_dict() for record in compiled])
    return compiled
