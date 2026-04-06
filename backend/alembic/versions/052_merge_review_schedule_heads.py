"""merge review schedule heads

Revision ID: 052_merge_review_schedule_heads
Revises: 051_srs_bucket_step, 051_timezone_safe_review_sched
Create Date: 2026-04-06 21:30:00.000000
"""

# revision identifiers, used by Alembic.
revision = "052_merge_review_schedule_heads"
down_revision = ("051_srs_bucket_step", "051_timezone_safe_review_sched")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
