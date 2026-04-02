from __future__ import annotations

import atexit
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any, Callable
import json
import math
import select
import shutil
import subprocess
import sys
import time

from tools.lexicon.compile_export import compile_word_result
from tools.lexicon.contracts import ALLOWED_CEFR_LEVELS, ALLOWED_REGISTERS, REQUIRED_TRANSLATION_LOCALES
from tools.lexicon.config import LexiconSettings
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.ids import make_enrichment_id, make_sense_id
from tools.lexicon.jsonl_io import append_jsonl, read_jsonl, write_jsonl
from tools.lexicon.models import EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord
from tools.lexicon.review_prep import build_review_prep_rows
from tools.lexicon.runtime_logging import RuntimeLogConfig, RuntimeLogger
from tools.lexicon.schemas.word_enrichment_schema import (
    build_single_sense_response_schema as _build_single_sense_response_schema,
    build_word_enrichment_response_schema as _build_word_enrichment_response_schema,
    normalize_phonetics_payload as _normalize_phonetics_payload,
    normalize_word_enrichment_payload as _normalize_word_enrichment_payload,
)
from tools.lexicon.schemas.phrase_enrichment_schema import (
    build_phrase_enrichment_response_schema as _build_phrase_enrichment_response_schema,
    normalize_phrase_enrichment_payload as _normalize_phrase_enrichment_payload,
)
try:
    from openai import OpenAI
except ImportError:  # pragma: no cover
    OpenAI = None

EnrichmentProvider = Callable[..., EnrichmentRecord]
Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
NodeRunner = Callable[[dict[str, Any]], dict[str, Any]]
_PROVIDER_MODES = {"auto", "placeholder", "openai_compatible", "openai_compatible_node"}
_WORD_PROMPT_MODES = {"grounded", "word_only"}
_ALLOWED_CEFR_LEVELS = set(ALLOWED_CEFR_LEVELS)
_ALLOWED_REGISTERS = set(ALLOWED_REGISTERS)
_STRING_LIST_FIELDS = ('secondary_domains', 'synonyms', 'antonyms', 'collocations', 'grammar_patterns')
_REQUIRED_TRANSLATION_LOCALES = tuple(REQUIRED_TRANSLATION_LOCALES)
_DEFAULT_LLM_TIMEOUT_SECONDS = 60
_DEFAULT_WORD_TRANSIENT_RETRIES = 2
_DEFAULT_WORD_REPAIR_ATTEMPTS = 1
_NODE_RUN_TIMEOUT_SECONDS = _DEFAULT_LLM_TIMEOUT_SECONDS
_WORD_DECISIONS = {"discard", "keep_standard", "keep_derived_special"}
_WORD_SENSE_KINDS = {"standard_meaning", "base_form_reference", "special_meaning"}
_DEFAULT_RUNTIME_LOG_FILE = "enrich.log"


def _validate_resume_mode_flags(*, resume: bool, retry_failed_only: bool, skip_failed: bool) -> None:
    if retry_failed_only and skip_failed:
        raise ValueError('retry_failed_only and skip_failed cannot be used together')
    if (retry_failed_only or skip_failed) and not resume:
        raise ValueError('retry_failed_only and skip_failed require resume=True')


@dataclass(frozen=True)
class EnrichmentRunResult:
    output_path: Path
    enrichments: list[EnrichmentRecord]
    lexeme_count: int = 0
    mode: str = "per_word"


@dataclass(frozen=True)
class WordJobOutcome:
    records: list[EnrichmentRecord]
    decision: str
    base_word: str | None = None
    discard_reason: str | None = None
    phonetics: dict[str, dict[str, Any]] | None = None

    def __iter__(self):
        return iter(self.records)

    def __len__(self) -> int:
        return len(self.records)

    def __bool__(self) -> bool:
        return bool(self.records)


WordEnrichmentProvider = Callable[..., WordJobOutcome | list[EnrichmentRecord]]


class OpenAICompatibleResponsesClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        transport: Transport | None = None,
        client: Any | None = None,
        timeout_seconds: int = 60,
        reasoning_effort: str | None = None,
    ) -> None:
        if client is None and transport is None:
            if OpenAI is None:
                raise LexiconDependencyError('The Python openai package is required for openai_compatible enrichment mode')
            client = OpenAI(
                api_key=api_key,
                base_url=endpoint.rstrip("/"),
                timeout=timeout_seconds,
            )
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.client = client
        self.reasoning_effort = reasoning_effort

    def responses_url(self) -> str:
        if self.endpoint.endswith("/responses"):
            return self.endpoint
        return f"{self.endpoint}/responses"

    def generate_json(self, prompt: str, *, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "instructions": _SYSTEM_PROMPT,
            "input": prompt,
            "text": {"format": _response_text_format(response_schema)},
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self.transport is not None:
                response = self.transport(self.responses_url(), payload, headers)
            else:
                response = self.client.responses.create(**payload)
        except Exception as exc:  # pragma: no cover - SDK exception types vary
            raise RuntimeError(str(exc)) from exc
        text = _extract_output_text(response)
        try:
            return _parse_json_payload_text(text)
        except RuntimeError as exc:
            raise RuntimeError("OpenAI-compatible endpoint returned non-JSON enrichment output") from exc


def _default_node_runner(payload: dict[str, Any], *, timeout_seconds: int = _NODE_RUN_TIMEOUT_SECONDS) -> dict[str, Any]:
    node_bin = shutil.which('node')
    if not node_bin:
        raise LexiconDependencyError('Node.js is required for openai_compatible_node enrichment mode')

    script_path = Path(__file__).resolve().parent / 'node' / 'openai_compatible_responses.mjs'
    if not script_path.exists():
        raise LexiconDependencyError(f'Node enrichment script is missing: {script_path}')

    try:
        completed = subprocess.run(
            [node_bin, str(script_path)],
            input=json.dumps(payload),
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f'Node OpenAI-compatible transport timed out after {timeout_seconds} seconds'
        ) from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or 'Node OpenAI-compatible transport failed'
        raise RuntimeError(message)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Node OpenAI-compatible transport returned non-JSON output') from exc


class _PersistentNodeRunner:
    def __init__(self, *, timeout_seconds: int = _NODE_RUN_TIMEOUT_SECONDS) -> None:
        self.timeout_seconds = timeout_seconds
        self._lock = Lock()
        self._request_ids = count(1)
        self._process: subprocess.Popen[str] | None = None
        atexit.register(self.close)

    def _start_process(self) -> subprocess.Popen[str]:
        node_bin = shutil.which('node')
        if not node_bin:
            raise LexiconDependencyError('Node.js is required for openai_compatible_node enrichment mode')

        script_path = Path(__file__).resolve().parent / 'node' / 'openai_compatible_responses.mjs'
        if not script_path.exists():
            raise LexiconDependencyError(f'Node enrichment script is missing: {script_path}')

        self._process = subprocess.Popen(
            [node_bin, str(script_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        return self._process

    def _ensure_process(self) -> subprocess.Popen[str]:
        if self._process is not None and self._process.poll() is None:
            return self._process
        self.close()
        return self._start_process()

    def _read_response_line(self, process: subprocess.Popen[str], *, request_id: str) -> str:
        stdout = process.stdout
        if stdout is None:
            raise RuntimeError('Node OpenAI-compatible transport is missing stdout')
        deadline = time.monotonic() + self.timeout_seconds
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.close()
                raise RuntimeError(f'Node OpenAI-compatible transport timed out after {self.timeout_seconds} seconds')
            ready, _, _ = select.select([stdout], [], [], remaining)
            if not ready:
                continue
            line = stdout.readline()
            if line:
                return line
            stderr_output = ''
            if process.stderr is not None:
                stderr_output = process.stderr.read().strip()
            self.close()
            raise RuntimeError(
                stderr_output
                or f'Node OpenAI-compatible transport exited before returning a response for request {request_id}'
            )

    def __call__(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            process = self._ensure_process()
            stdin = process.stdin
            if stdin is None:
                self.close()
                raise RuntimeError('Node OpenAI-compatible transport is missing stdin')

            request_id = str(next(self._request_ids))
            message = dict(payload)
            message['request_id'] = request_id

            try:
                stdin.write(json.dumps(message) + '\n')
                stdin.flush()
            except BrokenPipeError as exc:
                self.close()
                raise RuntimeError('Node OpenAI-compatible transport failed while writing request payload') from exc

            raw_line = self._read_response_line(process, request_id=request_id).strip()
            try:
                envelope = json.loads(raw_line)
            except json.JSONDecodeError as exc:
                self.close()
                raise RuntimeError('Node OpenAI-compatible transport returned non-JSON output') from exc

            if envelope.get('request_id') != request_id:
                raise RuntimeError(
                    f"Node OpenAI-compatible transport response ID mismatch: expected {request_id}, got {envelope.get('request_id')!r}"
                )
            if not envelope.get('ok'):
                raise RuntimeError(str(envelope.get('error') or 'Node OpenAI-compatible transport failed'))
            response = envelope.get('response')
            if not isinstance(response, dict):
                raise RuntimeError('Node OpenAI-compatible transport returned a non-object response envelope')
            return response

    def close(self) -> None:
        process, self._process = self._process, None
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        if process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if process.stdout is not None:
            process.stdout.close()
        if process.stderr is not None:
            process.stderr.close()


class NodeOpenAICompatibleResponsesClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        runner: NodeRunner | None = None,
        timeout_seconds: int = _NODE_RUN_TIMEOUT_SECONDS,
        reasoning_effort: str | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.runner = runner or _PersistentNodeRunner(timeout_seconds=self.timeout_seconds)
        self.reasoning_effort = reasoning_effort

    def generate_json(self, prompt: str, *, response_schema: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {
            'base_url': self.endpoint,
            'api_key': self.api_key,
            'model': self.model,
            'prompt': prompt,
            'system_prompt': _SYSTEM_PROMPT,
        }
        if self.reasoning_effort:
            payload['reasoning_effort'] = self.reasoning_effort
        if response_schema is not None:
            payload['response_schema'] = response_schema
        response = self.runner(payload)
        text = _extract_output_text(response)
        try:
            return _parse_json_payload_text(text)
        except RuntimeError as exc:
            raise RuntimeError('OpenAI-compatible node endpoint returned non-JSON enrichment output') from exc


_SYSTEM_PROMPT = (
    "You are enriching English vocabulary records for learners. "
    "Return only a single JSON object matching the requested schema."
)


def _response_text_format(response_schema: dict[str, Any] | None) -> dict[str, Any]:
    if response_schema is None:
        return {"type": "json_object"}
    return {
        "type": "json_schema",
        "name": str(response_schema["name"]),
        "schema": response_schema["schema"],
        "strict": bool(response_schema.get("strict", True)),
    }


def _client_generate_json(
    client: OpenAICompatibleResponsesClient | NodeOpenAICompatibleResponsesClient | Any,
    prompt: str,
    *,
    response_schema: dict[str, Any] | None = None,
    reasoning_effort_override: str | None = None,
) -> dict[str, Any]:
    def call_client() -> dict[str, Any]:
        try:
            return client.generate_json(prompt, response_schema=response_schema)
        except TypeError as exc:
            if "response_schema" not in str(exc):
                raise
            return client.generate_json(prompt)

    if reasoning_effort_override is None or not hasattr(client, "reasoning_effort"):
        return call_client()

    original_reasoning_effort = getattr(client, "reasoning_effort")
    setattr(client, "reasoning_effort", reasoning_effort_override)
    try:
        return call_client()
    finally:
        setattr(client, "reasoning_effort", original_reasoning_effort)


def _validation_retry_reasoning_effort(client: Any) -> str | None:
    current_effort = str(getattr(client, "reasoning_effort", "") or "").strip().lower()
    if current_effort in {"", "none"}:
        return "low"
    return None


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _default_forms(lemma: str, part_of_speech: str) -> dict[str, Any]:
    verb_forms: dict[str, str] = {}
    if part_of_speech == 'verb':
        verb_forms = {
            'base': lemma,
            'third_person_singular': '',
            'past': '',
            'past_participle': '',
            'gerund': '',
        }
    return {
        'plural_forms': [],
        'verb_forms': verb_forms,
        'comparative': None,
        'superlative': None,
        'derivations': [],
    }


def _default_example(lemma: str, part_of_speech: str) -> str:
    if part_of_speech == 'verb':
        return f'I {lemma} every day.'
    if part_of_speech == 'adjective':
        return f'This example is very {lemma}.'
    if part_of_speech == 'adverb':
        return f'She speaks {lemma} in class.'
    return f'This {lemma} is useful for learners.'


def _default_phonetics(lemma: str) -> dict[str, dict[str, Any]]:
    ipa = f'/{lemma}/'
    return {
        'us': {'ipa': ipa, 'confidence': 0.5},
        'uk': {'ipa': ipa, 'confidence': 0.5},
        'au': {'ipa': ipa, 'confidence': 0.5},
    }


def _variant_prompt_guidance(lexeme: LexemeRecord) -> str:
    if not lexeme.is_variant_with_distinct_meanings or not lexeme.variant_base_form:
        return ""
    if lexeme.variant_relationship == "distinct_derived_form":
        note = f"Special note for this entry: {lexeme.variant_prompt_note}\n" if lexeme.variant_prompt_note else ""
        return (
            f"This entry is morphologically related to the base word '{lexeme.variant_base_form}', but it must be treated as its own learner entry.\n"
            "Do not restate the ordinary inflectional or base-word meanings already covered by the base word.\n"
            f"Generate only the standalone meanings and uses that justify keeping '{lexeme.lemma}' as its own entry.\n"
            f"Include a short usage note that links '{lexeme.lemma}' back to '{lexeme.variant_base_form}'.\n"
            f"{note}"
        )
    return (
        f"This word is another form of the base word '{lexeme.variant_base_form}', but it remains a separate learner entry because it has distinct meanings of its own.\n"
        "Do not repeat the ordinary meanings already covered by the base word.\n"
        f"Generate only the meanings that are distinct or special to '{lexeme.lemma}'.\n"
        f"Include a short usage note that says it is another form of '{lexeme.variant_base_form}'.\n"
    )


def _entity_category_prompt_guidance(lexeme: LexemeRecord) -> str:
    if lexeme.entity_category == "general":
        return ""
    return (
        f"This entry is categorized as '{lexeme.entity_category}', not a plain general-vocabulary item.\n"
        "Keep the explanation grounded in the specific named-entity or specialized-entity use of this entry.\n"
        "Do not broaden it into unrelated ordinary meanings from similarly spelled common words.\n"
    )


def build_enrichment_prompt(*, lexeme: LexemeRecord, sense: SenseRecord) -> str:
    return (
        "Return only valid content for the required fields.\n"
        "Top-level output shape: a single JSON object with the enrichment fields only.\n"
        "Required top-level fields: definition, examples, confidence, and translations.\n"
        "The confidence field must be a numeric value between 0 and 1.\n"
        f"For every selected sense, include all required translation locales exactly once: {', '.join(_REQUIRED_TRANSLATION_LOCALES)}.\n"
        "For each translation locale, include definition, usage_note, and examples.\n"
        "For each locale, translations.examples must contain exactly the same number of items as the English examples array, in the same order.\n"
        "Return a JSON object only. No prose, no markdown, no code fences, and no extra keys outside the schema.\n"
        f"Generate learner-facing enrichment for the English word '{lexeme.lemma}'.\n"
        f"Part of speech: {sense.part_of_speech}.\n"
        f"Canonical gloss: {sense.canonical_gloss}.\n"
        f"Word frequency rank: {lexeme.wordfreq_rank}.\n"
        f"{_entity_category_prompt_guidance(lexeme)}"
        f"{_variant_prompt_guidance(lexeme)}"
    )


def _extract_output_text(response_payload: dict[str, Any] | Any) -> str:
    output_text = getattr(response_payload, 'output_text', None)
    if isinstance(output_text, str):
        return output_text
    if hasattr(response_payload, 'model_dump'):
        response_payload = response_payload.model_dump()
    if not isinstance(response_payload, dict):
        raise RuntimeError('OpenAI-compatible endpoint response was not an object')
    if isinstance(response_payload.get('output_text'), str):
        return response_payload['output_text']
    for item in response_payload.get('output', []):
        if not isinstance(item, dict):
            continue
        for content in item.get('content') or []:
            if not isinstance(content, dict):
                continue
            if content.get('type') in {'output_text', 'text'} and isinstance(content.get('text'), str):
                return content['text']
    raise RuntimeError('OpenAI-compatible endpoint response did not contain output text')


def _parse_json_payload_text(text: str) -> dict[str, Any]:
    normalized = text.strip()
    if normalized.startswith("```"):
        lines = normalized.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        normalized = "\n".join(lines).strip()

    try:
        payload = json.loads(normalized)
    except json.JSONDecodeError:
        start = normalized.find('{')
        end = normalized.rfind('}')
        if start == -1 or end == -1 or end <= start:
            raise RuntimeError('JSON object not found in model output')
        try:
            payload = json.loads(normalized[start:end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError('JSON object not found in model output') from exc

    if not isinstance(payload, dict):
        raise RuntimeError('OpenAI-compatible endpoint returned a non-object enrichment payload')
    return payload


def _payload_error(field: str, message: str) -> RuntimeError:
    return RuntimeError(f"OpenAI-compatible enrichment payload field '{field}' {message}")


def _require_non_empty_string(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise _payload_error(field, 'must be a non-empty string')
    return value.strip()


def _validate_optional_enum(value: Any, *, field: str, allowed: set[str]) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise _payload_error(field, f"must be one of {sorted(allowed)}")
    normalized = value.strip()
    if normalized not in allowed:
        raise _payload_error(field, f"must be one of {sorted(allowed)}")
    return normalized


def _validate_string_list_field(value: Any, *, field: str) -> list[str] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _payload_error(field, 'must be a list of non-empty strings')

    normalized: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str):
            raise _payload_error(f'{field}[{index}]', 'must be a non-empty string')
        candidate = item.strip()
        if not candidate:
            continue
        normalized.append(candidate)
    return normalized


def _validate_examples(value: Any) -> list[SenseExample]:
    if not isinstance(value, list) or not value:
        raise _payload_error('examples', 'must be a non-empty list')

    examples: list[SenseExample] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _payload_error(f'examples[{index}]', 'must be an object')

        sentence = _require_non_empty_string(item.get('sentence'), field=f'examples[{index}].sentence')
        difficulty_value = item.get('difficulty')
        if difficulty_value is None:
            difficulty = 'B1'
        elif isinstance(difficulty_value, str) and difficulty_value.strip():
            difficulty = difficulty_value.strip()
        else:
            raise _payload_error(f'examples[{index}].difficulty', 'must be a non-empty string when provided')

        if difficulty not in _ALLOWED_CEFR_LEVELS:
            raise _payload_error(f'examples[{index}].difficulty', f"must be one of {sorted(_ALLOWED_CEFR_LEVELS)}")

        examples.append(SenseExample(sentence=sentence, difficulty=difficulty))

    return examples


def _validate_forms(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise _payload_error('forms', 'must be an object')

    required_keys = {'plural_forms', 'verb_forms', 'comparative', 'superlative', 'derivations'}
    missing = sorted(required_keys - set(value.keys()))
    if missing:
        raise _payload_error('forms', f"is missing required keys {missing}")

    plural_forms = _validate_string_list_field(value.get('plural_forms'), field='forms.plural_forms')
    derivations = _validate_string_list_field(value.get('derivations'), field='forms.derivations')

    verb_forms = value.get('verb_forms')
    if not isinstance(verb_forms, dict):
        raise _payload_error('forms.verb_forms', 'must be an object')
    normalized_verb_forms: dict[str, str] = {}
    for subfield, subvalue in verb_forms.items():
        if not isinstance(subfield, str) or not subfield.strip():
            raise _payload_error('forms.verb_forms', 'must use non-empty string keys')
        if not isinstance(subvalue, str):
            raise _payload_error(f'forms.verb_forms.{subfield}', 'must be a string')
        normalized_verb_forms[subfield] = subvalue.strip()

    comparative = value.get('comparative')
    if comparative is not None and not isinstance(comparative, str):
        raise _payload_error('forms.comparative', 'must be a string or null')

    superlative = value.get('superlative')
    if superlative is not None and not isinstance(superlative, str):
        raise _payload_error('forms.superlative', 'must be a string or null')

    return {
        'plural_forms': plural_forms or [],
        'verb_forms': normalized_verb_forms,
        'comparative': comparative.strip() if isinstance(comparative, str) else None,
        'superlative': superlative.strip() if isinstance(superlative, str) else None,
        'derivations': derivations or [],
    }


def _validate_confusable_words(value: Any) -> list[dict[str, str]] | None:
    if value is None:
        return None
    if not isinstance(value, list):
        raise _payload_error('confusable_words', 'must be a list of objects')

    normalized: list[dict[str, str]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _payload_error(f'confusable_words[{index}]', 'must be an object')
        word = _require_non_empty_string(item.get('word'), field=f'confusable_words[{index}].word')
        note_value = item.get('note')
        if not isinstance(note_value, str):
            raise _payload_error(f'confusable_words[{index}].note', 'must be a string')
        normalized.append({'word': word, 'note': note_value.strip()})
    return normalized


def _validate_confidence(value: Any) -> float:
    if isinstance(value, str):
        stripped = value.strip()
        try:
            value = float(stripped)
        except ValueError as exc:
            raise _payload_error('confidence', 'must be a numeric value between 0 and 1') from exc

    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _payload_error('confidence', 'must be a numeric value between 0 and 1')

    confidence = float(value)
    if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
        raise _payload_error('confidence', 'must be a finite number between 0 and 1')

    return confidence


def _validate_translations(value: Any, *, example_count: int) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        raise _payload_error('translations', 'must be an object keyed by locale')

    normalized: dict[str, dict[str, Any]] = {}
    for locale in _REQUIRED_TRANSLATION_LOCALES:
        locale_payload = value.get(locale)
        if not isinstance(locale_payload, dict):
            raise RuntimeError(f"OpenAI-compatible enrichment payload field 'translations' must include required locale '{locale}'")
        definition = _require_non_empty_string(locale_payload.get('definition'), field=f'translations.{locale}.definition')
        usage_note = _require_non_empty_string(locale_payload.get('usage_note'), field=f'translations.{locale}.usage_note')
        examples = locale_payload.get('examples')
        if not isinstance(examples, list) or not examples:
            raise _payload_error(f'translations.{locale}.examples', 'must be a non-empty list of strings')
        normalized_examples: list[str] = []
        for index, item in enumerate(examples):
            if not isinstance(item, str) or not item.strip():
                raise _payload_error(f'translations.{locale}.examples[{index}]', 'must be a non-empty string')
            normalized_examples.append(item.strip())
        if len(normalized_examples) != example_count:
            raise _payload_error(
                f'translations.{locale}.examples',
                f'must contain exactly {example_count} item(s) to align with the English examples'
            )
        normalized[locale] = {
            'definition': definition,
            'usage_note': usage_note,
            'examples': normalized_examples,
        }

    return normalized


def _validate_openai_compatible_payload(response: dict[str, Any]) -> dict[str, Any]:
    return _normalize_word_enrichment_payload(response)


def _validate_openai_compatible_phrase_payload(response: dict[str, Any]) -> dict[str, Any]:
    return _normalize_phrase_enrichment_payload(response)


def _normalize_examples(value: Any, *, fallback_sentence: str) -> list[SenseExample]:
    examples: list[SenseExample] = []
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, dict):
                continue
            sentence = str(item.get('sentence') or '').strip()
            if not sentence:
                continue
            difficulty = str(item.get('difficulty') or 'B1')
            examples.append(SenseExample(sentence=sentence, difficulty=difficulty))
    if examples:
        return examples
    return [SenseExample(sentence=fallback_sentence, difficulty='B1')]


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _normalize_confusable_words(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        word = str(item.get('word') or '').strip()
        note = str(item.get('note') or '').strip()
        if not word:
            continue
        normalized.append({'word': word, 'note': note})
    return normalized




def learner_meaning_cap(wordfreq_rank: int) -> int:
    rank = int(wordfreq_rank or 0)
    if rank <= 0:
        return 4
    if rank <= 250:
        return 5
    if rank <= 1000:
        return 6
    if rank <= 5000:
        return 8
    if rank <= 10000:
        return 6
    return 4

def _word_enrichment_grounding_payload(*, senses: list[SenseRecord]) -> list[dict[str, Any]]:
    sense_rows = [
        {
            'sense_id': sense.sense_id,
            'wn_synset_id': sense.wn_synset_id,
            'part_of_speech': sense.part_of_speech,
            'canonical_gloss': sense.canonical_gloss,
            'sense_order': sense.sense_order,
            'selection_reason': sense.selection_reason,
        }
        for sense in sorted(senses, key=lambda item: item.sense_order)
    ]
    return sense_rows


def build_word_enrichment_prompt(*, lexeme: LexemeRecord, senses: list[SenseRecord], prompt_mode: str = "grounded") -> str:
    max_meanings = learner_meaning_cap(lexeme.wordfreq_rank)
    if prompt_mode not in _WORD_PROMPT_MODES:
        raise ValueError(f"Unsupported word prompt mode: {prompt_mode}")
    guidance_lines = [
        f"Select at most {max_meanings} learner-friendly meanings in total.",
        f"If more than {max_meanings} candidates seem useful, keep only the strongest {max_meanings}.",
        "For very common grammar or function words, merge closely related micro-uses into broader learner-facing senses.",
        "Do not split tiny contextual variants into separate senses when one broader sense can cover them clearly.",
        "Return only valid content for the required fields.",
        f"Decide whether the English word '{lexeme.lemma}' should be discarded or kept as a learner entry.",
        f"Word frequency rank: {lexeme.wordfreq_rank}.",
        f"Valid decisions are exactly: {', '.join(sorted(_WORD_DECISIONS))}.",
        "Use 'discard' when the surface word is not a useful standalone learner entry or is only an ordinary inflectional form with no special meaning of its own.",
        "Do not discard common closed-class grammar words such as pronouns, determiners, and possessives just because they are morphologically related to another word.",
        "Plain auxiliary verb inflections such as is, are, and has should still be discarded unless they have a truly separate lexicalized meaning of their own.",
        "Plain contractions such as \"it's\" or \"i'm\" should be discarded unless they have a truly separate lexicalized meaning of their own.",
        "Use 'keep_standard' when the word should be kept as a normal standalone learner entry.",
        "Use 'keep_derived_special' when the word is related to a base word but has lexicalized or otherwise special meanings worth teaching separately.",
        "If a word is primarily an inflected or derived form of another word and is kept only because of a smaller subset of special, shifted, or lexicalized uses, prefer keep_derived_special over keep_standard.",
        "Do not return internal meaning IDs. Internal IDs are assigned by the tool after validation.",
        "Each kept sense must include part_of_speech and sense_kind.",
        "Allowed sense_kind values are: standard_meaning, base_form_reference, special_meaning.",
        "For 'keep_standard', use only standard_meaning senses and leave base_word null.",
        "For 'keep_derived_special', set base_word to the related base word, include exactly one brief base_form_reference sense, and focus the remaining senses on special_meaning entries rather than ordinary base-word meanings.",
        "For 'discard', return an empty senses array and a short discard_reason.",
        "For every kept word, include phonetics.us, phonetics.uk, and phonetics.au with IPA and confidence for each accent.",
        f"For every kept sense, include all required translation locales exactly once: {', '.join(_REQUIRED_TRANSLATION_LOCALES)}.",
        "For each translation locale, include definition, usage_note, and examples.",
        "For each locale, translations.examples must contain exactly the same number of items as the English examples array, in the same order.",
        "Return a JSON object only. No prose, no markdown, no code fences, and no extra keys outside the schema.",
        _entity_category_prompt_guidance(lexeme).strip(),
        _variant_prompt_guidance(lexeme).strip(),
    ]
    if prompt_mode == "grounded" and senses:
        guidance_lines.append(
            f"Optional grounding context only, not a hard schema contract: {json.dumps(_word_enrichment_grounding_payload(senses=senses))}."
        )
    return (
        f"The response is invalid if the senses array contains more than {max_meanings} items.\n"
        + "\n".join(line for line in guidance_lines if line)
        + "\n"
    )


def build_phrase_enrichment_prompt(*, lexeme: LexemeRecord) -> str:
    display_form = lexeme.display_form or lexeme.lemma
    phrase_kind = lexeme.phrase_kind or "multiword_expression"
    return (
        f"Create learner-facing enrichment for the English phrase '{display_form}'.\n"
        f"Phrase kind: {phrase_kind}.\n"
        "Return 1 to 2 learner-relevant senses for the phrase as a whole, not its component words.\n"
        "Each sense must include definition, part_of_speech, at least one example, grammar_patterns, usage_note, and translations.\n"
        f"Each example difficulty must be one of: {', '.join(_ALLOWED_CEFR_LEVELS)}.\n"
        f"Use the exact required translation locales: {', '.join(_REQUIRED_TRANSLATION_LOCALES)}.\n"
        "For each locale, translations.examples must contain exactly the same number of items as the English examples array, in the same order.\n"
        "Use the exact phrase naturally in the examples.\n"
        "Return JSON only.\n"
    )


def build_phrase_enrichment_repair_prompt(*, lexeme: LexemeRecord, previous_error: str) -> str:
    return (
        f"Repair the previous learner-facing enrichment response for the English phrase '{lexeme.display_form or lexeme.lemma}'.\n"
        f"The previous response was invalid: {previous_error}\n"
        + build_phrase_enrichment_prompt(lexeme=lexeme)
    )


def build_word_enrichment_repair_prompt(*, lexeme: LexemeRecord, senses: list[SenseRecord], previous_error: str, prompt_mode: str = "grounded") -> str:
    max_meanings = learner_meaning_cap(lexeme.wordfreq_rank)
    if prompt_mode not in _WORD_PROMPT_MODES:
        raise ValueError(f"Unsupported word prompt mode: {prompt_mode}")
    return (
        f"Repair the previous learner-facing enrichment response for the English word '{lexeme.lemma}'.\n"
        f"The previous response was invalid: {previous_error}\n"
        f"The repaired response is invalid if the senses array contains more than {max_meanings} items.\n"
        + build_word_enrichment_prompt(lexeme=lexeme, senses=senses, prompt_mode=prompt_mode)
    )


def _base_enrichment_item_schema() -> dict[str, Any]:
    def nullable_schema(inner: dict[str, Any]) -> dict[str, Any]:
        return {
            "anyOf": [
                inner,
                {"type": "null"},
            ]
        }

    verb_forms_schema = {
        "type": "object",
        "properties": {
            "base": {"type": "string"},
            "third_person_singular": {"type": "string"},
            "past": {"type": "string"},
            "past_participle": {"type": "string"},
            "gerund": {"type": "string"},
        },
        "required": [
            "base",
            "third_person_singular",
            "past",
            "past_participle",
            "gerund",
        ],
        "additionalProperties": False,
    }

    example_schema = {
        "type": "object",
        "properties": {
            "sentence": {"type": "string"},
            "difficulty": {"type": "string", "enum": sorted(_ALLOWED_CEFR_LEVELS)},
        },
        "required": ["sentence", "difficulty"],
        "additionalProperties": False,
    }
    translation_schema = {
        "type": "object",
        "properties": {
            "definition": {"type": "string"},
            "usage_note": {"type": "string"},
            "examples": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["definition", "usage_note", "examples"],
        "additionalProperties": False,
    }
    properties = {
        "definition": {"type": "string"},
        "examples": {"type": "array", "items": example_schema, "minItems": 1},
        "cefr_level": nullable_schema({"type": "string", "enum": sorted(_ALLOWED_CEFR_LEVELS)}),
        "primary_domain": nullable_schema({"type": "string"}),
        "secondary_domains": nullable_schema({"type": "array", "items": {"type": "string"}}),
        "register": nullable_schema({"type": "string", "enum": sorted(_ALLOWED_REGISTERS)}),
        "synonyms": nullable_schema({"type": "array", "items": {"type": "string"}}),
        "antonyms": nullable_schema({"type": "array", "items": {"type": "string"}}),
        "collocations": nullable_schema({"type": "array", "items": {"type": "string"}}),
        "grammar_patterns": nullable_schema({"type": "array", "items": {"type": "string"}}),
        "usage_note": nullable_schema({"type": "string"}),
        "forms": nullable_schema({
            "type": "object",
            "properties": {
                "plural_forms": {"type": "array", "items": {"type": "string"}},
                "verb_forms": verb_forms_schema,
                "comparative": nullable_schema({"type": "string"}),
                "superlative": nullable_schema({"type": "string"}),
                "derivations": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["plural_forms", "verb_forms", "comparative", "superlative", "derivations"],
            "additionalProperties": False,
        }),
        "confusable_words": nullable_schema({
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "word": {"type": "string"},
                    "note": {"type": "string"},
                },
                "required": ["word", "note"],
                "additionalProperties": False,
            },
        }),
        "confidence": {"type": "number"},
        "translations": {
            "type": "object",
            "properties": {locale: translation_schema for locale in _REQUIRED_TRANSLATION_LOCALES},
            "required": list(_REQUIRED_TRANSLATION_LOCALES),
            "additionalProperties": False,
        },
    }
    return {
        "type": "object",
        "properties": properties,
        "required": list(properties.keys()),
        "additionalProperties": False,
    }


def _single_sense_response_schema() -> dict[str, Any]:
    return _build_single_sense_response_schema()


def _word_enrichment_response_schema() -> dict[str, Any]:
    return _build_word_enrichment_response_schema()


def _phrase_enrichment_response_schema() -> dict[str, Any]:
    return _build_phrase_enrichment_response_schema()


def _is_repairable_word_payload_error(error: RuntimeError) -> bool:
    message = str(error).lower()
    non_repairable_markers = (
        'request failed',
        'transport failed',
        'timed out',
        'cloudflare',
        'status 4',
        'status 5',
    )
    return not any(marker in message for marker in non_repairable_markers)


def _is_retryable_word_generation_error(error: RuntimeError) -> bool:
    message = str(error).lower()
    retryable_markers = (
        'timed out',
        'non-json',
        'temporarily unavailable',
        'connection reset',
        'connection aborted',
        'bad gateway',
        'error code 502',
        'error code 503',
        'error code 504',
        'cloudflare',
        'status 429',
        'status 502',
        'status 503',
        'status 504',
        'rate limit',
        'service unavailable',
        'gateway timeout',
    )
    return any(marker in message for marker in retryable_markers)


def _transient_retry_backoff_seconds(retry_number: int) -> float:
    return min(0.5 * (2 ** max(retry_number - 1, 0)), 5.0)


def _is_retryable_phrase_payload_error(error: RuntimeError) -> bool:
    return _is_repairable_word_payload_error(error)


def _retry_reason_label(error: BaseException) -> str:
    message = str(error)
    phrase_marker = 'missing_translated_usage_note_with_source_note_present'
    if phrase_marker in message.lower():
        return phrase_marker
    return message


def _build_runtime_logger(*, snapshot_dir: Path, log_level: str, log_file: Path | None) -> RuntimeLogger:
    effective_log_file = log_file or (snapshot_dir / _DEFAULT_RUNTIME_LOG_FILE)
    return RuntimeLogger(
        RuntimeLogConfig(level=log_level, log_file=effective_log_file),
        stream=sys.stderr,
    )


def _lexeme_runtime_fields(lexeme: LexemeRecord) -> dict[str, Any]:
    return {
        'lexeme_id': lexeme.lexeme_id,
        'entry_id': lexeme.entry_id,
        'entry_type': lexeme.entry_type,
        'lemma': lexeme.lemma,
    }


def _emit_lexeme_event(
    runtime_logger: RuntimeLogger | None,
    event: str,
    message: str,
    *,
    lexeme: LexemeRecord,
    **fields: Any,
) -> None:
    if runtime_logger is None:
        return
    runtime_logger.info(event, message, **_lexeme_runtime_fields(lexeme), **fields)


def _emit_retry_events(
    runtime_logger: RuntimeLogger | None,
    *,
    lexeme: LexemeRecord,
    retry_kind: str,
    retry_reason: str,
    retries_remaining: int,
    sense_id: str | None = None,
) -> None:
    if runtime_logger is None:
        return
    fields: dict[str, Any] = {
        'retry_kind': retry_kind,
        'retry_reason': retry_reason,
        'retries_remaining': retries_remaining,
    }
    if sense_id is not None:
        fields['sense_id'] = sense_id
    _emit_lexeme_event(
        runtime_logger,
        'retry-reason',
        'Retry reason recorded',
        lexeme=lexeme,
        **fields,
    )
    _emit_lexeme_event(
        runtime_logger,
        'retry-scheduled',
        'Retry scheduled',
        lexeme=lexeme,
        **fields,
    )


def _emit_validation_terminal_event(
    runtime_logger: RuntimeLogger | None,
    *,
    lexeme: LexemeRecord,
    outcome: str,
    retry_count: int,
    error: RuntimeError | None = None,
    sense_id: str | None = None,
) -> None:
    if runtime_logger is None:
        return
    fields: dict[str, Any] = {
        'outcome': outcome,
        'retry_count': retry_count,
    }
    if error is not None:
        fields['error'] = str(error)
    if sense_id is not None:
        fields['sense_id'] = sense_id
    _emit_lexeme_event(
        runtime_logger,
        'validation-outcome',
        'Validation outcome recorded',
        lexeme=lexeme,
        **fields,
    )


def _generate_validated_phrase_payload_with_stats(
    *,
    client: OpenAICompatibleResponsesClient | NodeOpenAICompatibleResponsesClient,
    lexeme: LexemeRecord,
    max_transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    max_validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    prompt = build_phrase_enrichment_prompt(lexeme=lexeme)
    response_schema = _phrase_enrichment_response_schema()
    last_error: RuntimeError | None = None
    transient_retries = 0
    repair_attempts = 0
    effective_max_transient_retries = max(0, int(max_transient_retries))
    effective_max_validation_retries = max(0, int(max_validation_retries))

    while True:
        try:
            response = _client_generate_json(
                client,
                prompt,
                response_schema=response_schema,
                reasoning_effort_override=(
                    _validation_retry_reasoning_effort(client)
                    if repair_attempts > 0
                    else None
                ),
            )
        except RuntimeError as exc:
            if _is_retryable_word_generation_error(exc) and transient_retries < effective_max_transient_retries:
                transient_retries += 1
                _emit_retry_events(
                    runtime_logger,
                    retry_kind='transient',
                    retries_remaining=max(0, effective_max_transient_retries - transient_retries),
                    retry_reason=_retry_reason_label(exc),
                    lexeme=lexeme,
                )
                time.sleep(_transient_retry_backoff_seconds(transient_retries))
                continue
            raise

        try:
            validated = _validate_openai_compatible_phrase_payload(response)
            if repair_attempts > 0:
                _emit_validation_terminal_event(
                    runtime_logger,
                    lexeme=lexeme,
                    outcome='repaired',
                    retry_count=repair_attempts,
                )
            return validated, {
                "validation_retry_count": repair_attempts,
                "transient_retry_count": transient_retries,
            }
        except RuntimeError as exc:
            last_error = exc
            if not _is_retryable_phrase_payload_error(exc) or repair_attempts >= effective_max_validation_retries:
                _emit_validation_terminal_event(
                    runtime_logger,
                    lexeme=lexeme,
                    outcome='failed',
                    retry_count=repair_attempts,
                    error=exc,
                )
                raise
            repair_attempts += 1
            transient_retries = 0
            _emit_retry_events(
                runtime_logger,
                retry_kind='validation',
                retries_remaining=max(0, effective_max_validation_retries - repair_attempts),
                retry_reason=_retry_reason_label(exc),
                lexeme=lexeme,
            )
            prompt = build_phrase_enrichment_repair_prompt(
                lexeme=lexeme,
                previous_error=str(last_error),
            )


def _generate_validated_single_sense_payload_with_stats(
    *,
    client: OpenAICompatibleResponsesClient | NodeOpenAICompatibleResponsesClient,
    lexeme: LexemeRecord,
    sense: SenseRecord,
    max_transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    max_validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    prompt = build_enrichment_prompt(lexeme=lexeme, sense=sense)
    response_schema = _single_sense_response_schema()
    transient_retries = 0
    validation_retries = 0
    effective_max_transient_retries = max(0, int(max_transient_retries))
    effective_max_validation_retries = max(0, int(max_validation_retries))

    while True:
        try:
            response = _client_generate_json(
                client,
                prompt,
                response_schema=response_schema,
                reasoning_effort_override=(
                    _validation_retry_reasoning_effort(client)
                    if validation_retries > 0
                    else None
                ),
            )
        except RuntimeError as exc:
            if _is_retryable_word_generation_error(exc) and transient_retries < effective_max_transient_retries:
                transient_retries += 1
                _emit_retry_events(
                    runtime_logger,
                    retry_kind='transient',
                    retries_remaining=max(0, effective_max_transient_retries - transient_retries),
                    retry_reason=_retry_reason_label(exc),
                    lexeme=lexeme,
                    sense_id=sense.sense_id,
                )
                time.sleep(_transient_retry_backoff_seconds(transient_retries))
                continue
            raise

        try:
            validated = _validate_openai_compatible_payload(response)
            if validation_retries > 0:
                _emit_validation_terminal_event(
                    runtime_logger,
                    lexeme=lexeme,
                    outcome='repaired',
                    retry_count=validation_retries,
                    sense_id=sense.sense_id,
                )
            return validated, {
                "validation_retry_count": validation_retries,
                "transient_retry_count": transient_retries,
            }
        except RuntimeError as exc:
            if _is_repairable_word_payload_error(exc) and validation_retries < effective_max_validation_retries:
                validation_retries += 1
                _emit_retry_events(
                    runtime_logger,
                    retry_kind='validation',
                    retries_remaining=max(0, effective_max_validation_retries - validation_retries),
                    retry_reason=_retry_reason_label(exc),
                    lexeme=lexeme,
                    sense_id=sense.sense_id,
                )
                continue
            _emit_validation_terminal_event(
                runtime_logger,
                lexeme=lexeme,
                outcome='failed',
                retry_count=validation_retries,
                error=exc,
                sense_id=sense.sense_id,
            )
            raise


def _generate_validated_word_payload_with_stats(
    *,
    client: OpenAICompatibleResponsesClient | NodeOpenAICompatibleResponsesClient,
    lexeme: LexemeRecord,
    senses: list[SenseRecord],
    prompt_mode: str = "grounded",
    max_transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    max_validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> tuple[dict[str, Any], dict[str, int]]:
    prompt = build_word_enrichment_prompt(lexeme=lexeme, senses=senses, prompt_mode=prompt_mode)
    response_schema = _word_enrichment_response_schema()
    last_error: RuntimeError | None = None
    repair_attempts = 0
    transient_retries = 0
    effective_max_transient_retries = max(0, int(max_transient_retries))
    effective_max_validation_retries = max(0, int(max_validation_retries))

    while True:
        try:
            response = _client_generate_json(
                client,
                prompt,
                response_schema=response_schema,
                reasoning_effort_override=(
                    _validation_retry_reasoning_effort(client)
                    if repair_attempts > 0
                    else None
                ),
            )
            validated = _validate_openai_compatible_word_payload(response, lexeme=lexeme, senses=senses)
            if repair_attempts > 0:
                _emit_validation_terminal_event(
                    runtime_logger,
                    lexeme=lexeme,
                    outcome='repaired',
                    retry_count=repair_attempts,
                )
            return validated, {
                "repair_count": repair_attempts,
                "retry_count": transient_retries,
            }
        except RuntimeError as exc:
            last_error = exc
            if _is_retryable_word_generation_error(exc) and transient_retries < effective_max_transient_retries:
                transient_retries += 1
                _emit_retry_events(
                    runtime_logger,
                    retry_kind='transient',
                    retries_remaining=max(0, effective_max_transient_retries - transient_retries),
                    retry_reason=_retry_reason_label(exc),
                    lexeme=lexeme,
                )
                time.sleep(_transient_retry_backoff_seconds(transient_retries))
                continue
            if not _is_repairable_word_payload_error(exc) or repair_attempts >= effective_max_validation_retries:
                _emit_validation_terminal_event(
                    runtime_logger,
                    lexeme=lexeme,
                    outcome='failed',
                    retry_count=repair_attempts,
                    error=exc,
                )
                raise
            repair_attempts += 1
            transient_retries = 0
            _emit_retry_events(
                runtime_logger,
                retry_kind='validation',
                retries_remaining=max(0, effective_max_validation_retries - repair_attempts),
                retry_reason=_retry_reason_label(exc),
                lexeme=lexeme,
            )
            prompt = build_word_enrichment_repair_prompt(
                lexeme=lexeme,
                senses=senses,
                previous_error=str(last_error),
                prompt_mode=prompt_mode,
            )


def _generate_validated_word_payload(
    *,
    client: OpenAICompatibleResponsesClient | NodeOpenAICompatibleResponsesClient,
    lexeme: LexemeRecord,
    senses: list[SenseRecord],
    prompt_mode: str = "grounded",
    max_transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    max_validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> dict[str, Any]:
    rows, _ = _generate_validated_word_payload_with_stats(
        client=client,
        lexeme=lexeme,
        senses=senses,
        prompt_mode=prompt_mode,
        max_transient_retries=max_transient_retries,
        max_validation_retries=max_validation_retries,
        runtime_logger=runtime_logger,
    )
    return rows


def _build_enrichment_record(*, lexeme: LexemeRecord, sense: SenseRecord, response: dict[str, Any], model_name: str, prompt_version: str, generation_run_id: str, review_status: str, generated_at: str) -> EnrichmentRecord:
    return EnrichmentRecord(
        snapshot_id=sense.snapshot_id,
        enrichment_id=make_enrichment_id(sense.sense_id, prompt_version),
        sense_id=sense.sense_id,
        definition=response['definition'],
        examples=response['examples'],
        cefr_level=response.get('cefr_level') or 'B1',
        primary_domain=str(response.get('primary_domain') or 'general'),
        secondary_domains=response.get('secondary_domains') or [],
        register=response.get('register') or 'neutral',
        synonyms=response.get('synonyms') or [],
        antonyms=response.get('antonyms') or [],
        collocations=response.get('collocations') or [],
        grammar_patterns=response.get('grammar_patterns') or [],
        usage_note=str(response.get('usage_note') or f'Auto-generated learner note for {lexeme.lemma}.'),
        forms=response.get('forms') or _default_forms(lexeme.lemma, sense.part_of_speech),
        confusable_words=response.get('confusable_words') or [],
        translations=response.get('translations') or {},
        model_name=str(model_name),
        prompt_version=prompt_version,
        generation_run_id=generation_run_id,
        confidence=response['confidence'],
        review_status=review_status,
        generated_at=generated_at,
        lexeme_id=lexeme.lexeme_id,
        sense_order=sense.sense_order,
        part_of_speech=sense.part_of_speech,
    )


def _build_word_enrichment_records(
    *,
    lexeme: LexemeRecord,
    response: dict[str, Any],
    model_name: str,
    prompt_version: str,
    generation_run_id: str,
    review_status: str,
    generated_at: str,
) -> list[EnrichmentRecord]:
    decision = str(response["decision"])
    base_word_value = response.get("base_word")
    base_word = str(base_word_value).strip() if isinstance(base_word_value, str) and base_word_value.strip() else None
    records: list[EnrichmentRecord] = []
    for index, row in enumerate(response.get("senses") or [], start=1):
        sense_id = make_sense_id(lexeme.lexeme_id, index)
        part_of_speech = str(row.get("part_of_speech") or "").strip() or "noun"
        records.append(
            EnrichmentRecord(
                snapshot_id=lexeme.snapshot_id,
                enrichment_id=make_enrichment_id(sense_id, prompt_version),
                sense_id=sense_id,
                definition=row["definition"],
                examples=row["examples"],
                cefr_level=row.get("cefr_level") or "B1",
                primary_domain=str(row.get("primary_domain") or "general"),
                secondary_domains=row.get("secondary_domains") or [],
                register=row.get("register") or "neutral",
                synonyms=row.get("synonyms") or [],
                antonyms=row.get("antonyms") or [],
                collocations=row.get("collocations") or [],
                grammar_patterns=row.get("grammar_patterns") or [],
                usage_note=str(row.get("usage_note") or f"Auto-generated learner note for {lexeme.lemma}."),
                forms=row.get("forms") or _default_forms(lexeme.lemma, part_of_speech),
                confusable_words=row.get("confusable_words") or [],
                translations=row.get("translations") or {},
                phonetics=response.get("phonetics"),
                model_name=str(model_name),
                prompt_version=prompt_version,
                generation_run_id=generation_run_id,
                confidence=row["confidence"],
                review_status=review_status,
                generated_at=generated_at,
                lexeme_id=lexeme.lexeme_id,
                sense_order=index,
                part_of_speech=part_of_speech,
                sense_kind=str(row.get("sense_kind") or "standard_meaning"),
                decision=decision,
                base_word=base_word,
            )
        )
    return records


def _build_word_job_outcome(
    *,
    lexeme: LexemeRecord,
    response: dict[str, Any],
    model_name: str,
    prompt_version: str,
    generation_run_id: str,
    review_status: str,
    generated_at: str,
) -> WordJobOutcome:
    decision = str(response["decision"])
    base_word_value = response.get("base_word")
    base_word = str(base_word_value).strip() if isinstance(base_word_value, str) and base_word_value.strip() else None
    discard_reason_value = response.get("discard_reason")
    discard_reason = (
        str(discard_reason_value).strip()
        if isinstance(discard_reason_value, str) and discard_reason_value.strip()
        else None
    )
    records = _build_word_enrichment_records(
        lexeme=lexeme,
        response=response,
        model_name=model_name,
        prompt_version=prompt_version,
        generation_run_id=generation_run_id,
        review_status=review_status,
        generated_at=generated_at,
    )
    return WordJobOutcome(
        records=records,
        decision=decision,
        base_word=base_word,
        discard_reason=discard_reason,
        phonetics=response.get("phonetics"),
    )


def _build_phrase_job_outcome(
    *,
    lexeme: LexemeRecord,
    response: dict[str, Any],
    model_name: str,
    prompt_version: str,
    generation_run_id: str,
    review_status: str,
    generated_at: str,
) -> WordJobOutcome:
    records: list[EnrichmentRecord] = []
    for index, row in enumerate(response.get("senses") or [], start=1):
        sense_id = make_sense_id(lexeme.lexeme_id, index)
        part_of_speech = str(row.get("part_of_speech") or "phrase").strip() or "phrase"
        records.append(
            EnrichmentRecord(
                snapshot_id=lexeme.snapshot_id,
                enrichment_id=make_enrichment_id(sense_id, prompt_version),
                sense_id=sense_id,
                definition=row["definition"],
                examples=row["examples"],
                cefr_level="B1",
                primary_domain="general",
                secondary_domains=[],
                register="neutral",
                synonyms=[],
                antonyms=[],
                collocations=[],
                grammar_patterns=row.get("grammar_patterns") or [],
                usage_note=str(row.get("usage_note") or f"Auto-generated learner note for {lexeme.lemma}."),
                forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                confusable_words=[],
                translations=row.get("translations") or {},
                model_name=str(model_name),
                prompt_version=prompt_version,
                generation_run_id=generation_run_id,
                confidence=response["confidence"],
                review_status=review_status,
                generated_at=generated_at,
                lexeme_id=lexeme.lexeme_id,
                sense_order=index,
                part_of_speech=part_of_speech,
                sense_kind="standard_meaning",
                decision="keep_standard",
                base_word=None,
            )
        )
    return WordJobOutcome(records=records, decision="keep_standard", base_word=None, discard_reason=None, phonetics=None)


def _validate_openai_compatible_word_payload(response: dict[str, Any], *, lexeme: LexemeRecord, senses: list[SenseRecord]) -> dict[str, Any]:
    if not isinstance(response, dict):
        raise RuntimeError('OpenAI-compatible endpoint returned a non-object word enrichment payload')
    value = response.get('senses')
    if not isinstance(value, list):
        raise RuntimeError("OpenAI-compatible word enrichment payload field 'senses' must be a list")
    decision_value = response.get('decision')
    if decision_value is None and value:
        decision = 'keep_standard'
    else:
        decision = _require_non_empty_string(decision_value, field='decision')
        if decision not in _WORD_DECISIONS:
            raise RuntimeError(f"OpenAI-compatible word enrichment payload returned unsupported decision '{decision}'")

    max_meanings = learner_meaning_cap(lexeme.wordfreq_rank)
    if len(value) > max_meanings:
        raise RuntimeError(
            f"OpenAI-compatible word enrichment payload must select at most {max_meanings} learner-friendly meanings for frequency rank {lexeme.wordfreq_rank}"
        )

    discard_reason_value = response.get('discard_reason')
    if discard_reason_value is None:
        discard_reason = None
    elif isinstance(discard_reason_value, str):
        discard_reason = discard_reason_value.strip() or None
    else:
        raise RuntimeError("OpenAI-compatible word enrichment payload field 'discard_reason' must be a string or null")

    base_word_value = response.get('base_word')
    if base_word_value is None:
        base_word = None
    elif isinstance(base_word_value, str) and base_word_value.strip():
        base_word = base_word_value.strip()
    else:
        raise RuntimeError("OpenAI-compatible word enrichment payload field 'base_word' must be a non-empty string or null")

    normalized_rows: list[dict[str, Any]] = []
    phonetics = _normalize_phonetics_payload(response.get("phonetics"))
    source_senses_by_id = {sense.sense_id: sense for sense in senses}
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RuntimeError(f"OpenAI-compatible word enrichment payload field 'senses[{index}]' must be an object")
        normalized = _validate_openai_compatible_payload(item)
        legacy_sense_id = item.get('sense_id')
        source_sense = source_senses_by_id.get(str(legacy_sense_id or '').strip())
        if isinstance(legacy_sense_id, str) and legacy_sense_id.strip():
            normalized['sense_id'] = legacy_sense_id.strip()
        part_of_speech_value = item.get('part_of_speech')
        if part_of_speech_value is None and source_sense is not None:
            part_of_speech_value = source_sense.part_of_speech
        normalized['part_of_speech'] = _require_non_empty_string(part_of_speech_value, field=f'senses[{index}].part_of_speech')
        sense_kind_value = item.get('sense_kind') or 'standard_meaning'
        normalized['sense_kind'] = _require_non_empty_string(sense_kind_value, field=f'senses[{index}].sense_kind')
        if normalized['sense_kind'] not in _WORD_SENSE_KINDS:
            raise RuntimeError(
                f"OpenAI-compatible word enrichment payload field 'senses[{index}].sense_kind' must be one of {sorted(_WORD_SENSE_KINDS)}"
            )
        normalized_rows.append(normalized)

    if decision == 'discard':
        if normalized_rows:
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'discard' must use an empty senses array")
        if not discard_reason:
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'discard' must include discard_reason")
        if phonetics is not None:
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'discard' must leave phonetics null")
    elif not normalized_rows:
        raise RuntimeError(f"OpenAI-compatible word enrichment payload for decision '{decision}' must include at least one sense")
    elif phonetics is None:
        raise RuntimeError(f"OpenAI-compatible word enrichment payload for decision '{decision}' must include phonetics")

    if decision == 'keep_standard':
        if base_word is not None:
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'keep_standard' must leave base_word null")
        if any(row['sense_kind'] != 'standard_meaning' for row in normalized_rows):
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'keep_standard' may use only standard_meaning senses")
    elif decision == 'keep_derived_special':
        if not base_word:
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'keep_derived_special' must include base_word")
        if sum(1 for row in normalized_rows if row['sense_kind'] == 'base_form_reference') != 1:
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'keep_derived_special' must include exactly one base_form_reference sense")
        if not any(row['sense_kind'] == 'special_meaning' for row in normalized_rows):
            raise RuntimeError("OpenAI-compatible word enrichment payload for decision 'keep_derived_special' must include at least one special_meaning sense")

    return {
        'decision': decision,
        'discard_reason': discard_reason,
        'base_word': base_word,
        'phonetics': phonetics,
        'senses': normalized_rows,
    }


def build_placeholder_enrichment_provider(
    *,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    review_status: str = 'draft',
) -> EnrichmentProvider:
    effective_settings = settings or LexiconSettings.from_env()
    effective_model_name = model_name or effective_settings.llm_model or 'placeholder-llm'

    def provider(*, lexeme: LexemeRecord, sense: SenseRecord, settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> EnrichmentRecord:
        return EnrichmentRecord(
            snapshot_id=sense.snapshot_id,
            enrichment_id=make_enrichment_id(sense.sense_id, prompt_version),
            sense_id=sense.sense_id,
            definition=sense.canonical_gloss,
            examples=[SenseExample(sentence=_default_example(lexeme.lemma, sense.part_of_speech), difficulty='B1')],
            cefr_level='B1',
            primary_domain='general',
            secondary_domains=[],
            register='neutral',
            synonyms=[],
            antonyms=[],
            collocations=[],
            grammar_patterns=[],
            usage_note=f'Auto-generated learner note for {lexeme.lemma}.',
            forms=_default_forms(lexeme.lemma, sense.part_of_speech),
            confusable_words=[],
            translations={
                locale: {
                    'definition': f'[{locale}] learner definition for {lexeme.lemma}',
                    'usage_note': f'[{locale}] learner note for {lexeme.lemma}',
                    'examples': [f'[{locale}] {_default_example(lexeme.lemma, sense.part_of_speech)}'],
                }
                for locale in _REQUIRED_TRANSLATION_LOCALES
            },
            model_name=effective_model_name,
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            confidence=0.5,
            review_status=review_status,
            generated_at=generated_at,
            phonetics=_default_phonetics(lexeme.lemma),
        )

    return provider


def build_placeholder_word_enrichment_provider(
    *,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    review_status: str = 'draft',
) -> WordEnrichmentProvider:
    effective_settings = settings or LexiconSettings.from_env()
    effective_model_name = model_name or effective_settings.llm_model or 'placeholder-llm'
    sense_provider = build_placeholder_enrichment_provider(
        settings=effective_settings,
        model_name=effective_model_name,
        review_status=review_status,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> list[EnrichmentRecord]:
        if not senses:
            synthetic_pos = "noun"
            response = {
                "decision": "keep_standard",
                "discard_reason": None,
                "base_word": None,
                "phonetics": _default_phonetics(lexeme.lemma),
                "senses": [
                    {
                        "part_of_speech": synthetic_pos,
                        "sense_kind": "standard_meaning",
                        "definition": f"placeholder learner definition for {lexeme.lemma}",
                        "examples": [SenseExample(sentence=_default_example(lexeme.lemma, synthetic_pos), difficulty='B1')],
                        "cefr_level": "B1",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": f"Auto-generated learner note for {lexeme.lemma}.",
                        "forms": _default_forms(lexeme.lemma, synthetic_pos),
                        "confusable_words": [],
                        "confidence": 0.5,
                        "translations": {
                            locale: {
                                'definition': f'[{locale}] learner definition for {lexeme.lemma}',
                                'usage_note': f'[{locale}] learner note for {lexeme.lemma}',
                                'examples': [f'[{locale}] {_default_example(lexeme.lemma, synthetic_pos)}'],
                            }
                            for locale in _REQUIRED_TRANSLATION_LOCALES
                        },
                    }
                ],
            }
            outcome = _build_word_job_outcome(
                lexeme=lexeme,
                response=response,
                model_name=str(effective_model_name),
                prompt_version=prompt_version,
                generation_run_id=generation_run_id,
                review_status=review_status,
                generated_at=generated_at,
            )
            _validate_compiled_word_outcome(lexeme=lexeme, outcome=outcome)
            return outcome
        return [
            sense_provider(
                lexeme=lexeme,
                sense=sense,
                settings=settings,
                generated_at=generated_at,
                generation_run_id=generation_run_id,
                prompt_version=prompt_version,
            )
            for sense in sorted(senses, key=lambda item: item.sense_order)
        ]

    return provider


def build_openai_compatible_node_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    runner: NodeRunner | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> EnrichmentProvider:
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for openai_compatible_node enrichment mode')
    if not (model_name or settings.llm_model):
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for openai_compatible_node enrichment mode')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for openai_compatible_node enrichment mode')

    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    client = NodeOpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        runner=runner,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, sense: SenseRecord, settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> EnrichmentRecord:
        response, _ = _generate_validated_single_sense_payload_with_stats(
            client=client,
            lexeme=lexeme,
            sense=sense,
            max_transient_retries=transient_retries,
            max_validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
        return _build_enrichment_record(
            lexeme=lexeme,
            sense=sense,
            response=response,
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            review_status=review_status,
            generated_at=generated_at,
        )

    return provider


def build_openai_compatible_node_word_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    runner: NodeRunner | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> WordEnrichmentProvider:
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for openai_compatible_node enrichment mode')
    if not (model_name or settings.llm_model):
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for openai_compatible_node enrichment mode')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for openai_compatible_node enrichment mode')

    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    client = NodeOpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        runner=runner,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> list[EnrichmentRecord]:
        ordered_senses = sorted(senses, key=lambda item: item.sense_order)
        response = _generate_validated_word_payload(
            client=client,
            lexeme=lexeme,
            senses=ordered_senses,
            prompt_mode="word_only",
            max_transient_retries=transient_retries,
            max_validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
        outcome = _build_word_job_outcome(
            lexeme=lexeme,
            response=response,
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            review_status=review_status,
            generated_at=generated_at,
        )
        _validate_compiled_word_outcome(lexeme=lexeme, outcome=outcome)
        return outcome

    return provider


def build_openai_compatible_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    client: Any | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> EnrichmentProvider:
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for openai_compatible enrichment mode')
    if not (model_name or settings.llm_model):
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for openai_compatible enrichment mode')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for openai_compatible enrichment mode')

    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    client = OpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        client=client,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, sense: SenseRecord, settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> EnrichmentRecord:
        response, _ = _generate_validated_single_sense_payload_with_stats(
            client=client,
            lexeme=lexeme,
            sense=sense,
            max_transient_retries=transient_retries,
            max_validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
        return _build_enrichment_record(
            lexeme=lexeme,
            sense=sense,
            response=response,
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            review_status=review_status,
            generated_at=generated_at,
        )

    return provider


def build_openai_compatible_word_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    client: Any | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> WordEnrichmentProvider:
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for openai_compatible enrichment mode')
    if not (model_name or settings.llm_model):
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for openai_compatible enrichment mode')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for openai_compatible enrichment mode')

    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    client = OpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        client=client,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> list[EnrichmentRecord]:
        ordered_senses = sorted(senses, key=lambda item: item.sense_order)
        response = _generate_validated_word_payload(
            client=client,
            lexeme=lexeme,
            senses=ordered_senses,
            prompt_mode="word_only",
            max_transient_retries=transient_retries,
            max_validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
        outcome = _build_word_job_outcome(
            lexeme=lexeme,
            response=response,
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            review_status=review_status,
            generated_at=generated_at,
        )
        _validate_compiled_word_outcome(lexeme=lexeme, outcome=outcome)
        return outcome

    return provider


def build_openai_compatible_phrase_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    client: Any | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> WordEnrichmentProvider:
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for openai_compatible enrichment mode')
    if not (model_name or settings.llm_model):
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for openai_compatible enrichment mode')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for openai_compatible enrichment mode')

    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    client = OpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        client=client,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> WordJobOutcome:
        del senses
        response, _ = _generate_validated_phrase_payload_with_stats(
            client=client,
            lexeme=lexeme,
            max_transient_retries=transient_retries,
            max_validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
        return _build_phrase_job_outcome(
            lexeme=lexeme,
            response=response,
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            review_status=review_status,
            generated_at=generated_at,
        )

    return provider


def build_openai_compatible_node_phrase_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    runner: NodeRunner | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> WordEnrichmentProvider:
    if not settings.llm_base_url:
        raise LexiconDependencyError('LEXICON_LLM_BASE_URL is required for openai_compatible_node enrichment mode')
    if not (model_name or settings.llm_model):
        raise LexiconDependencyError('LEXICON_LLM_MODEL is required for openai_compatible_node enrichment mode')
    if not settings.llm_api_key:
        raise LexiconDependencyError('LEXICON_LLM_API_KEY is required for openai_compatible_node enrichment mode')

    effective_model_name = model_name or settings.llm_model
    effective_reasoning_effort = reasoning_effort or settings.llm_reasoning_effort
    client = NodeOpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        runner=runner,
        timeout_seconds=settings.llm_timeout_seconds,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> WordJobOutcome:
        del senses
        response, _ = _generate_validated_phrase_payload_with_stats(
            client=client,
            lexeme=lexeme,
            max_transient_retries=transient_retries,
            max_validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
        return _build_phrase_job_outcome(
            lexeme=lexeme,
            response=response,
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            review_status=review_status,
            generated_at=generated_at,
        )

    return provider


def build_enrichment_provider(
    *,
    settings: LexiconSettings,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    client: Any | None = None,
    runner: NodeRunner | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> EnrichmentProvider:
    if provider_mode not in _PROVIDER_MODES:
        raise ValueError(f'Unsupported provider mode: {provider_mode}')
    if provider_mode == 'placeholder':
        return build_placeholder_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)
    if provider_mode == 'openai_compatible':
        return build_openai_compatible_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            client=client,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    if provider_mode == 'openai_compatible_node':
        return build_openai_compatible_node_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            runner=runner,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        if settings.llm_transport == 'node':
            return build_openai_compatible_node_enrichment_provider(
                settings=settings,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                review_status=review_status,
                runner=runner,
                transient_retries=transient_retries,
                validation_retries=validation_retries,
                runtime_logger=runtime_logger,
            )
        return build_openai_compatible_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            client=client,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    return build_placeholder_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)


def build_word_enrichment_provider(
    *,
    settings: LexiconSettings,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    client: Any | None = None,
    runner: NodeRunner | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> WordEnrichmentProvider:
    if provider_mode not in _PROVIDER_MODES:
        raise ValueError(f'Unsupported provider mode: {provider_mode}')
    if provider_mode == 'placeholder':
        return build_placeholder_word_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)
    if provider_mode == 'openai_compatible':
        return build_openai_compatible_word_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            client=client,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    if provider_mode == 'openai_compatible_node':
        return build_openai_compatible_node_word_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            runner=runner,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        if settings.llm_transport == 'node':
            return build_openai_compatible_node_word_enrichment_provider(
                settings=settings,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                review_status=review_status,
                runner=runner,
                transient_retries=transient_retries,
                validation_retries=validation_retries,
                runtime_logger=runtime_logger,
            )
        return build_openai_compatible_word_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            client=client,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    return build_placeholder_word_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)


def build_phrase_enrichment_provider(
    *,
    settings: LexiconSettings,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    client: Any | None = None,
    runner: NodeRunner | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    runtime_logger: RuntimeLogger | None = None,
) -> WordEnrichmentProvider:
    if provider_mode not in _PROVIDER_MODES:
        raise ValueError(f'Unsupported provider mode: {provider_mode}')
    if provider_mode == 'placeholder':
        return build_placeholder_word_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)
    if provider_mode == 'openai_compatible':
        return build_openai_compatible_phrase_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            client=client,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    if provider_mode == 'openai_compatible_node':
        return build_openai_compatible_node_phrase_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            runner=runner,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        if settings.llm_transport == 'node':
            return build_openai_compatible_node_phrase_enrichment_provider(
                settings=settings,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                review_status=review_status,
                runner=runner,
                transient_retries=transient_retries,
                validation_retries=validation_retries,
                runtime_logger=runtime_logger,
            )
        return build_openai_compatible_phrase_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            client=client,
            transient_retries=transient_retries,
            validation_retries=validation_retries,
            runtime_logger=runtime_logger,
        )
    return build_placeholder_word_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)


def _build_phrase_lexeme(row: dict[str, Any]) -> LexemeRecord:
    source_refs = [
        str(item.get("source") or "").strip()
        for item in list(row.get("source_provenance") or [])
        if isinstance(item, dict) and str(item.get("source") or "").strip()
    ] or ["phrase_seed"]
    display_form = str(row.get("display_form") or row.get("normalized_form") or "").strip()
    normalized_form = str(row.get("normalized_form") or display_form).strip().lower()
    return LexemeRecord(
        snapshot_id=str(row.get("snapshot_id") or ""),
        lexeme_id=str(row.get("entry_id") or ""),
        lemma=display_form or normalized_form,
        language=str(row.get("language") or "en"),
        wordfreq_rank=int(row.get("frequency_rank") or 0),
        is_wordnet_backed=False,
        source_refs=source_refs,
        created_at=str(row.get("created_at") or _utc_now()),
        entry_id=str(row.get("entry_id") or ""),
        entry_type="phrase",
        normalized_form=normalized_form,
        source_provenance=list(row.get("source_provenance") or []),
        display_form=display_form or normalized_form,
        phrase_kind=str(row.get("phrase_kind") or "multiword_expression"),
        seed_metadata=dict(row.get("seed_metadata") or {}),
    )


def read_snapshot_inputs(snapshot_dir: Path) -> tuple[list[LexemeRecord], list[SenseRecord]]:
    lexemes_path = snapshot_dir / 'lexemes.jsonl'
    lexemes = [LexemeRecord(**row) for row in read_jsonl(lexemes_path)] if lexemes_path.exists() else []
    phrases_path = snapshot_dir / 'phrases.jsonl'
    if phrases_path.exists():
        lexemes.extend(_build_phrase_lexeme(row) for row in read_jsonl(phrases_path))
    senses_path = snapshot_dir / 'senses.jsonl'
    senses = [SenseRecord(**row) for row in read_jsonl(senses_path)] if senses_path.exists() else []
    return lexemes, senses


def _read_jsonl_if_exists(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return read_jsonl(path)


def _load_completed_lexeme_ids(checkpoint_path: Path) -> set[str]:
    completed: set[str] = set()
    for row in _read_jsonl_if_exists(checkpoint_path):
        if str(row.get('status') or '') == 'completed' and row.get('lexeme_id'):
            completed.add(str(row['lexeme_id']))
    return completed


def _load_failed_lexeme_ids(failures_path: Path) -> set[str]:
    return {
        str(row['lexeme_id'])
        for row in _read_jsonl_if_exists(failures_path)
        if str(row.get('status') or '') == 'failed' and row.get('lexeme_id')
    }


def _load_existing_output_rows(output_path: Path) -> list[dict[str, Any]]:
    if not output_path.exists():
        return []
    return [dict(row) for row in read_jsonl(output_path)]


def _reconcile_decisions_output(
    decisions_path: Path,
    *,
    completed_lexeme_ids: set[str],
) -> None:
    if not decisions_path.exists():
        return
    reconciled_rows = [
        row for row in read_jsonl(decisions_path)
        if str(row.get('lexeme_id') or '') in completed_lexeme_ids
    ]
    write_jsonl(decisions_path, reconciled_rows)


def _coerce_word_job_outcome(result: WordJobOutcome | list[EnrichmentRecord]) -> WordJobOutcome:
    if isinstance(result, WordJobOutcome):
        return result
    records = list(result)
    decision = records[0].decision if records else 'discard'
    base_word = records[0].base_word if records else None
    return WordJobOutcome(
        records=records,
        decision=decision,
        base_word=base_word,
        discard_reason=None,
        phonetics=records[0].phonetics if records else None,
    )


def _reconcile_resumable_output(
    output_path: Path,
    *,
    completed_lexeme_ids: set[str],
    lexeme_id_by_entry_id: dict[str, str],
) -> None:
    if not output_path.exists():
        return
    reconciled_rows: list[dict[str, Any]] = []
    for row in read_jsonl(output_path):
        lexeme_id = lexeme_id_by_entry_id.get(str(row.get('entry_id') or ''))
        if lexeme_id and lexeme_id in completed_lexeme_ids:
            reconciled_rows.append(row)
    write_jsonl(output_path, reconciled_rows)


def _append_completed_lexeme_records(
    output_path: Path,
    decisions_path: Path,
    checkpoint_path: Path,
    *,
    lexeme: LexemeRecord,
    outcome: WordJobOutcome,
    generation_run_id: str,
    completed_lexeme_ids: set[str],
    runtime_logger: RuntimeLogger | None = None,
) -> None:
    completed_at = _utc_now()
    compiled_row = _compiled_row_from_outcome(lexeme=lexeme, outcome=outcome)
    if compiled_row is not None:
        append_jsonl(output_path, [compiled_row])
    _write_per_word_decision(
        decisions_path,
        lexeme=lexeme,
        generation_run_id=generation_run_id,
        completed_at=completed_at,
        outcome=outcome,
    )
    _write_per_word_checkpoint(
        checkpoint_path,
        lexeme=lexeme,
        generation_run_id=generation_run_id,
        completed_at=completed_at,
    )
    completed_lexeme_ids.add(lexeme.lexeme_id)
    _emit_lexeme_event(
        runtime_logger,
        'lexeme-complete',
        'Lexeme completed',
        lexeme=lexeme,
        status='completed',
        accepted_sense_count=len(outcome.records),
    )


def _compiled_row_from_outcome(*, lexeme: LexemeRecord, outcome: WordJobOutcome) -> dict[str, Any] | None:
    compiled = compile_word_result(lexeme=lexeme, enrichments=outcome.records)
    if compiled is None:
        return None
    return compiled.to_dict()


def _validate_compiled_word_outcome(*, lexeme: LexemeRecord, outcome: WordJobOutcome) -> None:
    compiled_row = _compiled_row_from_outcome(lexeme=lexeme, outcome=outcome)
    if compiled_row is None:
        return
    review_row = build_review_prep_rows([compiled_row], origin="realtime")[0]
    if str(review_row.get("verdict") or "").strip().lower() == "pass":
        return
    messages = [
        *(str(item) for item in (review_row.get("reasons") or []) if str(item).strip()),
        *(str(item) for item in (review_row.get("warning_labels") or []) if str(item).strip()),
    ]
    if not messages and review_row.get("review_notes"):
        messages.append(str(review_row["review_notes"]))
    raise RuntimeError("compiled QC failed: " + "; ".join(messages or ["unknown validation error"]))


def _write_per_word_decision(
    decisions_path: Path,
    *,
    lexeme: LexemeRecord,
    generation_run_id: str,
    completed_at: str,
    outcome: WordJobOutcome,
) -> None:
    append_jsonl(decisions_path, [{
        'lexeme_id': lexeme.lexeme_id,
        'lemma': lexeme.lemma,
        'status': 'completed',
        'generation_run_id': generation_run_id,
        'completed_at': completed_at,
        'decision': outcome.decision,
        'base_word': outcome.base_word,
        'discard_reason': outcome.discard_reason,
        'accepted_sense_count': len(outcome.records),
    }])


def _write_per_word_checkpoint(checkpoint_path: Path, *, lexeme: LexemeRecord, generation_run_id: str, completed_at: str) -> None:
    append_jsonl(checkpoint_path, [{
        'lexeme_id': lexeme.lexeme_id,
        'lemma': lexeme.lemma,
        'status': 'completed',
        'generation_run_id': generation_run_id,
        'completed_at': completed_at,
    }])


def _write_per_word_failure(failures_output: Path, *, lexeme: LexemeRecord, generation_run_id: str, error_message: str, failed_at: str) -> None:
    append_jsonl(failures_output, [{
        'lexeme_id': lexeme.lexeme_id,
        'entry_id': lexeme.entry_id,
        'entry_type': lexeme.entry_type,
        'lemma': lexeme.lemma,
        'display_form': lexeme.display_form,
        'normalized_form': lexeme.normalized_form,
        'phrase_kind': lexeme.phrase_kind,
        'status': 'failed',
        'generation_run_id': generation_run_id,
        'failed_at': failed_at,
        'error': error_message,
    }])


def enrich_snapshot(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    word_provider: WordEnrichmentProvider | None = None,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    generated_at: str | None = None,
    generation_run_id: str | None = None,
    prompt_version: str = 'v1',
    review_status: str = 'draft',
    provider_mode: str = 'auto',
    reasoning_effort: str | None = None,
    mode: str = 'per_word',
    max_concurrency: int = 1,
    resume: bool = False,
    retry_failed_only: bool = False,
    skip_failed: bool = False,
    checkpoint_path: Path | None = None,
    failures_output: Path | None = None,
    max_failures: int | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    log_level: str = 'info',
    log_file: Path | None = None,
    request_delay_seconds: float = 0.0,
    max_new_completed_lexemes: int | None = None,
) -> list[EnrichmentRecord]:
    if mode != 'per_word':
        raise ValueError(f'Unsupported enrichment mode: {mode}')
    _validate_resume_mode_flags(resume=resume, retry_failed_only=retry_failed_only, skip_failed=skip_failed)
    effective_settings = settings or LexiconSettings.from_env()
    effective_generated_at = generated_at or _utc_now()
    effective_generation_run_id = generation_run_id or f'enrich-{effective_generated_at}'
    runtime_logger = _build_runtime_logger(snapshot_dir=snapshot_dir, log_level=log_level, log_file=log_file)
    lexemes, senses = read_snapshot_inputs(snapshot_dir)
    lexemes_by_id = {lexeme.lexeme_id: lexeme for lexeme in lexemes}
    senses_by_lexeme: dict[str, list[SenseRecord]] = {}
    for sense in senses:
        senses_by_lexeme.setdefault(sense.lexeme_id, []).append(sense)

    destination = output_path or snapshot_dir / 'words.enriched.jsonl'
    effective_max_concurrency = max(1, int(max_concurrency or 1))
    effective_request_delay_seconds = max(0.0, float(request_delay_seconds or 0.0))
    checkpoint_destination = checkpoint_path or snapshot_dir / 'enrich.checkpoint.jsonl'
    failures_destination = failures_output or snapshot_dir / 'enrich.failures.jsonl'
    decisions_destination = snapshot_dir / 'enrich.decisions.jsonl'
    effective_max_failures = None if max_failures is None else max(1, int(max_failures))
    effective_max_new_completed_lexemes = (
        None
        if max_new_completed_lexemes is None
        else max(1, int(max_new_completed_lexemes))
    )
    word_enrichment_provider = word_provider or build_word_enrichment_provider(
        settings=effective_settings,
        provider_mode=provider_mode,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        review_status=review_status,
        client=None,
        transient_retries=transient_retries,
        validation_retries=validation_retries,
        runtime_logger=runtime_logger,
    )
    phrase_enrichment_provider = build_phrase_enrichment_provider(
        settings=effective_settings,
        provider_mode=provider_mode,
        model_name=model_name,
        reasoning_effort=reasoning_effort,
        review_status=review_status,
        client=None,
        transient_retries=transient_retries,
        validation_retries=validation_retries,
        runtime_logger=runtime_logger,
    )
    ordered_lexemes = sorted(lexemes, key=lambda item: (item.wordfreq_rank, item.lemma))
    ordered_sense_lists = {
        lexeme.lexeme_id: sorted(senses_by_lexeme.get(lexeme.lexeme_id, []), key=lambda item: item.sense_order)
        for lexeme in ordered_lexemes
    }
    lexeme_id_by_entry_id = {lexeme.entry_id: lexeme.lexeme_id for lexeme in ordered_lexemes}
    completed_lexeme_ids = _load_completed_lexeme_ids(checkpoint_destination) if resume else set()
    load_failed_lexeme_ids = resume and (retry_failed_only or skip_failed)
    failed_lexeme_ids = _load_failed_lexeme_ids(failures_destination) if load_failed_lexeme_ids else set()
    unresolved_failed_lexeme_ids = failed_lexeme_ids - completed_lexeme_ids
    completed_count_before_run = len(completed_lexeme_ids)
    if resume:
        _reconcile_resumable_output(
            destination,
            completed_lexeme_ids=completed_lexeme_ids,
            lexeme_id_by_entry_id=lexeme_id_by_entry_id,
        )
        _reconcile_decisions_output(
            decisions_destination,
            completed_lexeme_ids=completed_lexeme_ids,
        )
    if resume and retry_failed_only:
        pending_lexemes = [lexeme for lexeme in ordered_lexemes if lexeme.lexeme_id in unresolved_failed_lexeme_ids]
    elif resume and skip_failed:
        pending_lexemes = [
            lexeme
            for lexeme in ordered_lexemes
            if lexeme.lexeme_id not in completed_lexeme_ids and lexeme.lexeme_id not in unresolved_failed_lexeme_ids
        ]
    else:
        pending_lexemes = [lexeme for lexeme in ordered_lexemes if lexeme.lexeme_id not in completed_lexeme_ids]
    if not resume:
        write_jsonl(destination, [])
        write_jsonl(checkpoint_destination, [])
        write_jsonl(failures_destination, [])
        write_jsonl(decisions_destination, [])
        completed_count_before_run = 0

    failures: list[str] = []
    request_start_lock = Lock()
    last_request_started_at = [0.0]

    def reached_completion_cap() -> bool:
        if effective_max_new_completed_lexemes is None:
            return False
        return (len(completed_lexeme_ids) - completed_count_before_run) >= effective_max_new_completed_lexemes

    def submission_capacity_remaining(future_map_size: int) -> bool:
        if effective_max_new_completed_lexemes is None:
            return True
        completed_this_run = len(completed_lexeme_ids) - completed_count_before_run
        return (completed_this_run + future_map_size) < effective_max_new_completed_lexemes

    def run_word_job(lexeme: LexemeRecord) -> WordJobOutcome:
        word_senses = ordered_sense_lists.get(lexeme.lexeme_id, [])
        _emit_lexeme_event(
            runtime_logger,
            'lexeme-start',
            'Lexeme processing started',
            lexeme=lexeme,
            sense_count=len(word_senses),
            mode=mode,
        )
        if effective_request_delay_seconds > 0:
            with request_start_lock:
                now = time.monotonic()
                wait_for = effective_request_delay_seconds - (now - last_request_started_at[0])
                if wait_for > 0:
                    time.sleep(wait_for)
                    now = time.monotonic()
                last_request_started_at[0] = now
        selected_provider = (
            word_provider
            if word_provider is not None
            else (phrase_enrichment_provider if lexeme.entry_type == "phrase" else word_enrichment_provider)
        )
        return _coerce_word_job_outcome(
            selected_provider(
                lexeme=lexeme,
                senses=word_senses,
                settings=effective_settings,
                generated_at=effective_generated_at,
                generation_run_id=effective_generation_run_id,
                prompt_version=prompt_version,
            )
        )

    def persist_completed(lexeme: LexemeRecord, outcome: WordJobOutcome) -> None:
        if lexeme.lexeme_id in completed_lexeme_ids:
            return
        _append_completed_lexeme_records(
            destination,
            decisions_destination,
            checkpoint_destination,
            lexeme=lexeme,
            outcome=outcome,
            generation_run_id=effective_generation_run_id,
            completed_lexeme_ids=completed_lexeme_ids,
            runtime_logger=runtime_logger,
        )

    def handle_failure(lexeme: LexemeRecord, exc: Exception) -> None:
        message = f'{lexeme.lemma}: {exc}'
        failures.append(message)
        _emit_lexeme_event(
            runtime_logger,
            'lexeme-failure',
            'Lexeme failed',
            lexeme=lexeme,
            error=str(exc),
        )
        _write_per_word_failure(
            failures_destination,
            lexeme=lexeme,
            generation_run_id=effective_generation_run_id,
            error_message=str(exc),
            failed_at=_utc_now(),
        )

    if effective_max_concurrency == 1:
        for lexeme in pending_lexemes:
            if reached_completion_cap():
                break
            try:
                outcome = run_word_job(lexeme)
                persist_completed(lexeme, outcome)
                if reached_completion_cap():
                    break
            except Exception as exc:  # pragma: no cover - exercised via tests through raised summary
                handle_failure(lexeme, exc)
                if effective_max_failures is not None and len(failures) >= effective_max_failures:
                    break
    else:
        with ThreadPoolExecutor(max_workers=effective_max_concurrency) as executor:
            pending_iter = iter(pending_lexemes)
            future_map: dict[Any, LexemeRecord] = {}

            def submit_next() -> bool:
                if not submission_capacity_remaining(len(future_map)):
                    return False
                try:
                    lexeme = next(pending_iter)
                except StopIteration:
                    return False
                future_map[executor.submit(run_word_job, lexeme)] = lexeme
                return True

            while len(future_map) < effective_max_concurrency and submit_next():
                pass

            stop_submitting = False
            while future_map:
                future = next(as_completed(list(future_map)))
                lexeme = future_map.pop(future)
                try:
                    outcome = future.result()
                    persist_completed(lexeme, outcome)
                    if reached_completion_cap():
                        stop_submitting = True
                except Exception as exc:  # pragma: no cover - exercised via tests through raised summary
                    handle_failure(lexeme, exc)
                    if effective_max_failures is not None and len(failures) >= effective_max_failures:
                        stop_submitting = True
                if stop_submitting:
                    continue
                while len(future_map) < effective_max_concurrency and submit_next():
                    pass

    if failures:
        raise RuntimeError('Per-word enrichment failed for ' + '; '.join(sorted(failures)))

    if resume:
        return _load_existing_output_rows(destination)

    return _load_existing_output_rows(destination)


def run_enrichment(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    word_provider: WordEnrichmentProvider | None = None,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    generated_at: str | None = None,
    generation_run_id: str | None = None,
    prompt_version: str = 'v1',
    review_status: str = 'draft',
    provider_mode: str = 'auto',
    reasoning_effort: str | None = None,
    mode: str = 'per_word',
    max_concurrency: int = 1,
    resume: bool = False,
    retry_failed_only: bool = False,
    skip_failed: bool = False,
    checkpoint_path: Path | None = None,
    failures_output: Path | None = None,
    max_failures: int | None = None,
    transient_retries: int = _DEFAULT_WORD_TRANSIENT_RETRIES,
    validation_retries: int = _DEFAULT_WORD_REPAIR_ATTEMPTS,
    log_level: str = 'info',
    log_file: Path | None = None,
    request_delay_seconds: float = 0.0,
    max_new_completed_lexemes: int | None = None,
) -> EnrichmentRunResult:
    if mode != 'per_word':
        raise ValueError(f'Unsupported enrichment mode: {mode}')
    _validate_resume_mode_flags(resume=resume, retry_failed_only=retry_failed_only, skip_failed=skip_failed)
    destination = output_path or snapshot_dir / 'words.enriched.jsonl'
    lexemes, _ = read_snapshot_inputs(snapshot_dir)
    enrichments = enrich_snapshot(
        snapshot_dir,
        output_path=destination,
        word_provider=word_provider,
        settings=settings,
        model_name=model_name,
        generated_at=generated_at,
        generation_run_id=generation_run_id,
        prompt_version=prompt_version,
        review_status=review_status,
        provider_mode=provider_mode,
        reasoning_effort=reasoning_effort,
        mode=mode,
        max_concurrency=max_concurrency,
        resume=resume,
        retry_failed_only=retry_failed_only,
        skip_failed=skip_failed,
        checkpoint_path=checkpoint_path,
        failures_output=failures_output,
        max_failures=max_failures,
        transient_retries=transient_retries,
        validation_retries=validation_retries,
        log_level=log_level,
        log_file=log_file,
        request_delay_seconds=request_delay_seconds,
        max_new_completed_lexemes=max_new_completed_lexemes,
    )
    return EnrichmentRunResult(output_path=destination, enrichments=enrichments, lexeme_count=len(lexemes), mode=mode)
