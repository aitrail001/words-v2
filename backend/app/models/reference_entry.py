import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_table_args

if TYPE_CHECKING:
    from app.models.reference_localization import ReferenceLocalization


class ReferenceEntry(Base):
    __tablename__ = "reference_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    reference_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    display_form: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_form: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    translation_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    brief_description: Mapped[str] = mapped_column(Text, nullable=False)
    pronunciation: Mapped[str] = mapped_column(String(255), nullable=False)
    learner_tip: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str] = mapped_column(String(10), nullable=False, insert_default="en")
    source_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    source_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    localizations: Mapped[list["ReferenceLocalization"]] = relationship(
        "ReferenceLocalization",
        back_populates="reference_entry",
        cascade="all, delete-orphan",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("normalized_form", "language", name="uq_reference_entry_normalized_language"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("language", "en")
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ReferenceEntry {self.display_form} ({self.reference_type})>"
