import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.import_job import ImportJob
    from app.models.import_source_entry import ImportSourceEntry


class ImportSource(Base):
    __tablename__ = "import_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    source_hash_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    pipeline_version: Mapped[str] = mapped_column(String(64), nullable=False)
    lexicon_version: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    author: Mapped[str | None] = mapped_column(String(500), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_identifier: Mapped[str | None] = mapped_column(String(255), nullable=True)
    published_year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    isbn: Mapped[str | None] = mapped_column(String(32), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="pending", index=True)
    matched_entry_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    entries: Mapped[list["ImportSourceEntry"]] = relationship(
        "ImportSourceEntry",
        back_populates="import_source",
        cascade="all, delete-orphan",
    )
    import_jobs: Mapped[list["ImportJob"]] = relationship(
        "ImportJob",
        back_populates="import_source",
    )

    __table_args__ = (
        UniqueConstraint(
            "source_type",
            "source_hash_sha256",
            "pipeline_version",
            "lexicon_version",
            name="uq_import_sources_exact_version",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "pending")
        kwargs.setdefault("matched_entry_count", 0)
        super().__init__(**kwargs)
