"""Inline voice storage configuration on policies

Revision ID: 034
Revises: 033
Create Date: 2026-03-29
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "034"
down_revision: Union[str, None] = "033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("lexicon_voice_storage_policies", sa.Column("primary_storage_kind", sa.String(length=32), nullable=True), schema="lexicon")
    op.add_column("lexicon_voice_storage_policies", sa.Column("primary_storage_base", sa.String(length=1024), nullable=True), schema="lexicon")
    op.add_column("lexicon_voice_storage_policies", sa.Column("fallback_storage_kind", sa.String(length=32), nullable=True), schema="lexicon")
    op.add_column("lexicon_voice_storage_policies", sa.Column("fallback_storage_base", sa.String(length=1024), nullable=True), schema="lexicon")

    op.execute(
        sa.text(
            """
            update lexicon.lexicon_voice_storage_policies as policy
            set
              primary_storage_kind = (
                select root.storage_kind
                from lexicon.lexicon_voice_storage_roots as root
                where root.id = policy.primary_storage_root_id
              ),
              primary_storage_base = (
                select root.storage_base
                from lexicon.lexicon_voice_storage_roots as root
                where root.id = policy.primary_storage_root_id
              ),
              fallback_storage_kind = (
                select root.storage_kind
                from lexicon.lexicon_voice_storage_roots as root
                where root.id = policy.fallback_storage_root_id
              ),
              fallback_storage_base = (
                select root.storage_base
                from lexicon.lexicon_voice_storage_roots as root
                where root.id = policy.fallback_storage_root_id
              )
            """
        )
    )

    op.alter_column("lexicon_voice_storage_policies", "primary_storage_kind", nullable=False, schema="lexicon")
    op.alter_column("lexicon_voice_storage_policies", "primary_storage_base", nullable=False, schema="lexicon")

    op.drop_index(op.f("ix_lexicon_lexicon_voice_storage_policies_primary_storage_root_id"), table_name="lexicon_voice_storage_policies", schema="lexicon")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_storage_policies_fallback_storage_root_id"), table_name="lexicon_voice_storage_policies", schema="lexicon")
    op.drop_constraint("fk_lx_voice_storage_policies_primary_root", "lexicon_voice_storage_policies", schema="lexicon", type_="foreignkey")
    op.drop_constraint("fk_lx_voice_storage_policies_fallback_root", "lexicon_voice_storage_policies", schema="lexicon", type_="foreignkey")
    op.drop_column("lexicon_voice_storage_policies", "primary_storage_root_id", schema="lexicon")
    op.drop_column("lexicon_voice_storage_policies", "fallback_storage_root_id", schema="lexicon")

    op.drop_table("lexicon_voice_storage_roots", schema="lexicon")


def downgrade() -> None:
    raise RuntimeError("034_inline_voice_storage_on_policies is not reversible")
