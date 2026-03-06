import uuid
from unittest.mock import MagicMock, patch

import ebooklib

from app.models.epub_import import EpubImport
from app.models.import_job import ImportJob
from app.tasks.epub_processing import extract_epub_vocabulary, process_word_list_import


class TestExtractEpubVocabulary:
    @staticmethod
    def _mock_import_lookup(import_id: uuid.UUID, user_id: uuid.UUID) -> EpubImport:
        return EpubImport(
            id=import_id,
            user_id=user_id,
            filename="book.epub",
            file_hash="a" * 64,
            status="pending",
        )

    @staticmethod
    def _mock_session(session_cls, *execute_results):
        mock_db = MagicMock()
        mock_db.execute.side_effect = execute_results

        mock_session_cm = MagicMock()
        mock_session_cm.__enter__.return_value = mock_db
        mock_session_cm.__exit__.return_value = None
        session_cls.return_value = mock_session_cm

        return mock_db

    @staticmethod
    def _mock_import_job_lookup(job_id: uuid.UUID, user_id: uuid.UUID) -> ImportJob:
        return ImportJob(
            id=job_id,
            user_id=user_id,
            source_filename="book.epub",
            source_hash="b" * 64,
            list_name="Imported list",
            status="queued",
        )

    @patch("app.tasks.epub_processing._cleanup_uploaded_file")
    @patch("app.tasks.epub_processing.epub.read_epub")
    @patch("spacy.blank")
    @patch("spacy.load")
    @patch("app.tasks.epub_processing.Session")
    def test_extract_vocabulary_success(
        self, mock_session_cls, mock_spacy_load, mock_spacy_blank, mock_read_epub, mock_cleanup
    ):
        # Mock ePub content
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = ebooklib.ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<html><body>The quick brown fox jumps over the lazy dog.</body></html>"
        mock_book.get_items.return_value = [mock_item]
        mock_read_epub.return_value = mock_book

        # Mock spaCy NLP
        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        mock_token1 = MagicMock(
            text="quick", lemma_="quick", pos_="ADJ", is_alpha=True, is_stop=False
        )
        mock_token2 = MagicMock(
            text="brown", lemma_="brown", pos_="ADJ", is_alpha=True, is_stop=False
        )
        mock_token3 = MagicMock(
            text="fox", lemma_="fox", pos_="NOUN", is_alpha=True, is_stop=False
        )
        mock_doc.__iter__ = MagicMock(return_value=iter([mock_token1, mock_token2, mock_token3]))
        mock_nlp.return_value = mock_doc
        mock_spacy_load.return_value = mock_nlp
        mock_spacy_blank.return_value = mock_nlp

        user_id = uuid.uuid4()
        import_id = uuid.uuid4()
        file_path = "/tmp/test.epub"
        import_record = self._mock_import_lookup(import_id, user_id)

        import_result = MagicMock()
        import_result.scalar_one_or_none.return_value = import_record
        no_word_result = MagicMock()
        no_word_result.scalar_one_or_none.return_value = None
        self._mock_session(
            mock_session_cls,
            import_result,
            no_word_result,
            no_word_result,
            no_word_result,
        )

        result = extract_epub_vocabulary(str(import_id), str(user_id), file_path)

        assert result["status"] == "completed"
        assert result["total_words"] > 0
        assert "words_created" in result
        mock_cleanup.assert_called_once_with(file_path, str(import_id))

    @patch("app.tasks.epub_processing._cleanup_uploaded_file")
    @patch("app.tasks.epub_processing.epub.read_epub")
    @patch("app.tasks.epub_processing.Session")
    def test_extract_vocabulary_invalid_epub(
        self, mock_session_cls, mock_read_epub, mock_cleanup
    ):
        mock_read_epub.side_effect = Exception("Invalid ePub format")

        user_id = uuid.uuid4()
        import_id = uuid.uuid4()
        file_path = "/tmp/invalid.epub"
        import_record = self._mock_import_lookup(import_id, user_id)

        import_result = MagicMock()
        import_result.scalar_one_or_none.return_value = import_record
        self._mock_session(mock_session_cls, import_result)

        result = extract_epub_vocabulary(str(import_id), str(user_id), file_path)

        assert result["status"] == "failed"
        assert "error" in result
        mock_cleanup.assert_called_once_with(file_path, str(import_id))

    @patch("app.tasks.epub_processing._cleanup_uploaded_file")
    @patch("app.tasks.epub_processing.epub.read_epub")
    @patch("spacy.blank")
    @patch("spacy.load")
    @patch("app.tasks.epub_processing.Session")
    def test_extract_vocabulary_filters_stop_words(
        self, mock_session_cls, mock_spacy_load, mock_spacy_blank, mock_read_epub, mock_cleanup
    ):
        # Mock ePub content
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = ebooklib.ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<html><body>The run go 123.</body></html>"
        mock_book.get_items.return_value = [mock_item]
        mock_read_epub.return_value = mock_book

        # Only "run" passes all filters (alpha, non-stop, len > 2)
        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        stop_word = MagicMock(
            text="the", lemma_="the", pos_="DET", is_alpha=True, is_stop=True
        )
        valid_word = MagicMock(
            text="run", lemma_="run", pos_="VERB", is_alpha=True, is_stop=False
        )
        short_word = MagicMock(
            text="go", lemma_="go", pos_="VERB", is_alpha=True, is_stop=False
        )
        non_alpha = MagicMock(
            text="123", lemma_="123", pos_="NUM", is_alpha=False, is_stop=False
        )
        mock_doc.__iter__ = MagicMock(
            return_value=iter([stop_word, valid_word, short_word, non_alpha])
        )
        mock_nlp.return_value = mock_doc
        mock_spacy_load.return_value = mock_nlp
        mock_spacy_blank.return_value = mock_nlp

        user_id = uuid.uuid4()
        import_id = uuid.uuid4()
        file_path = "/tmp/stop-words.epub"
        import_record = self._mock_import_lookup(import_id, user_id)

        import_result = MagicMock()
        import_result.scalar_one_or_none.return_value = import_record
        no_word_result = MagicMock()
        no_word_result.scalar_one_or_none.return_value = None
        self._mock_session(mock_session_cls, import_result, no_word_result)

        result = extract_epub_vocabulary(str(import_id), str(user_id), file_path)

        assert result["status"] == "completed"
        assert result["total_words"] == 1
        assert result["words_created"] == 1
        mock_cleanup.assert_called_once_with(file_path, str(import_id))

    @patch("app.tasks.epub_processing._cleanup_uploaded_file")
    @patch("app.tasks.epub_processing.epub.read_epub")
    @patch("spacy.blank")
    @patch("spacy.load")
    @patch("app.tasks.epub_processing.Session")
    def test_extract_vocabulary_lemmatization(
        self, mock_session_cls, mock_spacy_load, mock_spacy_blank, mock_read_epub, mock_cleanup
    ):
        # Mock ePub content
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = ebooklib.ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<html><body>Running runs walked.</body></html>"
        mock_book.get_items.return_value = [mock_item]
        mock_read_epub.return_value = mock_book

        # "Running" and "runs" collapse into lemma "run"
        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        running = MagicMock(
            text="Running", lemma_="Run", pos_="VERB", is_alpha=True, is_stop=False
        )
        runs = MagicMock(
            text="runs", lemma_="run", pos_="VERB", is_alpha=True, is_stop=False
        )
        walked = MagicMock(
            text="walked", lemma_="walk", pos_="VERB", is_alpha=True, is_stop=False
        )
        mock_doc.__iter__ = MagicMock(return_value=iter([running, runs, walked]))
        mock_nlp.return_value = mock_doc
        mock_spacy_load.return_value = mock_nlp
        mock_spacy_blank.return_value = mock_nlp

        user_id = uuid.uuid4()
        import_id = uuid.uuid4()
        file_path = "/tmp/lemmatization.epub"
        import_record = self._mock_import_lookup(import_id, user_id)

        import_result = MagicMock()
        import_result.scalar_one_or_none.return_value = import_record
        no_word_result = MagicMock()
        no_word_result.scalar_one_or_none.return_value = None
        self._mock_session(
            mock_session_cls,
            import_result,
            no_word_result,
            no_word_result,
        )

        result = extract_epub_vocabulary(str(import_id), str(user_id), file_path)

        assert result["status"] == "completed"
        assert result["total_words"] == 2
        assert result["words_created"] == 2
        mock_cleanup.assert_called_once_with(file_path, str(import_id))

    @patch("app.tasks.epub_processing._cleanup_uploaded_file")
    @patch("app.tasks.epub_processing.epub.read_epub")
    @patch("spacy.blank")
    @patch("spacy.load")
    @patch("app.tasks.epub_processing.Session")
    def test_extract_vocabulary_missing_spacy_model_falls_back_and_completes(
        self, mock_session_cls, mock_spacy_load, mock_spacy_blank, mock_read_epub, mock_cleanup
    ):
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = ebooklib.ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<html><body>Alpha beta gamma.</body></html>"
        mock_book.get_items.return_value = [mock_item]
        mock_read_epub.return_value = mock_book

        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        alpha = MagicMock(text="Alpha", lemma_="alpha", is_alpha=True, is_stop=False)
        beta = MagicMock(text="beta", lemma_="beta", is_alpha=True, is_stop=False)
        gamma = MagicMock(text="gamma", lemma_="gamma", is_alpha=True, is_stop=False)
        mock_doc.__iter__ = MagicMock(return_value=iter([alpha, beta, gamma]))
        mock_nlp.return_value = mock_doc

        mock_spacy_load.side_effect = OSError("Model not found")
        mock_spacy_blank.return_value = mock_nlp

        user_id = uuid.uuid4()
        import_id = uuid.uuid4()
        file_path = "/tmp/model-missing.epub"
        import_record = self._mock_import_lookup(import_id, user_id)

        import_result = MagicMock()
        import_result.scalar_one_or_none.return_value = import_record
        no_word_result = MagicMock()
        no_word_result.scalar_one_or_none.return_value = None
        self._mock_session(
            mock_session_cls,
            import_result,
            no_word_result,
            no_word_result,
            no_word_result,
        )

        result = extract_epub_vocabulary(str(import_id), str(user_id), file_path)

        assert result["status"] == "completed"
        assert result["total_words"] == 3
        assert result["words_created"] == 3
        mock_spacy_load.assert_called_once_with("en_core_web_sm")
        mock_spacy_blank.assert_called_once_with("en")
        mock_cleanup.assert_called_once_with(file_path, str(import_id))

    @patch("app.tasks.epub_processing._cleanup_uploaded_file")
    @patch("app.tasks.epub_processing.epub.read_epub")
    @patch("spacy.blank")
    @patch("spacy.load")
    @patch("app.tasks.epub_processing.Session")
    def test_process_word_list_import_missing_spacy_model_falls_back_and_completes(
        self, mock_session_cls, mock_spacy_load, mock_spacy_blank, mock_read_epub, mock_cleanup
    ):
        mock_book = MagicMock()
        mock_item = MagicMock()
        mock_item.get_type.return_value = ebooklib.ITEM_DOCUMENT
        mock_item.get_content.return_value = b"<html><body>the and or</body></html>"
        mock_book.get_items.return_value = [mock_item]
        mock_book.get_metadata.return_value = []
        mock_read_epub.return_value = mock_book

        mock_nlp = MagicMock()
        mock_doc = MagicMock()
        mock_doc.__iter__ = MagicMock(return_value=iter([]))
        mock_nlp.return_value = mock_doc

        mock_spacy_load.side_effect = OSError("Model not found")
        mock_spacy_blank.return_value = mock_nlp

        user_id = uuid.uuid4()
        job_id = uuid.uuid4()
        file_path = "/tmp/model-missing-import-job.epub"
        import_job = self._mock_import_job_lookup(job_id, user_id)

        import_job_result = MagicMock()
        import_job_result.scalar_one_or_none.return_value = import_job
        no_book_result = MagicMock()
        no_book_result.scalar_one_or_none.return_value = None
        self._mock_session(mock_session_cls, import_job_result, no_book_result)

        result = process_word_list_import(str(job_id), str(user_id), file_path)

        assert result["status"] == "completed"
        assert import_job.status == "completed"
        assert import_job.error_count == 0
        mock_spacy_load.assert_called_once_with("en_core_web_sm")
        mock_spacy_blank.assert_called_once_with("en")
        mock_cleanup.assert_called_once_with(file_path, str(job_id))
