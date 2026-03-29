import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.schema_names import lexicon_table_args

if TYPE_CHECKING:
    from app.models.lexicon_voice_asset import LexiconVoiceAsset


class LexiconVoiceStoragePolicy(Base):
    __tablename__ = "lexicon_voice_storage_policies"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, insert_default=uuid.uuid4)
    policy_key: Mapped[str] = mapped_column(String(255), nullable=False)
    source_reference: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    content_scope: Mapped[str] = mapped_column(String(16), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    family: Mapped[str] = mapped_column(String(32), nullable=False)
    locale: Mapped[str] = mapped_column(String(16), nullable=False)
    primary_storage_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    primary_storage_base: Mapped[str] = mapped_column(String(1024), nullable=False)
    fallback_storage_kind: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fallback_storage_base: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
    voice_assets: Mapped[list["LexiconVoiceAsset"]] = relationship("LexiconVoiceAsset", back_populates="storage_policy")

    __table_args__ = lexicon_table_args(
        UniqueConstraint("policy_key", name="uq_lexicon_voice_storage_policies_policy_key"),
        UniqueConstraint(
            "source_reference",
            "content_scope",
            "provider",
            "family",
            "locale",
            name="uq_lexicon_voice_storage_policies_dims",
        ),
        CheckConstraint(
            "policy_key IN ('word_default', 'definition_default', 'example_default')",
            name="ck_lexicon_voice_storage_policies_allowed_keys",
        ),
        CheckConstraint(
            "(policy_key = 'word_default' AND content_scope = 'word') OR "
            "(policy_key = 'definition_default' AND content_scope = 'definition') OR "
            "(policy_key = 'example_default' AND content_scope = 'example')",
            name="ck_lexicon_voice_storage_policies_key_matches_scope",
        ),
        CheckConstraint("source_reference = 'global'", name="ck_lexicon_voice_storage_policies_global_source"),
        CheckConstraint("provider = 'default'", name="ck_lexicon_voice_storage_policies_default_provider"),
        CheckConstraint("family = 'default'", name="ck_lexicon_voice_storage_policies_default_family"),
        CheckConstraint("locale = 'all'", name="ck_lexicon_voice_storage_policies_all_locale"),
    )
