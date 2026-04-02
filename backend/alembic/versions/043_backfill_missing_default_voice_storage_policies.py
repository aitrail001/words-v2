"""Backfill missing default voice storage policies

Revision ID: 043
Revises: 042
Create Date: 2026-04-02
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "043"
down_revision: Union[str, None] = "042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_DEFAULT_POLICY_KEYS = {
    "word": "word_default",
    "definition": "definition_default",
    "example": "example_default",
}


def upgrade() -> None:
    connection = op.get_bind()

    template_row = connection.execute(
        sa.text(
            """
            select
              primary_storage_kind,
              primary_storage_base,
              fallback_storage_kind,
              fallback_storage_base
            from lexicon.lexicon_voice_storage_policies
            where policy_key in ('word_default', 'definition_default', 'example_default')
            order by case when policy_key = 'word_default' then 0 else 1 end, content_scope asc
            limit 1
            """
        )
    ).mappings().first()

    primary_storage_kind = str((template_row or {}).get("primary_storage_kind") or "local").strip()
    primary_storage_base = str((template_row or {}).get("primary_storage_base") or "data/lexicon/voice").strip()
    fallback_storage_kind = str((template_row or {}).get("fallback_storage_kind") or "").strip() or None
    fallback_storage_base = str((template_row or {}).get("fallback_storage_base") or "").strip() or None

    for content_scope, policy_key in _DEFAULT_POLICY_KEYS.items():
        existing_row = connection.execute(
            sa.text(
                """
                select id
                from lexicon.lexicon_voice_storage_policies
                where policy_key = :policy_key
                """
            ),
            {"policy_key": policy_key},
        ).mappings().first()
        if existing_row is not None:
            continue
        connection.execute(
            sa.text(
                """
                insert into lexicon.lexicon_voice_storage_policies (
                  id,
                  policy_key,
                  source_reference,
                  content_scope,
                  provider,
                  family,
                  locale,
                  primary_storage_kind,
                  primary_storage_base,
                  fallback_storage_kind,
                  fallback_storage_base
                ) values (
                  :id,
                  :policy_key,
                  'global',
                  :content_scope,
                  'default',
                  'default',
                  'all',
                  :primary_storage_kind,
                  :primary_storage_base,
                  :fallback_storage_kind,
                  :fallback_storage_base
                )
                """
            ),
            {
                "id": uuid.uuid4(),
                "policy_key": policy_key,
                "content_scope": content_scope,
                "primary_storage_kind": primary_storage_kind,
                "primary_storage_base": primary_storage_base,
                "fallback_storage_kind": fallback_storage_kind,
                "fallback_storage_base": fallback_storage_base,
            },
        )


def downgrade() -> None:
    raise RuntimeError("043_backfill_missing_default_voice_storage_policies is not reversible")
