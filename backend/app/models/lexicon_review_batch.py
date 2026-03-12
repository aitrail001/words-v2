import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_review_item import LexiconReviewItem


class LexiconReviewBatch(Base):
    __tablename__ = "lexicon_review_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, insert_default="importing", index=True)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    snapshot_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    review_required_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    auto_accepted_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    import_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items: Mapped[list["LexiconReviewItem"]] = relationship(
        "LexiconReviewItem", back_populates="batch", cascade="all, delete-orphan"
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("user_id", "source_hash", name="uq_lexicon_review_batch_user_hash"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "importing")
        kwargs.setdefault("total_items", 0)
        kwargs.setdefault("review_required_count", 0)
        kwargs.setdefault("auto_accepted_count", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconReviewBatch {self.id} status={self.status}>"
