from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
import hashlib
import json

from tools.lexicon.batch_ledger import append_jsonl_rows, load_jsonl_rows, write_jsonl_rows
from tools.lexicon.import_db import load_compiled_rows


DEFAULT_VOICE_MAP: dict[str, dict[str, dict[str, dict[str, str]]]] = {
    "google": {
        "neural2": {
            "en-US": {
                "female": "en-US-Neural2-C",
                "male": "en-US-Neural2-D",
            },
            "en-GB": {
                "female": "en-GB-Neural2-F",
                "male": "en-GB-Neural2-B",
            },
        }
    }
}

DEFAULT_PROFILE_MAP: dict[str, dict[str, dict[str, Any]]] = {
    "google": {
        "word": {
            "speaking_rate": 0.86,
            "pitch_semitones": 1.0,
            "lead_ms": 140,
            "tail_ms": 220,
            "effects_profile_id": "handset-class-device",
        },
        "definition": {
            "speaking_rate": 0.94,
            "pitch_semitones": 0.0,
            "lead_ms": 80,
            "tail_ms": 120,
            "effects_profile_id": "handset-class-device",
        },
        "example": {
            "speaking_rate": 0.98,
            "pitch_semitones": 0.3,
            "lead_ms": 60,
            "tail_ms": 100,
            "effects_profile_id": "handset-class-device",
        },
    }
}

FORMAT_TO_MIME = {
    "mp3": "audio/mpeg",
    "ogg_opus": "audio/ogg",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = json.loads(json.dumps(base))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _load_optional_json(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    with Path(path).open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise RuntimeError(f"Expected JSON object in {path}")
    return payload


def _slug_locale(locale: str) -> str:
    return locale.replace("-", "_").lower()


def _load_prior_unit_sets(manifest_path: Path, errors_path: Path) -> tuple[set[str], set[str]]:
    completed: set[str] = set()
    failed: set[str] = set()

    for row in load_jsonl_rows(manifest_path):
        unit_id = str(row.get("unit_id") or "").strip()
        if not unit_id:
            continue
        status = str(row.get("status") or "").strip().lower()
        if status in {"generated", "existing"}:
            completed.add(unit_id)

    for row in load_jsonl_rows(errors_path):
        unit_id = str(row.get("unit_id") or "").strip()
        if not unit_id:
            continue
        failed.add(unit_id)

    failed.difference_update(completed)
    return completed, failed


def _emit_progress(
    progress_callback: Callable[..., None] | None,
    event: str,
    *,
    message: str,
    **fields: Any,
) -> None:
    if progress_callback is None:
        return
    progress_callback(event, message=message, **fields)


@dataclass(frozen=True)
class VoiceWorkUnit:
    unit_id: str
    entry_id: str
    entry_type: str
    word: str
    source_reference: str
    language: str
    content_scope: str
    locale: str
    voice_role: str
    provider: str
    family: str
    voice_id: str
    profile_key: str
    audio_format: str
    mime_type: str
    speaking_rate: float
    pitch_semitones: float
    lead_ms: int
    tail_ms: int
    effects_profile_id: str | None
    storage_kind: str
    storage_base: str
    relative_path: str
    source_text: str
    source_text_hash: str
    sense_id: str | None = None
    meaning_index: int | None = None
    example_index: int | None = None

    def to_plan_row(self) -> dict[str, Any]:
        return asdict(self)

    def to_manifest_row(self, *, status: str, generated_at: str, generation_error: str | None = None) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = status
        payload["generated_at"] = generated_at
        payload["generation_error"] = generation_error
        return payload


class VoiceSynthProvider(Protocol):
    def synthesize(self, unit: VoiceWorkUnit, output_path: Path) -> None:
        ...


class GoogleVoiceSynthProvider:
    def __init__(self) -> None:
        try:
            from google.cloud import texttospeech_v1 as texttospeech
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "google-cloud-texttospeech is required for provider=google. "
                "Install tools/lexicon requirements before running voice-generate."
            ) from exc

        self._texttospeech = texttospeech
        self._client = texttospeech.TextToSpeechClient()

    def synthesize(self, unit: VoiceWorkUnit, output_path: Path) -> None:
        texttospeech = self._texttospeech
        encoding_name = "MP3" if unit.audio_format == "mp3" else "OGG_OPUS"
        audio_encoding = getattr(texttospeech.AudioEncoding, encoding_name)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=audio_encoding,
            speaking_rate=unit.speaking_rate,
            pitch=unit.pitch_semitones,
        )
        if unit.effects_profile_id:
            audio_config.effects_profile_id = [unit.effects_profile_id]
        request = texttospeech.SynthesizeSpeechRequest(
            input=texttospeech.SynthesisInput(text=unit.source_text),
            voice=texttospeech.VoiceSelectionParams(
                language_code=unit.locale,
                name=unit.voice_id,
            ),
            audio_config=audio_config,
        )
        response = self._client.synthesize_speech(request=request)
        output_path.write_bytes(response.audio_content)


def _build_relative_path(
    *,
    entry_id: str,
    content_scope: str,
    locale: str,
    sense_id: str | None,
    example_index: int | None,
    voice_role: str,
    profile_key: str,
    source_text_hash: str,
    audio_format: str,
) -> str:
    locale_slug = _slug_locale(locale)
    ext = audio_format.replace("_", ".")
    filename = f"{voice_role}-{profile_key}-{source_text_hash[:12]}.{ext}"
    if content_scope == "word":
        return str(Path(entry_id) / "word" / locale_slug / filename)
    if content_scope == "definition":
        return str(Path(entry_id) / "meaning" / str(sense_id or "unknown") / "definition" / locale_slug / filename)
    return str(Path(entry_id) / "meaning" / str(sense_id or "unknown") / f"example-{int(example_index or 0)}" / locale_slug / filename)


def _resolve_voice_id(
    voice_map: dict[str, Any],
    *,
    provider: str,
    family: str,
    locale: str,
    voice_role: str,
) -> str:
    try:
        value = voice_map[provider][family][locale][voice_role]
    except KeyError as exc:
        raise RuntimeError(
            f"Missing voice mapping for provider={provider} family={family} locale={locale} role={voice_role}"
        ) from exc
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(
            f"Voice mapping for provider={provider} family={family} locale={locale} role={voice_role} must be a non-empty string"
        )
    return value.strip()


def _resolve_profile(profile_map: dict[str, Any], *, provider: str, profile_key: str) -> dict[str, Any]:
    try:
        payload = profile_map[provider][profile_key]
    except KeyError as exc:
        raise RuntimeError(f"Missing profile config for provider={provider} profile={profile_key}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"Profile config for provider={provider} profile={profile_key} must be an object")
    return payload


def plan_voice_work_units(
    rows: list[dict[str, Any]],
    *,
    provider: str,
    family: str,
    locales: list[str],
    audio_format: str,
    storage_kind: str,
    storage_base: str,
    voice_map: dict[str, Any] | None = None,
    profile_map: dict[str, Any] | None = None,
) -> list[VoiceWorkUnit]:
    effective_voice_map = voice_map or DEFAULT_VOICE_MAP
    effective_profile_map = profile_map or DEFAULT_PROFILE_MAP
    units: list[VoiceWorkUnit] = []

    def append_units(
        *,
        row: dict[str, Any],
        content_scope: str,
        source_text: str,
        profile_key: str,
        sense_id: str | None,
        meaning_index: int | None,
        example_index: int | None,
    ) -> None:
        text = str(source_text or "").strip()
        if not text:
            return
        source_text_hash = _hash_text(text)
        profile = _resolve_profile(effective_profile_map, provider=provider, profile_key=profile_key)
        for locale in locales:
            for voice_role in ("female", "male"):
                voice_id = _resolve_voice_id(
                    effective_voice_map,
                    provider=provider,
                    family=family,
                    locale=locale,
                    voice_role=voice_role,
                )
                unit_key = "|".join(
                    [
                        str(row.get("entry_id") or row.get("word") or ""),
                        str(row.get("source_reference") or ""),
                        content_scope,
                        str(sense_id or ""),
                        str(meaning_index if meaning_index is not None else ""),
                        str(example_index if example_index is not None else ""),
                        locale,
                        voice_role,
                        provider,
                        family,
                        voice_id,
                        profile_key,
                        audio_format,
                        source_text_hash,
                    ]
                )
                units.append(
                    VoiceWorkUnit(
                        unit_id=_hash_text(unit_key),
                        entry_id=str(row.get("entry_id") or row.get("word") or ""),
                        entry_type=entry_type,
                        word=str(row.get("word") or "").strip(),
                        source_reference=str(row.get("source_reference") or "").strip(),
                        language=str(row.get("language") or "en").strip() or "en",
                        content_scope=content_scope,
                        locale=locale,
                        voice_role=voice_role,
                        provider=provider,
                        family=family,
                        voice_id=voice_id,
                        profile_key=profile_key,
                        audio_format=audio_format,
                        mime_type=FORMAT_TO_MIME[audio_format],
                        speaking_rate=float(profile.get("speaking_rate") or 1.0),
                        pitch_semitones=float(profile.get("pitch_semitones") or 0.0),
                        lead_ms=int(profile.get("lead_ms") or 0),
                        tail_ms=int(profile.get("tail_ms") or 0),
                        effects_profile_id=(
                            str(profile.get("effects_profile_id")).strip()
                            if isinstance(profile.get("effects_profile_id"), str) and str(profile.get("effects_profile_id")).strip()
                            else None
                        ),
                        storage_kind=storage_kind,
                        storage_base=storage_base,
                        relative_path=_build_relative_path(
                            entry_id=str(row.get("entry_id") or row.get("word") or ""),
                            content_scope=content_scope,
                            locale=locale,
                            sense_id=sense_id,
                            example_index=example_index,
                            voice_role=voice_role,
                            profile_key=profile_key,
                            source_text_hash=source_text_hash,
                            audio_format=audio_format,
                        ),
                        source_text=text,
                        source_text_hash=source_text_hash,
                        sense_id=sense_id,
                        meaning_index=meaning_index,
                        example_index=example_index,
                    )
                )

    for row in rows:
        entry_type = str(row.get("entry_type") or "word").strip().lower() or "word"
        if entry_type not in {"word", "phrase"}:
            continue
        append_units(
            row=row,
            content_scope="word",
            source_text=str(row.get("word") or ""),
            profile_key="word",
            sense_id=None,
            meaning_index=None,
            example_index=None,
        )
        for meaning_index, sense in enumerate(row.get("senses") or []):
            if not isinstance(sense, dict):
                continue
            sense_id = str(sense.get("sense_id") or f"sense-{meaning_index}").strip()
            append_units(
                row=row,
                content_scope="definition",
                source_text=str(sense.get("definition") or ""),
                profile_key="definition",
                sense_id=sense_id,
                meaning_index=meaning_index,
                example_index=None,
            )
            for example_index, example in enumerate(sense.get("examples") or []):
                if not isinstance(example, dict):
                    continue
                append_units(
                    row=row,
                    content_scope="example",
                    source_text=str(example.get("sentence") or ""),
                    profile_key="example",
                    sense_id=sense_id,
                    meaning_index=meaning_index,
                    example_index=example_index,
                )
    return units


def _build_provider(provider: str) -> VoiceSynthProvider:
    if provider == "google":
        return GoogleVoiceSynthProvider()
    raise RuntimeError(f"Unsupported voice provider: {provider}")


def run_voice_generation(
    *,
    input_path: str | Path,
    output_dir: str | Path,
    provider: str = "google",
    family: str = "neural2",
    locales: list[str] | None = None,
    audio_format: str = "mp3",
    max_concurrency: int = 4,
    storage_kind: str = "local",
    storage_base: str | None = None,
    voice_map_path: str | None = None,
    profile_config_path: str | None = None,
    overwrite_existing: bool = False,
    resume: bool = False,
    retry_failed_only: bool = False,
    skip_failed: bool = False,
    dry_run: bool = False,
    synth_provider: VoiceSynthProvider | None = None,
    progress_callback: Callable[..., None] | None = None,
) -> dict[str, Any]:
    if audio_format not in FORMAT_TO_MIME:
        raise RuntimeError(f"Unsupported audio format: {audio_format}")

    resolved_output_dir = Path(output_dir)
    resolved_output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = resolved_output_dir / "voice_manifest.jsonl"
    errors_path = resolved_output_dir / "voice_errors.jsonl"
    plan_path = resolved_output_dir / "voice_plan.jsonl"

    rows = load_compiled_rows(input_path)
    effective_locales = locales or ["en-US", "en-GB"]
    effective_voice_map = _deep_merge(DEFAULT_VOICE_MAP, _load_optional_json(voice_map_path))
    effective_profile_map = _deep_merge(DEFAULT_PROFILE_MAP, _load_optional_json(profile_config_path))
    effective_storage_base = storage_base or str(resolved_output_dir.resolve())
    rows_scanned = len(rows)
    eligible_word_count = sum(
        1 for row in rows if str(row.get("entry_type") or "word").strip().lower() == "word"
    )
    eligible_phrase_count = sum(
        1 for row in rows if str(row.get("entry_type") or "word").strip().lower() == "phrase"
    )

    _emit_progress(
        progress_callback,
        "voice-generate-start",
        message="Voice generation started",
        input=str(Path(input_path)),
        output_dir=str(resolved_output_dir),
        provider=provider,
        family=family,
        locales=effective_locales,
        audio_format=audio_format,
        max_concurrency=max_concurrency,
        storage_kind=storage_kind,
        storage_base=effective_storage_base,
        resume=resume,
        retry_failed_only=retry_failed_only,
        skip_failed=skip_failed,
    )

    units = plan_voice_work_units(
        rows,
        provider=provider,
        family=family,
        locales=effective_locales,
        audio_format=audio_format,
        storage_kind=storage_kind,
        storage_base=effective_storage_base,
        voice_map=effective_voice_map,
        profile_map=effective_profile_map,
    )
    planned_scope_counts: dict[str, int] = {}
    planned_locale_counts: dict[str, int] = {}
    planned_voice_role_counts: dict[str, int] = {}
    for unit in units:
        planned_scope_counts[unit.content_scope] = planned_scope_counts.get(unit.content_scope, 0) + 1
        planned_locale_counts[unit.locale] = planned_locale_counts.get(unit.locale, 0) + 1
        planned_voice_role_counts[unit.voice_role] = planned_voice_role_counts.get(unit.voice_role, 0) + 1

    _emit_progress(
        progress_callback,
        "voice-generate-plan",
        message="Voice generation planned",
        rows_scanned=rows_scanned,
        eligible_word_count=eligible_word_count,
        eligible_phrase_count=eligible_phrase_count,
        planned_count=len(units),
        planned_scope_counts=planned_scope_counts,
        planned_locale_counts=planned_locale_counts,
        planned_voice_role_counts=planned_voice_role_counts,
    )
    write_jsonl_rows(plan_path, [unit.to_plan_row() for unit in units])

    completed_unit_ids: set[str] = set()
    failed_unit_ids: set[str] = set()
    if resume or retry_failed_only:
        completed_unit_ids, failed_unit_ids = _load_prior_unit_sets(manifest_path, errors_path)

    all_unit_ids = {unit.unit_id for unit in units}

    if retry_failed_only:
        units_to_run = [unit for unit in units if unit.unit_id in failed_unit_ids]
    elif resume and skip_failed:
        units_to_run = [unit for unit in units if unit.unit_id not in completed_unit_ids and unit.unit_id not in failed_unit_ids]
    elif resume:
        units_to_run = [unit for unit in units if unit.unit_id not in completed_unit_ids]
    else:
        units_to_run = units

    skipped_completed_count = len(completed_unit_ids.intersection(all_unit_ids)) if resume else 0
    skipped_failed_count = len(failed_unit_ids.intersection(all_unit_ids)) if (resume and skip_failed) else 0
    retried_failed_count = len(units_to_run) if retry_failed_only else 0

    if dry_run:
        _emit_progress(
            progress_callback,
            "voice-generate-complete",
            message="Voice generation dry run complete",
            planned_count=len(units),
            scheduled_count=len(units_to_run),
            generated_count=0,
            existing_count=0,
            failed_count=0,
            skipped_completed_count=skipped_completed_count,
            skipped_failed_count=skipped_failed_count,
            retried_failed_count=retried_failed_count,
            manifest_path=str(manifest_path),
            errors_path=str(errors_path),
            plan_path=str(plan_path),
        )
        return {
            "planned_count": len(units),
            "scheduled_count": len(units_to_run),
            "generated_count": 0,
            "existing_count": 0,
            "failed_count": 0,
            "skipped_completed_count": skipped_completed_count,
            "skipped_failed_count": skipped_failed_count,
            "retried_failed_count": retried_failed_count,
            "manifest_path": str(manifest_path),
            "errors_path": str(errors_path),
            "plan_path": str(plan_path),
        }

    provider_client = synth_provider or _build_provider(provider)
    generated_count = 0
    existing_count = 0
    failed_count = 0
    progress_count = 0

    def run_unit(unit: VoiceWorkUnit) -> dict[str, Any]:
        destination = resolved_output_dir / unit.relative_path
        if destination.exists() and not overwrite_existing:
            return unit.to_manifest_row(status="existing", generated_at=_utc_now())
        destination.parent.mkdir(parents=True, exist_ok=True)
        provider_client.synthesize(unit, destination)
        return unit.to_manifest_row(status="generated", generated_at=_utc_now())

    with ThreadPoolExecutor(max_workers=max(1, int(max_concurrency))) as executor:
        futures = {executor.submit(run_unit, unit): unit for unit in units_to_run}
        for future in as_completed(futures):
            unit = futures[future]
            try:
                row = future.result()
            except Exception as exc:
                failed_count += 1
                append_jsonl_rows(
                    errors_path,
                    [unit.to_manifest_row(status="failed", generated_at=_utc_now(), generation_error=str(exc))],
                )
                progress_count += 1
                _emit_progress(
                    progress_callback,
                    "voice-generate-unit-failed",
                    message="Voice generation unit failed",
                    unit_id=unit.unit_id,
                    entry_id=unit.entry_id,
                    word=unit.word,
                    content_scope=unit.content_scope,
                    locale=unit.locale,
                    voice_role=unit.voice_role,
                    error=str(exc),
                )
                _emit_progress(
                    progress_callback,
                    "voice-generate-progress",
                    message="Voice generation progress",
                    planned_count=len(units),
                    scheduled_count=len(units_to_run),
                    completed_count=progress_count,
                    generated_count=generated_count,
                    existing_count=existing_count,
                    failed_count=failed_count,
                    in_flight_count=max(len(units_to_run) - progress_count, 0),
                )
                continue
            if row["status"] == "existing":
                existing_count += 1
            else:
                generated_count += 1
            append_jsonl_rows(manifest_path, [row])
            progress_count += 1
            _emit_progress(
                progress_callback,
                "voice-generate-progress",
                message="Voice generation progress",
                planned_count=len(units),
                scheduled_count=len(units_to_run),
                completed_count=progress_count,
                generated_count=generated_count,
                existing_count=existing_count,
                failed_count=failed_count,
                in_flight_count=max(len(units_to_run) - progress_count, 0),
            )

    _emit_progress(
        progress_callback,
        "voice-generate-complete",
        message="Voice generation complete",
        planned_count=len(units),
        scheduled_count=len(units_to_run),
        generated_count=generated_count,
        existing_count=existing_count,
        failed_count=failed_count,
        skipped_completed_count=skipped_completed_count,
        skipped_failed_count=skipped_failed_count,
        retried_failed_count=retried_failed_count,
        manifest_path=str(manifest_path),
        errors_path=str(errors_path),
        plan_path=str(plan_path),
    )
    return {
        "planned_count": len(units),
        "scheduled_count": len(units_to_run),
        "generated_count": generated_count,
        "existing_count": existing_count,
        "failed_count": failed_count,
        "skipped_completed_count": skipped_completed_count,
        "skipped_failed_count": skipped_failed_count,
        "retried_failed_count": retried_failed_count,
        "manifest_path": str(manifest_path),
        "errors_path": str(errors_path),
        "plan_path": str(plan_path),
    }
