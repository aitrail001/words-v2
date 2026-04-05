import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EntryReviewState(Base):
    __tablename__ = "entry_review_states"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    srs_bucket: Mapped[str] = mapped_column(String(16), nullable=False, insert_default="1d")
    cadence_step: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    stability: Mapped[float] = mapped_column(Float, nullable=False, insert_default=0.3)
    difficulty: Mapped[float] = mapped_column(Float, nullable=False, insert_default=0.5)
    success_streak: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    lapse_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    exposure_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    times_remembered: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    last_prompt_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_submission_prompt_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_fragile: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False)
    is_suspended: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False)
    relearning: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False)
    relearning_trigger: Mapped[str | None] = mapped_column(String(32), nullable=True)
    recheck_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    next_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.now(timezone.utc)
    )

    __table_args__ = (
        CheckConstraint(
            "srs_bucket IN ('1d', '2d', '3d', '5d', '7d', '14d', '30d', '90d', '180d', 'known')",
            name="ck_entry_review_states_srs_bucket_valid",
        ),
        CheckConstraint(
            "cadence_step IN (0, 1, 2)",
            name="ck_entry_review_states_cadence_step_valid",
        ),
        CheckConstraint(
            "srs_bucket <> 'known' OR cadence_step = 0",
            name="ck_entry_review_states_known_bucket_cadence_step",
        ),
        Index(
            "ix_entry_review_states_user_recheck_due",
            "user_id",
            "is_suspended",
            "recheck_due_at",
        ),
        Index(
            "ix_entry_review_states_user_next_due",
            "user_id",
            "is_suspended",
            "next_due_at",
        ),
        UniqueConstraint("user_id", "target_type", "target_id", name="uq_entry_review_state_user_target"),
    )


class EntryReviewEvent(Base):
    __tablename__ = "entry_review_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    review_state_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("entry_review_states.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    entry_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    prompt_type: Mapped[str] = mapped_column(String(32), nullable=False)
    prompt_family: Mapped[str | None] = mapped_column(String(32), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    response_input_mode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    response_value: Mapped[str | None] = mapped_column(String(256), nullable=True)
    used_audio_placeholder: Mapped[bool] = mapped_column(Boolean, nullable=False, insert_default=False)
    audio_replay_count: Mapped[int] = mapped_column(Integer, nullable=False, insert_default=0)
    selected_option_id: Mapped[str | None] = mapped_column(String(8), nullable=True)
    scheduled_interval_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    scheduled_by: Mapped[str | None] = mapped_column(String(32), nullable=True)
    time_spent_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
