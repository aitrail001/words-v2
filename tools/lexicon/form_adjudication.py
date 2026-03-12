from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import json
import uuid

from tools.lexicon.config import LexiconSettings
from tools.lexicon.enrich import (
    NodeOpenAICompatibleResponsesClient,
    OpenAICompatibleResponsesClient,
    _default_node_runner,
    _default_transport,
)
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import AmbiguousFormRecord, FormAdjudicationRecord
from tools.lexicon.wordfreq_utils import normalize_word_candidate

_ALLOWED_ACTIONS = {"collapse_to_canonical", "keep_separate", "keep_both_linked"}
_PROVIDER_MODES = {"auto", "placeholder", "openai_compatible", "openai_compatible_node"}
_PROMPT_VERSION = "canonical-form-adjudication-v1"


@dataclass(frozen=True)
class AdjudicationRunResult:
    output_path: Path
    rows: list[FormAdjudicationRecord]


def validate_adjudication_row(row: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(row, dict):
        raise RuntimeError("Adjudication row must be an object")

    surface_form = normalize_word_candidate(str(row.get("surface_form") or ""))
    if not surface_form:
        raise RuntimeError("Adjudication row surface_form must be a non-empty normalized word")

    candidate_forms = [
        candidate
        for candidate in (
            normalize_word_candidate(str(item or ""))
            for item in (row.get("candidate_forms") or [])
        )
        if candidate
    ]
    selected_action = str(row.get("selected_action") or "").strip()
    if selected_action not in _ALLOWED_ACTIONS:
        raise RuntimeError(f"Adjudication row for {surface_form} must use a valid selected_action")

    selected_canonical_form = normalize_word_candidate(str(row.get("selected_canonical_form") or ""))
    if not selected_canonical_form or (selected_canonical_form != surface_form and selected_canonical_form not in candidate_forms):
        raise RuntimeError(
            f"Adjudication row for {surface_form} selected_canonical_form must be the surface form or one of the candidate_forms"
        )

    linked_raw = row.get("selected_linked_canonical_form")
    linked_canonical_form = normalize_word_candidate(str(linked_raw)) if linked_raw else None
    if linked_canonical_form and linked_canonical_form not in candidate_forms:
        raise RuntimeError(
            f"Adjudication row for {surface_form} selected_linked_canonical_form must be null or one of the candidate_forms"
        )

    confidence = float(row.get("confidence") or 0.0)
    if confidence < 0 or confidence > 1:
        raise RuntimeError(f"Adjudication row for {surface_form} confidence must be between 0 and 1")

    return {
        "surface_form": surface_form,
        "candidate_forms": candidate_forms,
        "selected_action": selected_action,
        "selected_canonical_form": selected_canonical_form,
        "selected_linked_canonical_form": linked_canonical_form,
        "confidence": confidence,
        "adjudication_reason": str(row.get("adjudication_reason") or "").strip(),
        "model_name": str(row.get("model_name") or "").strip(),
        "prompt_version": str(row.get("prompt_version") or _PROMPT_VERSION),
        "generation_run_id": str(row.get("generation_run_id") or "").strip(),
    }


def load_adjudications(path: str | Path) -> dict[str, dict[str, Any]]:
    rows = [validate_adjudication_row(dict(row)) for row in read_jsonl(Path(path))]
    return {row["surface_form"]: row for row in rows}


def load_ambiguous_forms(path: str | Path) -> list[AmbiguousFormRecord]:
    return [AmbiguousFormRecord(**row) for row in read_jsonl(Path(path))]


def _build_prompt(row: AmbiguousFormRecord) -> str:
    schema_hint = {
        "selected_action": "collapse_to_canonical|keep_separate|keep_both_linked",
        "selected_canonical_form": "surface_form or one of candidate_forms",
        "selected_linked_canonical_form": "string|null",
        "adjudication_reason": "string",
        "confidence": "number",
    }
    payload = {
        "surface_form": row.surface_form,
        "deterministic_decision": row.deterministic_decision,
        "canonical_form": row.canonical_form,
        "linked_canonical_form": row.linked_canonical_form,
        "candidate_forms": row.candidate_forms,
        "decision_reason": row.decision_reason,
        "wordfreq_rank": row.wordfreq_rank,
        "sense_labels": row.sense_labels,
        "ambiguity_reason": row.ambiguity_reason,
    }
    return (
        f"Adjudicate the canonical form for the English surface form '{row.surface_form}'.\n"
        f"Use only this bounded evidence: {json.dumps(payload)}\n"
        "You must choose only among the provided candidate_forms or keep the surface form itself.\n"
        "Do not invent any new lemma or linked target.\n"
        f"Return JSON only with this schema: {json.dumps(schema_hint)}"
    )


def _client_for_mode(*, settings: LexiconSettings, provider_mode: str, model_name: str | None, reasoning_effort: str | None):
    mode = provider_mode
    if mode == "auto":
        mode = "openai_compatible_node" if settings.llm_transport == "node" else "openai_compatible"
    effective_model = model_name or settings.llm_model
    if mode == "placeholder":
        return None
    if not settings.llm_base_url:
        raise LexiconDependencyError("LEXICON_LLM_BASE_URL is required for adjudicate-forms")
    if not effective_model:
        raise LexiconDependencyError("LEXICON_LLM_MODEL is required for adjudicate-forms")
    if not settings.llm_api_key:
        raise LexiconDependencyError("LEXICON_LLM_API_KEY is required for adjudicate-forms")
    if mode == "openai_compatible_node":
        return NodeOpenAICompatibleResponsesClient(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=str(effective_model),
            runner=_default_node_runner,
            reasoning_effort=reasoning_effort or settings.llm_reasoning_effort,
        )
    if mode == "openai_compatible":
        return OpenAICompatibleResponsesClient(
            endpoint=settings.llm_base_url,
            api_key=settings.llm_api_key,
            model=str(effective_model),
            transport=_default_transport,
            reasoning_effort=reasoning_effort or settings.llm_reasoning_effort,
        )
    raise ValueError(f"Unsupported provider mode: {provider_mode}")


def _placeholder_adjudication(row: AmbiguousFormRecord) -> dict[str, Any]:
    preferred_candidate = row.candidate_forms[0] if row.candidate_forms else row.surface_form
    return {
        "surface_form": row.surface_form,
        "candidate_forms": list(row.candidate_forms),
        "selected_action": "collapse_to_canonical" if row.candidate_forms else "keep_separate",
        "selected_canonical_form": preferred_candidate if row.candidate_forms else row.surface_form,
        "selected_linked_canonical_form": None,
        "confidence": 0.6,
        "adjudication_reason": "placeholder adjudicator chose the first candidate form",
    }


def adjudicate_forms(
    input_path: str | Path,
    *,
    output_path: str | Path,
    provider_mode: str = "auto",
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    settings: LexiconSettings | None = None,
) -> AdjudicationRunResult:
    if provider_mode not in _PROVIDER_MODES:
        raise ValueError(f"Unsupported provider mode: {provider_mode}")

    ambiguous_rows = load_ambiguous_forms(input_path)
    effective_settings = settings or LexiconSettings.from_env()
    client = _client_for_mode(settings=effective_settings, provider_mode=provider_mode, model_name=model_name, reasoning_effort=reasoning_effort)
    effective_model = str(model_name or effective_settings.llm_model or "placeholder-adjudicator")

    output_records: list[FormAdjudicationRecord] = []
    for row in ambiguous_rows:
        if client is None:
            payload = _placeholder_adjudication(row)
        else:
            response = client.generate_json(_build_prompt(row))
            payload = dict(response)
            payload["surface_form"] = row.surface_form
            payload["candidate_forms"] = list(row.candidate_forms)
        validated = validate_adjudication_row(payload)
        generation_run_id = validated["generation_run_id"] or f"adj-{uuid.uuid4()}"
        output_records.append(
            FormAdjudicationRecord(
                surface_form=validated["surface_form"],
                selected_action=validated["selected_action"],
                selected_canonical_form=validated["selected_canonical_form"],
                selected_linked_canonical_form=validated["selected_linked_canonical_form"],
                candidate_forms=validated["candidate_forms"],
                model_name=validated["model_name"] or effective_model,
                prompt_version=validated["prompt_version"] or _PROMPT_VERSION,
                generation_run_id=generation_run_id,
                confidence=validated["confidence"],
                adjudication_reason=validated["adjudication_reason"],
            )
        )

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_jsonl(output_path, [record.to_dict() for record in output_records])
    return AdjudicationRunResult(output_path=output_path, rows=output_records)
