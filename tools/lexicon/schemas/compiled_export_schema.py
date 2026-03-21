"""Compiled export schema helpers."""

from __future__ import annotations

from typing import Any


def build_compiled_export_schema() -> dict[str, Any]:
    return {
        "name": "lexicon_compiled_export_row",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "schema_version": {"type": "string"},
                "entry_id": {"type": "string"},
                "entry_type": {"type": "string"},
                "normalized_form": {"type": "string"},
                "source_provenance": {"type": "array", "items": {"type": "object"}},
                "entity_category": {"type": "string"},
                "word": {"type": "string"},
                "part_of_speech": {"type": "array", "items": {"type": "string"}},
                "cefr_level": {"type": "string"},
                "frequency_rank": {"type": "integer"},
                "forms": {"type": "object"},
                "senses": {"type": "array", "items": {"type": "object"}},
                "confusable_words": {"type": "array", "items": {"type": "object"}},
                "generated_at": {"type": "string"},
            },
            "required": [
                "schema_version",
                "entry_id",
                "entry_type",
                "normalized_form",
                "source_provenance",
                "entity_category",
                "word",
                "part_of_speech",
                "cefr_level",
                "frequency_rank",
                "forms",
                "senses",
                "confusable_words",
                "generated_at",
            ],
            "additionalProperties": False,
        },
    }
