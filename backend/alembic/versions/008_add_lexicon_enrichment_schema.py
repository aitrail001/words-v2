"""Add lexicon enrichment schema tables

Revision ID: 008
Revises: 007
Create Date: 2026-03-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_enrichment_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word_id", UUID(as_uuid=True), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
        sa.Column("phase", sa.String(length=20), nullable=False, server_default="phase1"),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("word_id", "phase", name="uq_lexicon_enrichment_job_word_phase"),
    )
    op.create_index("ix_lexicon_enrichment_jobs_word_id", "lexicon_enrichment_jobs", ["word_id"])
    op.create_index("ix_lexicon_enrichment_jobs_status", "lexicon_enrichment_jobs", ["status"])
    op.create_index("ix_lexicon_enrichment_jobs_priority", "lexicon_enrichment_jobs", ["priority"])

    op.create_table(
        "lexicon_enrichment_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "enrichment_job_id",
            UUID(as_uuid=True),
            sa.ForeignKey("lexicon_enrichment_jobs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("generator_provider", sa.String(length=50), nullable=True),
        sa.Column("generator_model", sa.String(length=100), nullable=True),
        sa.Column("validator_provider", sa.String(length=50), nullable=True),
        sa.Column("validator_model", sa.String(length=100), nullable=True),
        sa.Column("prompt_version", sa.String(length=50), nullable=True),
        sa.Column("prompt_hash", sa.String(length=128), nullable=True),
        sa.Column("generator_output", sa.JSON(), nullable=True),
        sa.Column("validator_output", sa.JSON(), nullable=True),
        sa.Column("verdict", sa.String(length=20), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("token_input", sa.Integer(), nullable=True),
        sa.Column("token_output", sa.Integer(), nullable=True),
        sa.Column("estimated_cost", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_lexicon_enrichment_runs_confidence_range",
        ),
    )
    op.create_index("ix_lexicon_enrichment_runs_enrichment_job_id", "lexicon_enrichment_runs", ["enrichment_job_id"])

    op.create_table(
        "meaning_examples",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("meaning_id", UUID(as_uuid=True), sa.ForeignKey("meanings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sentence", sa.Text(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "enrichment_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("lexicon_enrichment_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("meaning_id", "sentence", name="uq_meaning_example_meaning_sentence"),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_meaning_examples_confidence_range",
        ),
    )
    op.create_index("ix_meaning_examples_meaning_id", "meaning_examples", ["meaning_id"])
    op.create_index("ix_meaning_examples_enrichment_run_id", "meaning_examples", ["enrichment_run_id"])

    op.create_table(
        "word_relations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("word_id", UUID(as_uuid=True), sa.ForeignKey("words.id", ondelete="CASCADE"), nullable=False),
        sa.Column("meaning_id", UUID(as_uuid=True), sa.ForeignKey("meanings.id", ondelete="CASCADE"), nullable=True),
        sa.Column("relation_type", sa.String(length=50), nullable=False),
        sa.Column("related_word", sa.String(length=255), nullable=False),
        sa.Column("related_word_id", UUID(as_uuid=True), sa.ForeignKey("words.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column(
            "enrichment_run_id",
            UUID(as_uuid=True),
            sa.ForeignKey("lexicon_enrichment_runs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint(
            "word_id",
            "meaning_id",
            "relation_type",
            "related_word",
            name="uq_word_relation_scope",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="ck_word_relations_confidence_range",
        ),
    )
    op.create_index("ix_word_relations_word_id", "word_relations", ["word_id"])
    op.create_index("ix_word_relations_meaning_id", "word_relations", ["meaning_id"])
    op.create_index("ix_word_relations_relation_type", "word_relations", ["relation_type"])
    op.create_index("ix_word_relations_related_word_id", "word_relations", ["related_word_id"])
    op.create_index("ix_word_relations_enrichment_run_id", "word_relations", ["enrichment_run_id"])

    op.add_column("words", sa.Column("phonetic_source", sa.String(length=50), nullable=True))
    op.add_column("words", sa.Column("phonetic_confidence", sa.Float(), nullable=True))
    op.add_column("words", sa.Column("phonetic_enrichment_run_id", UUID(as_uuid=True), nullable=True))
    op.create_check_constraint(
        "ck_words_phonetic_confidence_range",
        "words",
        "phonetic_confidence IS NULL OR (phonetic_confidence >= 0 AND phonetic_confidence <= 1)",
    )
    op.create_foreign_key(
        "fk_words_phonetic_enrichment_run_id_lexicon_enrichment_runs",
        "words",
        "lexicon_enrichment_runs",
        ["phonetic_enrichment_run_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_words_phonetic_enrichment_run_id", "words", ["phonetic_enrichment_run_id"])


def downgrade() -> None:
    op.drop_index("ix_words_phonetic_enrichment_run_id", table_name="words")
    op.drop_constraint(
        "fk_words_phonetic_enrichment_run_id_lexicon_enrichment_runs",
        "words",
        type_="foreignkey",
    )
    op.drop_constraint("ck_words_phonetic_confidence_range", "words", type_="check")
    op.drop_column("words", "phonetic_enrichment_run_id")
    op.drop_column("words", "phonetic_confidence")
    op.drop_column("words", "phonetic_source")

    op.drop_index("ix_word_relations_enrichment_run_id", table_name="word_relations")
    op.drop_index("ix_word_relations_related_word_id", table_name="word_relations")
    op.drop_index("ix_word_relations_relation_type", table_name="word_relations")
    op.drop_index("ix_word_relations_meaning_id", table_name="word_relations")
    op.drop_index("ix_word_relations_word_id", table_name="word_relations")
    op.drop_table("word_relations")

    op.drop_index("ix_meaning_examples_enrichment_run_id", table_name="meaning_examples")
    op.drop_index("ix_meaning_examples_meaning_id", table_name="meaning_examples")
    op.drop_table("meaning_examples")

    op.drop_index("ix_lexicon_enrichment_runs_enrichment_job_id", table_name="lexicon_enrichment_runs")
    op.drop_table("lexicon_enrichment_runs")

    op.drop_index("ix_lexicon_enrichment_jobs_priority", table_name="lexicon_enrichment_jobs")
    op.drop_index("ix_lexicon_enrichment_jobs_status", table_name="lexicon_enrichment_jobs")
    op.drop_index("ix_lexicon_enrichment_jobs_word_id", table_name="lexicon_enrichment_jobs")
    op.drop_table("lexicon_enrichment_jobs")
