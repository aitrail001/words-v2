from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.lexicon.review_materialize import materialize_review_outputs


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def _phonetics() -> dict[str, object]:
    return {
        "us": {"ipa": "/bæŋk/", "confidence": 0.99},
        "uk": {"ipa": "/bæŋk/", "confidence": 0.98},
        "au": {"ipa": "/bæŋk/", "confidence": 0.97},
    }


def _compiled_rows() -> list[dict]:
    return [
        {
            "schema_version": "1.1.0",
            "entry_id": "word:bank",
            "entry_type": "word",
            "normalized_form": "bank",
            "source_provenance": [{"source": "snapshot"}],
            "entity_category": "general",
            "word": "bank",
            "part_of_speech": ["noun"],
            "cefr_level": "B1",
            "frequency_rank": 100,
            "forms": {"plural_forms": ["banks"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [
                {
                    "sense_id": "sense-bank-1",
                    "definition": "a financial institution",
                    "examples": [{"sentence": "She went to the bank.", "difficulty": "easy"}],
                    "translations": {
                        "zh-Hans": {"definition": "银行", "usage_note": "常见词义", "examples": ["她去了银行。"]},
                        "es": {"definition": "banco", "usage_note": "uso comun", "examples": ["Ella fue al banco."]},
                        "ar": {"definition": "بنك", "usage_note": "معنى شائع", "examples": ["ذهبت إلى البنك."]},
                        "pt-BR": {"definition": "banco", "usage_note": "uso comum", "examples": ["Ela foi ao banco."]},
                        "ja": {"definition": "銀行", "usage_note": "よくある意味", "examples": ["彼女は銀行に行った。"]},
                    },
                }
            ],
            "confusable_words": [],
            "phonetics": _phonetics(),
            "generated_at": "2026-03-21T00:00:00Z",
        },
        {
            "schema_version": "1.1.0",
            "entry_id": "phrase:break-a-leg",
            "entry_type": "phrase",
            "normalized_form": "break a leg",
            "source_provenance": [{"source": "snapshot"}],
            "entity_category": "general",
            "word": "break a leg",
            "part_of_speech": ["idiom"],
            "cefr_level": "B1",
            "frequency_rank": 5000,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [{"sense_id": "phrase-1", "definition": "good luck", "examples": [{"sentence": "Break a leg tonight.", "difficulty": "easy"}]}],
            "confusable_words": [],
            "generated_at": "2026-03-21T00:00:00Z",
            "phrase_kind": "idiom",
            "display_form": "break a leg",
        },
        {
            "schema_version": "1.1.0",
            "entry_id": "rf_australia",
            "entry_type": "reference",
            "normalized_form": "australia",
            "source_provenance": [{"source": "reference_seed"}],
            "entity_category": "general",
            "word": "Australia",
            "part_of_speech": [],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [],
            "confusable_words": [],
            "generated_at": "2026-03-21T00:00:00Z",
            "reference_type": "country",
            "display_form": "Australia",
            "translation_mode": "localized",
            "brief_description": "A country in the Southern Hemisphere.",
            "pronunciation": "/ɔˈstreɪliə/",
            "localized_display_form": {"es": "Australia"},
            "localized_brief_description": {"es": "País del hemisferio sur."},
            "learner_tip": "Stress is on STRAY.",
            "localizations": [],
        },
    ]


def test_materialize_review_outputs_happy_path(tmp_path: Path) -> None:
    compiled_path = tmp_path / "compiled.jsonl"
    decisions_input_path = tmp_path / "review.decisions.input.jsonl"
    decisions_output_path = tmp_path / "review.decisions.jsonl"
    approved_path = tmp_path / "approved.jsonl"
    rejected_path = tmp_path / "rejected.jsonl"
    regenerate_path = tmp_path / "regenerate.jsonl"

    rows = _compiled_rows()
    _write_jsonl(compiled_path, rows)
    _write_jsonl(
        decisions_input_path,
        [
            {"entry_id": "word:bank", "entry_type": "word", "decision": "approved", "decision_reason": "ready"},
            {"entry_id": "phrase:break-a-leg", "entry_type": "phrase", "decision": "rejected", "decision_reason": "needs regen"},
            {"entry_id": "rf_australia", "entry_type": "reference", "decision": "approved", "decision_reason": "safe"},
        ],
    )

    summary = materialize_review_outputs(
        compiled_path=compiled_path,
        decisions_input_path=decisions_input_path,
        decisions_output_path=decisions_output_path,
        approved_output_path=approved_path,
        rejected_output_path=rejected_path,
        regenerate_output_path=regenerate_path,
    )

    assert summary["approved_count"] == 2
    assert summary["rejected_count"] == 1
    assert summary["regenerate_count"] == 1

    approved_rows = [json.loads(line) for line in approved_path.read_text(encoding="utf-8").splitlines()]
    rejected_rows = [json.loads(line) for line in rejected_path.read_text(encoding="utf-8").splitlines()]
    regenerate_rows = [json.loads(line) for line in regenerate_path.read_text(encoding="utf-8").splitlines()]
    decision_rows = [json.loads(line) for line in decisions_output_path.read_text(encoding="utf-8").splitlines()]

    assert approved_rows == [rows[0], rows[2]]
    assert rejected_rows[0]["entry_id"] == "phrase:break-a-leg"
    assert rejected_rows[0]["decision"] == "rejected"
    assert regenerate_rows[0]["entry_id"] == "phrase:break-a-leg"
    assert regenerate_rows[0]["entry_type"] == "phrase"
    assert len(decision_rows) == 3
    assert all(row["artifact_sha256"] for row in decision_rows)
    assert all(row["compiled_payload_sha256"] for row in decision_rows)


def test_materialize_review_outputs_rejects_duplicate_decisions(tmp_path: Path) -> None:
    compiled_path = tmp_path / "compiled.jsonl"
    _write_jsonl(compiled_path, _compiled_rows())

    with pytest.raises(ValueError, match="Duplicate review decision"):
        materialize_review_outputs(
            compiled_path=compiled_path,
            decisions=[
                {"entry_id": "word:bank", "entry_type": "word", "decision": "approved"},
                {"entry_id": "word:bank", "entry_type": "word", "decision": "rejected"},
            ],
        )


def test_materialize_review_outputs_rejects_unknown_entry_ids(tmp_path: Path) -> None:
    compiled_path = tmp_path / "compiled.jsonl"
    _write_jsonl(compiled_path, _compiled_rows())

    with pytest.raises(ValueError, match="Unknown review decision entry_id"):
        materialize_review_outputs(
            compiled_path=compiled_path,
            decisions=[{"entry_id": "word:missing", "entry_type": "word", "decision": "approved"}],
        )


def test_materialize_review_outputs_rejects_mixed_artifact_hashes(tmp_path: Path) -> None:
    compiled_path = tmp_path / "compiled.jsonl"
    _write_jsonl(compiled_path, _compiled_rows())

    with pytest.raises(ValueError, match="mixed artifact_sha256"):
        materialize_review_outputs(
            compiled_path=compiled_path,
            decisions=[
                {"entry_id": "word:bank", "entry_type": "word", "decision": "approved", "artifact_sha256": "a" * 64},
                {"entry_id": "phrase:break-a-leg", "entry_type": "phrase", "decision": "rejected", "artifact_sha256": "b" * 64},
            ],
        )


def test_materialize_review_outputs_rejects_missing_full_batch_decisions(tmp_path: Path) -> None:
    compiled_path = tmp_path / "compiled.jsonl"
    _write_jsonl(compiled_path, _compiled_rows())

    with pytest.raises(ValueError, match="Missing review decisions"):
        materialize_review_outputs(
            compiled_path=compiled_path,
            decisions=[{"entry_id": "word:bank", "entry_type": "word", "decision": "approved"}],
        )
