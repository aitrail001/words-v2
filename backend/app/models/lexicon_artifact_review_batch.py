import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_table_args


class LexiconArtifactReviewBatch(Base):
    __tablename__ = "lexicon_artifact_review_batches"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4)
    artifact_family: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    artifact_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    artifact_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_row_count: Mapped[int] = mapped_column(Integer, nullable=False)
    compiled_schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    snapshot_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    source_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    generator_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, insert_default="pending_review", index=True)
    total_items: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    pending_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    approved_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    items = relationship("LexiconArtifactReviewItem", back_populates="batch", cascade="all, delete-orphan")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("artifact_sha256", name="uq_lexicon_artifact_review_batch_sha256"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "pending_review")
        kwargs.setdefault("total_items", 0)
        kwargs.setdefault("pending_count", 0)
        kwargs.setdefault("approved_count", 0)
        kwargs.setdefault("rejected_count", 0)
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        kwargs.setdefault("updated_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<LexiconArtifactReviewBatch {self.id} status={self.status}>"
