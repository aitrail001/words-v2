import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.import_job import ImportJob
    from app.models.user import User


class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    batch_type: Mapped[str] = mapped_column(String(32), nullable=False, insert_default="epub_preimport")
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    created_by_user: Mapped["User"] = relationship("User")
    import_jobs: Mapped[list["ImportJob"]] = relationship("ImportJob", back_populates="import_batch")

    def __init__(self, **kwargs):
        kwargs.setdefault("batch_type", "epub_preimport")
        super().__init__(**kwargs)
