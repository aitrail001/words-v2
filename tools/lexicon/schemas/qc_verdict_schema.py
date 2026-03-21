"""QC verdict schema helpers."""

from __future__ import annotations

from typing import Any

from tools.lexicon.contracts import ALLOWED_QC_VERDICTS


def build_qc_verdict_schema() -> dict[str, Any]:
    return {
        "name": "lexicon_qc_verdict",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "entry_kind": {"type": "string", "enum": ["word", "phrase", "reference"]},
                "verdict": {"type": "string", "enum": sorted(ALLOWED_QC_VERDICTS)},
                "confidence": {"type": "number"},
                "reasons": {"type": "array", "items": {"type": "string"}},
                "review_notes": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "model_name": {"anyOf": [{"type": "string"}, {"type": "null"}]},
                "prompt_version": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            },
            "required": [
                "entry_kind",
                "verdict",
                "confidence",
                "reasons",
                "review_notes",
                "model_name",
                "prompt_version",
            ],
            "additionalProperties": False,
        },
    }
