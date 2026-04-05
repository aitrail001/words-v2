import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

OUTCOME_FACTORS = {
    "correct_tested": 2.2,
    "remember": 1.6,
    "lookup": 0.6,
    "wrong": 0.35,
}

GRADE_FACTORS = {
    "fail": 0.35,
    "hard_pass": 0.55,
    "good_pass": 1.0,
    "easy_pass": 1.45,
}

CONTEXT_FACTORS = {
    "confidence_check": 0.9,
    "sentence_gap": 1.10,
    "definition_to_entry": 1.05,
    "audio_to_definition": 1.00,
    "entry_to_definition": 0.95,
    "meaning_discrimination": 1.08,
    "typed_recall": 1.15,
    "collocation_check": 1.07,
    "situation_matching": 1.09,
}


@dataclass
class EntryReviewResult:
    outcome: str
    stability: float
    difficulty: float
    interval_days: int
    next_review: datetime
    is_fragile: bool


def calculate_next_review(
    *,
    outcome: str,
    prompt_type: str,
    stability: float = 0.3,
    difficulty: float = 0.5,
    grade: str | None = None,
) -> EntryReviewResult:
    normalized_outcome = outcome if outcome in OUTCOME_FACTORS else "wrong"
    normalized_prompt_type = (
        prompt_type if prompt_type in CONTEXT_FACTORS else "definition_to_entry"
    )
    normalized_grade = grade if grade in GRADE_FACTORS else None

    clamped_stability = max(0.15, float(stability or 0.3))
    clamped_difficulty = min(0.95, max(0.15, float(difficulty or 0.5)))
    difficulty_factor = 1.3 - clamped_difficulty

    if normalized_grade == "fail" or normalized_outcome in {"lookup", "wrong"}:
        next_stability = max(
            0.2 if normalized_outcome == "lookup" else 0.15,
            clamped_stability * OUTCOME_FACTORS[normalized_outcome],
        )
        next_difficulty = min(
            0.95,
            clamped_difficulty + (0.08 if normalized_outcome == "lookup" else 0.12),
        )
    else:
        grade_factor = GRADE_FACTORS.get(
            normalized_grade or ("good_pass" if normalized_outcome == "correct_tested" else "hard_pass"),
            1.0,
        )
        candidate_interval = (
            clamped_stability
            * (OUTCOME_FACTORS[normalized_outcome] if normalized_grade is None else grade_factor)
            * difficulty_factor
            * CONTEXT_FACTORS[normalized_prompt_type]
        )
        next_stability = max(0.15, candidate_interval)
        next_difficulty = max(
            0.15,
            clamped_difficulty - (0.03 if normalized_outcome == "correct_tested" else 0.01),
        )

    interval_days = max(0, int(round(min(next_stability, 180))))
    next_review = datetime.now(timezone.utc) + timedelta(days=next_stability)
    is_fragile = normalized_outcome in {"lookup", "wrong"}

    logger.debug(
        "entry_review_schedule outcome=%s prompt_type=%s stability=%.2f->%.2f difficulty=%.2f->%.2f interval_days=%d",
        normalized_outcome,
        normalized_prompt_type,
        clamped_stability,
        next_stability,
        clamped_difficulty,
        next_difficulty,
        interval_days,
    )

    return EntryReviewResult(
        outcome=normalized_outcome,
        stability=round(next_stability, 2),
        difficulty=round(next_difficulty, 2),
        interval_days=interval_days,
        next_review=next_review,
        is_fragile=is_fragile,
    )
