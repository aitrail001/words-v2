import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun
    from app.models.meaning import Meaning


class MeaningExample(Base):
    __tablename__ = "meaning_examples"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    meaning_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sentence: Mapped[str] = mapped_column(Text, nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    source: Mapped[str | None] = mapped_column(String(50), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    enrichment_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("lexicon_enrichment_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    meaning: Mapped["Meaning"] = relationship("Meaning")
    enrichment_run: Mapped["LexiconEnrichmentRun | None"] = relationship(
        "LexiconEnrichmentRun",
        back_populates="meaning_examples",
    )

    __table_args__ = (
        UniqueConstraint("meaning_id", "sentence", name="uq_meaning_example_meaning_sentence"),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_meaning_examples_confidence_range",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("order_index", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<MeaningExample {self.sentence[:50]}>"
