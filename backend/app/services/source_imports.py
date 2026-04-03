import csv
import hashlib
import io
import re
import uuid
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import ebooklib
from bs4 import BeautifulSoup
from ebooklib import epub
from sqlalchemy import Select, and_, func, literal_column, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.models.import_job import ImportJob
from app.models.import_source import ImportSource
from app.models.import_source_entry import ImportSourceEntry
from app.models.learner_catalog_entry import LearnerCatalogEntry
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
SOFT_HYPHEN_RE = re.compile("\u00ad")
INTRA_WORD_BREAK_RE = re.compile(r"(?<=[A-Za-z])-\s+(?=[A-Za-z])")
FRAGMENTED_CAPS_RE = re.compile(r"\b(?:[A-Z]{1,8}\s+){2,}[A-Z]{1,8}\b")
LIGATURE_TRANSLATION = str.maketrans({
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬀ": "ff",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
})


@dataclass(frozen=True)
class EntryRef:
    entry_type: str
    entry_id: uuid.UUID


class ImportCacheDeletedError(ValueError):
    pass


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
    publisher: str | None
    language: str | None
    source_identifier: str | None
    published_year: int | None
    isbn: str | None


@dataclass(frozen=True)
class EpubMetadataEntry:
    value: str
    id: str | None
    attrs: dict[str, str]
    refinements: dict[str, list[str]]


@dataclass(frozen=True)
class EpubPackageMetadata:
    titles: list[EpubMetadataEntry]
    creators: list[EpubMetadataEntry]
    contributors: list[EpubMetadataEntry]
    dates: list[EpubMetadataEntry]
    identifiers: list[EpubMetadataEntry]
    publishers: list[EpubMetadataEntry]
    languages: list[EpubMetadataEntry]
    content_title_candidates: list[str]


@dataclass(frozen=True)
class EpubContentFallbacks:
    title_candidates: list[str]
    author_candidates: list[str]
    publisher_candidates: list[str]
    isbn_candidates: list[str]


@dataclass(frozen=True)
class ExtractionProgress:
    completed: int
    total: int
    label: str


@dataclass(frozen=True)
class MatchProgress:
    completed: int
    total: int
    matched_entries: int
    label: str


YEAR_RE = re.compile(r"(19|20)\d{2}")
ISBN_CLEAN_RE = re.compile(r"[^0-9Xx]")
TITLE_FILE_EXT_RE = re.compile(r"\.(epub|pdf|mobi|azw3)\s*$", re.IGNORECASE)
TITLE_VENDOR_TAG_RE = re.compile(r"\(\s*pdfdrive(?:\.com)?\s*\)", re.IGNORECASE)
TITLE_MULTI_SPACE_RE = re.compile(r"\s{2,}")
BRACKET_DUPLICATE_RE = re.compile(r"\s*\[[^\]]+\]\s*$")
TITLE_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’\-:;,!?]+")
TITLE_BY_AUTHOR_RE = re.compile(r"^(?P<title>.+?)\s+by\s+(?P<author>.+)$", re.IGNORECASE)
NON_AUTHOR_HINT_RE = re.compile(
    r"\b(ed\.?|editor|edited by|translator|translated by|foreword|introduction|preface)\b",
    re.IGNORECASE,
)
PUBLISHER_NOISE_RE = re.compile(
    r"\b(pdfdrive|welib|calibre|ebooks?|chenjin|publisher|media)\b",
    re.IGNORECASE,
)
BAD_TITLE_VALUE_RE = re.compile(r"^(unknown|cover|contents?|chapter(?:\s+\d+)?)$", re.IGNORECASE)
SITE_NOISE_RE = re.compile(r"(?:https?://|www\.|\.com\b|\.org\b)")
UNKNOWN_PERSON_RE = re.compile(r"^(unknown|anonymous|n/?a)$", re.IGNORECASE)
COPYRIGHT_LINE_RE = re.compile(
    r"(?:©|copyright(?:\s+©)?)(?:\s*\d{4})?(?:\s+by)?\s+(?P<names>[^.]{5,260})",
    re.IGNORECASE,
)
BYLINE_RE = re.compile(r"\bby\s+(?P<names>[A-Z][^.]{3,160})", re.IGNORECASE)
ISBN_TEXT_RE = re.compile(r"\bISBN(?:-?1[03])?(?::|\s)\s*(?P<value>[0-9Xx\- ]{10,24})")
PUBLISHER_TEXT_RE = re.compile(
    r"\b(?P<publisher>[A-Z][A-Za-z&' .-]{2,80}(?:Press|Publishing Group|Publishing|Books|House|Perennial|LLC|Inc\.?|Group))\b"
)
IMPRINT_PUBLISHER_RE = re.compile(
    r"\b(?:AN\s+IMPRINT\s+OF|Published\s+by|Publisher)\s+(?P<publisher>[A-Z][A-Za-z0-9&' .-]{2,120}?)(?=\s+(?:\d{2,}|Copyright|ISBN|All rights|Printed in)\b|$)",
    re.IGNORECASE,
)
NON_PERSON_ENTITY_RE = re.compile(
    r"\b(isbn|press|publishing|books|house|llc|group|portland|oregon|academy|company|project|guide|rights|reserved|cover|story|fundamentals|chapter|personal|penguin|random)\b",
    re.IGNORECASE,
)
CONTENT_TITLE_BY_AUTHOR_RE = re.compile(
    r"(?P<title>[A-Z][A-Za-z0-9'’:;,\-!? ]{2,120})\s+By\s+(?P<author>[A-Z][A-Za-z0-9'’.\- ]{2,80})",
    re.IGNORECASE,
)
CONTENT_TITLE_PREFIX_RE = re.compile(r"^(unknown|cover|contents?)\s+", re.IGNORECASE)

CONTAINER_NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container"}
OPF_NS = {
    "opf": "http://www.idpf.org/2007/opf",
    "dc": "http://purl.org/dc/elements/1.1/",
}
OPF_ROLE_ATTR = "{http://www.idpf.org/2007/opf}role"
OPF_EVENT_ATTR = "{http://www.idpf.org/2007/opf}event"


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


def normalize_extraction_text(value: str) -> str:
    normalized = str(value or "")
    normalized = normalized.translate(LIGATURE_TRANSLATION)
    normalized = SOFT_HYPHEN_RE.sub("", normalized)
    normalized = DASH_RE.sub("-", normalized)
    normalized = INTRA_WORD_BREAK_RE.sub("", normalized)
    normalized = _repair_fragmented_caps_text(normalized)
    return normalized


def normalize_word_surface(value: str) -> str:
    normalized = normalize_matching_text(value)
    normalized = PUNCT_TRIM_RE.sub("", normalized)
    return normalized


def iter_normalized_words(text: str) -> list[str]:
    normalized_text = normalize_extraction_text(text)
    return [normalize_word_surface(match.group(0)) for match in WORD_RE.finditer(normalized_text)]


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
        "went": "go",
        "gone": "go",
        "better": "good",
        "best": "good",
        "worse": "bad",
        "worst": "bad",
        "did": "do",
        "done": "do",
        "was": "be",
        "were": "be",
    }
    if value in irregular:
        return irregular[value]
    if len(value) > 4 and value.endswith("ied"):
        return f"{value[:-3]}y"
    if len(value) > 4 and value.endswith("ies"):
        return f"{value[:-3]}y"
    if len(value) > 4 and value.endswith("ves"):
        return f"{value[:-3]}f"
    if len(value) > 4 and value.endswith("ing"):
        base = value[:-3]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        elif base.endswith("at") or base.endswith("it") or base.endswith("iz"):
            base = f"{base}e"
        return base
    if len(value) > 3 and value.endswith("ed"):
        if value.endswith("ied"):
            return f"{value[:-3]}y"
        base = value[:-2]
        if len(base) >= 2 and base[-1] == base[-2]:
            base = base[:-1]
        elif not base.endswith("e") and (
            base.endswith("at")
            or base.endswith("it")
            or base.endswith("iz")
        ):
            base = f"{base}e"
        return base
    if len(value) > 3 and value.endswith("es"):
        if value.endswith(("ses", "xes", "zes", "ches", "shes")):
            return value[:-2]
        return value[:-1]
    if len(value) > 2 and value.endswith("s"):
        return value[:-1]
    return value


def _repair_fragmented_caps_text(text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        tokens = match.group(0).split()
        repaired = _repair_fragmented_caps_tokens(tokens)
        return " ".join(repaired)

    return FRAGMENTED_CAPS_RE.sub(replace, text)


def _repair_fragmented_caps_tokens(tokens: Sequence[str]) -> list[str]:
    suffixes = {"LLC", "INC", "LTD", "USA", "UK"}
    repaired: list[str] = []
    current = ""

    def flush() -> None:
        nonlocal current
        if not current:
            return
        if current in suffixes:
            repaired.append(current)
        elif len(current) > 1:
            repaired.append(current.title())
        else:
            repaired.append(current)
        current = ""

    for token in tokens:
        if token in suffixes:
            flush()
            repaired.append(token)
            continue
        if not current:
            current = token
            continue
        if len(current) == 1:
            current = f"{current}{token}"
            continue
        if len(token) == 1:
            flush()
            current = token
            continue
        if len(token) <= 2 and len(current) <= 4:
            current = f"{current}{token}"
            continue
        flush()
        current = token
    flush()
    return repaired


def parse_bulk_entry_text(raw_text: str) -> list[str]:
    stripped = raw_text.strip()
    if not stripped:
        return []

    if "\n" in stripped and not any(separator in stripped for separator in (",", ";", '"')):
        return [line.strip() for line in stripped.splitlines() if line.strip()][:MAX_BULK_RESOLVE_TERMS]

    if any(separator in stripped for separator in ("\n", ",", ";", '"')):
        items: list[str] = []
        for row in csv.reader(io.StringIO(stripped), skipinitialspace=True):
            for cell in row:
                for part in cell.splitlines():
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
        *,
        progress_callback: Callable[[ExtractionProgress], None] | None = None,
    ) -> tuple[ExtractedSourceMetadata, Iterable[str]]:
        raise NotImplementedError


class EpubTextExtractor(SourceTextExtractor):
    def extract_metadata_and_chunks(
        self,
        file_path: str | Path,
        *,
        progress_callback: Callable[[ExtractionProgress], None] | None = None,
    ) -> tuple[ExtractedSourceMetadata, Iterable[str]]:
        book = epub.read_epub(str(file_path))
        package_metadata = _read_epub_package_metadata(file_path)
        content_fallbacks = _collect_content_fallbacks_for_file(file_path)
        author_values = _select_best_author_names(
            package_metadata.creators,
            package_metadata.contributors,
        )
        if not author_values:
            author_values = _select_best_author_names(
                package_metadata.creators,
                package_metadata.contributors,
                content_author_candidates=content_fallbacks.author_candidates,
            )
        content_title_candidates = _collect_content_title_candidates_for_file(file_path, author_values)
        best_identifier = _select_best_identifier(package_metadata.identifiers)
        best_isbn = _select_best_isbn(package_metadata.identifiers)
        if best_isbn is None and content_fallbacks.isbn_candidates:
            best_isbn = content_fallbacks.isbn_candidates[0]
        if best_identifier is None and best_isbn is not None:
            best_identifier = best_isbn

        publisher = _select_best_publisher(package_metadata.publishers)
        if publisher is None and content_fallbacks.publisher_candidates:
            publisher = _select_best_publisher([], content_candidates=content_fallbacks.publisher_candidates)

        metadata = ExtractedSourceMetadata(
            title=_select_best_title(
                title_entries=package_metadata.titles,
                author_values=author_values,
                content_title_candidates=content_title_candidates,
                source_filename=Path(file_path).name,
            ),
            author=", ".join(author_values) if author_values else None,
            publisher=publisher,
            language=package_metadata.languages[0].value if package_metadata.languages else None,
            source_identifier=best_identifier,
            published_year=_extract_published_year(package_metadata.dates),
            isbn=best_isbn,
        )

        document_items = []
        for item in book.get_items():
            if item.get_type() != ebooklib.ITEM_DOCUMENT:
                continue
            name = str(getattr(item, "file_name", "") or "").lower()
            if "nav" in name or "toc" in name:
                continue
            document_items.append(item)

        chunks: list[str] = []
        total_documents = len(document_items)
        for index, item in enumerate(document_items, start=1):
            soup = BeautifulSoup(item.get_content(), "html.parser")
            text = soup.get_text(" ", strip=True)
            if text:
                chunks.append(text)
            if progress_callback is not None:
                progress_callback(
                    ExtractionProgress(
                        completed=index,
                        total=total_documents,
                        label=f"Extracting text {index}/{total_documents}",
                    )
                )

        return metadata, chunks


def _read_epub_package_metadata(file_path: str | Path) -> EpubPackageMetadata:
    with zipfile.ZipFile(file_path) as archive:
        container_root = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container_root.find(".//c:rootfile", CONTAINER_NS)
        if rootfile is None:
            return EpubPackageMetadata([], [], [], [], [], [], [], [])

        opf_path = rootfile.attrib["full-path"]
        opf_root = ET.fromstring(archive.read(opf_path))
        metadata = opf_root.find(".//opf:metadata", OPF_NS)
        if metadata is None:
            return EpubPackageMetadata([], [], [], [], [], [], [], [])

        refinements = _collect_metadata_refinements(metadata)
        package_metadata = EpubPackageMetadata(
            titles=_collect_metadata_entries(metadata, "title", refinements),
            creators=_collect_metadata_entries(metadata, "creator", refinements),
            contributors=_collect_metadata_entries(metadata, "contributor", refinements),
            dates=_collect_metadata_entries(metadata, "date", refinements),
            identifiers=_collect_metadata_entries(metadata, "identifier", refinements),
            publishers=_collect_metadata_entries(metadata, "publisher", refinements),
            languages=_collect_metadata_entries(metadata, "language", refinements),
            content_title_candidates=[],
        )
        return package_metadata


def _collect_content_title_candidates_for_file(
    file_path: str | Path,
    author_values: Sequence[str],
) -> list[str]:
    return _collect_content_fallbacks_for_file(file_path, author_values=author_values).title_candidates


def _collect_content_fallbacks_for_file(
    file_path: str | Path,
    *,
    author_values: Sequence[str] = (),
) -> EpubContentFallbacks:
    with zipfile.ZipFile(file_path) as archive:
        container_root = ET.fromstring(archive.read("META-INF/container.xml"))
        rootfile = container_root.find(".//c:rootfile", CONTAINER_NS)
        if rootfile is None:
            return EpubContentFallbacks([], [], [], [])
        opf_path = rootfile.attrib["full-path"]
        opf_root = ET.fromstring(archive.read(opf_path))
        return _collect_content_fallbacks(archive, opf_root, opf_path, author_values)


def _collect_metadata_refinements(metadata: ET.Element) -> dict[str, dict[str, list[str]]]:
    refinements: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    for meta in metadata.findall("opf:meta", OPF_NS):
        refines = (meta.attrib.get("refines") or "").strip()
        prop = (meta.attrib.get("property") or "").strip()
        value = (meta.text or "").strip()
        if not refines or not prop or not value:
            continue
        refinements[refines.lstrip("#")][prop].append(value)
    return {key: dict(value) for key, value in refinements.items()}


def _collect_metadata_entries(
    metadata: ET.Element,
    tag: str,
    refinements: dict[str, dict[str, list[str]]],
) -> list[EpubMetadataEntry]:
    entries: list[EpubMetadataEntry] = []
    for element in metadata.findall(f"dc:{tag}", OPF_NS):
        value = (element.text or "").strip()
        if not value:
            continue
        entry_id = element.attrib.get("id")
        entries.append(
            EpubMetadataEntry(
                value=value,
                id=entry_id,
                attrs=dict(element.attrib),
                refinements=refinements.get(entry_id or "", {}),
            )
        )
    return entries


def _collect_content_fallbacks(
    archive: zipfile.ZipFile,
    opf_root: ET.Element,
    opf_path: str,
    author_values: Sequence[str],
) -> EpubContentFallbacks:
    manifest = {
        item.attrib.get("id"): item.attrib.get("href")
        for item in opf_root.findall(".//opf:item", OPF_NS)
    }
    spine_ids = [item.attrib.get("idref") for item in opf_root.findall(".//opf:itemref", OPF_NS)]
    base_path = Path(opf_path).parent
    title_candidates: list[str] = []
    author_candidates: list[str] = []
    publisher_candidates: list[str] = []
    isbn_candidates: list[str] = []

    for spine_id in spine_ids[:5]:
        href = manifest.get(spine_id)
        if not href:
            continue
        lowered_href = href.casefold()
        if any(marker in lowered_href for marker in ("cover", "nav", "toc")):
            continue
        full_path = (base_path / href).as_posix()
        try:
            content = archive.read(full_path)
        except KeyError:
            continue
        soup = BeautifulSoup(content, "html.parser")
        title_text = soup.title.get_text(" ", strip=True) if soup.title else ""
        heading = soup.find(["h1", "h2"])
        heading_text = heading.get_text(" ", strip=True) if heading else ""
        body_text = WHITESPACE_RE.sub(" ", soup.get_text(" ", strip=True))

        for candidate in (title_text, heading_text):
            normalized = _normalize_source_title(candidate)
            if normalized and not BAD_TITLE_VALUE_RE.match(normalized):
                title_candidates.append(normalized)

        snippet_title = _extract_title_from_content_text(body_text, author_values)
        if snippet_title:
            title_candidates.append(snippet_title)
        author_candidates.extend(_extract_authors_from_content_text(body_text))
        publisher_candidates.extend(_extract_publishers_from_content_text(body_text))
        isbn_candidates.extend(_extract_isbns_from_content_text(body_text))

    return EpubContentFallbacks(
        title_candidates=_dedupe_casefold(title_candidates),
        author_candidates=_dedupe_casefold(author_candidates),
        publisher_candidates=_dedupe_casefold(publisher_candidates),
        isbn_candidates=_dedupe_casefold(isbn_candidates),
    )


def _dedupe_casefold(values: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    deduped: list[str] = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _extract_title_from_content_text(text: str, author_values: Sequence[str]) -> str | None:
    if not text:
        return None
    snippet = WHITESPACE_RE.sub(" ", text).strip()[:400]
    if author_values:
        for author in author_values:
            match = re.search(
                rf"(?P<title>[A-Z][A-Za-z0-9'’:;,\-!? ]{{2,120}}?)\s+By\s+{re.escape(author)}\b",
                snippet,
                flags=re.IGNORECASE,
            )
            if not match:
                continue
            title = _normalize_source_title(match.group("title"))
            while title and CONTENT_TITLE_PREFIX_RE.match(title):
                title = CONTENT_TITLE_PREFIX_RE.sub("", title).strip()
            if not title or BAD_TITLE_VALUE_RE.match(title):
                continue
            alpha_only = "".join(character for character in title if character.isalpha())
            if alpha_only and alpha_only.upper() == alpha_only:
                title = title.title()
            return title

    match = CONTENT_TITLE_BY_AUTHOR_RE.search(snippet)
    if not match:
        return None
    matched_author = _clean_person_name(match.group("author"))
    if author_values and (
        not matched_author
        or normalize_matching_text(matched_author) not in {normalize_matching_text(value) for value in author_values}
    ):
        return None
    title = _normalize_source_title(match.group("title"))
    while title and CONTENT_TITLE_PREFIX_RE.match(title):
        title = CONTENT_TITLE_PREFIX_RE.sub("", title).strip()
    if not title or BAD_TITLE_VALUE_RE.match(title):
        return None
    alpha_only = "".join(character for character in title if character.isalpha())
    if alpha_only and alpha_only.upper() == alpha_only:
        title = title.title()
    return title


def _extract_published_year(date_entries: Sequence[EpubMetadataEntry]) -> int | None:
    ranked_dates = sorted(date_entries, key=_score_date_entry, reverse=True)
    for entry in ranked_dates:
        raw_value = str(entry.value or "").strip()
        if not raw_value:
            continue
        match = YEAR_RE.search(raw_value)
        if match:
            return int(match.group(0))
    return None


def _score_date_entry(entry: EpubMetadataEntry) -> int:
    score = 0
    event = (entry.attrs.get(OPF_EVENT_ATTR) or "").strip().lower()
    if event == "modification":
        score -= 50
    if YEAR_RE.search(entry.value):
        score += 20
    return score


def _select_best_title(
    *,
    title_entries: Sequence[EpubMetadataEntry],
    author_values: Sequence[str],
    content_title_candidates: Sequence[str],
    source_filename: str,
) -> str | None:
    candidates: list[tuple[int, str]] = []
    for entry in title_entries:
        for candidate in _build_title_candidates(entry, title_entries):
            candidates.append((_score_title_candidate(candidate, author_values) + 20, candidate))

    for candidate in content_title_candidates:
        candidates.append((_score_title_candidate(candidate, author_values) + 5, candidate))

    if not candidates:
        return _normalize_source_title(source_filename)

    best_score, best_value = max(candidates, key=lambda item: item[0])
    if best_score < 5:
        return _normalize_source_title(source_filename)
    return best_value


def _build_title_candidates(
    entry: EpubMetadataEntry,
    all_entries: Sequence[EpubMetadataEntry],
) -> list[str]:
    candidates: list[str] = []
    normalized = _normalize_source_title(entry.value)
    if normalized:
        candidates.append(normalized)

    title_type_values = [value.casefold() for value in entry.refinements.get("title-type", [])]
    entry_id = (entry.id or "").casefold()
    if "main" in title_type_values or "maintitle" in entry_id or entry_id.endswith("main"):
        subtitle = _find_subtitle_candidate(all_entries, exclude_id=entry.id)
        if normalized and subtitle:
            candidates.append(f"{normalized}: {subtitle}")
    return list(dict.fromkeys(candidates))


def _find_subtitle_candidate(entries: Sequence[EpubMetadataEntry], exclude_id: str | None) -> str | None:
    for entry in entries:
        if entry.id == exclude_id:
            continue
        title_type_values = [value.casefold() for value in entry.refinements.get("title-type", [])]
        entry_id = (entry.id or "").casefold()
        if "subtitle" in title_type_values or "subtitle" in entry_id:
            return _normalize_source_title(entry.value)
    return None


def _score_title_candidate(candidate: str | None, author_values: Sequence[str]) -> int:
    if not candidate:
        return -100
    score = 0
    normalized = candidate.strip()
    lowered = normalized.casefold()
    if BAD_TITLE_VALUE_RE.match(normalized):
        return -100
    if TITLE_VENDOR_TAG_RE.search(normalized) or TITLE_FILE_EXT_RE.search(normalized):
        score -= 80
    if SITE_NOISE_RE.search(normalized):
        score -= 40
    if " -- " in normalized or " _ " in normalized:
        score -= 15
    if len(normalized) < 3:
        score -= 20
    if len(normalized) <= 80:
        score += 15
    if len(normalized) > 140:
        score -= 20
    if ": " in normalized:
        score += 5
    if len(TITLE_WORD_RE.findall(normalized)) >= 2:
        score += 10
    for author in author_values:
        author_match = TITLE_BY_AUTHOR_RE.match(normalized)
        if author_match and normalize_matching_text(author_match.group("author")) == normalize_matching_text(author):
            score -= 50
            score += 20
            break
        if normalize_matching_text(author) in lowered:
            score -= 10
    return score


def _select_best_author_names(
    creator_entries: Sequence[EpubMetadataEntry],
    contributor_entries: Sequence[EpubMetadataEntry],
    *,
    content_author_candidates: Sequence[str] = (),
) -> list[str]:
    candidates: list[tuple[int, int, str]] = []
    order = 0
    for entry in [*creator_entries, *contributor_entries]:
        base_score = _score_person_entry(entry, is_contributor=entry in contributor_entries)
        for person in _split_person_candidates(entry.value):
            cleaned = _clean_person_name(person)
            if not cleaned:
                continue
            score = base_score + _score_person_name(cleaned, raw_value=person)
            candidates.append((score, order, cleaned))
            order += 1
    for person in content_author_candidates:
        cleaned = _clean_person_name(person)
        if not cleaned:
            continue
        candidates.append((35 + _score_person_name(cleaned, raw_value=person), order, cleaned))
        order += 1

    if not candidates:
        return []

    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    best_score = candidates[0][0]
    selected: list[str] = []
    seen: set[str] = set()
    for score, _, name in candidates:
        if score < max(20, best_score - 40):
            continue
        key = normalize_matching_text(name)
        if key in seen:
            continue
        seen.add(key)
        selected.append(name)
        if len(selected) == 3:
            break
    return selected


def _split_person_candidates(raw_value: str) -> list[str]:
    if ";" in raw_value:
        return [part.strip() for part in raw_value.split(";") if part.strip()]
    return [raw_value.strip()]


def _clean_person_name(raw_value: str) -> str | None:
    value = BRACKET_DUPLICATE_RE.sub("", raw_value).strip(" ,")
    value = re.sub(r",\s*(ed|eds|editor|edited by)\.?$", "", value, flags=re.IGNORECASE).strip(" ,")
    value = WHITESPACE_RE.sub(" ", value)
    if UNKNOWN_PERSON_RE.match(value):
        return None
    if "," in value:
        parts = [part.strip() for part in value.split(",")]
        if (
            len(parts) == 2
            and len(parts[0].split()) == 1
            and 1 <= len(parts[1].split()) <= 2
            and parts[1].casefold() not in {"md", "phd", "jr", "sr", "ii", "iii", "iv"}
        ):
            value = f"{parts[1]} {parts[0]}".strip()
    return value or None


def _score_person_entry(entry: EpubMetadataEntry, *, is_contributor: bool) -> int:
    score = 30 if not is_contributor else 15
    role_values = [value.casefold() for value in entry.refinements.get("role", [])]
    role_attr = (entry.attrs.get(OPF_ROLE_ATTR) or "").strip().casefold()
    roles = set(role_values + ([role_attr] if role_attr else []))
    if "aut" in roles:
        score += 40
    if entry.refinements.get("display-seq"):
        score += 10
    if roles & {"edt", "ed"}:
        score -= 30
    return score


def _score_person_name(value: str, *, raw_value: str | None = None) -> int:
    score = 0
    if NON_AUTHOR_HINT_RE.search(value) or (raw_value and NON_AUTHOR_HINT_RE.search(raw_value)):
        score -= 60
    if PUBLISHER_NOISE_RE.search(value):
        score -= 60
    if SITE_NOISE_RE.search(value):
        score -= 80
    if len(value.split()) >= 2:
        score += 10
    return score


def _select_best_publisher(
    entries: Sequence[EpubMetadataEntry],
    *,
    content_candidates: Sequence[str] = (),
) -> str | None:
    candidates = [(_score_publisher(entry.value), entry.value.strip()) for entry in entries if entry.value.strip()]
    candidates.extend((_score_publisher(value) + 10, value.strip()) for value in content_candidates if value.strip())
    if not candidates:
        return None
    candidates.sort(key=lambda item: (-item[0], item[1]))
    return candidates[0][1] if candidates[0][0] > 0 else None


def _score_publisher(value: str) -> int:
    score = 20
    if PUBLISHER_NOISE_RE.search(value):
        score -= 60
    if SITE_NOISE_RE.search(value):
        score -= 80
    if any(marker in value for marker in ("Press", "Publishing", "Books", "House", "Perennial", "Group", "LLC")):
        score += 15
    return score


def _select_best_identifier(entries: Sequence[EpubMetadataEntry]) -> str | None:
    ranked = sorted(entries, key=_score_identifier_entry, reverse=True)
    for entry in ranked:
        if entry.value.strip():
            normalized = _normalize_identifier_for_storage(entry)
            if normalized:
                return normalized
    return None


def _normalize_source_title(raw_title: str | None) -> str | None:
    if not raw_title:
        return None
    title = str(raw_title).strip()
    if not title:
        return None
    title = title.replace("\\(", "(").replace("\\)", ")")
    title = TITLE_VENDOR_TAG_RE.sub("", title)
    title = TITLE_FILE_EXT_RE.sub("", title)
    title = TITLE_MULTI_SPACE_RE.sub(" ", title).strip(" -_\t")
    return title or None


def _select_best_isbn(entries: Sequence[EpubMetadataEntry]) -> str | None:
    ranked = sorted(entries, key=_score_identifier_entry, reverse=True)
    for entry in ranked:
        normalized = _extract_isbn_from_identifier(entry)
        if normalized:
            return normalized
    return None


def _score_identifier_entry(entry: EpubMetadataEntry) -> int:
    cleaned = ISBN_CLEAN_RE.sub("", entry.value)
    scheme = " ".join(
        [
            (entry.attrs.get("scheme") or ""),
            (entry.attrs.get("{http://www.idpf.org/2007/opf}scheme") or ""),
            (entry.id or ""),
            " ".join(entry.refinements.get("identifier-type", [])),
        ]
    ).casefold()
    if len(cleaned) in {10, 13}:
        return 100
    if "isbn" in scheme or "isbn" in entry.value.casefold():
        return 90
    if "asin" in scheme:
        return 20
    if "uuid" in scheme or "uuid" in entry.value.casefold():
        return 5
    if "calibre" in scheme:
        return 0
    return 10


def _normalize_identifier_for_storage(entry: EpubMetadataEntry) -> str | None:
    isbn = _extract_isbn_from_identifier(entry)
    if isbn:
        return isbn
    value = entry.value.strip()
    return value or None


def _extract_isbn_from_identifier(entry: EpubMetadataEntry) -> str | None:
    raw_identifier = entry.value
    if not raw_identifier:
        return None
    cleaned = ISBN_CLEAN_RE.sub("", raw_identifier)
    if len(cleaned) in {10, 13}:
        return cleaned.upper()
    lowered = raw_identifier.lower()
    scheme = " ".join(
        [
            lowered,
            (entry.attrs.get("scheme") or "").lower(),
            (entry.attrs.get("{http://www.idpf.org/2007/opf}scheme") or "").lower(),
            (entry.id or "").lower(),
            " ".join(value.lower() for value in entry.refinements.get("identifier-type", [])),
        ]
    )
    if "isbn" in scheme:
        trailing = ISBN_CLEAN_RE.sub("", raw_identifier.split(":")[-1])
        if len(trailing) in {10, 13}:
            return trailing.upper()
    return None


def _extract_authors_from_content_text(text: str) -> list[str]:
    matches: list[str] = []
    snippet = WHITESPACE_RE.sub(" ", text).strip()[:800]
    for match in COPYRIGHT_LINE_RE.finditer(snippet):
        segment = re.split(
            r"\b(?:ISBN(?:-?1[03])?|All rights|Printed in|For ordering|Copyright)\b",
            match.group("names"),
            maxsplit=1,
        )[0]
        matches.extend(_extract_person_names(segment))
    return _dedupe_casefold(matches)


def _extract_person_names(text: str) -> list[str]:
    names: list[str] = []
    normalized = re.sub(r"^\d{4}\s+", "", text.strip())
    normalized = normalized.replace("&", ";").replace(" and ", ";")
    for segment in re.split(r"[;]", normalized):
        segment = segment.strip(" ,")
        if not segment:
            continue
        for match in re.finditer(r"[A-Z][A-Za-z.'-]+(?:\s+[A-Z][A-Za-z.'-]+){1,3}", segment):
            candidate = re.split(
                r"\b(?:The|All|Rights|Reserved|Cover|Project|Guide|Story|Fundamentals|Chapter|Personal)\b",
                match.group(0),
                maxsplit=1,
            )[0].strip()
            cleaned = _clean_person_name(candidate)
            if cleaned and not NON_PERSON_ENTITY_RE.search(cleaned):
                names.append(cleaned)
    return names


def _extract_publishers_from_content_text(text: str) -> list[str]:
    snippet = WHITESPACE_RE.sub(" ", text).strip()[:800]
    publishers: list[str] = []
    normalized_snippet = _normalize_fragmented_publisher_text(snippet)
    for match in IMPRINT_PUBLISHER_RE.finditer(normalized_snippet):
        publisher = _normalize_publisher_value(match.group("publisher"))
        if publisher:
            publishers.append(publisher)
    for match in PUBLISHER_TEXT_RE.finditer(snippet):
        publisher = _normalize_publisher_value(match.group("publisher"))
        if publisher and sum(1 for token in publisher.split() if len(token) == 1) < 3:
            publishers.append(publisher)
    return _dedupe_casefold(publishers)


def _extract_isbns_from_content_text(text: str) -> list[str]:
    snippet = WHITESPACE_RE.sub(" ", text).strip()[:800]
    isbns: list[str] = []
    for match in ISBN_TEXT_RE.finditer(snippet):
        cleaned = ISBN_CLEAN_RE.sub("", match.group("value"))
        if len(cleaned) in {10, 13}:
            isbns.append(cleaned.upper())
    return _dedupe_casefold(isbns)


def _normalize_fragmented_publisher_text(text: str) -> str:
    normalized = text
    suffixes = {"LLC", "INC", "LTD", "CO", "CORP"}
    while True:
        updated = re.sub(
            r"\b([A-Z])\s+([A-Z]{2,8})\b",
            lambda match: f"{match.group(1)}{match.group(2)}",
            normalized,
        )
        updated = re.sub(
            r"\b([A-Z]{3,6})\s+([A-Z]{1,3})\b",
            lambda match: (
                match.group(0)
                if match.group(1) in {"THE", "AND", "FOR", "WITH", "FROM", "THIS", "THAT"}
                or match.group(2) in suffixes
                else f"{match.group(1)}{match.group(2)}"
            ),
            updated,
        )
        if updated == normalized:
            return updated
        normalized = updated


def _normalize_publisher_value(raw_value: str | None) -> str | None:
    if not raw_value:
        return None
    value = _normalize_fragmented_publisher_text(WHITESPACE_RE.sub(" ", raw_value).strip(" ,.;:-"))
    value = re.sub(r"^(?:An\s+Imprint\s+Of|Published\s+by|Publisher)\s+", "", value, flags=re.IGNORECASE)
    if not value:
        return None
    alpha_only = "".join(character for character in value if character.isalpha())
    if alpha_only and alpha_only.upper() == alpha_only:
        tokens = []
        for token in value.split():
            if token in {"LLC", "INC", "LTD", "USA", "UK"}:
                tokens.append(token)
            else:
                tokens.append(token.title())
        value = " ".join(tokens)
    return value or None


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
        return self.match_chunks_with_progress(chunks)

    def match_chunks_with_progress(
        self,
        chunks: Iterable[str],
        *,
        progress_callback: Callable[[MatchProgress], None] | None = None,
    ) -> list[MatchedImportEntry]:
        word_counts: Counter[uuid.UUID] = Counter()
        phrase_counts: Counter[uuid.UUID] = Counter()
        phrase_rows_by_id: dict[uuid.UUID, dict[str, object]] = {}
        chunk_list = list(chunks)
        total_chunks = len(chunk_list)

        for index, text in enumerate(chunk_list, start=1):
            normalized_words = iter_normalized_words(text)
            for match in self._match_phrases(normalized_words):
                phrase_counts[match["entry_id"]] += 1
                phrase_rows_by_id[match["entry_id"]] = match

            for surface in normalized_words:
                resolved = self._resolve_word(surface)
                if resolved is not None:
                    word_counts[resolved] += 1

            if progress_callback is not None:
                progress_callback(
                    MatchProgress(
                        completed=index,
                        total=total_chunks,
                        matched_entries=len(word_counts) + len(phrase_counts),
                        label=f"Matching entries {index}/{total_chunks}",
                    )
                )

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
        if import_source.deleted_at is not None:
            import_source.deleted_at = None
            import_source.deleted_by_user_id = None
            import_source.deletion_reason = None
            import_source.status = "pending"
            import_source.error_message = None
            import_source.processed_at = None
            import_source.matched_entry_count = 0
            await db.commit()
            await db.refresh(import_source)
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
        if import_source.deleted_at is not None:
            import_source.deleted_at = None
            import_source.deleted_by_user_id = None
            import_source.deletion_reason = None
            import_source.status = "pending"
            import_source.error_message = None
            import_source.processed_at = None
            import_source.matched_entry_count = 0
            db.commit()
            db.refresh(import_source)
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
    job_origin: str = "user_import",
    import_batch_id: uuid.UUID | None = None,
) -> ImportJob:
    cache_available = import_source.status == "completed" and import_source.deleted_at is None
    completed_at = datetime.now(timezone.utc) if cache_available else None
    job = ImportJob(
        user_id=user_id,
        import_source_id=import_source.id,
        import_batch_id=import_batch_id,
        job_origin=job_origin,
        source_filename=source_filename,
        source_hash=import_source.source_hash_sha256,
        list_name=list_name,
        list_description=list_description,
        source_title_snapshot=import_source.title,
        source_author_snapshot=import_source.author,
        source_isbn_snapshot=import_source.isbn,
        status="completed" if cache_available else "queued",
        total_items=import_source.matched_entry_count,
        processed_items=import_source.matched_entry_count if cache_available else 0,
        progress_stage="completed" if cache_available else "queued",
        progress_total=import_source.matched_entry_count if cache_available else 0,
        progress_completed=import_source.matched_entry_count if cache_available else 0,
        progress_current_label="Completed from cached import" if cache_available else "Queued",
        matched_entry_count=import_source.matched_entry_count,
        completed_at=completed_at,
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)
    return job


def sync_job_with_source(job: ImportJob, import_source: ImportSource) -> None:
    job.import_source_id = import_source.id
    job.source_hash = import_source.source_hash_sha256
    job.total_items = import_source.matched_entry_count
    is_completed = import_source.status == "completed"
    is_failed = import_source.status == "failed"
    job.processed_items = import_source.matched_entry_count if is_completed else 0
    job.progress_total = import_source.matched_entry_count
    job.progress_completed = import_source.matched_entry_count if is_completed else 0
    job.matched_entry_count = import_source.matched_entry_count
    job.status = "completed" if is_completed else "failed" if is_failed else "processing"
    job.progress_stage = "completed" if is_completed else "failed" if is_failed else "matching"
    if is_completed:
        job.progress_current_label = "Completed from cached import" if job.started_at is None else "Import completed"
    elif is_failed:
        job.progress_current_label = "Import failed"
    else:
        job.progress_current_label = "Continuing import"
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
    if import_source.deleted_at is not None:
        raise ImportCacheDeletedError(
            "This cached import is no longer available. Re-upload the EPUB to regenerate import cache."
        )

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
