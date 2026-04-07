"""add timezone-safe review schedule fields

Revision ID: 051_timezone_safe_review_sched
Revises: 050_drop_legacy_review_tables
Create Date: 2026-04-06 11:15:00.000000
"""

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from alembic import op
import sqlalchemy as sa


revision = "051_timezone_safe_review_sched"
down_revision = "050_drop_legacy_review_tables"
branch_labels = None
depends_on = None


def _resolved_timezone(raw_timezone: str | None) -> str:
    # Legacy rows can be missing timezone data during rollout; default to UTC for backfill.
    return raw_timezone or "UTC"


def _normalize_utc_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _user_zone(user_timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {user_timezone}") from exc


def _effective_review_date(*, instant_utc: datetime, user_timezone: str, release_hour_local: int = 4) -> date:
    local_instant = _normalize_utc_instant(instant_utc).astimezone(_user_zone(user_timezone))
    if local_instant.hour < release_hour_local:
        return local_instant.date() - timedelta(days=1)
    return local_instant.date()


def upgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column("timezone", sa.String(length=64), nullable=True),
    )
    op.add_column("entry_review_states", sa.Column("due_review_date", sa.Date(), nullable=True))
    op.add_column("entry_review_states", sa.Column("min_due_at_utc", sa.DateTime(timezone=True), nullable=True))
    op.create_index(
        "ix_entry_review_states_due_review_date",
        "entry_review_states",
        ["due_review_date"],
        unique=False,
    )
    op.create_index(
        "ix_entry_review_states_min_due_at_utc",
        "entry_review_states",
        ["min_due_at_utc"],
        unique=False,
    )

    conn = op.get_bind()
    conn.execute(
        sa.text(
            """
            UPDATE user_preferences
            SET timezone = 'UTC'
            WHERE timezone IS NULL
            """
        )
    )
    rows = conn.execute(
        sa.text(
            """
            SELECT ers.id, ers.next_due_at, up.timezone
            FROM entry_review_states AS ers
            LEFT JOIN user_preferences AS up ON up.user_id = ers.user_id
            WHERE ers.next_due_at IS NOT NULL
            """
        )
    ).mappings()

    for row in rows:
        min_due_at_utc = row["next_due_at"]
        if min_due_at_utc.tzinfo is None:
            min_due_at_utc = min_due_at_utc.replace(tzinfo=timezone.utc)

        user_timezone = _resolved_timezone(row["timezone"])
        try:
            due_review_date = _effective_review_date(
                instant_utc=min_due_at_utc,
                user_timezone=user_timezone,
            )
        except ValueError:
            due_review_date = _effective_review_date(
                instant_utc=min_due_at_utc,
                user_timezone="UTC",
            )

        conn.execute(
            sa.text(
                """
                UPDATE entry_review_states
                SET min_due_at_utc = :min_due_at_utc,
                    due_review_date = :due_review_date
                WHERE id = :id
                """
            ),
            {
                "id": row["id"],
                "min_due_at_utc": min_due_at_utc,
                "due_review_date": due_review_date,
            },
        )

    op.alter_column("user_preferences", "timezone", nullable=False)


def downgrade() -> None:
    op.drop_index("ix_entry_review_states_min_due_at_utc", table_name="entry_review_states")
    op.drop_index("ix_entry_review_states_due_review_date", table_name="entry_review_states")
    op.drop_column("entry_review_states", "min_due_at_utc")
    op.drop_column("entry_review_states", "due_review_date")
    op.drop_column("user_preferences", "timezone")
