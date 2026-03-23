"""Add lexicon jobs table

Revision ID: 015
Revises: 014
Create Date: 2026-03-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision: str = "015"
down_revision: Union[str, None] = "014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "lexicon_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_by", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("job_type", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'queued'")),
        sa.Column("target_key", sa.Text(), nullable=False),
        sa.Column("request_payload", JSONB(), nullable=False),
        sa.Column("result_payload", JSONB(), nullable=True),
        sa.Column("progress_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_completed", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("progress_current_label", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        schema="lexicon",
    )
    op.create_index("ix_lexicon_jobs_created_by", "lexicon_jobs", ["created_by"], schema="lexicon")
    op.create_index("ix_lexicon_jobs_job_type", "lexicon_jobs", ["job_type"], schema="lexicon")
    op.create_index("ix_lexicon_jobs_status", "lexicon_jobs", ["status"], schema="lexicon")
    op.create_index("ix_lexicon_jobs_target_key", "lexicon_jobs", ["target_key"], schema="lexicon")


def downgrade() -> None:
    op.drop_index("ix_lexicon_jobs_target_key", table_name="lexicon_jobs", schema="lexicon")
    op.drop_index("ix_lexicon_jobs_status", table_name="lexicon_jobs", schema="lexicon")
    op.drop_index("ix_lexicon_jobs_job_type", table_name="lexicon_jobs", schema="lexicon")
    op.drop_index("ix_lexicon_jobs_created_by", table_name="lexicon_jobs", schema="lexicon")
    op.drop_table("lexicon_jobs", schema="lexicon")
