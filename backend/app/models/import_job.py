import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.book import Book
    from app.models.import_batch import ImportBatch
    from app.models.import_source import ImportSource
    from app.models.word_list import WordList


class ImportJob(Base):
    __tablename__ = "import_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    book_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("books.id", ondelete="SET NULL"), nullable=True, index=True
    )
    import_source_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_sources.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    word_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("word_lists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    import_batch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_batches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    job_origin: Mapped[str] = mapped_column(String(32), nullable=False, insert_default="user_import", index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="queued", index=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    list_name: Mapped[str] = mapped_column(String(255), nullable=False)
    list_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_title_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_author_snapshot: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_isbn_snapshot: Mapped[str | None] = mapped_column(String(32), nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    progress_stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    progress_completed: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    progress_current_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    matched_entry_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    word_entry_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    phrase_entry_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    created_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    not_found_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    not_found_words: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    book: Mapped["Book"] = relationship("Book", back_populates="import_jobs")
    import_source: Mapped["ImportSource | None"] = relationship("ImportSource", back_populates="import_jobs")
    word_list: Mapped["WordList"] = relationship("WordList", back_populates="import_jobs")
    import_batch: Mapped["ImportBatch | None"] = relationship("ImportBatch", back_populates="import_jobs")

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "queued")
        kwargs.setdefault("job_origin", "user_import")
        kwargs.setdefault("total_items", 0)
        kwargs.setdefault("processed_items", 0)
        kwargs.setdefault("progress_total", 0)
        kwargs.setdefault("progress_completed", 0)
        kwargs.setdefault("matched_entry_count", 0)
        kwargs.setdefault("word_entry_count", 0)
        kwargs.setdefault("phrase_entry_count", 0)
        kwargs.setdefault("created_count", 0)
        kwargs.setdefault("skipped_count", 0)
        kwargs.setdefault("not_found_count", 0)
        kwargs.setdefault("error_count", 0)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ImportJob {self.source_filename} status={self.status}>"
