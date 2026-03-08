from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import CompiledWordRecord, EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord


COMPILED_SCHEMA_VERSION = "1.1.0"


def compile_words(
    lexemes: list[LexemeRecord],
    senses: list[SenseRecord],
    enrichments: list[EnrichmentRecord],
) -> list[CompiledWordRecord]:
    senses_by_lexeme: dict[str, list[SenseRecord]] = defaultdict(list)
    for sense in senses:
        senses_by_lexeme[sense.lexeme_id].append(sense)

    enrichments_by_sense: dict[str, list[EnrichmentRecord]] = defaultdict(list)
    for enrichment in enrichments:
        enrichments_by_sense[enrichment.sense_id].append(enrichment)

    compiled: list[CompiledWordRecord] = []
    for lexeme in lexemes:
        ordered_senses = sorted(senses_by_lexeme.get(lexeme.lexeme_id, []), key=lambda item: item.sense_order)
        compiled_senses: list[dict] = []
        top_level_pos: list[str] = []
        top_level_forms = None
        top_level_confusables = None
        top_level_cefr = None
        generated_at = None

        for sense in ordered_senses:
            candidates = enrichments_by_sense.get(sense.sense_id, [])
            if not candidates:
                continue
            enrichment = sorted(candidates, key=lambda item: (-item.confidence, item.generated_at))[0]
            if sense.part_of_speech not in top_level_pos:
                top_level_pos.append(sense.part_of_speech)
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
                    "sense_id": sense.sense_id,
                    "wn_synset_id": sense.wn_synset_id,
                    "pos": sense.part_of_speech,
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
                }
            )

        if not compiled_senses:
            continue

        compiled.append(
            CompiledWordRecord(
                schema_version=COMPILED_SCHEMA_VERSION,
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


def compile_snapshot(snapshot_dir: Path, output_path: Path) -> list[CompiledWordRecord]:
    lexemes = _load_lexemes(snapshot_dir / "lexemes.jsonl")
    senses = _load_senses(snapshot_dir / "senses.jsonl")
    enrichments = _load_enrichments(snapshot_dir / "enrichments.jsonl")
    compiled = compile_words(lexemes, senses, enrichments)
    write_jsonl(output_path, [record.to_dict() for record in compiled])
    return compiled
