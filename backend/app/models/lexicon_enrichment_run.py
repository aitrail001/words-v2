import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, String, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
    from app.models.meaning_example import MeaningExample
    from app.models.word import Word
    from app.models.word_relation import WordRelation


class LexiconEnrichmentRun(Base):
    __tablename__ = "lexicon_enrichment_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    enrichment_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("lexicon_enrichment_jobs"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    generator_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    generator_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    validator_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    validator_model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(50), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    generator_output: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    validator_output: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(JSON, nullable=True)
    verdict: Mapped[str | None] = mapped_column(String(20), nullable=True)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estimated_cost: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    enrichment_job: Mapped["LexiconEnrichmentJob"] = relationship(
        "LexiconEnrichmentJob",
        back_populates="runs",
    )
    meaning_examples: Mapped[list["MeaningExample"]] = relationship(
        "MeaningExample",
        back_populates="enrichment_run",
    )
    word_relations: Mapped[list["WordRelation"]] = relationship(
        "WordRelation",
        back_populates="enrichment_run",
    )
    phonetic_words: Mapped[list["Word"]] = relationship(
        "Word",
        back_populates="phonetic_enrichment_run",
        foreign_keys="Word.phonetic_enrichment_run_id",
    )

    __table_args__ = lexicon_table_args(
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_lexicon_enrichment_runs_confidence_range",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconEnrichmentRun {self.enrichment_job_id}>"
