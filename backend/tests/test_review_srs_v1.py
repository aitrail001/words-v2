import uuid

import pytest

from app.models.entry_review import EntryReviewState
from app.services.review_srs_v1 import (
    REVIEW_SRS_V1_BUCKETS,
    advance_bucket,
    backoff_bucket,
    bucket_for_interval_days,
    cadence_step_for_bucket,
    normalize_review_mode,
    select_cadence_family,
    should_graduate_to_known,
    stage_group_for_bucket,
)


def test_review_srs_v1_bucket_order_is_explicit_and_stable():
    assert REVIEW_SRS_V1_BUCKETS == (
        "1d",
        "2d",
        "3d",
        "5d",
        "7d",
        "14d",
        "30d",
        "90d",
        "180d",
        "known",
    )


@pytest.mark.parametrize(
    ("bucket", "expected_group"),
    [
        ("1d", ("1d", "2d", "3d")),
        ("2d", ("1d", "2d", "3d")),
        ("3d", ("1d", "2d", "3d")),
        ("5d", ("5d", "7d", "14d")),
        ("7d", ("5d", "7d", "14d")),
        ("14d", ("5d", "7d", "14d")),
        ("30d", ("30d", "90d", "180d")),
        ("90d", ("30d", "90d", "180d")),
        ("180d", ("30d", "90d", "180d")),
        ("known", ("known",)),
    ],
)
def test_stage_group_for_bucket_is_deterministic(bucket, expected_group):
    assert stage_group_for_bucket(bucket) == expected_group


@pytest.mark.parametrize(
    ("bucket", "expected_step"),
    [
        ("1d", 0),
        ("2d", 1),
        ("3d", 2),
        ("5d", 0),
        ("7d", 1),
        ("14d", 2),
        ("30d", 0),
        ("90d", 1),
        ("180d", 2),
        ("known", 0),
    ],
)
def test_cadence_step_for_bucket_is_deterministic(bucket, expected_step):
    assert cadence_step_for_bucket(bucket) == expected_step


@pytest.mark.parametrize(
    ("bucket", "expected_next", "expected_previous"),
    [
        ("1d", "2d", "1d"),
        ("2d", "3d", "1d"),
        ("3d", "5d", "2d"),
        ("5d", "7d", "3d"),
        ("7d", "14d", "5d"),
        ("14d", "30d", "7d"),
        ("30d", "90d", "14d"),
        ("90d", "180d", "30d"),
        ("180d", "known", "90d"),
        ("known", "known", "180d"),
    ],
)
def test_bucket_advancement_and_backoff_are_deterministic(bucket, expected_next, expected_previous):
    assert advance_bucket(bucket) == expected_next
    assert backoff_bucket(bucket) == expected_previous


@pytest.mark.parametrize(
    ("review_mode", "bucket", "cadence_step", "expected_family"),
    [
        ("gentle", "1d", 0, "simple"),
        ("balanced", "7d", 1, "simple"),
        ("standard", "1d", 0, "simple"),
        ("standard", "7d", 1, "simple"),
        ("standard", "14d", 2, "hard"),
        ("standard", "30d", 0, "hard"),
        ("standard", "90d", 1, "simple"),
        ("standard", "180d", 2, "hard"),
        ("deep", "1d", 0, "simple"),
        ("deep", "2d", 1, "simple"),
        ("deep", "3d", 2, "hard"),
        ("deep", "5d", 0, "hard"),
        ("deep", "14d", 2, "hard"),
        ("deep", "180d", 2, "simple"),
    ],
)
def test_select_cadence_family_is_deterministic(
    review_mode, bucket, cadence_step, expected_family
):
    assert select_cadence_family(review_mode, bucket, cadence_step) == expected_family


@pytest.mark.parametrize(
    ("review_mode", "expected_normalized"),
    [
        ("gentle", "standard"),
        ("balanced", "standard"),
        ("standard", "standard"),
        ("deep", "deep"),
        (None, "standard"),
    ],
)
def test_normalize_review_mode_accepts_current_and_target_names(review_mode, expected_normalized):
    assert normalize_review_mode(review_mode) == expected_normalized


@pytest.mark.parametrize(
    ("interval_days", "expected_bucket"),
    [
        (1, "1d"),
        (2, "2d"),
        (3, "3d"),
        (4, "5d"),
        (5, "5d"),
        (6, "7d"),
        (7, "7d"),
        (10, "14d"),
        (14, "14d"),
        (20, "30d"),
        (30, "30d"),
        (60, "90d"),
        (90, "90d"),
        (180, "180d"),
    ],
)
def test_bucket_for_interval_days_maps_to_official_bucket_list(
    interval_days, expected_bucket
):
    assert bucket_for_interval_days(interval_days) == expected_bucket


def test_select_cadence_family_rejects_invalid_cadence_step():
    with pytest.raises(ValueError):
        select_cadence_family("standard", "1d", 3)


@pytest.mark.parametrize(
    ("bucket", "cadence_step"),
    [
        ("2d", 1),
        ("3d", 2),
    ],
)
def test_select_cadence_family_wraps_short_standard_stage_one_sequence(bucket, cadence_step):
    assert select_cadence_family("balanced", bucket, cadence_step) == "simple"


@pytest.mark.parametrize(
    ("bucket", "prompt_type", "outcome", "expected"),
    [
        ("180d", "confidence_check", "remember", False),
        ("180d", "confidence_check", "correct_tested", False),
        ("180d", "entry_to_definition", "correct_tested", True),
        ("180d", "typed_recall", "correct_tested", True),
        ("90d", "entry_to_definition", "correct_tested", False),
        ("180d", "sentence_gap", "wrong", False),
    ],
)
def test_known_safeguard_requires_objective_success(
    bucket, prompt_type, outcome, expected
):
    assert should_graduate_to_known(bucket, prompt_type, outcome) is expected


def test_entry_review_state_accepts_new_srs_fields():
    state = EntryReviewState(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        entry_type="word",
        entry_id=uuid.uuid4(),
        stability=3.0,
        difficulty=0.5,
        srs_bucket="1d",
        cadence_step=0,
    )

    assert state.srs_bucket == "1d"
    assert state.cadence_step == 0


def test_entry_review_state_table_includes_srs_guardrails():
    constraint_names = {constraint.name for constraint in EntryReviewState.__table__.constraints}

    assert "ck_entry_review_states_srs_bucket_valid" in constraint_names
    assert "ck_entry_review_states_cadence_step_valid" in constraint_names
    assert "ck_entry_review_states_known_bucket_cadence_step" in constraint_names
