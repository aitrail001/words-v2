import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_fk, lexicon_table_args

if TYPE_CHECKING:
    from app.models.phrase_sense_example import PhraseSenseExample


class PhraseSenseExampleLocalization(Base):
    __tablename__ = "phrase_sense_example_localizations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    phrase_sense_example_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(lexicon_fk("phrase_sense_examples"), ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    translation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    phrase_sense_example: Mapped["PhraseSenseExample"] = relationship(
        "PhraseSenseExample",
        back_populates="localizations",
    )

    __table_args__ = lexicon_table_args(
        UniqueConstraint(
            "phrase_sense_example_id",
            "locale",
            name="uq_phrase_sense_example_localization_example_locale",
        ),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("created_at", datetime.now(timezone.utc))
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<PhraseSenseExampleLocalization {self.locale}>"
