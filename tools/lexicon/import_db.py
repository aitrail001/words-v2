from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional, Type
import hashlib
import json
import sys


SUPPORTED_RELATION_FIELDS = (
    ("synonym", "synonyms"),
    ("antonym", "antonyms"),
    ("collocation", "collocations"),
)


def _ensure_backend_path() -> None:
    backend_path = Path(__file__).resolve().parents[2] / "backend"
    backend_str = str(backend_path)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)


def _default_models() -> tuple[type, type, type, type, type, type]:
    _ensure_backend_path()
    from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.word import Word
    from app.models.word_relation import WordRelation

    return Word, Meaning, MeaningExample, WordRelation, LexiconEnrichmentJob, LexiconEnrichmentRun


@dataclass(frozen=True)
class ImportSummary:
    created_words: int = 0
    updated_words: int = 0
    created_meanings: int = 0
    updated_meanings: int = 0
    created_examples: int = 0
    deleted_examples: int = 0
    created_relations: int = 0
    deleted_relations: int = 0
    created_enrichment_jobs: int = 0
    reused_enrichment_jobs: int = 0
    created_enrichment_runs: int = 0
    reused_enrichment_runs: int = 0


def _increment(summary: ImportSummary, **changes: int) -> ImportSummary:
    values = summary.__dict__.copy()
    for key, delta in changes.items():
        values[key] = values.get(key, 0) + delta
    return replace(summary, **values)


def _first_example_sentence(sense: dict[str, Any]) -> str | None:
    examples = sense.get("examples") or []
    if not examples:
        return None
    example = examples[0] or {}
    return example.get("sentence")


def _is_sqlalchemy_model(model: Type[Any]) -> bool:
    return hasattr(model, "__table__")


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    return datetime.fromisoformat(text)


def _normalize_confidence(value: Any) -> float | None:
    if value is None or value == "":
        return None
    confidence = float(value)
    if confidence < 0 or confidence > 1:
        raise ValueError(f"confidence must be between 0 and 1; got {value}")
    return confidence


def _find_existing_word(session: Any, word_model: Type[Any], lemma: str, language: str) -> Any | None:
    if _is_sqlalchemy_model(word_model):
        from sqlalchemy import select

        result = session.execute(
            select(word_model).where(
                word_model.word == lemma,
                word_model.language == language,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _load_existing_meanings(session: Any, meaning_model: Type[Any], word_id: Any) -> list[Any]:
    if _is_sqlalchemy_model(meaning_model):
        from sqlalchemy import select

        result = session.execute(
            select(meaning_model)
            .where(meaning_model.word_id == word_id)
            .order_by(meaning_model.order_index.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _find_existing_enrichment_job(session: Any, job_model: Type[Any], word_id: Any, phase: str) -> Any | None:
    if _is_sqlalchemy_model(job_model):
        from sqlalchemy import select

        result = session.execute(
            select(job_model).where(
                job_model.word_id == word_id,
                job_model.phase == phase,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _find_existing_enrichment_run(
    session: Any,
    run_model: Type[Any],
    enrichment_job_id: Any,
    prompt_version: str | None,
    prompt_hash: str,
) -> Any | None:
    if _is_sqlalchemy_model(run_model):
        from sqlalchemy import select

        result = session.execute(
            select(run_model).where(
                run_model.enrichment_job_id == enrichment_job_id,
                run_model.prompt_version == prompt_version,
                run_model.prompt_hash == prompt_hash,
            )
        )
        return result.scalar_one_or_none()

    result = session.execute(object())
    return result.scalar_one_or_none()


def _load_existing_examples(session: Any, example_model: Type[Any], meaning_id: Any, source: str) -> list[Any]:
    if _is_sqlalchemy_model(example_model):
        from sqlalchemy import select

        result = session.execute(
            select(example_model)
            .where(
                example_model.meaning_id == meaning_id,
                example_model.source == source,
            )
            .order_by(example_model.order_index.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _load_existing_relations(session: Any, relation_model: Type[Any], meaning_id: Any, source: str) -> list[Any]:
    if _is_sqlalchemy_model(relation_model):
        from sqlalchemy import select

        relation_types = [relation_type for relation_type, _ in SUPPORTED_RELATION_FIELDS]
        result = session.execute(
            select(relation_model)
            .where(
                relation_model.meaning_id == meaning_id,
                relation_model.source == source,
                relation_model.relation_type.in_(relation_types),
            )
            .order_by(relation_model.relation_type.asc(), relation_model.related_word.asc())
        )
        return list(result.scalars().all())

    result = session.execute(object())
    return list(result.scalars().all())


def _make_prompt_hash(source_type: str, source_reference: str, word: str, sense: dict[str, Any]) -> str:
    payload = "|".join(
        [
            source_type,
            source_reference,
            word,
            str(sense.get("sense_id") or ""),
            str(sense.get("generation_run_id") or ""),
            str(sense.get("model_name") or ""),
            str(sense.get("prompt_version") or ""),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sync_word_level_enrichment_fields(word: Any, row: dict[str, Any], run: Any | None, source_type: str) -> None:
    if row.get("phonetic") is not None and hasattr(word, "phonetic"):
        word.phonetic = row.get("phonetic")
    if row.get("phonetic") is not None and hasattr(word, "phonetic_source"):
        word.phonetic_source = source_type
    if row.get("phonetic_confidence") is not None and hasattr(word, "phonetic_confidence"):
        word.phonetic_confidence = _normalize_confidence(row.get("phonetic_confidence"))
    if run is not None and row.get("phonetic") is not None and hasattr(word, "phonetic_enrichment_run_id"):
        word.phonetic_enrichment_run_id = run.id


def import_compiled_rows(
    session: Any,
    rows: Iterable[dict[str, Any]],
    *,
    source_type: str,
    source_reference: str,
    language: str = "en",
    word_model: Optional[Type[Any]] = None,
    meaning_model: Optional[Type[Any]] = None,
    meaning_example_model: Optional[Type[Any]] = None,
    word_relation_model: Optional[Type[Any]] = None,
    lexicon_enrichment_job_model: Optional[Type[Any]] = None,
    lexicon_enrichment_run_model: Optional[Type[Any]] = None,
) -> ImportSummary:
    if word_model is None or meaning_model is None:
        (
            word_model,
            meaning_model,
            default_meaning_example_model,
            default_word_relation_model,
            default_job_model,
            default_run_model,
        ) = _default_models()
        if meaning_example_model is None:
            meaning_example_model = default_meaning_example_model
        if word_relation_model is None:
            word_relation_model = default_word_relation_model
        if lexicon_enrichment_job_model is None:
            lexicon_enrichment_job_model = default_job_model
        if lexicon_enrichment_run_model is None:
            lexicon_enrichment_run_model = default_run_model

    summary = ImportSummary()

    for row in rows:
        word = _find_existing_word(session, word_model, row["word"], language)
        if word is None:
            word = word_model(
                word=row["word"],
                language=language,
                frequency_rank=row.get("frequency_rank"),
                word_forms=row.get("forms"),
                source_type=source_type,
                source_reference=source_reference,
            )
            session.add(word)
            session.flush()
            summary = _increment(summary, created_words=1)
        else:
            word.frequency_rank = row.get("frequency_rank")
            word.word_forms = row.get("forms")
            if hasattr(word, "source_type"):
                word.source_type = source_type
            if hasattr(word, "source_reference"):
                word.source_reference = source_reference
            summary = _increment(summary, updated_words=1)

        existing_meanings = _load_existing_meanings(session, meaning_model, word.id)
        matched_meaning_ids: set[Any] = set()
        enrichment_job = None

        if lexicon_enrichment_job_model is not None and lexicon_enrichment_run_model is not None:
            enrichment_job = _find_existing_enrichment_job(
                session,
                lexicon_enrichment_job_model,
                word.id,
                "phase1",
            )
            if enrichment_job is None:
                enrichment_job = lexicon_enrichment_job_model(
                    word_id=word.id,
                    phase="phase1",
                    status="completed",
                    started_at=_parse_timestamp(row.get("generated_at")),
                    completed_at=_parse_timestamp(row.get("generated_at")),
                )
                session.add(enrichment_job)
                session.flush()
                summary = _increment(summary, created_enrichment_jobs=1)
            else:
                if hasattr(enrichment_job, "status"):
                    enrichment_job.status = "completed"
                if hasattr(enrichment_job, "completed_at"):
                    enrichment_job.completed_at = _parse_timestamp(row.get("generated_at"))
                summary = _increment(summary, reused_enrichment_jobs=1)

        for index, sense in enumerate(row.get("senses") or []):
            sense_source_reference = f"{source_reference}:{sense['sense_id']}"
            example_sentence = _first_example_sentence(sense)
            meaning = next(
                (
                    item
                    for item in existing_meanings
                    if getattr(item, "source_reference", None) == sense_source_reference
                    or getattr(item, "order_index", None) == index
                ),
                None,
            )
            if meaning is None:
                meaning = meaning_model(
                    word_id=word.id,
                    definition=sense["definition"],
                    part_of_speech=sense.get("pos"),
                    example_sentence=example_sentence,
                    order_index=index,
                    source=source_type,
                    source_reference=sense_source_reference,
                )
                session.add(meaning)
                session.flush()
                summary = _increment(summary, created_meanings=1)
                existing_meanings.append(meaning)
            else:
                meaning.definition = sense["definition"]
                meaning.part_of_speech = sense.get("pos")
                meaning.example_sentence = example_sentence
                meaning.order_index = index
                if hasattr(meaning, "source"):
                    meaning.source = source_type
                if hasattr(meaning, "source_reference"):
                    meaning.source_reference = sense_source_reference
                summary = _increment(summary, updated_meanings=1)
            matched_meaning_ids.add(meaning.id)

            enrichment_run = None
            if enrichment_job is not None and lexicon_enrichment_run_model is not None:
                prompt_version = sense.get("prompt_version")
                prompt_hash = _make_prompt_hash(source_type, source_reference, row["word"], sense)
                enrichment_run = _find_existing_enrichment_run(
                    session,
                    lexicon_enrichment_run_model,
                    enrichment_job.id,
                    prompt_version,
                    prompt_hash,
                )
                if enrichment_run is None:
                    enrichment_run = lexicon_enrichment_run_model(
                        enrichment_job_id=enrichment_job.id,
                        generator_provider=source_type,
                        generator_model=sense.get("model_name"),
                        prompt_version=prompt_version,
                        prompt_hash=prompt_hash,
                        verdict="imported",
                        confidence=_normalize_confidence(sense.get("confidence")),
                        created_at=_parse_timestamp(sense.get("generated_at") or row.get("generated_at")),
                    )
                    session.add(enrichment_run)
                    session.flush()
                    summary = _increment(summary, created_enrichment_runs=1)
                else:
                    if hasattr(enrichment_run, "generator_provider"):
                        enrichment_run.generator_provider = source_type
                    if hasattr(enrichment_run, "generator_model"):
                        enrichment_run.generator_model = sense.get("model_name")
                    if hasattr(enrichment_run, "verdict"):
                        enrichment_run.verdict = "imported"
                    if hasattr(enrichment_run, "confidence"):
                        enrichment_run.confidence = _normalize_confidence(sense.get("confidence"))
                    summary = _increment(summary, reused_enrichment_runs=1)

            _sync_word_level_enrichment_fields(word, row, enrichment_run, source_type)

            if meaning_example_model is not None:
                existing_examples = _load_existing_examples(session, meaning_example_model, meaning.id, source_type)
                for existing_example in existing_examples:
                    session.delete(existing_example)
                    summary = _increment(summary, deleted_examples=1)
                for example_index, example in enumerate(sense.get("examples") or []):
                    sentence = str((example or {}).get("sentence") or "").strip()
                    if not sentence:
                        continue
                    meaning_example = meaning_example_model(
                        meaning_id=meaning.id,
                        sentence=sentence,
                        order_index=example_index,
                        source=source_type,
                        confidence=_normalize_confidence(sense.get("confidence")),
                        enrichment_run_id=getattr(enrichment_run, "id", None),
                    )
                    session.add(meaning_example)
                    summary = _increment(summary, created_examples=1)

            if word_relation_model is not None:
                existing_relations = _load_existing_relations(session, word_relation_model, meaning.id, source_type)
                for existing_relation in existing_relations:
                    session.delete(existing_relation)
                    summary = _increment(summary, deleted_relations=1)
                for relation_type, source_field in SUPPORTED_RELATION_FIELDS:
                    for related_word in sense.get(source_field) or []:
                        related_text = str(related_word or "").strip()
                        if not related_text:
                            continue
                        relation = word_relation_model(
                            word_id=word.id,
                            meaning_id=meaning.id,
                            relation_type=relation_type,
                            related_word=related_text,
                            related_word_id=None,
                            source=source_type,
                            confidence=_normalize_confidence(sense.get("confidence")),
                            enrichment_run_id=getattr(enrichment_run, "id", None),
                        )
                        session.add(relation)
                        summary = _increment(summary, created_relations=1)

        for existing_meaning in list(existing_meanings):
            if existing_meaning.id in matched_meaning_ids:
                continue
            if getattr(existing_meaning, "source", None) != source_type:
                continue
            session.delete(existing_meaning)

    return summary


def load_compiled_rows(path: str | Path) -> list[dict[str, Any]]:
    source_path = Path(path)
    rows: list[dict[str, Any]] = []
    with source_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def _default_source_reference(path: str | Path) -> str:
    source_path = Path(path)
    return source_path.stem or "compiled-lexicon"


def run_import_file(
    path: str | Path,
    *,
    source_type: str,
    source_reference: str | None = None,
    language: str = "en",
) -> dict[str, int]:
    rows = load_compiled_rows(path)
    _ensure_backend_path()
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from app.core.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    effective_source_reference = source_reference or _default_source_reference(path)
    with Session(engine) as session:
        summary = import_compiled_rows(
            session,
            rows,
            source_type=source_type,
            source_reference=effective_source_reference,
            language=language,
        )
        session.commit()
    return {
        "created_words": summary.created_words,
        "updated_words": summary.updated_words,
        "created_meanings": summary.created_meanings,
        "updated_meanings": summary.updated_meanings,
        "created_examples": summary.created_examples,
        "deleted_examples": summary.deleted_examples,
        "created_relations": summary.created_relations,
        "deleted_relations": summary.deleted_relations,
        "created_enrichment_jobs": summary.created_enrichment_jobs,
        "reused_enrichment_jobs": summary.reused_enrichment_jobs,
        "created_enrichment_runs": summary.created_enrichment_runs,
        "reused_enrichment_runs": summary.reused_enrichment_runs,
    }
