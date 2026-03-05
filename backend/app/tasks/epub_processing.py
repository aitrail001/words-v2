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
from app.models.epub_import import EpubImport
from app.models.word import Word

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
