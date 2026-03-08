import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
    from app.models.word import Word


class LexiconEnrichmentJob(Base):
    __tablename__ = "lexicon_enrichment_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    word_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("words.id", ondelete="CASCADE"), nullable=False, index=True
    )
    phase: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="phase1")
    status: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="pending", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=100, index=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=3)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    word: Mapped["Word"] = relationship("Word", back_populates="enrichment_jobs")
    runs: Mapped[list["LexiconEnrichmentRun"]] = relationship(
        "LexiconEnrichmentRun",
        back_populates="enrichment_job",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint("word_id", "phase", name="uq_lexicon_enrichment_job_word_phase"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("phase", "phase1")
        kwargs.setdefault("status", "pending")
        kwargs.setdefault("priority", 100)
        kwargs.setdefault("attempt_count", 0)
        kwargs.setdefault("max_attempts", 3)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconEnrichmentJob {self.word_id} phase={self.phase} status={self.status}>"
