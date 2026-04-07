"""add srs bucket and cadence step

Revision ID: 051_srs_bucket_step
Revises: 050_drop_legacy_review_tables
Create Date: 2026-04-05 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "051_srs_bucket_step"
down_revision = "050_drop_legacy_review_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "entry_review_states",
        sa.Column(
            "srs_bucket",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'1d'"),
        ),
    )
    op.add_column(
        "entry_review_states",
        sa.Column(
            "cadence_step",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.execute(
        """
        -- Backfill Known rows first so the general bucket mapping below does not overwrite them.
        UPDATE entry_review_states AS ers
        SET srs_bucket = 'known',
            cadence_step = 0
        WHERE EXISTS (
            SELECT 1
            FROM learner_entry_statuses AS les
            WHERE les.user_id = ers.user_id
              AND les.entry_type = ers.entry_type
              AND les.entry_id = ers.entry_id
              AND les.status = 'known'
        )
        """
    )

    op.execute(
        """
        -- Map the existing schedule onto the nearest V1 bucket using explicit day thresholds.
        UPDATE entry_review_states AS ers
        SET srs_bucket = CASE
            WHEN ers.srs_bucket = 'known' THEN 'known'
            WHEN ers.next_due_at IS NOT NULL THEN CASE
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 1 THEN '1d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 2 THEN '2d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 3 THEN '3d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 5 THEN '5d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 7 THEN '7d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 14 THEN '14d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 30 THEN '30d'
                WHEN EXTRACT(EPOCH FROM (ers.next_due_at - NOW())) / 86400.0 <= 90 THEN '90d'
                ELSE '180d'
            END
            WHEN ers.stability IS NOT NULL THEN CASE
                WHEN ers.stability <= 1.5 THEN '1d'
                WHEN ers.stability <= 2.5 THEN '2d'
                WHEN ers.stability <= 4.0 THEN '3d'
                WHEN ers.stability <= 6.0 THEN '5d'
                WHEN ers.stability <= 10.0 THEN '7d'
                WHEN ers.stability <= 21.0 THEN '14d'
                WHEN ers.stability <= 60.0 THEN '30d'
                WHEN ers.stability <= 120.0 THEN '90d'
                ELSE '180d'
            END
            ELSE '1d'
        END
        WHERE ers.srs_bucket <> 'known'
        """
    )

    op.execute(
        """
        UPDATE entry_review_states
        SET cadence_step = CASE srs_bucket
            WHEN '1d' THEN 0
            WHEN '2d' THEN 1
            WHEN '3d' THEN 2
            WHEN '5d' THEN 0
            WHEN '7d' THEN 1
            WHEN '14d' THEN 2
            WHEN '30d' THEN 0
            WHEN '90d' THEN 1
            WHEN '180d' THEN 2
            WHEN 'known' THEN 0
            ELSE 0
        END
        """
    )

    op.create_check_constraint(
        "ck_entry_review_states_srs_bucket_valid",
        "entry_review_states",
        "srs_bucket IN ('1d', '2d', '3d', '5d', '7d', '14d', '30d', '90d', '180d', 'known')",
    )
    op.create_check_constraint(
        "ck_entry_review_states_cadence_step_valid",
        "entry_review_states",
        "cadence_step IN (0, 1, 2)",
    )
    op.create_check_constraint(
        "ck_entry_review_states_known_bucket_cadence_step",
        "entry_review_states",
        "srs_bucket <> 'known' OR cadence_step = 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_entry_review_states_known_bucket_cadence_step", "entry_review_states", type_="check")
    op.drop_constraint("ck_entry_review_states_cadence_step_valid", "entry_review_states", type_="check")
    op.drop_constraint("ck_entry_review_states_srs_bucket_valid", "entry_review_states", type_="check")
    op.drop_column("entry_review_states", "cadence_step")
    op.drop_column("entry_review_states", "srs_bucket")
