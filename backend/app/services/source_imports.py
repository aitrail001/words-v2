import csv
import hashlib
import io
import re
import uuid
from collections import Counter, defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from sqlalchemy import Select, and_, case, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.models.import_source_entry import ImportSourceEntry
from app.models.learner_catalog_entry import LearnerCatalogEntry
from app.models.phrase_entry import PhraseEntry
from app.models.word import Word
from app.models.word_form import WordForm
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem

IMPORT_PIPELINE_VERSION = "epub-import-v2"
IMPORT_LEXICON_VERSION = "learner-catalog-v1"
SOURCE_TYPE_EPUB = "epub"
ENTRY_TYPE_WORD = "word"
ENTRY_TYPE_PHRASE = "phrase"
JOB_TERMINAL_STATUSES = {"completed", "failed"}
JOB_ACTIVE_STATUSES = {"queued", "processing"}
MAX_BULK_RESOLVE_TERMS = 500

WORD_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")
WHITESPACE_RE = re.compile(r"\s+")
DASH_RE = re.compile(r"[\u2010-\u2015]")
PUNCT_TRIM_RE = re.compile(r"(^[^\w]+|[^\w]+$)")


@dataclass(frozen=True)
class EntryRef:
    entry_type: str
    entry_id: uuid.UUID


@dataclass(frozen=True)
class MatchedImportEntry:
    entry_type: str
    entry_id: uuid.UUID
    frequency_count: int
    browse_rank: int | None
    phrase_kind: str | None
    cefr_level: str | None
    normalization_method: str | None


@dataclass(frozen=True)
class ExtractedSourceMetadata:
    title: str | None
    author: str | None
    language: str | None
    source_identifier: str | None


def sha256_digest_from_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_import_cache_key(
    *,
    source_type: str,
    source_hash_sha256: str,
    pipeline_version: str = IMPORT_PIPELINE_VERSION,
    lexicon_version: str = IMPORT_LEXICON_VERSION,
) -> tuple[str, str, str, str]:
    return (source_type, source_hash_sha256, pipeline_version, lexicon_version)


def normalize_matching_text(value: str) -> str:
    normalized = value.strip().lower()
    normalized = DASH_RE.sub("-", normalized)
    normalized = normalized.replace("’", "'")
    normalized = WHITESPACE_RE.sub(" ", normalized)
    return normalized


def normalize_word_surface(value: str) -> str:
    normalized = normalize_matching_text(value)
    normalized = PUNCT_TRIM_RE.sub("", normalized)
    return normalized


def iter_normalized_words(text: str) -> list[str]:
    return [normalize_word_surface(match.group(0)) for match in WORD_RE.finditer(text)]


def deterministic_lemmatize(surface: str) -> str | None:
    value = normalize_word_surface(surface)
    if not value:
        return None
    irregular = {
        "men": "man",
        "women": "woman",
        "children": "child",
        "mice": "mouse",
        "geese": "goose",
    }
    if value in irregular:
        return irregular[value]
    if len(value) > 4 and value.endswith("ies"):
        return f"{value[:-3]}y"
    if len(value) > 4 and value.endswith("ves"):
        return f"{value[:-3]}f"
    if len(value) > 4 and value.endswith("ing"):
        base = value[:-3]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if len(value) > 3 and value.endswith("ed"):
        base = value[:-2]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        return base
    if len(value) > 3 and value.endswith("es"):
        if value.endswith(("ses", "xes", "zes", "ches", "shes")):
            return value[:-2]
        return value[:-1]
    if len(value) > 2 and value.endswith("s"):
        return value[:-1]
    return value


def parse_bulk_entry_text(raw_text: str) -> list[str]:
    stripped = raw_text.strip()
    if not stripped:
        return []

    if "\n" in stripped and not any(separator in stripped for separator in (",", ";", '"')):
        return [line.strip() for line in stripped.splitlines() if line.strip()][:MAX_BULK_RESOLVE_TERMS]

    if any(separator in stripped for separator in ("\n", ",", ";", '"')):
        rows = next(csv.reader(io.StringIO(stripped), skipinitialspace=True))
        items: list[str] = []
        for row in rows:
            for part in row.splitlines():
                for subpart in part.split(";"):
                    value = subpart.strip()
                    if value:
                        items.append(value)
        return items[:MAX_BULK_RESOLVE_TERMS]

    return [term for term in stripped.split() if term][:MAX_BULK_RESOLVE_TERMS]


class SourceTextExtractor:
    def extract_metadata_and_chunks(
        self,
        file_path: str | Path,
    ) -> tuple[ExtractedSourceMetadata, Iterable[str]]:
        raise NotImplementedError


class EpubTextExtractor(SourceTextExtractor):
    def extract_metadata_and_chunks(
        self,
        file_path: str | Path,
    ) -> tuple[ExtractedSourceMetadata, Iterable[str]]:
        book = epub.read_epub(str(file_path))
        title_entries = book.get_metadata("DC", "title")
        author_entries = book.get_metadata("DC", "creator")
        language_entries = book.get_metadata("DC", "language")
        identifier_entries = book.get_metadata("DC", "identifier")

        metadata = ExtractedSourceMetadata(
            title=title_entries[0][0] if title_entries else None,
            author=author_entries[0][0] if author_entries else None,
            language=language_entries[0][0] if language_entries else None,
            source_identifier=identifier_entries[0][0] if identifier_entries else None,
        )

        def iter_chunks() -> Iterable[str]:
            for item in book.get_items():
                if item.get_type() != ebooklib.ITEM_DOCUMENT:
                    continue
                name = str(getattr(item, "file_name", "") or "").lower()
                if "nav" in name or "toc" in name:
                    continue
                soup = BeautifulSoup(item.get_content(), "html.parser")
                text = soup.get_text(" ", strip=True)
                if text:
                    yield text

        return metadata, iter_chunks()


class ImportMatcher:
    def __init__(
        self,
        *,
        exact_words: dict[str, uuid.UUID],
        word_form_map: dict[str, uuid.UUID | None],
        phrase_rows: Sequence[dict[str, object]],
    ) -> None:
        self.exact_words = exact_words
        self.word_form_map = word_form_map
        self.max_phrase_len = 1
        self.phrase_patterns: dict[tuple[str, ...], list[dict[str, object]]] = defaultdict(list)
        for row in phrase_rows:
            normalized_form = str(row["normalized_form"])
            tokens = tuple(part for part in normalized_form.split(" ") if part)
            if not tokens:
                continue
            self.max_phrase_len = max(self.max_phrase_len, len(tokens))
            self.phrase_patterns[tokens].append(row)

    @classmethod
    def from_rows(
        cls,
        exact_words: Sequence[Word],
        word_forms: Sequence[WordForm],
        phrase_rows: Sequence[dict[str, object]],
    ) -> "ImportMatcher":
        exact_word_map = {
            normalize_word_surface(word.word): word.id
            for word in exact_words
        }
        grouped_forms: dict[str, set[uuid.UUID]] = defaultdict(set)
        for form in word_forms:
            grouped_forms[normalize_word_surface(form.value)].add(form.word_id)
        word_form_map: dict[str, uuid.UUID | None] = {
            key: next(iter(word_ids)) if len(word_ids) == 1 else None
            for key, word_ids in grouped_forms.items()
        }
        return cls(
            exact_words=exact_word_map,
            word_form_map=word_form_map,
            phrase_rows=phrase_rows,
        )

    def match_chunks(self, chunks: Iterable[str]) -> list[MatchedImportEntry]:
        word_counts: Counter[uuid.UUID] = Counter()
        phrase_counts: Counter[uuid.UUID] = Counter()
        phrase_rows_by_id: dict[uuid.UUID, dict[str, object]] = {}

        for text in chunks:
            normalized_words = iter_normalized_words(text)
            for match in self._match_phrases(normalized_words):
                phrase_counts[match["entry_id"]] += 1
                phrase_rows_by_id[match["entry_id"]] = match

            for surface in normalized_words:
                resolved = self._resolve_word(surface)
                if resolved is not None:
                    word_counts[resolved] += 1

        matched_entries: list[MatchedImportEntry] = []
        for entry_id, frequency_count in word_counts.items():
            matched_entries.append(
                MatchedImportEntry(
                    entry_type=ENTRY_TYPE_WORD,
                    entry_id=entry_id,
                    frequency_count=frequency_count,
                    browse_rank=None,
                    phrase_kind=None,
                    cefr_level=None,
                    normalization_method="word_lookup",
                )
            )

        for entry_id, frequency_count in phrase_counts.items():
            row = phrase_rows_by_id[entry_id]
            matched_entries.append(
                MatchedImportEntry(
                    entry_type=ENTRY_TYPE_PHRASE,
                    entry_id=entry_id,
                    frequency_count=frequency_count,
                    browse_rank=int(row["browse_rank"]) if row.get("browse_rank") is not None else None,
                    phrase_kind=str(row["phrase_kind"]) if row.get("phrase_kind") else None,
                    cefr_level=str(row["cefr_level"]) if row.get("cefr_level") else None,
                    normalization_method="phrase_exact",
                )
            )

        return matched_entries

    def resolve_terms(
        self,
        terms: Sequence[str],
        *,
        phrase_catalog: dict[str, dict[str, object]],
        learner_catalog: dict[tuple[str, uuid.UUID], dict[str, object]],
    ) -> dict[str, object]:
        found: list[dict[str, object]] = []
        ambiguous: list[str] = []
        not_found_count = 0

        for term in terms:
            normalized = normalize_matching_text(term)
            phrase_row = phrase_catalog.get(normalized)
            if phrase_row is not None:
                found.append(phrase_row)
                continue

            resolved_word = self._resolve_word(term)
            if resolved_word is None:
                if normalized in self.word_form_map and self.word_form_map[normalized] is None:
                    ambiguous.append(term)
                else:
                    not_found_count += 1
                continue

            catalog_row = learner_catalog.get((ENTRY_TYPE_WORD, resolved_word))
            if catalog_row is None:
                not_found_count += 1
                continue
            found.append(catalog_row)

        deduped: dict[tuple[str, uuid.UUID], dict[str, object]] = {}
        for row in found:
            deduped[(str(row["entry_type"]), row["entry_id"])] = row

        return {
            "found_entries": list(deduped.values()),
            "ambiguous_entries": ambiguous,
            "not_found_count": not_found_count,
        }

    def _resolve_word(self, surface: str) -> uuid.UUID | None:
        normalized = normalize_word_surface(surface)
        if not normalized:
            return None

        exact = self.exact_words.get(normalized)
        if exact is not None:
            return exact

        form_match = self.word_form_map.get(normalized)
        if form_match is not None:
            return form_match
        if normalized in self.word_form_map and form_match is None:
            return None

        lemma = deterministic_lemmatize(normalized)
        if not lemma:
            return None

        exact = self.exact_words.get(lemma)
        if exact is not None:
            return exact

        form_match = self.word_form_map.get(lemma)
        if form_match is not None:
            return form_match
        return None

    def _match_phrases(self, words: Sequence[str]) -> list[dict[str, object]]:
        candidates: list[dict[str, object]] = []
        word_count = len(words)
        for start in range(word_count):
            for length in range(self.max_phrase_len, 0, -1):
                end = start + length
                if end > word_count:
                    continue
                key = tuple(words[start:end])
                pattern_rows = self.phrase_patterns.get(key)
                if not pattern_rows:
                    continue
                ordered = sorted(
                    pattern_rows,
                    key=lambda row: (
                        -len(key),
                        int(row["browse_rank"]) if row.get("browse_rank") is not None else 1_000_000,
                        str(row["entry_id"]),
                    ),
                )
                chosen = ordered[0]
                candidates.append(
                    {
                        "start": start,
                        "end": end,
                        **chosen,
                    }
                )
                break

        accepted: list[dict[str, object]] = []
        occupied: set[int] = set()
        for candidate in sorted(
            candidates,
            key=lambda row: (
                row["start"],
                -(row["end"] - row["start"]),
                int(row["browse_rank"]) if row.get("browse_rank") is not None else 1_000_000,
                str(row["entry_id"]),
            ),
        ):
            span = set(range(candidate["start"], candidate["end"]))
            if occupied.intersection(span):
                continue
            occupied.update(span)
            accepted.append(candidate)
        return accepted


def build_review_entries_query(import_source_id: uuid.UUID) -> Select:
    return (
        select(
            ImportSourceEntry.id.label("source_entry_row_id"),
            ImportSourceEntry.entry_type,
            ImportSourceEntry.entry_id,
            ImportSourceEntry.frequency_count,
            func.coalesce(
                LearnerCatalogEntry.display_text,
                literal_column("''"),
            ).label("display_text"),
            LearnerCatalogEntry.normalized_form,
            func.coalesce(
                ImportSourceEntry.browse_rank_snapshot,
                LearnerCatalogEntry.browse_rank,
            ).label("browse_rank"),
            func.coalesce(
                ImportSourceEntry.cefr_level_snapshot,
                LearnerCatalogEntry.cefr_level,
            ).label("cefr_level"),
            func.coalesce(
                ImportSourceEntry.phrase_kind_snapshot,
                LearnerCatalogEntry.phrase_kind,
            ).label("phrase_kind"),
            LearnerCatalogEntry.primary_part_of_speech,
        )
        .select_from(ImportSourceEntry)
        .join(
            LearnerCatalogEntry,
            and_(
                LearnerCatalogEntry.entry_type == ImportSourceEntry.entry_type,
                LearnerCatalogEntry.entry_id == ImportSourceEntry.entry_id,
            ),
        )
        .where(ImportSourceEntry.import_source_id == import_source_id)
    )


async def fetch_import_matcher(db: AsyncSession) -> tuple[ImportMatcher, dict[str, dict[str, object]], dict[tuple[str, uuid.UUID], dict[str, object]]]:
    words = (
        await db.execute(select(Word).where(Word.language == "en"))
    ).scalars().all()
    word_forms = (
        await db.execute(select(WordForm))
    ).scalars().all()
    phrase_result = await db.execute(
        select(
            LearnerCatalogEntry.entry_type,
            LearnerCatalogEntry.entry_id,
            LearnerCatalogEntry.display_text,
            LearnerCatalogEntry.normalized_form,
            LearnerCatalogEntry.browse_rank,
            LearnerCatalogEntry.cefr_level,
            LearnerCatalogEntry.phrase_kind,
        ).where(LearnerCatalogEntry.entry_type == ENTRY_TYPE_PHRASE)
    )
    phrase_rows = [dict(row) for row in phrase_result.mappings().all()]
    learner_result = await db.execute(
        select(
            LearnerCatalogEntry.entry_type,
            LearnerCatalogEntry.entry_id,
            LearnerCatalogEntry.display_text,
            LearnerCatalogEntry.normalized_form,
            LearnerCatalogEntry.browse_rank,
            LearnerCatalogEntry.cefr_level,
            LearnerCatalogEntry.phrase_kind,
            LearnerCatalogEntry.primary_part_of_speech,
        )
    )
    learner_catalog_rows = [dict(row) for row in learner_result.mappings().all()]
    learner_catalog = {
        (str(row["entry_type"]), row["entry_id"]): row
        for row in learner_catalog_rows
    }
    phrase_catalog = {
        str(row["normalized_form"]): row
        for row in phrase_rows
    }
    return (
        ImportMatcher.from_rows(words, word_forms, phrase_rows),
        phrase_catalog,
        learner_catalog,
    )


def fetch_import_matcher_sync(
    db: Session,
) -> tuple[ImportMatcher, dict[str, dict[str, object]], dict[tuple[str, uuid.UUID], dict[str, object]]]:
    words = db.execute(select(Word).where(Word.language == "en")).scalars().all()
    word_forms = db.execute(select(WordForm)).scalars().all()
    phrase_rows = [
        dict(row)
        for row in db.execute(
            select(
                LearnerCatalogEntry.entry_type,
                LearnerCatalogEntry.entry_id,
                LearnerCatalogEntry.display_text,
                LearnerCatalogEntry.normalized_form,
                LearnerCatalogEntry.browse_rank,
                LearnerCatalogEntry.cefr_level,
                LearnerCatalogEntry.phrase_kind,
            ).where(LearnerCatalogEntry.entry_type == ENTRY_TYPE_PHRASE)
        ).mappings().all()
    ]
    learner_catalog_rows = [
        dict(row)
        for row in db.execute(
            select(
                LearnerCatalogEntry.entry_type,
                LearnerCatalogEntry.entry_id,
                LearnerCatalogEntry.display_text,
                LearnerCatalogEntry.normalized_form,
                LearnerCatalogEntry.browse_rank,
                LearnerCatalogEntry.cefr_level,
                LearnerCatalogEntry.phrase_kind,
                LearnerCatalogEntry.primary_part_of_speech,
            )
        ).mappings().all()
    ]
    learner_catalog = {
        (str(row["entry_type"]), row["entry_id"]): row
        for row in learner_catalog_rows
    }
    phrase_catalog = {
        str(row["normalized_form"]): row
        for row in phrase_rows
    }
    return (
        ImportMatcher.from_rows(words, word_forms, phrase_rows),
        phrase_catalog,
        learner_catalog,
    )


async def get_or_create_import_source(
    db: AsyncSession,
    *,
    source_type: str,
    source_hash_sha256: str,
) -> ImportSource:
    key = build_import_cache_key(
        source_type=source_type,
        source_hash_sha256=source_hash_sha256,
    )
    existing = await db.execute(
        select(ImportSource).where(
            ImportSource.source_type == key[0],
            ImportSource.source_hash_sha256 == key[1],
            ImportSource.pipeline_version == key[2],
            ImportSource.lexicon_version == key[3],
        )
    )
    import_source = existing.scalar_one_or_none()
    if import_source is not None:
        return import_source

    import_source = ImportSource(
        source_type=source_type,
        source_hash_sha256=source_hash_sha256,
        pipeline_version=IMPORT_PIPELINE_VERSION,
        lexicon_version=IMPORT_LEXICON_VERSION,
    )
    db.add(import_source)
    try:
        await db.commit()
        await db.refresh(import_source)
        return import_source
    except IntegrityError:
        await db.rollback()
        existing = await db.execute(
            select(ImportSource).where(
                ImportSource.source_type == key[0],
                ImportSource.source_hash_sha256 == key[1],
                ImportSource.pipeline_version == key[2],
                ImportSource.lexicon_version == key[3],
            )
        )
        return existing.scalar_one()


def get_or_create_import_source_sync(
    db: Session,
    *,
    source_type: str,
    source_hash_sha256: str,
) -> ImportSource:
    import_source = db.execute(
        select(ImportSource).where(
            ImportSource.source_type == source_type,
            ImportSource.source_hash_sha256 == source_hash_sha256,
            ImportSource.pipeline_version == IMPORT_PIPELINE_VERSION,
            ImportSource.lexicon_version == IMPORT_LEXICON_VERSION,
        )
    ).scalar_one_or_none()
    if import_source is not None:
        return import_source

    import_source = ImportSource(
        source_type=source_type,
        source_hash_sha256=source_hash_sha256,
        pipeline_version=IMPORT_PIPELINE_VERSION,
        lexicon_version=IMPORT_LEXICON_VERSION,
    )
    db.add(import_source)
    try:
        db.commit()
        db.refresh(import_source)
        return import_source
    except IntegrityError:
        db.rollback()
        return db.execute(
            select(ImportSource).where(
                ImportSource.source_type == source_type,
                ImportSource.source_hash_sha256 == source_hash_sha256,
                ImportSource.pipeline_version == IMPORT_PIPELINE_VERSION,
                ImportSource.lexicon_version == IMPORT_LEXICON_VERSION,
            )
        ).scalar_one()


async def create_import_job(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    import_source: ImportSource,
    source_filename: str,
    list_name: str,
    list_description: str | None,
) -> ImportJob:
    job = ImportJob(
        user_id=user_id,
        import_source_id=import_source.id,
        source_filename=source_filename,
        source_hash=import_source.source_hash_sha256,
        list_name=list_name,
        list_description=list_description,
        status="completed" if import_source.status == "completed" else "queued",
        total_items=import_source.matched_entry_count,
        processed_items=import_source.matched_entry_count if import_source.status == "completed" else 0,
        matched_entry_count=import_source.matched_entry_count,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def sync_job_with_source(job: ImportJob, import_source: ImportSource) -> None:
    job.import_source_id = import_source.id
    job.source_hash = import_source.source_hash_sha256
    job.total_items = import_source.matched_entry_count
    job.processed_items = import_source.matched_entry_count if import_source.status == "completed" else 0
    job.matched_entry_count = import_source.matched_entry_count
    job.status = "completed" if import_source.status == "completed" else "processing"
    job.error_message = import_source.error_message


def upsert_import_source_entries_sync(
    db: Session,
    *,
    import_source_id: uuid.UUID,
    matched_entries: Sequence[MatchedImportEntry],
    learner_catalog: dict[tuple[str, uuid.UUID], dict[str, object]],
) -> None:
    values = []
    for match in matched_entries:
        catalog_row = learner_catalog.get((match.entry_type, match.entry_id), {})
        values.append(
            {
                "import_source_id": import_source_id,
                "entry_type": match.entry_type,
                "entry_id": match.entry_id,
                "frequency_count": match.frequency_count,
                "browse_rank_snapshot": match.browse_rank or catalog_row.get("browse_rank"),
                "phrase_kind_snapshot": match.phrase_kind or catalog_row.get("phrase_kind"),
                "cefr_level_snapshot": match.cefr_level or catalog_row.get("cefr_level"),
                "normalization_method": match.normalization_method,
            }
        )
    if not values:
        return
    stmt = insert(ImportSourceEntry).values(values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_import_source_entries_entry",
        set_={
            "frequency_count": stmt.excluded.frequency_count,
            "browse_rank_snapshot": stmt.excluded.browse_rank_snapshot,
            "phrase_kind_snapshot": stmt.excluded.phrase_kind_snapshot,
            "cefr_level_snapshot": stmt.excluded.cefr_level_snapshot,
            "normalization_method": stmt.excluded.normalization_method,
        },
    )
    db.execute(stmt)


async def fetch_review_entries(
    db: AsyncSession,
    *,
    import_source_id: uuid.UUID,
    q: str | None,
    entry_type: str | None,
    phrase_kind: str | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> tuple[int, list[dict[str, object]]]:
    query = build_review_entries_query(import_source_id)
    if q:
        lowered = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(LearnerCatalogEntry.display_text).like(lowered),
                func.lower(LearnerCatalogEntry.normalized_form).like(lowered),
            )
        )
    if entry_type:
        query = query.where(ImportSourceEntry.entry_type == entry_type)
    if phrase_kind:
        query = query.where(
            func.coalesce(ImportSourceEntry.phrase_kind_snapshot, LearnerCatalogEntry.phrase_kind) == phrase_kind
        )

    count_query = select(func.count()).select_from(query.subquery())
    total = int((await db.execute(count_query)).scalar_one())

    order_column = {
        "book_frequency": ImportSourceEntry.frequency_count,
        "general_rank": func.coalesce(ImportSourceEntry.browse_rank_snapshot, LearnerCatalogEntry.browse_rank),
        "alpha": func.lower(LearnerCatalogEntry.display_text),
    }.get(sort, ImportSourceEntry.frequency_count)
    direction = order_column.desc() if order == "desc" else order_column.asc()
    query = query.order_by(direction, func.lower(LearnerCatalogEntry.display_text).asc()).limit(limit).offset(offset)
    rows = [dict(row) for row in (await db.execute(query)).mappings().all()]
    return total, rows


async def create_word_list_from_entries(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    job: ImportJob,
    name: str,
    description: str | None,
    selected_entries: Sequence[EntryRef],
) -> WordList:
    if job.import_source_id is None:
        raise ValueError("Import job is missing import source")
    if not selected_entries:
        raise ValueError("At least one entry must be selected")

    import_source = (
        await db.execute(select(ImportSource).where(ImportSource.id == job.import_source_id))
    ).scalar_one()

    wanted = {(entry.entry_type, entry.entry_id) for entry in selected_entries}
    source_entries = await db.execute(
        select(ImportSourceEntry).where(
            ImportSourceEntry.import_source_id == job.import_source_id,
            or_(
                *[
                    and_(
                        ImportSourceEntry.entry_type == entry_type,
                        ImportSourceEntry.entry_id == entry_id,
                    )
                    for entry_type, entry_id in wanted
                ]
            ),
        )
    )
    matched_rows = source_entries.scalars().all()
    if len(matched_rows) != len(wanted):
        raise ValueError("Selected entries must belong to the import session")

    word_list = WordList(
        user_id=user_id,
        name=name,
        description=description,
        source_type=import_source.source_type,
        source_reference=str(job.id),
    )
    db.add(word_list)
    await db.flush()

    for row in matched_rows:
        db.add(
            WordListItem(
                word_list_id=word_list.id,
                entry_type=row.entry_type,
                entry_id=row.entry_id,
                frequency_count=row.frequency_count,
            )
        )

    job.word_list_id = word_list.id
    job.created_count = len(matched_rows)
    await db.commit()
    await db.refresh(word_list)
    await db.refresh(job)
    return word_list


def hydrate_word_list_items(
    item_rows: Sequence[WordListItem],
    learner_catalog: dict[tuple[str, uuid.UUID], dict[str, object]],
) -> list[dict[str, object]]:
    hydrated: list[dict[str, object]] = []
    for item in item_rows:
        catalog_row = learner_catalog.get((item.entry_type, item.entry_id), {})
        hydrated.append(
            {
                "id": str(item.id),
                "entry_type": item.entry_type,
                "entry_id": str(item.entry_id),
                "display_text": catalog_row.get("display_text"),
                "normalized_form": catalog_row.get("normalized_form"),
                "browse_rank": catalog_row.get("browse_rank"),
                "cefr_level": catalog_row.get("cefr_level"),
                "phrase_kind": catalog_row.get("phrase_kind"),
                "part_of_speech": catalog_row.get("primary_part_of_speech"),
                "frequency_count": item.frequency_count,
                "added_at": item.added_at,
            }
        )
    return hydrated
