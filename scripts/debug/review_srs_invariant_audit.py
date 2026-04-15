from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
import sys
from typing import Any

from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import get_settings
from app.models.entry_review import EntryReviewEvent, EntryReviewState
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.phrase_entry import PhraseEntry
from app.models.user import User
from app.models.user_preference import UserPreference
from app.models.word import Word
from app.services.review_schedule import due_review_date_for_bucket, min_due_at_for_bucket
from app.services.review_srs_v1 import REVIEW_SRS_V1_BUCKETS, cadence_step_for_bucket


@dataclass(frozen=True)
class Finding:
    code: str
    label: str
    details: dict[str, Any]


def _iso(value: datetime | date | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        else:
            value = value.astimezone(timezone.utc)
    return value.isoformat()


def _anchor_reviewed_at(state: EntryReviewState) -> datetime:
    if state.last_reviewed_at is not None:
        return state.last_reviewed_at
    if state.created_at is not None:
        return state.created_at
    return datetime.now(timezone.utc)


def _entry_labels(session: Session, states: list[EntryReviewState]) -> dict[tuple[str, Any], str]:
    word_ids = sorted({state.entry_id for state in states if state.entry_type == "word"})
    phrase_ids = sorted({state.entry_id for state in states if state.entry_type == "phrase"})
    labels: dict[tuple[str, Any], str] = {}

    if word_ids:
        rows = session.execute(select(Word.id, Word.word).where(Word.id.in_(word_ids))).all()
        labels.update({("word", row.id): row.word for row in rows})
    if phrase_ids:
        rows = session.execute(
            select(PhraseEntry.id, PhraseEntry.phrase).where(PhraseEntry.id.in_(phrase_ids))
        ).all()
        labels.update({("phrase", row.id): row.phrase for row in rows})
    return labels


def _learner_statuses(session: Session, user_id: Any) -> dict[tuple[str, Any], str]:
    rows = session.execute(
        select(
            LearnerEntryStatus.entry_type,
            LearnerEntryStatus.entry_id,
            LearnerEntryStatus.status,
        ).where(LearnerEntryStatus.user_id == user_id)
    ).all()
    return {(row.entry_type, row.entry_id): row.status for row in rows}


def _state_payload(
    state: EntryReviewState,
    *,
    label: str | None,
    learner_status: str | None,
    user_timezone: str | None,
) -> dict[str, Any]:
    return {
        "state_id": str(state.id),
        "label": label or "UNKNOWN",
        "entry_type": state.entry_type,
        "entry_id": str(state.entry_id),
        "target_type": state.target_type,
        "target_id": str(state.target_id) if state.target_id is not None else None,
        "srs_bucket": state.srs_bucket,
        "cadence_step": state.cadence_step,
        "learner_status": learner_status,
        "due_review_date": _iso(state.due_review_date),
        "min_due_at_utc": _iso(state.min_due_at_utc),
        "recheck_due_at": _iso(state.recheck_due_at),
        "last_reviewed_at": _iso(state.last_reviewed_at),
        "created_at": _iso(state.created_at),
        "updated_at": _iso(state.updated_at),
        "user_timezone": user_timezone,
    }


def main() -> None:
    settings = get_settings()
    engine = create_engine(settings.database_url_sync, future=True)

    with Session(engine) as session:
        session.execute(text("SET TRANSACTION READ ONLY"))
        user = session.execute(select(User).where(User.email == "admin@admin.com")).scalar_one()
        preference = session.execute(
            select(UserPreference).where(UserPreference.user_id == user.id)
        ).scalar_one_or_none()
        user_timezone = preference.timezone if preference is not None else "UTC"

        states = session.execute(
            select(EntryReviewState)
            .where(EntryReviewState.user_id == user.id)
            .where(EntryReviewState.is_suspended.is_(False))
            .order_by(
                EntryReviewState.entry_type.asc(),
                EntryReviewState.entry_id.asc(),
                EntryReviewState.target_type.asc().nullsfirst(),
                EntryReviewState.target_id.asc().nullsfirst(),
                EntryReviewState.created_at.asc(),
            )
        ).scalars().all()
        state_ids = [state.id for state in states]
        event_counts = {}
        if state_ids:
            event_counts = {
                row.review_state_id: row.count
                for row in session.execute(
                    select(
                        EntryReviewEvent.review_state_id,
                        func.count(EntryReviewEvent.id).label("count"),
                    )
                    .where(EntryReviewEvent.review_state_id.in_(state_ids))
                    .group_by(EntryReviewEvent.review_state_id)
                ).all()
            }

        labels = _entry_labels(session, states)
        learner_statuses = _learner_statuses(session, user.id)

        print(f"user={user.email} role={user.role} timezone={user_timezone}")
        print(f"review_states={len(states)} review_events={sum(event_counts.values())}")
        print(f"bucket_counts={dict(sorted(Counter(state.srs_bucket for state in states).items()))}")
        print(
            "target_type_counts="
            f"{dict(sorted(Counter((state.target_type or 'entry') for state in states).items()))}"
        )
        print(
            "states_with_events="
            f"{sum(1 for state in states if event_counts.get(state.id, 0) > 0)}"
        )

        findings: list[Finding] = []

        duplicate_entry_groups: dict[tuple[str, Any], list[EntryReviewState]] = defaultdict(list)
        for state in states:
            duplicate_entry_groups[(state.entry_type, state.entry_id)].append(state)

        for (entry_type, entry_id), group in sorted(
            duplicate_entry_groups.items(),
            key=lambda item: (item[0][0], str(item[0][1])),
        ):
            if len(group) < 2:
                continue
            label = labels.get((entry_type, entry_id))
            findings.append(
                Finding(
                    code="duplicate_active_entry_state",
                    label=label or "UNKNOWN",
                    details={
                        "entry_type": entry_type,
                        "entry_id": str(entry_id),
                        "state_ids": [str(state.id) for state in group],
                        "target_shapes": [
                            {
                                "state_id": str(state.id),
                                "target_type": state.target_type,
                                "target_id": str(state.target_id) if state.target_id is not None else None,
                                "due_review_date": _iso(state.due_review_date),
                                "min_due_at_utc": _iso(state.min_due_at_utc),
                                "recheck_due_at": _iso(state.recheck_due_at),
                            }
                            for state in group
                        ],
                    },
                )
            )

        for state in states:
            label = labels.get((state.entry_type, state.entry_id))
            learner_status = learner_statuses.get((state.entry_type, state.entry_id))
            payload = _state_payload(
                state,
                label=label,
                learner_status=learner_status,
                user_timezone=user_timezone,
            )

            if state.srs_bucket not in REVIEW_SRS_V1_BUCKETS:
                findings.append(Finding("invalid_bucket", label or "UNKNOWN", payload))
                continue

            if state.target_type is None and state.target_id is not None:
                findings.append(Finding("target_id_without_type", label or "UNKNOWN", payload))
            if state.target_type is not None and state.target_id is None:
                findings.append(Finding("target_type_without_id", label or "UNKNOWN", payload))

            expected_cadence = cadence_step_for_bucket(state.srs_bucket)
            if state.cadence_step != expected_cadence:
                finding_payload = dict(payload)
                finding_payload["expected_cadence_step"] = expected_cadence
                findings.append(Finding("cadence_step_mismatch", label or "UNKNOWN", finding_payload))

            if state.srs_bucket == "known":
                if (
                    state.due_review_date is not None
                    or state.min_due_at_utc is not None
                    or state.recheck_due_at is not None
                ):
                    findings.append(Finding("known_bucket_has_schedule_fields", label or "UNKNOWN", payload))
                continue

            if state.recheck_due_at is None:
                if state.due_review_date is None or state.min_due_at_utc is None:
                    findings.append(Finding("missing_canonical_schedule", label or "UNKNOWN", payload))
                else:
                    anchor = _anchor_reviewed_at(state)
                    expected_due_review_date = due_review_date_for_bucket(
                        reviewed_at_utc=anchor,
                        user_timezone=user_timezone,
                        bucket=state.srs_bucket,
                    )
                    expected_min_due_at_utc = min_due_at_for_bucket(
                        reviewed_at_utc=anchor,
                        user_timezone=user_timezone,
                        bucket=state.srs_bucket,
                    )
                    if (
                        state.due_review_date != expected_due_review_date
                        or _iso(state.min_due_at_utc) != _iso(expected_min_due_at_utc)
                    ):
                        finding_payload = dict(payload)
                        finding_payload["expected_due_review_date"] = _iso(expected_due_review_date)
                        finding_payload["expected_min_due_at_utc"] = _iso(expected_min_due_at_utc)
                        findings.append(
                            Finding("canonical_schedule_mismatch", label or "UNKNOWN", finding_payload)
                        )

            if learner_status == "learning" and (
                state.recheck_due_at is None
                and state.due_review_date is None
                and state.min_due_at_utc is None
            ):
                findings.append(Finding("learning_state_without_next_step", label or "UNKNOWN", payload))

            if event_counts.get(state.id, 0) == 0:
                findings.append(
                    Finding(
                        "state_without_events",
                        label or "UNKNOWN",
                        {
                            **payload,
                            "event_count": 0,
                        },
                    )
                )

        print(f"findings={len(findings)}")
        for index, finding in enumerate(findings, start=1):
            print(f"[{index:02d}] {finding.code} label={finding.label}")
            for key, value in sorted(finding.details.items()):
                print(f"  {key}: {value}")


if __name__ == "__main__":
    main()
