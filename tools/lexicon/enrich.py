from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
import json
import math
from urllib import error, request

from tools.lexicon.config import LexiconSettings
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.ids import make_enrichment_id
from tools.lexicon.jsonl_io import read_jsonl, write_jsonl
from tools.lexicon.models import EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord

EnrichmentProvider = Callable[..., EnrichmentRecord]
Transport = Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]]
_PROVIDER_MODES = {"auto", "placeholder", "openai_compatible"}
_ALLOWED_CEFR_LEVELS = {'A1', 'A2', 'B1', 'B2', 'C1', 'C2'}
_ALLOWED_REGISTERS = {'neutral', 'formal', 'informal'}
_STRING_LIST_FIELDS = ('secondary_domains', 'synonyms', 'antonyms', 'collocations', 'grammar_patterns')


@dataclass(frozen=True)
class EnrichmentRunResult:
    output_path: Path
    enrichments: list[EnrichmentRecord]


class OpenAICompatibleResponsesClient:
    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        transport: Transport | None = None,
        timeout_seconds: int = 60,
    ) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.transport = transport or _default_transport
        self.timeout_seconds = timeout_seconds

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
            model_name=effective_model_name,
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            confidence=0.5,
            review_status=review_status,
            generated_at=generated_at,
        )

    return provider


def build_openai_compatible_enrichment_provider(
    *,
    settings: LexiconSettings,
    model_name: str | None = None,
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
    client = OpenAICompatibleResponsesClient(
        endpoint=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=str(effective_model_name),
        transport=transport,
    )

    def provider(*, lexeme: LexemeRecord, sense: SenseRecord, settings: LexiconSettings, generated_at: str, generation_run_id: str, prompt_version: str) -> EnrichmentRecord:
        response = _validate_openai_compatible_payload(client.generate_json(build_enrichment_prompt(lexeme=lexeme, sense=sense)))
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
            model_name=str(effective_model_name),
            prompt_version=prompt_version,
            generation_run_id=generation_run_id,
            confidence=response['confidence'],
            review_status=review_status,
            generated_at=generated_at,
        )

    return provider


def build_enrichment_provider(
    *,
    settings: LexiconSettings,
    provider_mode: str = 'auto',
    model_name: str | None = None,
    review_status: str = 'draft',
    transport: Transport | None = None,
) -> EnrichmentProvider:
    if provider_mode not in _PROVIDER_MODES:
        raise ValueError(f'Unsupported provider mode: {provider_mode}')
    if provider_mode == 'placeholder':
        return build_placeholder_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)
    if provider_mode == 'openai_compatible':
        return build_openai_compatible_enrichment_provider(
            settings=settings,
            model_name=model_name,
            review_status=review_status,
            transport=transport,
        )
    if settings.llm_base_url and settings.llm_model and settings.llm_api_key:
        return build_openai_compatible_enrichment_provider(
            settings=settings,
            model_name=model_name,
            review_status=review_status,
            transport=transport,
        )
    return build_placeholder_enrichment_provider(settings=settings, model_name=model_name, review_status=review_status)


def read_snapshot_inputs(snapshot_dir: Path) -> tuple[list[LexemeRecord], list[SenseRecord]]:
    lexemes = [LexemeRecord(**row) for row in read_jsonl(snapshot_dir / 'lexemes.jsonl')]
    senses = [SenseRecord(**row) for row in read_jsonl(snapshot_dir / 'senses.jsonl')]
    return lexemes, senses


def enrich_snapshot(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    provider: EnrichmentProvider | None = None,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    generated_at: str | None = None,
    generation_run_id: str | None = None,
    prompt_version: str = 'v1',
    review_status: str = 'draft',
    provider_mode: str = 'auto',
    transport: Transport | None = None,
) -> list[EnrichmentRecord]:
    effective_settings = settings or LexiconSettings.from_env()
    effective_generated_at = generated_at or _utc_now()
    effective_generation_run_id = generation_run_id or f'enrich-{effective_generated_at}'
    lexemes, senses = read_snapshot_inputs(snapshot_dir)
    lexemes_by_id = {lexeme.lexeme_id: lexeme for lexeme in lexemes}
    enrichment_provider = provider or build_enrichment_provider(
        settings=effective_settings,
        provider_mode=provider_mode,
        model_name=model_name,
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

    destination = output_path or snapshot_dir / 'enrichments.jsonl'
    write_jsonl(destination, [record.to_dict() for record in enrichments])
    return enrichments


def run_enrichment(
    snapshot_dir: Path,
    *,
    output_path: Path | None = None,
    provider: EnrichmentProvider | None = None,
    settings: LexiconSettings | None = None,
    model_name: str | None = None,
    generated_at: str | None = None,
    generation_run_id: str | None = None,
    prompt_version: str = 'v1',
    review_status: str = 'draft',
    provider_mode: str = 'auto',
    transport: Transport | None = None,
) -> EnrichmentRunResult:
    destination = output_path or snapshot_dir / 'enrichments.jsonl'
    enrichments = enrich_snapshot(
        snapshot_dir,
        output_path=destination,
        provider=provider,
        settings=settings,
        model_name=model_name,
        generated_at=generated_at,
        generation_run_id=generation_run_id,
        prompt_version=prompt_version,
        review_status=review_status,
        provider_mode=provider_mode,
        transport=transport,
    )
    return EnrichmentRunResult(output_path=destination, enrichments=enrichments)
