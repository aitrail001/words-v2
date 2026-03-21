import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args


class LexiconRegenerationRequest(Base):
    __tablename__ = "lexicon_regeneration_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("lexicon_artifact_review_batches"), ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("lexicon_artifact_review_items"), ondelete="CASCADE"), nullable=False, index=True
    )
    entry_id: Mapped[str] = mapped_column(String(255), nullable=False)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    request_status: Mapped[str] = mapped_column(String(16), nullable=False, insert_default="pending")
    request_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))

    item = relationship("LexiconArtifactReviewItem", back_populates="regeneration_request")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("batch_id", "item_id", name="uq_lexicon_regeneration_request_batch_item"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("request_status", "pending")
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconRegenerationRequest {self.entry_id} status={self.request_status}>"
