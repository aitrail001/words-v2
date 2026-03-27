import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.schema_names import lexicon_table_args


class LearnerCatalogEntry(Base):
    __tablename__ = "learner_catalog_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    display_text: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_form: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    browse_rank: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    bucket_start: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    cefr_level: Mapped[str | None] = mapped_column(String(50), nullable=True)
    primary_part_of_speech: Mapped[str | None] = mapped_column(String(50), nullable=True)
    phrase_kind: Mapped[str | None] = mapped_column(String(50), nullable=True)
    is_ranked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"),
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("entry_type", "entry_id", name="uq_learner_catalog_entries_entry"),
    )

