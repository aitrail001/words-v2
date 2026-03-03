import logging
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class SM2Result:
    """Result of SM-2 algorithm calculation."""
    ease_factor: float
    interval_days: int
    repetitions: int
    next_review: datetime
    is_mastered: bool


def calculate_next_review(
    quality: int,
    ease_factor: float = 2.5,
    interval_days: int = 0,
    repetitions: int = 0,
) -> SM2Result:
    """
    Calculate the next review date using the SM-2 algorithm.

    The SuperMemo 2 (SM-2) algorithm determines optimal review intervals
    based on how well the user recalls the information.

    Args:
        quality: User's rating of recall quality (0-5)
            - 0: Complete blackout, no recall
            - 1: Incorrect response, but upon seeing the answer, remembered
            - 2: Incorrect response, but seemed easy to recall after seeing answer
            - 3: Correct response with serious difficulty
            - 4: Correct response after hesitation
            - 5: Perfect response with no hesitation
        ease_factor: Current ease factor (difficulty multiplier, starts at 2.5)
        interval_days: Current interval in days
        repetitions: Number of successful repetitions

    Returns:
        SM2Result with updated values and next review date
    """
    # Minimum ease factor (prevents items from becoming too easy)
    MIN_EASE_FACTOR = 1.3

    # Quality threshold for a "correct" answer
    QUALITY_THRESHOLD = 3

    if quality >= QUALITY_THRESHOLD:
        # Correct response
        if repetitions == 0:
            new_interval = 1
        elif repetitions == 1:
            new_interval = 6
        else:
            new_interval = round(interval_days * ease_factor)

        new_repetitions = repetitions + 1

        # Update ease factor based on quality
        # EF' = EF + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
        new_ease_factor = ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    else:
        # Incorrect response - reset
        new_interval = 1
        new_repetitions = 0
        new_ease_factor = max(MIN_EASE_FACTOR, ease_factor - 0.2)

    # Ensure ease factor doesn't go below minimum
    new_ease_factor = max(MIN_EASE_FACTOR, new_ease_factor)

    # Calculate next review date
    next_review = datetime.now(timezone.utc) + timedelta(days=new_interval)

    # Consider mastered if interval is > 21 days (3 weeks)
    is_mastered = new_interval > 21 and quality >= QUALITY_THRESHOLD

    logger.debug(
        "SM-2 calculation: quality=%d interval=%d->%d ef=%.2f->%.2f mastered=%s",
        quality, interval_days, new_interval, ease_factor, new_ease_factor, is_mastered,
    )

    return SM2Result(
        ease_factor=round(new_ease_factor, 2),
        interval_days=new_interval,
        repetitions=new_repetitions,
        next_review=next_review,
        is_mastered=is_mastered,
    )
