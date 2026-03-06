import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import ebooklib
from ebooklib import epub
from bs4 import BeautifulSoup
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.celery_app import celery_app
from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.book import Book
from app.models.epub_import import EpubImport
from app.models.import_job import ImportJob
from app.models.word import Word
from app.models.word_list import WordList
from app.models.word_list_item import WordListItem

logger = get_logger(__name__)
settings = get_settings()

# Sync engine for Celery tasks (can't use async in Celery)
sync_engine = create_engine(settings.database_url_sync)


def _cleanup_uploaded_file(file_path: str, import_id: str) -> None:
    try:
        Path(file_path).unlink(missing_ok=True)
    except OSError as cleanup_error:
        logger.warning(
            "Failed to clean up uploaded file",
            import_id=import_id,
            path=file_path,
            error=str(cleanup_error),
        )


@celery_app.task(bind=True, name="extract_epub_vocabulary")
def extract_epub_vocabulary(self, import_id: str, user_id: str, file_path: str) -> dict:
    """
    Extract vocabulary from an ePub file using spaCy NLP.

    Args:
        import_id: UUID of the EpubImport record
        user_id: UUID of the user
        file_path: Path to the ePub file

    Returns:
        dict with status, total_words, words_created, or error
    """
    import_uuid = uuid.UUID(import_id)
    uuid.UUID(user_id)

    with Session(sync_engine) as db:
        # Update status to processing
        result = db.execute(select(EpubImport).where(EpubImport.id == import_uuid))
        epub_import = result.scalar_one_or_none()
        if not epub_import:
            _cleanup_uploaded_file(file_path, import_id)
            return {"status": "failed", "error": "Import record not found"}

        epub_import.status = "processing"
        epub_import.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            # Parse ePub file
            logger.info("Parsing ePub file", file_path=file_path, import_id=import_id)
            book = epub.read_epub(file_path)

            # Extract text from all items
            text_content = []
            for item in book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    content = item.get_content()
                    soup = BeautifulSoup(content, 'html.parser')
                    text_content.append(soup.get_text())

            full_text = " ".join(text_content)

            # Load spaCy model (English)
            try:
                import spacy
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                # Model not installed
                logger.error("spaCy model not installed. Run: python -m spacy download en_core_web_sm")
                raise Exception("spaCy model 'en_core_web_sm' not installed")

            # Process text with spaCy
            logger.info("Processing text with spaCy", text_length=len(full_text))
            doc = nlp(full_text[:1000000])  # Limit to 1M chars to avoid memory issues

            # Extract words: lemmatize, filter stop words, count frequency
            word_freq = Counter()
            for token in doc:
                if (
                    token.is_alpha  # Only alphabetic
                    and not token.is_stop  # Not a stop word
                    and len(token.text) > 2  # At least 3 characters
                ):
                    lemma = token.lemma_.lower()
                    word_freq[lemma] += 1

            # Update total words
            epub_import.total_words = len(word_freq)
            db.commit()

            # Create Word records for top words (limit to avoid overwhelming DB)
            words_created = 0
            top_words = word_freq.most_common(500)  # Top 500 words

            for lemma, freq in top_words:
                # Check if word already exists
                result = db.execute(
                    select(Word).where(Word.word == lemma, Word.language == "en")
                )
                existing_word = result.scalar_one_or_none()

                if not existing_word:
                    # Create new word
                    word = Word(
                        word=lemma,
                        language="en",
                        frequency_rank=freq,
                    )
                    db.add(word)
                    words_created += 1

                epub_import.processed_words += 1

                # Commit in batches
                if words_created % 50 == 0:
                    db.commit()

            db.commit()

            # Mark as completed
            epub_import.status = "completed"
            epub_import.completed_at = datetime.now(timezone.utc)
            db.commit()

            logger.info(
                "ePub processing completed",
                import_id=import_id,
                total_words=epub_import.total_words,
                words_created=words_created,
            )

            return {
                "status": "completed",
                "total_words": epub_import.total_words,
                "words_created": words_created,
            }

        except Exception as e:
            logger.error("ePub processing failed", import_id=import_id, error=str(e))
            epub_import.status = "failed"
            epub_import.error_message = str(e)
            epub_import.completed_at = datetime.now(timezone.utc)
            db.commit()

            return {"status": "failed", "error": str(e)}
        finally:
            _cleanup_uploaded_file(file_path, import_id)


def _extract_epub_metadata(book: epub.EpubBook) -> tuple[str | None, str | None]:
    title_entries = book.get_metadata("DC", "title")
    author_entries = book.get_metadata("DC", "creator")
    title = title_entries[0][0] if title_entries else None
    author = author_entries[0][0] if author_entries else None
    return title, author


@celery_app.task(bind=True, name="process_word_list_import")
def process_word_list_import(self, job_id: str, user_id: str, file_path: str) -> dict:
    """Process an import job into books, word lists, and word list items."""
    job_uuid = uuid.UUID(job_id)
    user_uuid = uuid.UUID(user_id)

    with Session(sync_engine) as db:
        result = db.execute(select(ImportJob).where(ImportJob.id == job_uuid))
        import_job = result.scalar_one_or_none()
        if import_job is None:
            _cleanup_uploaded_file(file_path, job_id)
            return {"status": "failed", "error": "Import job not found"}

        import_job.status = "processing"
        import_job.started_at = datetime.now(timezone.utc)
        db.commit()

        try:
            logger.info("Processing word-list import job", import_job_id=job_id, file_path=file_path)
            epub_book = epub.read_epub(file_path)
            title, author = _extract_epub_metadata(epub_book)

            text_content = []
            for item in epub_book.get_items():
                if item.get_type() == ebooklib.ITEM_DOCUMENT:
                    content = item.get_content()
                    soup = BeautifulSoup(content, "html.parser")
                    text_content.append(soup.get_text())

            full_text = " ".join(text_content)

            try:
                import spacy
                nlp = spacy.load("en_core_web_sm")
            except OSError:
                logger.error("spaCy model not installed. Run: python -m spacy download en_core_web_sm")
                raise Exception("spaCy model 'en_core_web_sm' not installed")

            doc = nlp(full_text[:1000000])
            word_freq = Counter()
            for token in doc:
                if token.is_alpha and not token.is_stop and len(token.text) > 2:
                    lemma = token.lemma_.lower()
                    word_freq[lemma] += 1

            top_words = word_freq.most_common(500)
            import_job.total_items = len(top_words)
            db.commit()

            book_result = db.execute(select(Book).where(Book.content_hash == import_job.source_hash))
            book = book_result.scalar_one_or_none()
            if book is None:
                book = Book(
                    content_hash=import_job.source_hash,
                    title=title,
                    author=author,
                    language="en",
                    word_count=len(word_freq),
                    file_path=file_path,
                    uploaded_by=user_uuid,
                )
                db.add(book)
                db.flush()
            else:
                if book.word_count is None:
                    book.word_count = len(word_freq)

            word_list = WordList(
                user_id=user_uuid,
                name=import_job.list_name,
                description=import_job.list_description,
                source_type="epub",
                source_reference=import_job.source_filename,
                book_id=book.id,
            )
            db.add(word_list)
            db.flush()

            import_job.book_id = book.id
            import_job.word_list_id = word_list.id

            created_count = 0
            skipped_count = 0

            for lemma, freq in top_words:
                word_result = db.execute(select(Word).where(Word.word == lemma, Word.language == "en"))
                word = word_result.scalar_one_or_none()
                if word is None:
                    word = Word(word=lemma, language="en", frequency_rank=freq)
                    db.add(word)
                    db.flush()

                item_result = db.execute(
                    select(WordListItem).where(
                        WordListItem.word_list_id == word_list.id,
                        WordListItem.word_id == word.id,
                    )
                )
                existing_item = item_result.scalar_one_or_none()
                if existing_item is None:
                    db.add(
                        WordListItem(
                            word_list_id=word_list.id,
                            word_id=word.id,
                            frequency_count=freq,
                        )
                    )
                    created_count += 1
                else:
                    existing_item.frequency_count += freq
                    skipped_count += 1

                import_job.processed_items += 1

                if import_job.processed_items % 25 == 0:
                    db.commit()

            import_job.created_count = created_count
            import_job.skipped_count = skipped_count
            import_job.status = "completed"
            import_job.completed_at = datetime.now(timezone.utc)
            db.commit()

            return {
                "status": "completed",
                "import_job_id": job_id,
                "word_list_id": str(word_list.id),
                "total_items": import_job.total_items,
                "created_count": created_count,
                "skipped_count": skipped_count,
            }
        except Exception as exc:
            logger.error("Word-list import job failed", import_job_id=job_id, error=str(exc))
            import_job.status = "failed"
            import_job.error_count += 1
            import_job.error_message = str(exc)
            import_job.completed_at = datetime.now(timezone.utc)
            db.commit()
            return {"status": "failed", "error": str(exc)}
        finally:
            _cleanup_uploaded_file(file_path, job_id)
