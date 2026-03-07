from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional, Type
import json
import sys


def _ensure_backend_path() -> None:
    backend_path = Path(__file__).resolve().parents[2] / "backend"
    backend_str = str(backend_path)
    if backend_str not in sys.path:
        sys.path.insert(0, backend_str)


def _default_models() -> tuple[type, type]:
    _ensure_backend_path()
    from app.models.meaning import Meaning
    from app.models.word import Word

    return Word, Meaning


@dataclass(frozen=True)
class ImportSummary:
    created_words: int = 0
    updated_words: int = 0
    created_meanings: int = 0
    updated_meanings: int = 0


def _first_example_sentence(sense: dict[str, Any]) -> str | None:
    examples = sense.get("examples") or []
    if not examples:
        return None
    example = examples[0] or {}
    return example.get("sentence")


def _is_sqlalchemy_model(model: Type[Any]) -> bool:
    return hasattr(model, "__table__")


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


def import_compiled_rows(
    session: Any,
    rows: Iterable[dict[str, Any]],
    *,
    source_type: str,
    source_reference: str,
    language: str = "en",
    word_model: Optional[Type[Any]] = None,
    meaning_model: Optional[Type[Any]] = None,
) -> ImportSummary:
    if word_model is None or meaning_model is None:
        word_model, meaning_model = _default_models()

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
            summary = ImportSummary(
                created_words=summary.created_words + 1,
                updated_words=summary.updated_words,
                created_meanings=summary.created_meanings,
                updated_meanings=summary.updated_meanings,
            )
        else:
            word.frequency_rank = row.get("frequency_rank")
            word.word_forms = row.get("forms")
            if hasattr(word, "source_type"):
                word.source_type = source_type
            if hasattr(word, "source_reference"):
                word.source_reference = source_reference
            summary = ImportSummary(
                created_words=summary.created_words,
                updated_words=summary.updated_words + 1,
                created_meanings=summary.created_meanings,
                updated_meanings=summary.updated_meanings,
            )

        existing_meanings = _load_existing_meanings(session, meaning_model, word.id)

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
                summary = ImportSummary(
                    created_words=summary.created_words,
                    updated_words=summary.updated_words,
                    created_meanings=summary.created_meanings + 1,
                    updated_meanings=summary.updated_meanings,
                )
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
                summary = ImportSummary(
                    created_words=summary.created_words,
                    updated_words=summary.updated_words,
                    created_meanings=summary.created_meanings,
                    updated_meanings=summary.updated_meanings + 1,
                )

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
    }
