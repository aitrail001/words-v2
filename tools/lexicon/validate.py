from __future__ import annotations

from pathlib import Path
from typing import Any

from tools.lexicon.jsonl_io import read_jsonl
from tools.lexicon.models import CompiledWordRecord, EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord

REQUIRED_COMPILED_FIELDS = [
    "schema_version",
    "word",
    "part_of_speech",
    "cefr_level",
    "frequency_rank",
    "forms",
    "senses",
    "confusable_words",
    "generated_at",
]


def validate_snapshot(
    lexemes: list[LexemeRecord],
    senses: list[SenseRecord],
    enrichments: list[EnrichmentRecord],
) -> list[str]:
    errors: list[str] = []
    lexeme_ids = {lexeme.lexeme_id for lexeme in lexemes}
    sense_ids = {sense.sense_id for sense in senses}
    duplicate_keys: set[tuple[str, str, str]] = set()

    for sense in senses:
        if sense.lexeme_id not in lexeme_ids:
            errors.append(f"sense {sense.sense_id} links missing lexeme {sense.lexeme_id}")
        duplicate_key = (sense.lexeme_id, sense.part_of_speech, sense.canonical_gloss.strip().lower())
        if duplicate_key in duplicate_keys:
            errors.append(
                f"duplicate sense for lexeme {sense.lexeme_id}: {sense.part_of_speech}|{sense.canonical_gloss.strip().lower()}"
            )
        duplicate_keys.add(duplicate_key)

    for enrichment in enrichments:
        if enrichment.sense_id not in sense_ids:
            errors.append(f"enrichment {enrichment.enrichment_id} links missing sense {enrichment.sense_id}")
        if not enrichment.examples:
            errors.append(f"enrichment {enrichment.enrichment_id} must include at least one example")

    return errors


def validate_compiled_record(record: CompiledWordRecord | dict[str, Any]) -> list[str]:
    payload = record.to_dict() if isinstance(record, CompiledWordRecord) else record
    errors: list[str] = []

    for field in REQUIRED_COMPILED_FIELDS:
        if field not in payload:
            errors.append(f"missing required field: {field}")

    senses = payload.get("senses", [])
    if isinstance(senses, list):
        for index, sense in enumerate(senses, start=1):
            examples = sense.get("examples", []) if isinstance(sense, dict) else []
            if not examples:
                errors.append(f"sense {index} must include at least one example")

    return errors



def validate_snapshot_files(snapshot_dir: Path) -> list[str]:
    lexemes = [LexemeRecord(**row) for row in read_jsonl(snapshot_dir / "lexemes.jsonl")]
    senses = [SenseRecord(**row) for row in read_jsonl(snapshot_dir / "senses.jsonl")]
    enrichments: list[EnrichmentRecord] = []
    enrichments_path = snapshot_dir / "enrichments.jsonl"
    if enrichments_path.exists():
        for row in read_jsonl(enrichments_path):
            row = dict(row)
            row["examples"] = [SenseExample(**example) for example in row.get("examples", [])]
            enrichments.append(EnrichmentRecord(**row))
    return validate_snapshot(lexemes=lexemes, senses=senses, enrichments=enrichments)
