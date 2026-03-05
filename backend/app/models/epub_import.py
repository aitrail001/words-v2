import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EpubImport(Base):
    __tablename__ = "epub_imports"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA256 hash
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, insert_default="pending"
    )  # pending, processing, completed, failed
    total_words: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    processed_words: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("status", "pending")
        kwargs.setdefault("total_words", 0)
        kwargs.setdefault("processed_words", 0)
        super().__init__(**kwargs)

    def __repr__(self) -> str:
        return f"<EpubImport {self.filename} status={self.status}>"
