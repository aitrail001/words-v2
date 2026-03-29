"""add phrase voice asset ownership

Revision ID: 036
Revises: 035
Create Date: 2026-03-29 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "036"
down_revision = "035"
branch_labels = None
depends_on = None


SCHEMA = "lexicon"
TABLE = "lexicon_voice_assets"
CONSTRAINT = "ck_lexicon_voice_assets_single_parent"


def upgrade() -> None:
    op.add_column(
        TABLE,
        sa.Column("phrase_entry_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("phrase_sense_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.add_column(
        TABLE,
        sa.Column("phrase_sense_example_id", postgresql.UUID(as_uuid=True), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_phrase_entry_id"), TABLE, ["phrase_entry_id"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_phrase_sense_id"), TABLE, ["phrase_sense_id"], unique=False, schema=SCHEMA)
    op.create_index(op.f("ix_lexicon_lexicon_voice_assets_phrase_sense_example_id"), TABLE, ["phrase_sense_example_id"], unique=False, schema=SCHEMA)
    op.create_foreign_key(
        "fk_voice_assets_phrase_entry",
        TABLE,
        "phrase_entries",
        ["phrase_entry_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_voice_assets_phrase_sense",
        TABLE,
        "phrase_senses",
        ["phrase_sense_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_voice_assets_phrase_example",
        TABLE,
        "phrase_sense_examples",
        ["phrase_sense_example_id"],
        ["id"],
        source_schema=SCHEMA,
        referent_schema=SCHEMA,
        ondelete="CASCADE",
    )
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        "((word_id IS NOT NULL)::int + (meaning_id IS NOT NULL)::int + (meaning_example_id IS NOT NULL)::int + (phrase_entry_id IS NOT NULL)::int + (phrase_sense_id IS NOT NULL)::int + (phrase_sense_example_id IS NOT NULL)::int) = 1",
        schema=SCHEMA,
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, schema=SCHEMA, type_="check")
    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        "((word_id IS NOT NULL)::int + (meaning_id IS NOT NULL)::int + (meaning_example_id IS NOT NULL)::int) = 1",
        schema=SCHEMA,
    )
    op.drop_constraint("fk_voice_assets_phrase_example", TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_constraint("fk_voice_assets_phrase_sense", TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_constraint("fk_voice_assets_phrase_entry", TABLE, schema=SCHEMA, type_="foreignkey")
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_phrase_sense_example_id"), table_name=TABLE, schema=SCHEMA)
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_phrase_sense_id"), table_name=TABLE, schema=SCHEMA)
    op.drop_index(op.f("ix_lexicon_lexicon_voice_assets_phrase_entry_id"), table_name=TABLE, schema=SCHEMA)
    op.drop_column(TABLE, "phrase_sense_example_id", schema=SCHEMA)
    op.drop_column(TABLE, "phrase_sense_id", schema=SCHEMA)
    op.drop_column(TABLE, "phrase_entry_id", schema=SCHEMA)
