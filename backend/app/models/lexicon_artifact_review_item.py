import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args


class LexiconArtifactReviewItem(Base):
    __tablename__ = "lexicon_artifact_review_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("lexicon_artifact_review_batches"), ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[str] = mapped_column(String(255), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    normalized_form: Mapped[str | None] = mapped_column(String(255), nullable=True)
    display_text: Mapped[str] = mapped_column(String(255), nullable=False)
    entity_category: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="en")
    frequency_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    cefr_level: Mapped[str | None] = mapped_column(String(8), nullable=True)
    review_status: Mapped[str] = mapped_column(String(16), nullable=False, insert_default="pending", index=True)
    review_priority: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=100, index=True)
    validator_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    validator_issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    qc_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    qc_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    qc_issues: Mapped[list[dict[str, Any]] | None] = mapped_column(JSONB, nullable=True)
    regen_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False)
    import_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    compiled_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    compiled_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    search_text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    batch = relationship("LexiconArtifactReviewBatch", back_populates="items")
    events = relationship("LexiconArtifactReviewItemEvent", back_populates="item", cascade="all, delete-orphan")
    regeneration_request = relationship("LexiconRegenerationRequest", back_populates="item", uselist=False)

    __table_args__ = lexicon_table_args(
        UniqueConstraint("batch_id", "entry_id", name="uq_lexicon_artifact_review_item_batch_entry"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("language", "en")
        kwargs.setdefault("review_status", "pending")
        kwargs.setdefault("review_priority", 100)
        kwargs.setdefault("regen_requested", False)
        kwargs.setdefault("import_eligible", False)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        kwargs.setdefault("updated_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconArtifactReviewItem {self.entry_id} status={self.review_status}>"
