"""Normalize lexicon voice storage roots

Revision ID: 031
Revises: 030
Create Date: 2026-03-29
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "031"
down_revision: Union[str, None] = "030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_voice_storage_roots",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("storage_kind", sa.String(length=32), nullable=False),
        sa.Column("storage_base", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("storage_kind", "storage_base", name="uq_lexicon_voice_storage_roots_kind_base"),
        schema="lexicon",
    )
    op.add_column(
        "lexicon_voice_assets",
        sa.Column("storage_root_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema="lexicon",
    )
    op.create_index(
        op.f("ix_lexicon_lexicon_voice_assets_storage_root_id"),
        "lexicon_voice_assets",
        ["storage_root_id"],
        unique=False,
        schema="lexicon",
    )
    connection = op.get_bind()
    distinct_roots = connection.execute(
        sa.text(
            """
            SELECT DISTINCT storage_kind, storage_base
            FROM lexicon.lexicon_voice_assets
            """
        )
    ).mappings()
    root_ids: dict[tuple[str, str], uuid.UUID] = {}
    for row in distinct_roots:
        root_id = uuid.uuid4()
        root_ids[(row["storage_kind"], row["storage_base"])] = root_id
        connection.execute(
            sa.text(
                """
                INSERT INTO lexicon.lexicon_voice_storage_roots (id, storage_kind, storage_base)
                VALUES (:id, :storage_kind, :storage_base)
                """
            ),
            {"id": root_id, "storage_kind": row["storage_kind"], "storage_base": row["storage_base"]},
        )
    for (storage_kind, storage_base), root_id in root_ids.items():
        connection.execute(
            sa.text(
                """
                UPDATE lexicon.lexicon_voice_assets
                SET storage_root_id = :root_id
                WHERE storage_kind = :storage_kind
                  AND storage_base = :storage_base
                """
            ),
            {"root_id": root_id, "storage_kind": storage_kind, "storage_base": storage_base},
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
    op.drop_column("lexicon_voice_assets", "storage_kind", schema="lexicon")
    op.drop_column("lexicon_voice_assets", "storage_base", schema="lexicon")


def downgrade() -> None:
    op.add_column(
        "lexicon_voice_assets",
        sa.Column("storage_base", sa.String(length=1024), nullable=True),
        schema="lexicon",
    )
    op.add_column(
        "lexicon_voice_assets",
        sa.Column("storage_kind", sa.String(length=32), nullable=True),
        schema="lexicon",
    )
    op.execute(
        """
        UPDATE lexicon.lexicon_voice_assets AS asset
        SET storage_kind = root.storage_kind,
            storage_base = root.storage_base
        FROM lexicon.lexicon_voice_storage_roots AS root
        WHERE root.id = asset.storage_root_id
        """
    )
    op.alter_column("lexicon_voice_assets", "storage_kind", nullable=False, server_default="local", schema="lexicon")
    op.alter_column("lexicon_voice_assets", "storage_base", nullable=False, schema="lexicon")
    op.drop_constraint("uq_lexicon_voice_assets_storage_path", "lexicon_voice_assets", schema="lexicon", type_="unique")
    op.create_unique_constraint(
        "uq_lexicon_voice_assets_storage_path",
        "lexicon_voice_assets",
        ["storage_kind", "storage_base", "relative_path"],
        schema="lexicon",
    )
    op.drop_constraint(
        "fk_lexicon_voice_assets_storage_root",
        "lexicon_voice_assets",
        schema="lexicon",
        type_="foreignkey",
    )
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_storage_root_id"), table_name="lexicon_voice_assets", schema="lexicon")
    op.drop_column("lexicon_voice_assets", "storage_root_id", schema="lexicon")
    op.drop_table("lexicon_voice_storage_roots", schema="lexicon")
