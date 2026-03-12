import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_review_batch import LexiconReviewBatch


class LexiconReviewItem(Base):
    __tablename__ = "lexicon_review_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("lexicon_review_batches"), ondelete="CASCADE"), nullable=False, index=True
    )
    lexeme_id: Mapped[str] = mapped_column(String(255), nullable=False)
    lemma: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="en")
    wordfreq_rank: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    risk_band: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    selection_risk_score: Mapped[int] = mapped_column(Integer, nullable=False)
    deterministic_selected_wn_synset_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    reranked_selected_wn_synset_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    candidate_metadata: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    auto_accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False, index=True)
    review_required: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="pending", index=True)
    review_override_wn_synset_ids: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    row_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    batch: Mapped["LexiconReviewBatch"] = relationship("LexiconReviewBatch", back_populates="items")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("batch_id", "lexeme_id", name="uq_lexicon_review_item_batch_lexeme"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("language", "en")
        kwargs.setdefault("auto_accepted", False)
        kwargs.setdefault("review_required", False)
        kwargs.setdefault("review_status", "pending")
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconReviewItem {self.lexeme_id} status={self.review_status}>"
