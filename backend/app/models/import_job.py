import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.book import Book
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
    word_list_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("word_lists.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="queued", index=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    list_name: Mapped[str] = mapped_column(String(255), nullable=False)
    list_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    processed_items: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
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
    word_list: Mapped["WordList"] = relationship("WordList", back_populates="import_jobs")

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "queued")
        kwargs.setdefault("total_items", 0)
        kwargs.setdefault("processed_items", 0)
        kwargs.setdefault("created_count", 0)
        kwargs.setdefault("skipped_count", 0)
        kwargs.setdefault("not_found_count", 0)
        kwargs.setdefault("error_count", 0)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ImportJob {self.source_filename} status={self.status}>"
