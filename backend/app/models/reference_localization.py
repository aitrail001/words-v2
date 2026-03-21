import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.reference_entry import ReferenceEntry


class ReferenceLocalization(Base):
    __tablename__ = "reference_localizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    reference_entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey(lexicon_fk("reference_entries"), ondelete="CASCADE"), nullable=False, index=True
    )
    locale: Mapped[str] = mapped_column(String(10), nullable=False)
    display_form: Mapped[str] = mapped_column(String(255), nullable=False)
    brief_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    translation_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    reference_entry: Mapped["ReferenceEntry"] = relationship(
        "ReferenceEntry",
        back_populates="localizations",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint("reference_entry_id", "locale", name="uq_reference_localization_entry_locale"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<ReferenceLocalization {self.locale}: {self.display_form[:30]}>"
