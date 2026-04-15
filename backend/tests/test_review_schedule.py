from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from app.services.review_schedule import (
    REVIEW_RELEASE_HOUR_LOCAL,
    bucket_days,
    due_now,
    due_review_date_for_bucket,
    effective_review_date,
    min_due_at_for_bucket,
    sticky_due,
)


def test_effective_review_date_uses_previous_day_before_release_hour() -> None:
    before_release = datetime(2026, 4, 9, 17, 59, tzinfo=timezone.utc)
    after_release = datetime(2026, 4, 9, 18, 0, tzinfo=timezone.utc)

    assert (
        effective_review_date(
            instant_utc=before_release,
            user_timezone="Australia/Melbourne",
        )
        == date(2026, 4, 9)
    )
    assert (
        effective_review_date(
            instant_utc=after_release,
            user_timezone="Australia/Melbourne",
        )
        == date(2026, 4, 10)
    )


def test_min_due_at_for_bucket_aligns_same_day_reviews_to_same_release_instant() -> None:
    morning_review = datetime(2026, 4, 10, 0, 0, tzinfo=timezone.utc)
    late_review = datetime(2026, 4, 10, 12, 30, tzinfo=timezone.utc)

    first = min_due_at_for_bucket(
        reviewed_at_utc=morning_review,
        user_timezone="Australia/Melbourne",
        bucket="3d",
    )
    second = min_due_at_for_bucket(
        reviewed_at_utc=late_review,
        user_timezone="Australia/Melbourne",
        bucket="3d",
    )

    assert first is not None
    assert second is not None
    assert first == second
    assert first.astimezone(ZoneInfo("Australia/Melbourne")).hour == REVIEW_RELEASE_HOUR_LOCAL


def test_min_due_at_for_bucket_uses_next_day_canonical_release_after_late_night_review() -> None:
    late_night_review = datetime(2026, 4, 15, 13, 55, tzinfo=timezone.utc)

    due_at = min_due_at_for_bucket(
        reviewed_at_utc=late_night_review,
        user_timezone="Australia/Melbourne",
        bucket="1d",
    )

    assert due_at == datetime(2026, 4, 15, 18, 0, tzinfo=timezone.utc)
    assert due_at.astimezone(ZoneInfo("Australia/Melbourne")) == datetime(
        2026,
        4,
        16,
        REVIEW_RELEASE_HOUR_LOCAL,
        0,
        tzinfo=ZoneInfo("Australia/Melbourne"),
    )


def test_bucket_days_maps_known_bucket_to_none() -> None:
    assert bucket_days("Known") is None


@pytest.mark.parametrize(
    ("bucket", "expected_days"),
    [
        ("30d", 30),
        ("1m", 30),
        ("90d", 90),
        ("3m", 90),
        ("180d", 180),
        ("6m", 180),
        ("never_for_now", 365),
    ],
)
def test_bucket_days_accepts_legacy_aliases(bucket: str, expected_days: int) -> None:
    assert bucket_days(bucket) == expected_days


def test_legacy_aliases_align_to_the_same_due_instant_as_canonical_buckets() -> None:
    reviewed_at_utc = datetime(2026, 4, 10, 12, 30, tzinfo=timezone.utc)

    assert due_review_date_for_bucket(
        reviewed_at_utc=reviewed_at_utc,
        user_timezone="UTC",
        bucket="1m",
    ) == due_review_date_for_bucket(
        reviewed_at_utc=reviewed_at_utc,
        user_timezone="UTC",
        bucket="30d",
    )
    assert min_due_at_for_bucket(
        reviewed_at_utc=reviewed_at_utc,
        user_timezone="UTC",
        bucket="3m",
    ) == min_due_at_for_bucket(
        reviewed_at_utc=reviewed_at_utc,
        user_timezone="UTC",
        bucket="90d",
    )
    assert min_due_at_for_bucket(
        reviewed_at_utc=reviewed_at_utc,
        user_timezone="UTC",
        bucket="never_for_now",
    ) is not None


def test_due_now_requires_both_review_day_and_min_due_at() -> None:
    now_utc = datetime(2026, 4, 10, 6, 0, tzinfo=timezone.utc)

    assert (
        due_now(
            now_utc=now_utc,
            user_timezone="Australia/Melbourne",
            due_review_date=date(2026, 4, 10),
            min_due_at_utc=now_utc + timedelta(hours=1),
        )
        is False
    )
    assert (
        due_now(
            now_utc=now_utc,
            user_timezone="Australia/Melbourne",
            due_review_date=date(2026, 4, 11),
            min_due_at_utc=now_utc - timedelta(minutes=1),
        )
        is False
    )
    assert (
        due_now(
            now_utc=now_utc,
            user_timezone="Australia/Melbourne",
            due_review_date=date(2026, 4, 10),
            min_due_at_utc=now_utc - timedelta(minutes=1),
        )
        is True
    )


@pytest.mark.parametrize(
    ("already_due", "dynamically_due", "expected"),
    [
        (False, False, False),
        (False, True, True),
        (True, False, True),
        (True, True, True),
    ],
)
def test_sticky_due_primitive(already_due: bool, dynamically_due: bool, expected: bool) -> None:
    assert sticky_due(already_due=already_due, dynamically_due=dynamically_due) is expected


def test_dst_keeps_local_release_hour() -> None:
    scheduled = min_due_at_for_bucket(
        reviewed_at_utc=datetime(2026, 10, 3, 5, 0, tzinfo=timezone.utc),
        user_timezone="Australia/Melbourne",
        bucket="1d",
    )

    assert scheduled is not None
    melbourne_time = scheduled.astimezone(ZoneInfo("Australia/Melbourne"))
    assert melbourne_time.hour == REVIEW_RELEASE_HOUR_LOCAL
    assert melbourne_time.minute == 0
