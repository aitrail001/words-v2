from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

REVIEW_RELEASE_HOUR_LOCAL = 4

_BUCKET_DAY_OFFSETS: dict[str, int | None] = {
    "1d": 1,
    "3d": 3,
    "7d": 7,
    "14d": 14,
    "30d": 30,
    "1m": 30,
    "90d": 90,
    "3m": 90,
    "180d": 180,
    "6m": 180,
    "Known": None,
    "never_for_now": 365,
}


def _normalize_utc_instant(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _user_zone(user_timezone: str) -> ZoneInfo:
    try:
        return ZoneInfo(user_timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"Unknown timezone: {user_timezone}") from exc


def bucket_days(bucket: str) -> int | None:
    if bucket not in _BUCKET_DAY_OFFSETS:
        raise ValueError(f"Unknown review bucket: {bucket}")
    return _BUCKET_DAY_OFFSETS[bucket]


def effective_review_date(
    *,
    instant_utc: datetime,
    user_timezone: str,
    release_hour_local: int = REVIEW_RELEASE_HOUR_LOCAL,
) -> date:
    local_instant = _normalize_utc_instant(instant_utc).astimezone(_user_zone(user_timezone))
    if local_instant.hour < release_hour_local:
        return local_instant.date() - timedelta(days=1)
    return local_instant.date()


def due_review_date_for_bucket(
    *,
    reviewed_at_utc: datetime,
    user_timezone: str,
    bucket: str,
    release_hour_local: int = REVIEW_RELEASE_HOUR_LOCAL,
) -> date | None:
    offset_days = bucket_days(bucket)
    if offset_days is None:
        return None
    return effective_review_date(
        instant_utc=reviewed_at_utc,
        user_timezone=user_timezone,
        release_hour_local=release_hour_local,
    ) + timedelta(days=offset_days)


def min_due_at_for_bucket(
    *,
    reviewed_at_utc: datetime,
    user_timezone: str,
    bucket: str,
    release_hour_local: int = REVIEW_RELEASE_HOUR_LOCAL,
) -> datetime | None:
    due_review_date = due_review_date_for_bucket(
        reviewed_at_utc=reviewed_at_utc,
        user_timezone=user_timezone,
        bucket=bucket,
        release_hour_local=release_hour_local,
    )
    if due_review_date is None:
        return None

    local_due = datetime.combine(
        due_review_date,
        time(hour=release_hour_local),
        tzinfo=_user_zone(user_timezone),
    )
    return local_due.astimezone(timezone.utc)


def due_now(
    *,
    now_utc: datetime,
    user_timezone: str,
    due_review_date: date | None,
    min_due_at_utc: datetime | None,
    release_hour_local: int = REVIEW_RELEASE_HOUR_LOCAL,
) -> bool:
    if due_review_date is None or min_due_at_utc is None:
        return False

    current_review_date = effective_review_date(
        instant_utc=now_utc,
        user_timezone=user_timezone,
        release_hour_local=release_hour_local,
    )
    if current_review_date != due_review_date:
        return False

    return _normalize_utc_instant(now_utc) >= _normalize_utc_instant(min_due_at_utc)


def sticky_due(*, already_due: bool, dynamically_due: bool) -> bool:
    return already_due or dynamically_due
