import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.import_source import ImportSource


class ImportSourceEntry(Base):
    __tablename__ = "import_source_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    import_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("import_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    entry_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    frequency_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=1)
    browse_rank_snapshot: Mapped[int | None] = mapped_column(Integer, nullable=True)
    phrase_kind_snapshot: Mapped[str | None] = mapped_column(String(50), nullable=True)
    cefr_level_snapshot: Mapped[str | None] = mapped_column(String(16), nullable=True)
    normalization_method: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    import_source: Mapped["ImportSource"] = relationship(
        "ImportSource",
        back_populates="entries",
    )

    __table_args__ = (
        UniqueConstraint(
            "import_source_id",
            "entry_type",
            "entry_id",
            name="uq_import_source_entries_entry",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("frequency_count", 1)
        super().__init__(**kwargs)
