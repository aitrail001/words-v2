"""Add lexicon voice storage policies

Revision ID: 032
Revises: 031
Create Date: 2026-03-29
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_voice_storage_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_key", sa.String(length=255), nullable=False),
        sa.Column("source_reference", sa.String(length=255), nullable=False),
        sa.Column("content_scope", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("family", sa.String(length=32), nullable=False),
        sa.Column("locale", sa.String(length=16), nullable=False),
        sa.Column("primary_storage_root_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fallback_storage_root_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["primary_storage_root_id"], ["lexicon.lexicon_voice_storage_roots.id"], ondelete="RESTRICT", name="fk_lx_voice_storage_policies_primary_root"),
        sa.ForeignKeyConstraint(["fallback_storage_root_id"], ["lexicon.lexicon_voice_storage_roots.id"], ondelete="RESTRICT", name="fk_lx_voice_storage_policies_fallback_root"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_key", name="uq_lexicon_voice_storage_policies_policy_key"),
        sa.UniqueConstraint("source_reference", "content_scope", "provider", "family", "locale", name="uq_lexicon_voice_storage_policies_dims"),
        schema="lexicon",
    )
    op.create_index(op.f("ix_lexicon_lexicon_voice_storage_policies_source_reference"), "lexicon_voice_storage_policies", ["source_reference"], unique=False, schema="lexicon")
    op.create_index(op.f("ix_lexicon_lexicon_voice_storage_policies_primary_storage_root_id"), "lexicon_voice_storage_policies", ["primary_storage_root_id"], unique=False, schema="lexicon")
    op.create_index(op.f("ix_lexicon_lexicon_voice_storage_policies_fallback_storage_root_id"), "lexicon_voice_storage_policies", ["fallback_storage_root_id"], unique=False, schema="lexicon")

    op.add_column(
        "lexicon_voice_assets",
        sa.Column("storage_policy_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="lexicon",
    )
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_storage_policy_id"), "lexicon_voice_assets", ["storage_policy_id"], unique=False, schema="lexicon")

    connection = op.get_bind()
    grouped_assets = connection.execute(
        sa.text(
            """
            select
              coalesce(w.source_reference, mw.source_reference, ew.source_reference) as source_reference,
              a.content_scope as content_scope,
              a.provider as provider,
              a.family as family,
              a.locale as locale,
              a.storage_root_id as storage_root_id
            from lexicon.lexicon_voice_assets a
            left join lexicon.words w on w.id = a.word_id
            left join lexicon.meanings m on m.id = a.meaning_id
            left join lexicon.words mw on mw.id = m.word_id
            left join lexicon.meaning_examples me on me.id = a.meaning_example_id
            left join lexicon.meanings em on em.id = me.meaning_id
            left join lexicon.words ew on ew.id = em.word_id
            group by coalesce(w.source_reference, mw.source_reference, ew.source_reference), a.content_scope, a.provider, a.family, a.locale, a.storage_root_id
            """
        )
    ).mappings()
    for row in grouped_assets:
        source_reference = row["source_reference"] or "legacy-voice"
        content_scope = row["content_scope"]
        provider = row["provider"]
        family = row["family"]
        locale = row["locale"]
        storage_root_id = row["storage_root_id"]
        policy_id = uuid.uuid4()
        policy_key = f"{source_reference}:{content_scope}:{provider}:{family}:{locale}"
        connection.execute(
            sa.text(
                """
                insert into lexicon.lexicon_voice_storage_policies (
                  id, policy_key, source_reference, content_scope, provider, family, locale, primary_storage_root_id, fallback_storage_root_id
                ) values (
                  :id, :policy_key, :source_reference, :content_scope, :provider, :family, :locale, :primary_storage_root_id, null
                )
                """
            ),
            {
                "id": policy_id,
                "policy_key": policy_key,
                "source_reference": source_reference,
                "content_scope": content_scope,
                "provider": provider,
                "family": family,
                "locale": locale,
                "primary_storage_root_id": storage_root_id,
            },
        )
        connection.execute(
            sa.text(
                """
                update lexicon.lexicon_voice_assets as a
                set storage_policy_id = :policy_id
                where a.content_scope = :content_scope
                  and a.provider = :provider
                  and a.family = :family
                  and a.locale = :locale
                  and a.storage_root_id = :storage_root_id
                  and coalesce(
                    (select w.source_reference from lexicon.words w where w.id = a.word_id),
                    (select w2.source_reference
                     from lexicon.meanings m2
                     join lexicon.words w2 on w2.id = m2.word_id
                     where m2.id = a.meaning_id),
                    (select w3.source_reference
                     from lexicon.meaning_examples me3
                     join lexicon.meanings m3 on m3.id = me3.meaning_id
                     join lexicon.words w3 on w3.id = m3.word_id
                     where me3.id = a.meaning_example_id)
                  ) = :source_reference
                """
            ),
            {
                "policy_id": policy_id,
                "content_scope": content_scope,
                "provider": provider,
                "family": family,
                "locale": locale,
                "storage_root_id": storage_root_id,
                "source_reference": source_reference,
            },
        )

    op.alter_column("lexicon_voice_assets", "storage_policy_id", nullable=False, schema="lexicon")
    op.create_foreign_key(
        "fk_lx_voice_assets_storage_policy",
        "lexicon_voice_assets",
        "lexicon_voice_storage_policies",
        ["storage_policy_id"],
        ["id"],
        source_schema="lexicon",
        referent_schema="lexicon",
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_lexicon_voice_assets_storage_path", "lexicon_voice_assets", schema="lexicon", type_="unique")
    op.create_unique_constraint(
        "uq_lexicon_voice_assets_storage_path",
        "lexicon_voice_assets",
        ["storage_policy_id", "relative_path"],
        schema="lexicon",
    )
    op.drop_constraint("fk_lexicon_voice_assets_storage_root", "lexicon_voice_assets", schema="lexicon", type_="foreignkey")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_storage_root_id"), table_name="lexicon_voice_assets", schema="lexicon")
    op.drop_column("lexicon_voice_assets", "storage_root_id", schema="lexicon")


def downgrade() -> None:
    op.add_column(
        "lexicon_voice_assets",
        sa.Column("storage_root_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="lexicon",
    )
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_storage_root_id"), "lexicon_voice_assets", ["storage_root_id"], unique=False, schema="lexicon")
    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            update lexicon.lexicon_voice_assets a
            set storage_root_id = p.primary_storage_root_id
            from lexicon.lexicon_voice_storage_policies p
            where p.id = a.storage_policy_id
            """
        )
    )
    op.alter_column("lexicon_voice_assets", "storage_root_id", nullable=False, schema="lexicon")
    op.create_foreign_key(
        "fk_lexicon_voice_assets_storage_root",
        "lexicon_voice_assets",
        "lexicon_voice_storage_roots",
        ["storage_root_id"],
        ["id"],
        source_schema="lexicon",
        referent_schema="lexicon",
        ondelete="RESTRICT",
    )
    op.drop_constraint("uq_lexicon_voice_assets_storage_path", "lexicon_voice_assets", schema="lexicon", type_="unique")
    op.create_unique_constraint(
        "uq_lexicon_voice_assets_storage_path",
        "lexicon_voice_assets",
        ["storage_root_id", "relative_path"],
        schema="lexicon",
    )
    op.drop_constraint("fk_lx_voice_assets_storage_policy", "lexicon_voice_assets", schema="lexicon", type_="foreignkey")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_storage_policy_id"), table_name="lexicon_voice_assets", schema="lexicon")
    op.drop_column("lexicon_voice_assets", "storage_policy_id", schema="lexicon")

    op.drop_index(op.f("ix_lexicon_lexicon_voice_storage_policies_fallback_storage_root_id"), table_name="lexicon_voice_storage_policies", schema="lexicon")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_storage_policies_primary_storage_root_id"), table_name="lexicon_voice_storage_policies", schema="lexicon")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_storage_policies_source_reference"), table_name="lexicon_voice_storage_policies", schema="lexicon")
    op.drop_table("lexicon_voice_storage_policies", schema="lexicon")
