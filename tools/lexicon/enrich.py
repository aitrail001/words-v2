from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import math
import shutil
import subprocess
from urllib import error, request

from tools.lexicon.config import LexiconSettings
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.ids import make_enrichment_id
from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord

EnrichmentProvider = Callable[..., EnrichmentRecord]
WordEnrichmentProvider = Callable[..., list[EnrichmentRecord]]
Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
NodeRunner = Callable[[dict[str, Any]], dict[str, Any]]
_PROVIDER_MODES = {"auto", "placeholder", "openai_compatible", "openai_compatible_node"}
_ENRICHMENT_MODES = {"per_sense", "per_word"}
_ALLOWED_CEFR_LEVELS = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}
_ALLOWED_REGISTERS = {'neutral', 'formal', 'informal'}
_STRING_LIST_FIELDS = ('secondary_domains', 'synonyms', 'antonyms', 'collocations', 'grammar_patterns')
_REQUIRED_TRANSLATION_LOCALES = ('zh-Hans', 'es', 'ar', 'pt-BR', 'ja')
_NODE_RUN_TIMEOUT_SECONDS = 60


@dataclass(frozen=True)
class EnrichmentRunResult:
    output_path: Path
    enrichments: list[EnrichmentRecord]
    lexeme_count: int = 0
    mode: str = "per_sense"


class OpenAICompatibleResponsesClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        transport: Transport | None = None,
        timeout_seconds: int = 60,
        reasoning_effort: str | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.transport = transport or _default_transport
        self.timeout_seconds = timeout_seconds
        self.reasoning_effort = reasoning_effort

    def responses_url(self) -> str:
        if self.endpoint.endswith("/responses"):
            return self.endpoint
        return f"{self.endpoint}/responses"

    def generate_json(self, prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "instructions": _SYSTEM_PROMPT,
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
        }
        if self.reasoning_effort:
            payload["reasoning"] = {"effort": self.reasoning_effort}
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        response = self.transport(self.responses_url(), payload, headers)
        text = _extract_output_text(response)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI-compatible endpoint returned non-JSON enrichment output") from exc


def _default_transport(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    encoded = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=encoded, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI-compatible endpoint request failed with status {exc.code}: {body}") from exc
    except error.URLError as exc:
        raise RuntimeError(f"OpenAI-compatible endpoint request failed: {exc.reason}") from exc


def _default_node_runner(payload: dict[str, Any]) -> dict[str, Any]:
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
            timeout=_NODE_RUN_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f'Node OpenAI-compatible transport timed out after {_NODE_RUN_TIMEOUT_SECONDS} seconds'
        ) from exc
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip() or 'Node OpenAI-compatible transport failed'
        raise RuntimeError(message)
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError('Node OpenAI-compatible transport returned non-JSON output') from exc


class NodeOpenAICompatibleResponsesClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        runner: NodeRunner | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self.endpoint = endpoint.rstrip('/')
        self.api_key = api_key
        self.model = model
        self.runner = runner or _default_node_runner
        self.reasoning_effort = reasoning_effort

    def generate_json(self, prompt: str) -> dict[str, Any]:
        payload = {
            'base_url': self.endpoint,
            'api_key': self.api_key,
            'model': self.model,
            'prompt': prompt,
            'system_prompt': _SYSTEM_PROMPT,
        }
        if self.reasoning_effort:
            payload['reasoning_effort'] = self.reasoning_effort
        response = self.runner(payload)
        text = _extract_output_text(response)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError('OpenAI-compatible node endpoint returned non-JSON enrichment output') from exc


_SYSTEM_PROMPT = (
    "You are enriching English vocabulary records for learners. "
    "Return only a single JSON object matching the requested schema."
)


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


def build_enrichment_prompt(*, lexeme: LexemeRecord, sense: SenseRecord) -> str:
    schema_hint = {
        'definition': 'string',
        'examples': [{'sentence': 'string', 'difficulty': 'A1|A2|B1|B2|C1|C2'}],
        'cefr_level': 'A1|A2|B1|B2|C1|C2',
        'primary_domain': 'string',
        'secondary_domains': ['string'],
        'register': 'neutral|formal|informal',
        'synonyms': ['string'],
        'antonyms': ['string'],
        'collocations': ['string'],
        'grammar_patterns': ['string'],
        'usage_note': 'string',
        'forms': {
            'plural_forms': ['string'],
            'verb_forms': {'base': 'string', 'third_person_singular': 'string', 'past': 'string', 'past_participle': 'string', 'gerund': 'string'},
            'comparative': 'string|null',
            'superlative': 'string|null',
            'derivations': ['string'],
        },
        'confusable_words': [{'word': 'string', 'note': 'string'}],
        'confidence': 'number',
        'translations': {locale: {'definition': 'string', 'usage_note': 'string', 'examples': ['string']} for locale in _REQUIRED_TRANSLATION_LOCALES},
    }
    return (
        f"Generate learner-facing enrichment for the English word '{lexeme.lemma}'.\n"
        f"Part of speech: {sense.part_of_speech}.\n"
        f"Canonical gloss: {sense.canonical_gloss}.\n"
        f"Word frequency rank: {lexeme.wordfreq_rank}.\n"
        f"Return JSON only with this schema: {json.dumps(schema_hint)}"
    )


def _extract_output_text(response_payload: dict[str, Any]) -> str:
    if isinstance(response_payload.get('output_text'), str):
        return response_payload['output_text']
    for item in response_payload.get('output', []):
        for content in item.get('content', []):
            if content.get('type') in {'output_text', 'text'} and isinstance(content.get('text'), str):
                return content['text']
    raise RuntimeError('OpenAI-compatible endpoint response did not contain output text')


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
        if not isinstance(item, str) or not item.strip():
            raise _payload_error(f'{field}[{index}]', 'must be a non-empty string')
        normalized.append(item.strip())
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
    if not isinstance(response, dict):
        raise RuntimeError('OpenAI-compatible endpoint returned a non-object enrichment payload')

    normalized = dict(response)
    normalized['definition'] = _require_non_empty_string(response.get('definition'), field='definition')
    normalized['examples'] = _validate_examples(response.get('examples'))
    normalized['confidence'] = _validate_confidence(response.get('confidence'))
    normalized['cefr_level'] = _validate_optional_enum(response.get('cefr_level'), field='cefr_level', allowed=_ALLOWED_CEFR_LEVELS)
    normalized['register'] = _validate_optional_enum(response.get('register'), field='register', allowed=_ALLOWED_REGISTERS)
    for field in _STRING_LIST_FIELDS:
        normalized[field] = _validate_string_list_field(response.get(field), field=field)
    normalized['forms'] = _validate_forms(response.get('forms'))
    normalized['confusable_words'] = _validate_confusable_words(response.get('confusable_words'))
    normalized['translations'] = _validate_translations(response.get('translations'), example_count=len(normalized['examples']))
    return normalized


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
    if rank <= 5000:
        return 8
    if rank <= 10000:
        return 6
    return 4

def _word_enrichment_grounding_payload(*, senses: list[SenseRecord]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
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
    schema_hint = {
        'senses': [
            {
                'sense_id': 'string',
                'definition': 'string',
                'examples': [{'sentence': 'string', 'difficulty': 'A1|A2|B1|B2|C1|C2'}],
                'cefr_level': 'A1|A2|B1|B2|C1|C2',
                'primary_domain': 'string',
                'secondary_domains': ['string'],
                'register': 'neutral|formal|informal',
                'synonyms': ['string'],
                'antonyms': ['string'],
                'collocations': ['string'],
                'grammar_patterns': ['string'],
                'usage_note': 'string',
                'forms': {
                    'plural_forms': ['string'],
                    'verb_forms': {'base': 'string', 'third_person_singular': 'string', 'past': 'string', 'past_participle': 'string', 'gerund': 'string'},
                    'comparative': 'string|null',
                    'superlative': 'string|null',
                    'derivations': ['string'],
                },
                'confusable_words': [{'word': 'string', 'note': 'string'}],
                'confidence': 'number',
                'translations': {locale: {'definition': 'string', 'usage_note': 'string', 'examples': ['string']} for locale in _REQUIRED_TRANSLATION_LOCALES},
            }
        ]
    }
    return sense_rows, schema_hint


def build_word_enrichment_prompt(*, lexeme: LexemeRecord, senses: list[SenseRecord]) -> str:
    sense_rows, schema_hint = _word_enrichment_grounding_payload(senses=senses)
    max_meanings = learner_meaning_cap(lexeme.wordfreq_rank)
    return (
        f"Generate learner-facing enrichment for the English word '{lexeme.lemma}'.\n"
        f"Word frequency rank: {lexeme.wordfreq_rank}.\n"
        f"Use these WordNet-grounded candidate senses as grounding context only: {json.dumps(sense_rows)}\n"
        f"Select at most {max_meanings} learner-friendly meanings. You may omit weak tail senses.\n"
        f"The response is invalid if the senses array contains more than {max_meanings} items.\n"
        f"If more than {max_meanings} candidates seem useful, keep only the strongest {max_meanings}.\n"
        "Do not invent new sense IDs. Reuse only sense_id values from the provided grounding context.\n"
        "Return a JSON object only. No prose, no markdown, no code fences, and no extra keys outside the schema.\n"
        f"Return JSON only with this schema: {json.dumps(schema_hint)}"
    )


def build_word_enrichment_repair_prompt(*, lexeme: LexemeRecord, senses: list[SenseRecord], previous_error: str) -> str:
    sense_rows, schema_hint = _word_enrichment_grounding_payload(senses=senses)
    max_meanings = learner_meaning_cap(lexeme.wordfreq_rank)
    return (
        f"Repair the previous learner-facing enrichment response for the English word '{lexeme.lemma}'.\n"
        f"The previous response was invalid: {previous_error}\n"
        f"Use these WordNet-grounded candidate senses as grounding context only: {json.dumps(sense_rows)}\n"
        f"Select at most {max_meanings} learner-friendly meanings.\n"
        f"The response is invalid if the senses array contains more than {max_meanings} items.\n"
        f"If more than {max_meanings} candidates seem useful, keep only the strongest {max_meanings}.\n"
        "Do not invent new sense IDs. Reuse only sense_id values from the provided grounding context.\n"
        "Return a JSON object only. No prose, no markdown, no code fences, and no extra keys outside the schema.\n"
        f"Return JSON only with this schema: {json.dumps(schema_hint)}"
    )


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


def _generate_validated_word_payload(
    *,
    client: OpenAICompatibleResponsesClient | NodeOpenAICompatibleResponsesClient,
    lexeme: LexemeRecord,
    senses: list[SenseRecord],
) -> list[dict[str, Any]]:
    try:
        first_response = client.generate_json(build_word_enrichment_prompt(lexeme=lexeme, senses=senses))
        return _validate_openai_compatible_word_payload(first_response, lexeme=lexeme, senses=senses)
    except RuntimeError as exc:
        if not _is_repairable_word_payload_error(exc):
            raise
        repair_response = client.generate_json(
            build_word_enrichment_repair_prompt(
                lexeme=lexeme,
                senses=senses,
                previous_error=str(exc),
            )
        )
        return _validate_openai_compatible_word_payload(repair_response, lexeme=lexeme, senses=senses)


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
    )


def _validate_openai_compatible_word_payload(response: dict[str, Any], *, lexeme: LexemeRecord, senses: list[SenseRecord]) -> list[dict[str, Any]]:
    if not isinstance(response, dict):
        raise RuntimeError('OpenAI-compatible endpoint returned a non-object word enrichment payload')
    value = response.get('senses')
    if not isinstance(value, list) or not value:
        raise RuntimeError("OpenAI-compatible word enrichment payload field 'senses' must be a non-empty list")

    max_meanings = learner_meaning_cap(lexeme.wordfreq_rank)
    if len(value) > max_meanings:
        raise RuntimeError(
            f"OpenAI-compatible word enrichment payload must select at most {max_meanings} learner-friendly meanings for frequency rank {lexeme.wordfreq_rank}"
        )

    expected_set = {sense.sense_id for sense in sorted(senses, key=lambda item: item.sense_order)}
    normalized_rows: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise RuntimeError(f"OpenAI-compatible word enrichment payload field 'senses[{index}]' must be an object")
        sense_id = _require_non_empty_string(item.get('sense_id'), field=f'senses[{index}].sense_id')
        if sense_id not in expected_set:
            raise RuntimeError(f"OpenAI-compatible word enrichment payload returned unknown sense_id '{sense_id}'")
        if sense_id in seen_ids:
            raise RuntimeError(f"OpenAI-compatible word enrichment payload returned duplicate sense_id '{sense_id}'")
        seen_ids.add(sense_id)
        normalized = _validate_openai_compatible_payload(item)
        normalized['sense_id'] = sense_id
        normalized_rows.append(normalized)

    return normalized_rows


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
        )

    return provider


def build_placeholder_word_enrichment_provider(
    *,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    review_status: str = 'draft',
) -> WordEnrichmentProvider:
    sense_provider = build_placeholder_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> list[EnrichmentRecord]:
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
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, sense: SenseRecord, settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> EnrichmentRecord:
        response = _validate_openai_compatible_payload(client.generate_json(build_enrichment_prompt(lexeme=lexeme, sense=sense)))
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
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> list[EnrichmentRecord]:
        ordered_senses = sorted(senses, key=lambda item: item.sense_order)
        response = _generate_validated_word_payload(client=client, lexeme=lexeme, senses=ordered_senses)
        sense_by_id = {sense.sense_id: sense for sense in ordered_senses}
        return [
            _build_enrichment_record(
                lexeme=lexeme,
                sense=sense_by_id[row['sense_id']],
                response=row,
                model_name=str(effective_model_name),
                prompt_version=prompt_version,
                generation_run_id=generation_run_id,
                review_status=review_status,
                generated_at=generated_at,
            )
            for row in response
        ]

    return provider


def build_openai_compatible_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    transport: Transport | None = None,
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
        transport=transport,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, sense: SenseRecord, settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> EnrichmentRecord:
        response = _validate_openai_compatible_payload(client.generate_json(build_enrichment_prompt(lexeme=lexeme, sense=sense)))
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
    transport: Transport | None = None,
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
        transport=transport,
        reasoning_effort=effective_reasoning_effort,
    )

    def provider(*, lexeme: LexemeRecord, senses: list[SenseRecord], settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> list[EnrichmentRecord]:
        ordered_senses = sorted(senses, key=lambda item: item.sense_order)
        response = _generate_validated_word_payload(client=client, lexeme=lexeme, senses=ordered_senses)
        sense_by_id = {sense.sense_id: sense for sense in ordered_senses}
        return [
            _build_enrichment_record(
                lexeme=lexeme,
                sense=sense_by_id[row['sense_id']],
                response=row,
                model_name=str(effective_model_name),
                prompt_version=prompt_version,
                generation_run_id=generation_run_id,
                review_status=review_status,
                generated_at=generated_at,
            )
            for row in response
        ]

    return provider


def build_enrichment_provider(
    *,
    settings: LexiconSettings,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    transport: Transport | None = None,
    runner: NodeRunner | None = None,
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
            transport=transport,
        )
    if provider_mode == 'openai_compatible_node':
        return build_openai_compatible_node_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            runner=runner,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        if settings.llm_transport == 'node':
            return build_openai_compatible_node_enrichment_provider(
                settings=settings,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                review_status=review_status,
                runner=runner,
            )
        return build_openai_compatible_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            transport=transport,
        )
    return build_placeholder_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)


def build_word_enrichment_provider(
    *,
    settings: LexiconSettings,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    reasoning_effort: str | None = None,
    review_status: str = 'draft',
    transport: Transport | None = None,
    runner: NodeRunner | None = None,
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
            transport=transport,
        )
    if provider_mode == 'openai_compatible_node':
        return build_openai_compatible_node_word_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            runner=runner,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        if settings.llm_transport == 'node':
            return build_openai_compatible_node_word_enrichment_provider(
                settings=settings,
                model_name=model_name,
                reasoning_effort=reasoning_effort,
                review_status=review_status,
                runner=runner,
            )
        return build_openai_compatible_word_enrichment_provider(
            settings=settings,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            transport=transport,
        )
    return build_placeholder_word_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)


def read_snapshot_inputs(snapshot_dir: Path) -> tuple[list[LexemeRecord], list[SenseRecord]]:
    lexemes = [LexemeRecord(**row) for row in read_jsonl(snapshot_dir / 'lexemes.jsonl')]
    senses = [SenseRecord(**row) for row in read_jsonl(snapshot_dir / 'senses.jsonl')]
    return lexemes, senses


def enrich_snapshot(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    provider: EnrichmentProvider | None = None,
    word_provider: WordEnrichmentProvider | None = None,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    generated_at: str | None = None,
    generation_run_id: str | None = None,
    prompt_version: str = 'v1',
    review_status: str = 'draft',
    provider_mode: str = 'auto',
    transport: Transport | None = None,
    reasoning_effort: str | None = None,
    mode: str = 'per_sense',
    max_concurrency: int = 1,
) -> list[EnrichmentRecord]:
    if mode not in _ENRICHMENT_MODES:
        raise ValueError(f'Unsupported enrichment mode: {mode}')
    effective_settings = settings or LexiconSettings.from_env()
    effective_generated_at = generated_at or _utc_now()
    effective_generation_run_id = generation_run_id or f'enrich-{effective_generated_at}'
    lexemes, senses = read_snapshot_inputs(snapshot_dir)
    lexemes_by_id = {lexeme.lexeme_id: lexeme for lexeme in lexemes}
    senses_by_lexeme: dict[str, list[SenseRecord]] = {}
    for sense in senses:
        senses_by_lexeme.setdefault(sense.lexeme_id, []).append(sense)

    if mode == 'per_sense':
        enrichment_provider = provider or build_enrichment_provider(
            settings=effective_settings,
            provider_mode=provider_mode,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            transport=transport,
        )
        enrichments: list[EnrichmentRecord] = []
        for sense in sorted(senses, key=lambda item: (item.lexeme_id, item.sense_order)):
            lexeme = lexemes_by_id.get(sense.lexeme_id)
            if lexeme is None:
                continue
            enrichments.append(
                enrichment_provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=effective_settings,
                    generated_at=effective_generated_at,
                    generation_run_id=effective_generation_run_id,
                    prompt_version=prompt_version,
                )
            )
    else:
        effective_max_concurrency = max(1, int(max_concurrency or 1))
        word_enrichment_provider = word_provider or build_word_enrichment_provider(
            settings=effective_settings,
            provider_mode=provider_mode,
            model_name=model_name,
            reasoning_effort=reasoning_effort,
            review_status=review_status,
            transport=transport,
        )
        ordered_lexemes = sorted(lexemes, key=lambda item: item.lemma)
        ordered_sense_lists = {
            lexeme.lexeme_id: sorted(senses_by_lexeme.get(lexeme.lexeme_id, []), key=lambda item: item.sense_order)
            for lexeme in ordered_lexemes
        }
        failures: list[str] = []
        per_lexeme_results: dict[str, list[EnrichmentRecord]] = {}

        def run_word_job(lexeme: LexemeRecord) -> list[EnrichmentRecord]:
            word_senses = ordered_sense_lists.get(lexeme.lexeme_id, [])
            if not word_senses:
                return []
            return word_enrichment_provider(
                lexeme=lexeme,
                senses=word_senses,
                settings=effective_settings,
                generated_at=effective_generated_at,
                generation_run_id=effective_generation_run_id,
                prompt_version=prompt_version,
            )

        if effective_max_concurrency == 1:
            for lexeme in ordered_lexemes:
                try:
                    per_lexeme_results[lexeme.lexeme_id] = run_word_job(lexeme)
                except Exception as exc:  # pragma: no cover - exercised via tests through raised summary
                    failures.append(f'{lexeme.lemma}: {exc}')
        else:
            with ThreadPoolExecutor(max_workers=effective_max_concurrency) as executor:
                future_map = {executor.submit(run_word_job, lexeme): lexeme for lexeme in ordered_lexemes}
                for future in as_completed(future_map):
                    lexeme = future_map[future]
                    try:
                        per_lexeme_results[lexeme.lexeme_id] = future.result()
                    except Exception as exc:  # pragma: no cover - exercised via tests through raised summary
                        failures.append(f'{lexeme.lemma}: {exc}')

        if failures:
            raise RuntimeError('Per-word enrichment failed for ' + '; '.join(sorted(failures)))

        enrichments = []
        for lexeme in ordered_lexemes:
            enrichments.extend(per_lexeme_results.get(lexeme.lexeme_id, []))

    destination = output_path or snapshot_dir / 'enrichments.jsonl'
    write_jsonl(destination, [record.to_dict() for record in enrichments])
    return enrichments


def run_enrichment(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    provider: EnrichmentProvider | None = None,
    word_provider: WordEnrichmentProvider | None = None,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    generated_at: str | None = None,
    generation_run_id: str | None = None,
    prompt_version: str = 'v1',
    review_status: str = 'draft',
    provider_mode: str = 'auto',
    transport: Transport | None = None,
    reasoning_effort: str | None = None,
    mode: str = 'per_sense',
    max_concurrency: int = 1,
) -> EnrichmentRunResult:
    destination = output_path or snapshot_dir / 'enrichments.jsonl'
    lexemes, _ = read_snapshot_inputs(snapshot_dir)
    enrichments = enrich_snapshot(
        snapshot_dir,
        output_path=destination,
        provider=provider,
        word_provider=word_provider,
        settings=settings,
        model_name=model_name,
        generated_at=generated_at,
        generation_run_id=generation_run_id,
        prompt_version=prompt_version,
        review_status=review_status,
        provider_mode=provider_mode,
        transport=transport,
        reasoning_effort=reasoning_effort,
        mode=mode,
        max_concurrency=max_concurrency,
    )
    return EnrichmentRunResult(output_path=destination, enrichments=enrichments, lexeme_count=len(lexemes), mode=mode)
