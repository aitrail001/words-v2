import base64
import hashlib
import json
import uuid
import re
import random
from inspect import isawaitable
from time import monotonic
from datetime import datetime, timezone, timedelta
from typing import Any, Callable

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import and_, func, literal, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models.meaning_example import MeaningExample
from app.models.meaning import Meaning
from app.models.entry_review import EntryReviewEvent, EntryReviewState
from app.models.lexicon_voice_asset import LexiconVoiceAsset
from app.models.learner_entry_status import LearnerEntryStatus
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.user_preference import UserPreference
from app.models.word import Word
from app.services.knowledge_map import extract_pronunciations, select_pronunciation
from app.services.review_prompt_builder import (
    build_available_prompt_types as build_available_prompt_types_impl,
    build_card_prompt as build_card_prompt_impl,
    load_definition_target_distractors as load_definition_target_distractors_impl,
    load_entry_target_distractors as load_entry_target_distractors_impl,
    load_prompt_audio_for_type as load_prompt_audio_for_type_impl,
    load_prompt_distractors as load_prompt_distractors_impl,
    resolve_prompt_preferences as resolve_prompt_preferences_impl,
)
from app.services.review_srs_v1 import (
    REVIEW_SRS_V1_BUCKETS,
    bucket_for_interval_days,
    interval_days_for_bucket,
    bucket_to_interval_days,
    bucket_to_label,
    cadence_step_for_bucket,
    due_at_for_bucket,
)
from app.services.review_submission import (
    apply_entry_state_review_result as apply_entry_state_review_result_impl,
    build_entry_state_detail as build_entry_state_detail_impl,
    submit_entry_state_review as submit_entry_state_review_impl,
    submit_queue_review as submit_queue_review_impl,
)
from app.services.voice_assets import (
    build_voice_asset_playback_url,
    load_phrase_voice_assets,
    load_word_voice_assets,
)
from app.services.review_schedule import (
    bucket_days as schedule_bucket_days,
    due_now,
    due_review_date_for_bucket,
    effective_review_date,
    min_due_at_for_bucket,
    sticky_due,
)

logger = get_logger(__name__)
settings = get_settings()

REVIEW_BUCKET_ORDER = [
    "1d",
    "2d",
    "3d",
    "5d",
    "7d",
    "14d",
    "30d",
    "90d",
    "180d",
]


class ReviewService:
    SCHEDULE_OVERRIDE_DAYS = {
        "1d": 1,
        "2d": 2,
        "3d": 3,
        "5d": 5,
        "7d": 7,
        "14d": 14,
        "30d": 30,
        "90d": 90,
        "180d": 180,
        "known": 180,
    }
    SCHEDULE_OVERRIDE_VALUES = set(SCHEDULE_OVERRIDE_DAYS.keys())
    REVIEW_MODE_CONFIDENCE = "confidence"
    REVIEW_MODE_MCQ = "mcq"
    PROMPT_TYPE_CONFIDENCE_CHECK = "confidence_check"
    PROMPT_TYPE_AUDIO_TO_DEFINITION = "audio_to_definition"
    PROMPT_TYPE_DEFINITION_TO_ENTRY = "definition_to_entry"
    PROMPT_TYPE_SENTENCE_GAP = "sentence_gap"
    PROMPT_TYPE_ENTRY_TO_DEFINITION = "entry_to_definition"
    PROMPT_TYPE_MEANING_DISCRIMINATION = "meaning_discrimination"
    PROMPT_TYPE_TYPED_RECALL = "typed_recall"
    PROMPT_TYPE_SPEAK_RECALL = "speak_recall"
    PROMPT_TYPE_COLLOCATION_CHECK = "collocation_check"
    PROMPT_TYPE_SITUATION_MATCHING = "situation_matching"
    FALLBACK_REVIEW_MODE = REVIEW_MODE_CONFIDENCE
    REVIEW_MODE_OPTIONS = [REVIEW_MODE_MCQ, REVIEW_MODE_CONFIDENCE]
    PROMPT_TYPE_OPTIONS = [
        PROMPT_TYPE_CONFIDENCE_CHECK,
        PROMPT_TYPE_AUDIO_TO_DEFINITION,
        PROMPT_TYPE_DEFINITION_TO_ENTRY,
        PROMPT_TYPE_SENTENCE_GAP,
        PROMPT_TYPE_ENTRY_TO_DEFINITION,
        PROMPT_TYPE_MEANING_DISCRIMINATION,
        PROMPT_TYPE_TYPED_RECALL,
        PROMPT_TYPE_SPEAK_RECALL,
        PROMPT_TYPE_COLLOCATION_CHECK,
        PROMPT_TYPE_SITUATION_MATCHING,
    ]
    PROMPT_FAMILY_BY_TYPE = {
        PROMPT_TYPE_CONFIDENCE_CHECK: "confidence_check",
        PROMPT_TYPE_AUDIO_TO_DEFINITION: "audio_recognition",
        PROMPT_TYPE_DEFINITION_TO_ENTRY: "definition_recall",
        PROMPT_TYPE_SENTENCE_GAP: "context_recall",
        PROMPT_TYPE_ENTRY_TO_DEFINITION: "recognition",
        PROMPT_TYPE_MEANING_DISCRIMINATION: "contrastive",
        PROMPT_TYPE_TYPED_RECALL: "typed_recall",
        PROMPT_TYPE_SPEAK_RECALL: "speech_placeholder",
        PROMPT_TYPE_COLLOCATION_CHECK: "collocation",
        PROMPT_TYPE_SITUATION_MATCHING: "situation",
    }
    SAME_DAY_DISTRACTOR_POOL_LIMIT = 256
    QUEUE_STATS_CACHE_TTL_SECONDS = 5.0
    ALLOWED_QUEUE_SORTS = {"next_review_at", "last_reviewed_at", "text"}
    ALLOWED_QUEUE_ORDERS = {"asc", "desc"}

    def __init__(
        self,
        db: AsyncSession,
    ):
        self.db = db
        self._queue_stats_cache: dict[uuid.UUID, tuple[float, dict[str, Any]]] = {}

    @staticmethod
    def _normalize_prompt_text(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        return trimmed or None

    @staticmethod
    def _normalize_typed_answer(value: str | None) -> str:
        if not value:
            return ""
        lowered = value.lower()
        normalized = re.sub(r"[^\w\s]", " ", lowered)
        return " ".join(normalized.split())

    @classmethod
    def _compare_typed_answer(
        cls,
        *,
        expected_input: str | None,
        typed_answer: str | None,
        entry_type: str,
    ) -> dict[str, Any]:
        normalized_expected = cls._normalize_typed_answer(expected_input)
        normalized_typed = cls._normalize_typed_answer(typed_answer)
        if not normalized_expected or not normalized_typed:
            return {"is_correct": False, "feedback_note": None}
        if normalized_expected == normalized_typed:
            return {"is_correct": True, "feedback_note": None}

        if cls._normalize_entry_type(entry_type) == "phrase":
            expected_tokens = normalized_expected.split()
            typed_tokens = normalized_typed.split()
            if (
                len(expected_tokens) >= 2
                and len(expected_tokens) == len(typed_tokens)
                and expected_tokens[0] == typed_tokens[0]
                and expected_tokens[-1] != typed_tokens[-1]
            ):
                return {
                    "is_correct": False,
                    "feedback_note": (
                        "The verb is right, but the particle is different. Changing the particle changes the phrase."
                    ),
                }

        return {"is_correct": False, "feedback_note": None}

    @staticmethod
    def _prompt_value_for_options(value: str | None) -> str:
        normalized = (value or "").strip()
        return normalized if normalized else "Unavailable"

    @staticmethod
    def _normalize_audio_locale(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().lower().replace("-", "_")
        if not normalized:
            return None
        if normalized in {"en_us", "us"}:
            return "us"
        if normalized in {"en_gb", "uk", "gb"}:
            return "uk"
        if normalized in {"en_au", "au"}:
            return "au"
        return normalized

    @staticmethod
    def _parse_optional_uuid(value: Any) -> uuid.UUID | None:
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError, AttributeError):
            return None

    @staticmethod
    def _prompt_token_expiry() -> datetime:
        return datetime.now(timezone.utc) + timedelta(hours=12)

    @staticmethod
    def _prompt_token_cipher() -> Fernet:
        key_material = hashlib.sha256(settings.jwt_secret.encode("utf-8")).digest()
        return Fernet(base64.urlsafe_b64encode(key_material))

    @staticmethod
    def _encode_prompt_token(payload: dict[str, Any]) -> str:
        token_payload = json.dumps(
            {
                **payload,
                "token_type": "review_prompt",
                "exp": ReviewService._prompt_token_expiry().isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return ReviewService._prompt_token_cipher().encrypt(token_payload).decode("utf-8")

    @staticmethod
    def _decode_prompt_token(token: str | None) -> dict[str, Any] | None:
        if not token:
            return None
        try:
            decrypted = ReviewService._prompt_token_cipher().decrypt(token.encode("utf-8"))
            payload = json.loads(decrypted.decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if payload.get("token_type") != "review_prompt":
            return None
        expiry = payload.get("exp")
        if not isinstance(expiry, str):
            return None
        try:
            expires_at = datetime.fromisoformat(expiry)
        except ValueError:
            return None
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=timezone.utc)
        if expires_at <= datetime.now(timezone.utc):
            return None
        return payload

    def _build_prompt_token_payload(
        self,
        *,
        prompt: dict[str, Any],
        user_id: uuid.UUID | None,
        queue_item_id: uuid.UUID | None,
    ) -> dict[str, Any]:
        options = prompt.get("options") or []
        correct_option_id = next(
            (str(option.get("option_id")) for option in options if option.get("is_correct")),
            None,
        )
        expected_input = prompt.get("expected_input")
        return {
            "prompt_id": str(uuid.uuid4()),
            "issued_at": datetime.now(timezone.utc).isoformat(),
            "user_id": str(user_id) if user_id is not None else None,
            "queue_item_id": str(queue_item_id) if queue_item_id is not None else None,
            "prompt_type": prompt.get("prompt_type"),
            "review_mode": prompt.get("mode"),
            "input_mode": prompt.get("input_mode"),
            "source_entry_type": prompt.get("source_entry_type"),
            "source_entry_id": prompt.get("source_word_id") or prompt.get("source_entry_id"),
            "source_meaning_id": prompt.get("source_meaning_id"),
            "correct_option_id": correct_option_id,
            "expected_input": expected_input,
        }

    def _sanitize_prompt_for_client(
        self,
        *,
        prompt: dict[str, Any],
        prompt_token: str,
    ) -> dict[str, Any]:
        sanitized_options = [
            {
                "option_id": str(option.get("option_id")),
                "label": str(option.get("label")),
            }
            for option in (prompt.get("options") or [])
        ] or None
        input_mode = prompt.get("input_mode")
        return {
            "mode": prompt.get("mode"),
            "prompt_type": prompt.get("prompt_type"),
            "prompt_token": prompt_token,
            "stem": prompt.get("stem"),
            "question": prompt.get("question"),
            "options": sanitized_options,
            "expected_input": None if input_mode in {"typed", "speech_placeholder"} else None,
            "input_mode": input_mode,
            "voice_placeholder_text": prompt.get("voice_placeholder_text"),
            "sentence_masked": prompt.get("sentence_masked"),
            "source_entry_type": prompt.get("source_entry_type"),
            "source_word_id": prompt.get("source_word_id"),
            "source_meaning_id": prompt.get("source_meaning_id"),
            "audio_state": prompt.get("audio_state", "not_available"),
            "audio": prompt.get("audio"),
        }

    def _derive_objective_outcome_from_prompt_token(
        self,
        *,
        prompt_token_payload: dict[str, Any],
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> str:
        input_mode = prompt_token_payload.get("input_mode")
        if input_mode in {"typed", "speech_placeholder"}:
            comparison = self._compare_typed_answer(
                expected_input=prompt_token_payload.get("expected_input"),
                typed_answer=typed_answer,
                entry_type=prompt_token_payload.get("source_entry_type") or "word",
            )
            return "correct_tested" if comparison["is_correct"] else "wrong"
        return (
            "correct_tested"
            if str(selected_option_id or "") == str(prompt_token_payload.get("correct_option_id") or "")
            else "wrong"
        )

    @classmethod
    def _resolve_submit_review_mode_from_prompt_token(
        cls,
        *,
        prompt_token_payload: dict[str, Any],
    ) -> str:
        return cls._normalize_review_mode(prompt_token_payload.get("review_mode"))

    def _resolve_submit_outcome_from_prompt_token(
        self,
        *,
        prompt_token_payload: dict[str, Any],
        outcome: str | None,
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> str:
        issued_review_mode = self._resolve_submit_review_mode_from_prompt_token(
            prompt_token_payload=prompt_token_payload
        )
        explicit_outcome = (
            outcome
            if issued_review_mode != self.REVIEW_MODE_MCQ and outcome in {"remember", "lookup"}
            else None
        )
        if explicit_outcome is not None:
            return explicit_outcome
        if issued_review_mode != self.REVIEW_MODE_MCQ:
            derived_outcome = self._derive_objective_outcome_from_prompt_token(
                prompt_token_payload=prompt_token_payload,
                selected_option_id=selected_option_id,
                typed_answer=typed_answer,
            )
            return "remember" if derived_outcome == "correct_tested" else "lookup"
        return self._derive_objective_outcome_from_prompt_token(
            prompt_token_payload=prompt_token_payload,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
        )

    @classmethod
    async def _build_prompt_audio_payload(
        cls,
        assets: list[LexiconVoiceAsset] | None,
        preferred_accent: str | None = None,
    ) -> dict[str, Any] | None:
        locales: dict[str, dict[str, str | None]] = {}
        for asset in assets or []:
            locale_key = cls._normalize_audio_locale(getattr(asset, "locale", None))
            if locale_key is None:
                continue
            locales.setdefault(
                locale_key,
                {
                    "playback_url": build_voice_asset_playback_url(asset),
                    "locale": asset.locale,
                    "relative_path": asset.relative_path,
                },
            )

        if not locales:
            return None

        preferred_locale = None
        candidate_order = [preferred_accent, "us", "uk", "au"]
        for candidate in candidate_order:
            if candidate is None:
                continue
            if candidate in locales:
                preferred_locale = candidate
                break
        if preferred_locale is None:
            preferred_locale = sorted(locales.keys())[0]

        return {
            "preferred_playback_url": locales[preferred_locale]["playback_url"],
            "preferred_locale": preferred_locale,
            "locales": locales,
        }

    async def _get_user_accent_preference(self, user_id: uuid.UUID) -> str:
        if not hasattr(self, "_accent_preference_cache"):
            self._accent_preference_cache: dict[uuid.UUID, str] = {}
        cached = self._accent_preference_cache.get(user_id)
        if cached:
            return cached
        result = await self.db.execute(
            select(UserPreference.accent_preference).where(UserPreference.user_id == user_id)
        )
        accent = result.scalar_one_or_none() or "us"
        self._accent_preference_cache[user_id] = accent
        return accent

    async def _get_user_review_preferences(self, user_id: uuid.UUID) -> UserPreference:
        if not hasattr(self, "_review_preferences_cache"):
            self._review_preferences_cache: dict[uuid.UUID, UserPreference] = {}
        cached = self._review_preferences_cache.get(user_id)
        if cached is not None:
            return cached

        result = await self.db.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        prefs = result.scalar_one_or_none()
        if prefs is None:
            prefs = UserPreference(user_id=user_id)
        self._review_preferences_cache[user_id] = prefs
        return prefs

    def _get_cached_queue_stats(self, user_id: uuid.UUID) -> dict[str, Any] | None:
        cached = self._queue_stats_cache.get(user_id)
        if cached is None:
            return None
        expires_at, payload = cached
        if expires_at <= monotonic():
            self._queue_stats_cache.pop(user_id, None)
            return None
        return dict(payload)

    def _store_cached_queue_stats(self, user_id: uuid.UUID, stats: dict[str, Any]) -> None:
        self._queue_stats_cache[user_id] = (
            monotonic() + self.QUEUE_STATS_CACHE_TTL_SECONDS,
            dict(stats),
        )

    def _invalidate_queue_stats_cache(self, user_id: uuid.UUID) -> None:
        self._queue_stats_cache.pop(user_id, None)

    @staticmethod
    def _normalize_review_depth_preset(value: str | None) -> str:
        normalized = (value or "balanced").strip().lower()
        if normalized in {"gentle", "balanced", "deep"}:
            return normalized
        return "balanced"

    @classmethod
    def _review_depth_cap(cls, preset: str | None) -> int:
        mapping = {"gentle": 1, "balanced": 2, "deep": 3}
        return mapping.get(cls._normalize_review_depth_preset(preset), 2)

    @staticmethod
    def _coverage_summary(total_targets: int, active_index: int) -> str:
        if total_targets <= 1 or active_index <= 0:
            return "familiar_with_1_meaning"
        if active_index >= total_targets - 1:
            return "deep_coverage"
        return "partial_coverage"

    @staticmethod
    def _unlock_threshold(entry_type: str, lapse_count: int) -> int:
        if entry_type == "phrase" or lapse_count > 0:
            return 4
        return 3

    @classmethod
    def _select_active_target_index(
        cls,
        *,
        total_targets: int,
        active_cap: int,
        success_streak: int,
        lapse_count: int,
        entry_type: str,
        is_fragile: bool,
    ) -> int:
        if total_targets <= 1:
            return 0
        if is_fragile:
            return 0
        window = max(1, min(total_targets, active_cap))
        unlocked = min(window - 1, max(0, success_streak // cls._unlock_threshold(entry_type, lapse_count)))
        return max(0, unlocked)

    @staticmethod
    def _start_of_utc_day(now: datetime | None = None) -> tuple[datetime, datetime]:
        current = now or datetime.now(timezone.utc)
        day_start = current.astimezone(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        return day_start, day_start + timedelta(days=1)

    @staticmethod
    def _same_day_due_condition(day_start: datetime, day_end: datetime):
        return (
            (EntryReviewState.recheck_due_at.is_not(None))
            & (EntryReviewState.recheck_due_at >= day_start)
            & (EntryReviewState.recheck_due_at < day_end)
        ) | (
            (EntryReviewState.next_due_at.is_not(None))
            & (EntryReviewState.next_due_at >= day_start)
            & (EntryReviewState.next_due_at < day_end)
        )

    @classmethod
    def _merge_distractor_candidates(
        cls,
        *,
        exclude: str | None,
        primary: list[str],
        fallback: list[str],
        limit: int,
    ) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        excluded = (exclude or "").strip().lower()
        for source in (primary, fallback):
            for candidate in source:
                normalized = cls._normalize_prompt_text(candidate)
                if normalized is None:
                    continue
                lowered = normalized.lower()
                if lowered == excluded or lowered in seen:
                    continue
                seen.add(lowered)
                merged.append(normalized)
                if len(merged) >= limit:
                    return merged
        return merged

    @classmethod
    def _rank_entry_distractors(
        cls,
        *,
        correct_text: str,
        candidates: list[str],
        contextual: bool = False,
    ) -> list[str]:
        normalized_correct = cls._normalize_prompt_text(correct_text) or ""
        correct_tokens = len(normalized_correct.split())
        correct_length = len(normalized_correct)

        def score(candidate: str) -> tuple[int, int, int, str]:
            normalized_candidate = cls._normalize_prompt_text(candidate) or ""
            token_gap = abs(len(normalized_candidate.split()) - correct_tokens)
            length_gap = abs(len(normalized_candidate) - correct_length)
            prefix_bonus = 0 if normalized_candidate[:1].lower() != normalized_correct[:1].lower() else 1
            return (
                token_gap,
                length_gap if contextual else 0,
                -prefix_bonus if contextual else 0,
                normalized_candidate.lower(),
            )

        unique: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized_candidate = cls._normalize_prompt_text(candidate)
            if normalized_candidate is None:
                continue
            lowered = normalized_candidate.lower()
            if lowered == normalized_correct.lower() or lowered in seen:
                continue
            seen.add(lowered)
            unique.append(normalized_candidate)

        return sorted(unique, key=score)

    @staticmethod
    def _normalize_entry_type(entry_type: str) -> str:
        normalized = (entry_type or "").strip().lower()
        if normalized not in {"word", "phrase"}:
            raise ValueError(f"Unsupported entry_type={entry_type}")
        return normalized

    @staticmethod
    def _build_mcq_options(correct: str, distractors: list[str]) -> list[dict[str, Any]]:
        option_labels = ["A", "B", "C", "D"]
        labels = [correct, *distractors]
        unique_values: list[str] = []
        seen: set[str] = set()

        for label in labels:
            normalized = label.strip()
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            unique_values.append(normalized)
            if len(unique_values) >= len(option_labels):
                break

        rng = random.Random((correct or "").__hash__())
        rng.shuffle(unique_values)
        target_size = min(len(option_labels), len(unique_values))
        unique_values = unique_values[:target_size]

        return [
            {
                "option_id": label,
                "label": value,
                "is_correct": value == correct,
            }
            for label, value in zip(option_labels[:target_size], unique_values)
        ]

    @staticmethod
    def _phrase_variants(token: str) -> list[str]:
        normalized = token.strip()
        if not normalized:
            return []

        variants = {normalized}
        lowered = normalized.lower()
        variants.add(f"{lowered}s")
        variants.add(f"{lowered}ed")
        variants.add(f"{lowered}ing")

        if lowered.endswith("e") and len(lowered) > 1:
            variants.add(f"{lowered[:-1]}ing")
            variants.add(f"{lowered[:-1]}ed")
        if lowered.endswith("y") and len(lowered) > 1:
            variants.add(f"{lowered[:-1]}ies")
            variants.add(f"{lowered[:-1]}ied")

        return sorted(variants, key=len, reverse=True)

    @classmethod
    def _mask_phrase_variant(cls, sentence: str, target: str) -> str | None:
        parts = [part for part in target.split() if part]
        if len(parts) < 2:
            return None

        first_token, remainder = parts[0], parts[1:]
        first_token_pattern = "|".join(re.escape(item) for item in cls._phrase_variants(first_token))
        remainder_pattern = r"\s+".join(re.escape(part) for part in remainder)
        pattern = rf"\b(?:{first_token_pattern})\s+{remainder_pattern}\b"
        masked, count = re.subn(pattern, "___", sentence, count=1, flags=re.IGNORECASE)
        return masked if count else None

    @classmethod
    def _mask_sentence(cls, sentence: str, target: str) -> str | None:
        if not sentence or not target:
            return None

        escaped = re.escape(target)
        masked, count = re.subn(
            rf"\b{escaped}\b",
            "___",
            sentence,
            count=1,
            flags=re.IGNORECASE,
        )
        if count:
            return masked

        phrase_masked = cls._mask_phrase_variant(sentence, target)
        if phrase_masked:
            return phrase_masked

        return sentence.replace(target, "___", 1) if target in sentence else None

    @classmethod
    def _build_collocation_fragment(cls, sentence: str | None, target: str) -> str | None:
        normalized_sentence = cls._normalize_prompt_text(sentence)
        normalized_target = cls._normalize_prompt_text(target)
        if normalized_sentence is None or normalized_target is None:
            return None

        masked = cls._mask_sentence(normalized_sentence, normalized_target)
        return masked or normalized_sentence

    @staticmethod
    def _build_review_prompt(
        review_mode: str,
        prompt_type: str,
        stem: str,
        question: str,
        options: list[dict[str, Any]] | None = None,
        expected_input: str | None = None,
        input_mode: str | None = None,
        voice_placeholder_text: str | None = None,
        sentence_masked: str | None = None,
        audio_state: str = "not_available",
        audio: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_audio_state = audio_state
        if audio is not None and resolved_audio_state == "not_available":
            resolved_audio_state = "ready"
        return {
            "mode": review_mode,
            "prompt_type": prompt_type,
            "stem": stem,
            "question": question,
            "options": options,
            "expected_input": expected_input,
            "input_mode": input_mode,
            "voice_placeholder_text": voice_placeholder_text,
            "sentence_masked": sentence_masked,
            "audio_state": resolved_audio_state,
            "audio": audio,
        }

    async def _fetch_word_distractors(self, correct_word: str, limit: int = 3) -> list[str]:
        if not correct_word:
            return []

        result = await self.db.execute(
            select(Word.word)
            .where(func.lower(Word.word) != correct_word.lower())
            .order_by(Word.frequency_rank.asc().nullslast(), Word.word.asc())
            .limit(limit + 5)
        )

        candidates = [word for word in result.scalars().all() if self._normalize_prompt_text(word)]
        return candidates[:limit]

    async def _fetch_word_confusable_distractors(
        self,
        *,
        target_entry_id: uuid.UUID,
        limit: int = 3,
    ) -> list[str]:
        result = await self.db.execute(
            select(Word)
            .options(selectinload(Word.confusable_entries))
            .where(Word.id == target_entry_id)
        )
        word = result.scalar_one_or_none()
        if word is None:
            return []
        confusable_entries = getattr(word, "confusable_entries", None)
        if not isinstance(confusable_entries, list):
            return []

        candidates: list[str] = []
        seen: set[str] = set()
        for entry in confusable_entries:
            normalized = self._normalize_prompt_text(getattr(entry, "confusable_word", None))
            if normalized is None:
                continue
            lowered = normalized.lower()
            if lowered in seen:
                continue
            seen.add(lowered)
            candidates.append(normalized)
            if len(candidates) >= limit:
                break
        return candidates

    async def _fetch_definition_distractors(
        self,
        correct_meaning_id: uuid.UUID,
        limit: int = 3,
    ) -> list[str]:
        result = await self.db.execute(
            select(Meaning.definition)
            .where(Meaning.id != correct_meaning_id)
            .order_by(Meaning.word_id.asc(), Meaning.order_index.asc(), Meaning.id.asc())
            .limit(limit + 5)
        )
        candidates = [definition for definition in result.scalars().all() if self._normalize_prompt_text(definition)]
        return candidates[:limit]

    async def _fetch_same_day_definition_distractors(
        self,
        *,
        user_id: uuid.UUID,
        target_meaning_id: uuid.UUID,
        target_entry_type: str,
        limit: int,
    ) -> list[str]:
        day_start, day_end = self._start_of_utc_day()
        entry_type = self._normalize_entry_type(target_entry_type)
        cache_key = (user_id, entry_type)
        if not hasattr(self, "_same_day_definition_distractor_pool_cache"):
            self._same_day_definition_distractor_pool_cache: dict[
                tuple[uuid.UUID, str], list[tuple[uuid.UUID, str]]
            ] = {}
        cached_pool = self._same_day_definition_distractor_pool_cache.get(cache_key)

        if cached_pool is None:
            if entry_type == "phrase":
                result = await self.db.execute(
                    select(PhraseSense.id, PhraseSense.definition)
                    .join(PhraseEntry, PhraseSense.phrase_entry_id == PhraseEntry.id)
                    .join(
                        EntryReviewState,
                        and_(
                            EntryReviewState.entry_type == literal("phrase"),
                            EntryReviewState.entry_id == PhraseEntry.id,
                        ),
                    )
                    .where(EntryReviewState.user_id == user_id)
                    .where(EntryReviewState.is_suspended.is_(False))
                    .where(self._same_day_due_condition(day_start, day_end))
                    .order_by(
                        EntryReviewState.recheck_due_at.asc().nullsfirst(),
                        EntryReviewState.next_due_at.asc().nullsfirst(),
                        PhraseEntry.phrase_text.asc(),
                        PhraseSense.order_index.asc(),
                    )
                    .limit(self.SAME_DAY_DISTRACTOR_POOL_LIMIT)
                )
            else:
                result = await self.db.execute(
                    select(Meaning.id, Meaning.definition)
                    .join(Word, Meaning.word_id == Word.id)
                    .join(
                        EntryReviewState,
                        and_(
                            EntryReviewState.entry_type == literal("word"),
                            EntryReviewState.entry_id == Word.id,
                        ),
                    )
                    .where(EntryReviewState.user_id == user_id)
                    .where(EntryReviewState.is_suspended.is_(False))
                    .where(self._same_day_due_condition(day_start, day_end))
                    .order_by(
                        EntryReviewState.recheck_due_at.asc().nullsfirst(),
                        EntryReviewState.next_due_at.asc().nullsfirst(),
                        Word.frequency_rank.asc().nullslast(),
                        Meaning.order_index.asc(),
                    )
                    .limit(self.SAME_DAY_DISTRACTOR_POOL_LIMIT)
                )

            cached_pool = [
                (meaning_id, definition)
                for meaning_id, definition in result.all()
                if self._normalize_prompt_text(definition)
            ]
            self._same_day_definition_distractor_pool_cache[cache_key] = cached_pool

        return [
            definition
            for meaning_id, definition in cached_pool
            if meaning_id != target_meaning_id
        ][:limit]

    async def _fetch_adjacent_definition_distractors(
        self,
        *,
        target_meaning_id: uuid.UUID,
        target_entry_type: str,
        limit: int,
    ) -> list[str]:
        entry_type = self._normalize_entry_type(target_entry_type)

        if entry_type == "phrase":
            result = await self.db.execute(
                select(PhraseSense.definition)
                .join(PhraseEntry, PhraseSense.phrase_entry_id == PhraseEntry.id)
                .where(PhraseSense.id != target_meaning_id)
                .order_by(PhraseEntry.phrase_text.asc(), PhraseSense.order_index.asc())
                .limit(limit + 5)
            )
            return [
                definition
                for definition in result.scalars().all()
                if self._normalize_prompt_text(definition)
            ][:limit]

        target_rank_result = await self.db.execute(
            select(Word.frequency_rank)
            .join(Meaning, Meaning.word_id == Word.id)
            .where(Meaning.id == target_meaning_id)
        )
        target_rank = target_rank_result.scalar_one_or_none()
        fallback_rank = 1_000_000
        distance_expr = func.abs(
            func.coalesce(Word.frequency_rank, literal(fallback_rank))
            - literal(target_rank if target_rank is not None else fallback_rank)
        )
        result = await self.db.execute(
            select(Meaning.definition)
            .join(Word, Meaning.word_id == Word.id)
            .where(Meaning.id != target_meaning_id)
            .order_by(distance_expr.asc(), Word.frequency_rank.asc().nullslast(), Word.word.asc(), Meaning.order_index.asc())
            .limit(limit + 10)
        )
        return [
            definition
            for definition in result.scalars().all()
            if self._normalize_prompt_text(definition)
        ][:limit]

    async def _fetch_phrase_distractors(
        self,
        correct_phrase: str,
        limit: int = 3,
    ) -> list[str]:
        if not correct_phrase:
            return []

        result = await self.db.execute(
            select(PhraseEntry.phrase_text)
            .where(func.lower(PhraseEntry.phrase_text) != correct_phrase.lower())
            .order_by(PhraseEntry.phrase_text.asc(), PhraseEntry.id.asc())
            .limit(limit + 5)
        )
        candidates = [
            phrase
            for phrase in result.scalars().all()
            if self._normalize_prompt_text(phrase)
        ]
        return candidates[:limit]

    async def _fetch_same_day_entry_distractors(
        self,
        *,
        user_id: uuid.UUID,
        target_entry_id: uuid.UUID,
        target_entry_type: str,
        limit: int,
    ) -> list[str]:
        day_start, day_end = self._start_of_utc_day()
        entry_type = self._normalize_entry_type(target_entry_type)
        cache_key = (user_id, entry_type)
        if not hasattr(self, "_same_day_entry_distractor_pool_cache"):
            self._same_day_entry_distractor_pool_cache: dict[
                tuple[uuid.UUID, str], list[tuple[uuid.UUID, str]]
            ] = {}
        cached_pool = self._same_day_entry_distractor_pool_cache.get(cache_key)

        if cached_pool is None:
            if entry_type == "phrase":
                result = await self.db.execute(
                    select(PhraseEntry.id, PhraseEntry.phrase_text)
                    .join(
                        EntryReviewState,
                        and_(
                            EntryReviewState.entry_type == literal("phrase"),
                            EntryReviewState.entry_id == PhraseEntry.id,
                        ),
                    )
                    .where(EntryReviewState.user_id == user_id)
                    .where(EntryReviewState.is_suspended.is_(False))
                    .where(self._same_day_due_condition(day_start, day_end))
                    .order_by(
                        EntryReviewState.recheck_due_at.asc().nullsfirst(),
                        EntryReviewState.next_due_at.asc().nullsfirst(),
                        PhraseEntry.phrase_text.asc(),
                    )
                    .limit(self.SAME_DAY_DISTRACTOR_POOL_LIMIT)
                )
            else:
                result = await self.db.execute(
                    select(Word.id, Word.word)
                    .join(
                        EntryReviewState,
                        and_(
                            EntryReviewState.entry_type == literal("word"),
                            EntryReviewState.entry_id == Word.id,
                        ),
                    )
                    .where(EntryReviewState.user_id == user_id)
                    .where(EntryReviewState.is_suspended.is_(False))
                    .where(self._same_day_due_condition(day_start, day_end))
                    .order_by(
                        EntryReviewState.recheck_due_at.asc().nullsfirst(),
                        EntryReviewState.next_due_at.asc().nullsfirst(),
                        Word.frequency_rank.asc().nullslast(),
                    )
                    .limit(self.SAME_DAY_DISTRACTOR_POOL_LIMIT)
                )

            cached_pool = [
                (entry_id, entry_text)
                for entry_id, entry_text in result.all()
                if self._normalize_prompt_text(entry_text)
            ]
            self._same_day_entry_distractor_pool_cache[cache_key] = cached_pool

        return [
            entry_text
            for entry_id, entry_text in cached_pool
            if entry_id != target_entry_id
        ][:limit]

    async def _fetch_adjacent_entry_distractors(
        self,
        *,
        target_entry_id: uuid.UUID,
        target_entry_type: str,
        limit: int,
    ) -> list[str]:
        entry_type = self._normalize_entry_type(target_entry_type)

        if entry_type == "phrase":
            result = await self.db.execute(
                select(PhraseEntry.phrase_text)
                .where(PhraseEntry.id != target_entry_id)
                .order_by(PhraseEntry.phrase_text.asc())
                .limit(limit + 5)
            )
            return [
                phrase
                for phrase in result.scalars().all()
                if self._normalize_prompt_text(phrase)
            ][:limit]

        target_rank_result = await self.db.execute(
            select(Word.frequency_rank).where(Word.id == target_entry_id)
        )
        target_rank = target_rank_result.scalar_one_or_none()
        fallback_rank = 1_000_000
        distance_expr = func.abs(
            func.coalesce(Word.frequency_rank, literal(fallback_rank))
            - literal(target_rank if target_rank is not None else fallback_rank)
        )
        result = await self.db.execute(
            select(Word.word)
            .where(Word.id != target_entry_id)
            .order_by(distance_expr.asc(), Word.frequency_rank.asc().nullslast(), Word.word.asc())
            .limit(limit + 10)
        )
        return [
            word
            for word in result.scalars().all()
            if self._normalize_prompt_text(word)
        ][:limit]

    @staticmethod
    def _format_interval_option_name(value: str) -> str:
        if value == "never_for_now":
            return "Never (365 days)"
        return value

    async def _fetch_first_meaning_sentence(self, meaning_id: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(MeaningExample.sentence)
            .where(MeaningExample.meaning_id == meaning_id)
            .order_by(MeaningExample.order_index.asc())
            .limit(1)
        )
        return self._normalize_prompt_text(result.scalar_one_or_none())

    async def _fetch_first_meaning_sentence_map(
        self,
        meaning_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, str | None]:
        if not meaning_ids:
            return {}

        first_example_subquery = (
            select(
                MeaningExample.meaning_id.label("meaning_id"),
                func.min(MeaningExample.order_index).label("first_order_index"),
            )
            .where(MeaningExample.meaning_id.in_(meaning_ids))
            .group_by(MeaningExample.meaning_id)
            .subquery()
        )
        result = await self.db.execute(
            select(MeaningExample.meaning_id, MeaningExample.sentence)
            .join(
                first_example_subquery,
                and_(
                    MeaningExample.meaning_id == first_example_subquery.c.meaning_id,
                    MeaningExample.order_index == first_example_subquery.c.first_order_index,
                ),
            )
        )
        return {
            meaning_id: self._normalize_prompt_text(sentence)
            for meaning_id, sentence in result.all()
        }

    async def _fetch_first_sense_sentence(self, sense_id: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(PhraseSenseExample.sentence)
            .where(PhraseSenseExample.phrase_sense_id == sense_id)
            .order_by(PhraseSenseExample.order_index.asc())
            .limit(1)
        )
        return self._normalize_prompt_text(result.scalar_one_or_none())

    async def _fetch_first_sense_sentence_map(
        self,
        sense_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, str | None]:
        if not sense_ids:
            return {}

        first_example_subquery = (
            select(
                PhraseSenseExample.phrase_sense_id.label("sense_id"),
                func.min(PhraseSenseExample.order_index).label("first_order_index"),
            )
            .where(PhraseSenseExample.phrase_sense_id.in_(sense_ids))
            .group_by(PhraseSenseExample.phrase_sense_id)
            .subquery()
        )
        result = await self.db.execute(
            select(PhraseSenseExample.phrase_sense_id, PhraseSenseExample.sentence)
            .join(
                first_example_subquery,
                and_(
                    PhraseSenseExample.phrase_sense_id == first_example_subquery.c.sense_id,
                    PhraseSenseExample.order_index == first_example_subquery.c.first_order_index,
                ),
            )
        )
        return {
            sense_id: self._normalize_prompt_text(sentence)
            for sense_id, sentence in result.all()
        }

    async def _fetch_history_count_by_word_id(
        self,
        *,
        user_id: uuid.UUID,
        meanings_by_word_id: dict[uuid.UUID, list[Meaning]],
    ) -> dict[uuid.UUID, int]:
        meaning_to_word_id: dict[uuid.UUID, uuid.UUID] = {}
        for word_id, meanings in meanings_by_word_id.items():
            for meaning in meanings:
                meaning_to_word_id[meaning.id] = word_id

        if not meaning_to_word_id:
            return {}

        result = await self.db.execute(
            select(EntryReviewEvent.target_id, func.count(EntryReviewEvent.id))
            .where(EntryReviewEvent.user_id == user_id)
            .where(EntryReviewEvent.target_id.in_(list(meaning_to_word_id.keys())))
            .where(EntryReviewEvent.outcome.in_(["correct_tested", "remember"]))
            .group_by(EntryReviewEvent.target_id)
        )
        counts_by_word_id: dict[uuid.UUID, int] = {}
        for meaning_id, count in result.all():
            word_id = meaning_to_word_id.get(meaning_id)
            if word_id is None:
                continue
            counts_by_word_id[word_id] = counts_by_word_id.get(word_id, 0) + int(count or 0)
        return counts_by_word_id

    async def _load_prompt_audio_assets(
        self,
        *,
        source_entry_type: str,
        source_entry_id: uuid.UUID,
        target_id: uuid.UUID | None = None,
        example_id: uuid.UUID | None = None,
    ) -> list[LexiconVoiceAsset]:
        entry_type = self._normalize_entry_type(source_entry_type)
        if entry_type == "phrase":
            assets = await load_phrase_voice_assets(
                self.db,
                phrase_entry_id=source_entry_id,
                phrase_sense_ids=[target_id] if target_id is not None else [],
                phrase_example_ids=[example_id] if example_id is not None else [],
            )
        else:
            assets = await load_word_voice_assets(
                self.db,
                word_id=source_entry_id,
                meaning_ids=[target_id] if target_id is not None else [],
                example_ids=[example_id] if example_id is not None else [],
            )
        return self._select_prompt_audio_assets(
            assets=assets,
            target_entry_type=entry_type,
            target_id=target_id,
            example_id=example_id,
        )

    @staticmethod
    def _select_prompt_audio_assets(
        *,
        assets: list[LexiconVoiceAsset],
        target_entry_type: str,
        target_id: uuid.UUID | None,
        example_id: uuid.UUID | None,
    ) -> list[LexiconVoiceAsset]:
        normalized_entry_type = ReviewService._normalize_entry_type(target_entry_type)

        def sort_key(asset: LexiconVoiceAsset) -> tuple[int, int, str, str]:
            locale = getattr(asset, "locale", "") or ""
            profile_key = getattr(asset, "profile_key", "") or ""
            content_scope = (getattr(asset, "content_scope", "") or "").strip().lower()
            scope_rank = 0 if content_scope == "word" else 1
            if normalized_entry_type == "phrase":
                if example_id is not None and getattr(asset, "phrase_sense_example_id", None) == example_id:
                    return (0, scope_rank, locale, profile_key)
                if target_id is not None and getattr(asset, "phrase_sense_id", None) == target_id:
                    return (1, scope_rank, locale, profile_key)
                if getattr(asset, "phrase_entry_id", None) is not None:
                    return (2, scope_rank, locale, profile_key)
            else:
                if example_id is not None and getattr(asset, "meaning_example_id", None) == example_id:
                    return (0, scope_rank, locale, profile_key)
                if target_id is not None and getattr(asset, "meaning_id", None) == target_id:
                    return (1, scope_rank, locale, profile_key)
                if getattr(asset, "word_id", None) is not None:
                    return (2, scope_rank, locale, profile_key)
            return (3, scope_rank, locale, profile_key)

        return sorted(list(assets), key=sort_key)

    async def _load_prompt_audio_payload(
        self,
        *,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        preferred_accent = await self._get_user_accent_preference(user_id)
        normalized_entry_type = self._normalize_entry_type(entry_type)
        if normalized_entry_type == "phrase":
            assets = await load_phrase_voice_assets(
                self.db,
                phrase_entry_id=entry_id,
                phrase_sense_ids=[],
                phrase_example_ids=[],
            )
            entry_assets = [
                asset
                for asset in assets
                if asset.content_scope == "word" and asset.phrase_entry_id == entry_id
            ]
            return await self._build_prompt_audio_payload(entry_assets, preferred_accent=preferred_accent)

        assets = await load_word_voice_assets(
            self.db,
            word_id=entry_id,
            meaning_ids=[],
            example_ids=[],
        )
        entry_assets = [
            asset
            for asset in assets
            if asset.content_scope == "word" and asset.word_id == entry_id
        ]
        return await self._build_prompt_audio_payload(entry_assets, preferred_accent=preferred_accent)

    async def _build_word_detail_payload(
        self,
        *,
        user_id: uuid.UUID,
        word: Word,
        meanings: list[Meaning],
        example_by_meaning_id: dict[uuid.UUID, str | None] | None = None,
        remembered_count: int | None = None,
        accent: str | None = None,
    ) -> dict[str, Any]:
        primary = meanings[0] if meanings else None
        resolved_accent = accent or await self._get_user_accent_preference(user_id)
        meaning_items: list[dict[str, Any]] = []
        for meaning in meanings[:5]:
            meaning_items.append(
                {
                    "id": str(meaning.id),
                    "definition": self._normalize_prompt_text(meaning.definition)
                    or "No definition available.",
                    "example": (
                        example_by_meaning_id.get(meaning.id)
                        if example_by_meaning_id is not None
                        else await self._fetch_first_meaning_sentence(meaning.id)
                    ),
                    "part_of_speech": self._normalize_prompt_text(meaning.part_of_speech),
                }
            )

        history_count = int(remembered_count or 0)
        if remembered_count is None:
            history_result = await self.db.execute(
                select(func.count(EntryReviewEvent.id))
                .where(EntryReviewEvent.user_id == user_id)
                .where(EntryReviewEvent.target_id.in_([meaning.id for meaning in meanings]))
                .where(EntryReviewEvent.outcome.in_(["correct_tested", "remember"]))
            )
            history_count = int(history_result.scalar_one() or 0)

        return {
            "entry_type": "word",
            "entry_id": str(word.id),
            "display_text": self._normalize_prompt_text(word.word) or "Unavailable",
            "pronunciation": select_pronunciation(word, resolved_accent),
            "pronunciations": extract_pronunciations(word),
            "part_of_speech": primary.part_of_speech if primary is not None else None,
            "primary_definition": primary.definition if primary is not None else None,
            "primary_example": meaning_items[0]["example"] if meaning_items else None,
            "meaning_count": len(meanings),
            "remembered_count": history_count,
            "pro_tip": primary.usage_note if primary is not None else None,
            "compare_with": [],
            "meanings": meaning_items,
            "audio_state": "not_available",
            "coverage_summary": self._coverage_summary(len(meanings), history_count),
        }

    async def _build_phrase_detail_payload(
        self,
        *,
        user_id: uuid.UUID,
        phrase: PhraseEntry,
        senses: list[PhraseSense],
        example_by_sense_id: dict[uuid.UUID, str | None] | None = None,
    ) -> dict[str, Any]:
        primary = senses[0] if senses else None
        meaning_items: list[dict[str, Any]] = []
        for sense in senses[:5]:
            meaning_items.append(
                {
                    "id": str(sense.id),
                    "definition": self._normalize_prompt_text(sense.definition)
                    or "No definition available.",
                    "example": (
                        example_by_sense_id.get(sense.id)
                        if example_by_sense_id is not None
                        else await self._fetch_first_sense_sentence(sense.id)
                    ),
                    "part_of_speech": self._normalize_prompt_text(sense.part_of_speech),
                }
            )

        return {
            "entry_type": "phrase",
            "entry_id": str(phrase.id),
            "display_text": self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
            "pronunciation": None,
            "pronunciations": {},
            "part_of_speech": primary.part_of_speech if primary is not None else None,
            "primary_definition": primary.definition if primary is not None else None,
            "primary_example": meaning_items[0]["example"] if meaning_items else None,
            "meaning_count": len(senses),
            "remembered_count": 0,
            "pro_tip": primary.usage_note if primary is not None else None,
            "compare_with": [],
            "meanings": meaning_items,
            "audio_state": "not_available",
            "coverage_summary": self._coverage_summary(len(senses), 0),
        }

    async def _get_entry_review_state(
        self,
        *,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> EntryReviewState | None:
        result = await self.db.execute(
            select(EntryReviewState).where(
                EntryReviewState.user_id == user_id,
                EntryReviewState.entry_type == entry_type,
                EntryReviewState.entry_id == entry_id,
                EntryReviewState.is_suspended.is_(False),
            )
        )
        state = result.scalar_one_or_none()
        if state is not None:
            self._normalize_active_review_state_schedule(state)
        return state

    async def _get_target_review_state(
        self,
        *,
        user_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
    ) -> EntryReviewState | None:
        result = await self.db.execute(
            select(EntryReviewState).where(
                EntryReviewState.user_id == user_id,
                EntryReviewState.target_type == target_type,
                EntryReviewState.target_id == target_id,
            )
        )
        state = result.scalar_one_or_none()
        if state is not None:
            self._normalize_active_review_state_schedule(state)
        return state

    @classmethod
    def _normalize_active_review_state_schedule(cls, state: EntryReviewState) -> None:
        resolved_bucket = cls._resolve_srs_bucket(state=state)
        if resolved_bucket == "known":
            state.srs_bucket = "known"
            state.interval_days = None
            state.next_due_at = None
            state.cadence_step = cadence_step_for_bucket("known")
            state.stability = max(0.15, float(state.stability or 180))
            return

        resolved_interval_days = bucket_to_interval_days(resolved_bucket)
        state.srs_bucket = resolved_bucket
        state.interval_days = resolved_interval_days
        state.cadence_step = cadence_step_for_bucket(resolved_bucket)
        state.stability = max(0.15, float(resolved_interval_days or state.stability or 1))

    async def _ensure_entry_review_state(
        self,
        *,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> EntryReviewState:
        existing = await self._get_entry_review_state(
            user_id=user_id,
            entry_type=entry_type,
            entry_id=entry_id,
        )
        if existing is not None:
            return existing
        state = EntryReviewState(
            user_id=user_id,
            entry_type=entry_type,
            entry_id=entry_id,
            stability=1.0,
            difficulty=0.5,
            next_due_at=due_at_for_bucket("1d"),
            srs_bucket="1d",
            cadence_step=cadence_step_for_bucket("1d"),
            success_streak=0,
            lapse_count=0,
            exposure_count=0,
            times_remembered=0,
            is_fragile=False,
            is_suspended=False,
        )
        state.interval_days = 1
        self.db.add(state)
        await self.db.flush()
        return state

    async def _ensure_learning_entry_has_review_state(
        self,
        *,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> None:
        existing_result = await self.db.execute(
            select(EntryReviewState.id)
            .where(
                EntryReviewState.user_id == user_id,
                EntryReviewState.entry_type == entry_type,
                EntryReviewState.entry_id == entry_id,
                EntryReviewState.is_suspended.is_(False),
            )
            .limit(1)
        )
        if existing_result.scalar_one_or_none() is not None:
            return
        await self._ensure_entry_review_state(
            user_id=user_id,
            entry_type=entry_type,
            entry_id=entry_id,
        )

    async def _ensure_target_review_state(
        self,
        *,
        user_id: uuid.UUID,
        target_type: str,
        target_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> EntryReviewState:
        existing = await self._get_target_review_state(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
        )
        if existing is not None:
            return existing

        state = EntryReviewState(
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            entry_type=entry_type,
            entry_id=entry_id,
            stability=1.0,
            difficulty=0.5,
            next_due_at=due_at_for_bucket("1d"),
            srs_bucket="1d",
            cadence_step=cadence_step_for_bucket("1d"),
            success_streak=0,
            lapse_count=0,
            exposure_count=0,
            times_remembered=0,
            is_fragile=False,
            is_suspended=False,
        )
        state.interval_days = 1
        try:
            async with self.db.begin_nested():
                self.db.add(state)
                await self.db.flush()
            return state
        except IntegrityError:
            existing = await self._get_target_review_state(
                user_id=user_id,
                target_type=target_type,
                target_id=target_id,
            )
            if existing is not None:
                return existing
            raise

    @staticmethod
    def _apply_sibling_bury_rule(states: list[EntryReviewState]) -> list[EntryReviewState]:
        kept: list[EntryReviewState] = []
        seen_parents: set[tuple[str, uuid.UUID]] = set()
        for state in states:
            parent_key = (state.entry_type, state.entry_id)
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            kept.append(state)
        return kept

    async def _record_entry_review_event(
        self,
        *,
        user_id: uuid.UUID,
        state: EntryReviewState,
        target_type: str | None,
        target_id: uuid.UUID | None,
        prompt_type: str,
        outcome: str,
        selected_option_id: str | None,
        typed_answer: str | None,
        audio_replay_count: int,
        scheduled_interval_days: int | None,
        scheduled_by: str | None,
        time_spent_ms: int,
        prompt: dict[str, Any] | None,
    ) -> None:
        prompt_family = self.PROMPT_FAMILY_BY_TYPE.get(prompt_type, "other")
        response_input_mode = self._derive_response_input_mode(
            prompt=prompt,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
        )
        event = EntryReviewEvent(
            user_id=user_id,
            review_state_id=state.id,
            target_type=target_type,
            target_id=target_id,
            entry_type=state.entry_type,
            entry_id=state.entry_id,
            prompt_type=prompt_type,
            prompt_family=prompt_family,
            outcome=outcome,
            response_input_mode=response_input_mode,
            response_value=self._normalize_prompt_text(typed_answer) or selected_option_id,
            used_audio_placeholder=((prompt or {}).get("audio_state") == "placeholder"),
            audio_replay_count=max(0, int(audio_replay_count or 0)),
            selected_option_id=selected_option_id,
            scheduled_interval_days=scheduled_interval_days,
            scheduled_by=scheduled_by,
            time_spent_ms=time_spent_ms,
        )
        self.db.add(event)

    @staticmethod
    def _derive_response_input_mode(
        *,
        prompt: dict[str, Any] | None,
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> str:
        if typed_answer and typed_answer.strip():
            return "typed"
        if selected_option_id:
            return "choice"
        if (prompt or {}).get("input_mode") == "speech_placeholder":
            return "speech_placeholder"
        return "confidence"

    async def _build_detail_payload_for_word_id(
        self,
        *,
        user_id: uuid.UUID,
        word_id: uuid.UUID,
    ) -> dict[str, Any]:
        word_result = await self.db.execute(select(Word).where(Word.id == word_id))
        word = word_result.scalar_one_or_none()
        if word is None or not hasattr(word, "word"):
            return {
                "entry_type": "word",
                "entry_id": str(word_id),
                "display_text": "Unavailable",
                "meaning_count": 0,
                "remembered_count": 0,
                "compare_with": [],
                "meanings": [],
                "audio_state": "not_available",
            }

        meanings_result = await self.db.execute(
            select(Meaning).where(Meaning.word_id == word_id).order_by(Meaning.order_index.asc())
        )
        meanings = meanings_result.scalars().all()
        return await self._build_word_detail_payload(user_id=user_id, word=word, meanings=meanings)

    def _select_review_mode(
        self,
        item: Any,
        word: str,
        index: int = 0,
        sentence: str | None = None,
        allow_confidence: bool = True,
    ) -> str:
        if not word:
            return self.REVIEW_MODE_CONFIDENCE
        if not allow_confidence:
            return self.REVIEW_MODE_MCQ
        if sentence is None:
            return self.REVIEW_MODE_MCQ
        seed = int.from_bytes(item.id.bytes[:8], "big", signed=False) if getattr(item, "id", None) else index
        return self.REVIEW_MODE_MCQ if (seed % 4) != 0 else self.REVIEW_MODE_CONFIDENCE

    @staticmethod
    def _normalize_review_mode(review_mode: str | None) -> str:
        normalized = (review_mode or ReviewService.REVIEW_MODE_CONFIDENCE).strip().lower()
        if normalized in ReviewService.REVIEW_MODE_OPTIONS:
            return normalized
        return ReviewService.REVIEW_MODE_CONFIDENCE

    @staticmethod
    def _normalize_outcome(outcome: str | None) -> str | None:
        normalized = (outcome or "").strip().lower()
        if normalized in {"correct_tested", "remember", "lookup", "wrong"}:
            return normalized
        return None

    @classmethod
    def _is_correct_mcq_answer(
        cls,
        prompt: dict[str, Any] | None,
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> bool:
        if prompt is None:
            return False

        selected = selected_option_id
        if selected is None and typed_answer:
            comparison = cls._compare_typed_answer(
                expected_input=prompt.get("expected_input"),
                typed_answer=typed_answer,
                entry_type=prompt.get("source_entry_type") or "word",
            )
            return bool(comparison["is_correct"])

        if selected is None:
            return False

        for option in prompt.get("options") or []:
            if str(option.get("option_id")) == str(selected):
                return bool(option.get("is_correct"))

        return False

    @staticmethod
    def _resolve_interval_days_or_zero(value: int | None) -> int:
        return int(value or 0)

    @classmethod
    def _resolve_srs_bucket(
        cls,
        *,
        state: EntryReviewState | None = None,
        interval_days: int | None = None,
    ) -> str:
        if state is not None:
            normalized_bucket = (getattr(state, "srs_bucket", None) or "").strip().lower()
            if normalized_bucket in REVIEW_SRS_V1_BUCKETS:
                return normalized_bucket
            derived_interval_days = getattr(state, "interval_days", None)
            if derived_interval_days is not None:
                return bucket_for_interval_days(int(derived_interval_days))
            if getattr(state, "stability", None) is not None:
                return bucket_for_interval_days(int(round(float(state.stability or 0))))
        if interval_days is not None:
            return bucket_for_interval_days(interval_days)
        return "1d"

    def _select_prompt_type(
        self,
        prompt_candidates: list[str],
        index: int = 0,
        previous_prompt_type: str | None = None,
    ) -> str:
        del index
        if not prompt_candidates:
            return self.PROMPT_TYPE_DEFINITION_TO_ENTRY
        if previous_prompt_type:
            for candidate in prompt_candidates:
                if candidate != previous_prompt_type:
                    return candidate
        return prompt_candidates[0]

    @classmethod
    def _extract_prompt_type_override(cls, state: EntryReviewState | None) -> str | None:
        marker = getattr(state, "last_submission_prompt_id", None)
        if not isinstance(marker, str):
            return None
        prefix = "manual_prompt_type:"
        if not marker.startswith(prefix):
            return None
        prompt_type = marker[len(prefix):].strip().lower()
        if prompt_type in cls.PROMPT_TYPE_OPTIONS:
            return prompt_type
        return None

    @classmethod
    def _review_mode_for_prompt_type(cls, prompt_type: str | None) -> str | None:
        if prompt_type is None:
            return None
        if prompt_type == cls.PROMPT_TYPE_CONFIDENCE_CHECK:
            return cls.REVIEW_MODE_CONFIDENCE
        return cls.REVIEW_MODE_MCQ

    async def _resolve_prompt_text(
        self,
        prompt_type: str,
        word: str,
        definition: str,
        sentence: str | None = None,
    ) -> tuple[str, str]:
        if prompt_type == self.PROMPT_TYPE_CONFIDENCE_CHECK:
            stem = "Read the sentence and decide whether you still remember this word or phrase."
            return stem, self._prompt_value_for_options(sentence)
        if prompt_type == self.PROMPT_TYPE_DEFINITION_TO_ENTRY:
            stem = "Choose the word or phrase that matches this definition."
            return stem, self._prompt_value_for_options(definition)
        if prompt_type == self.PROMPT_TYPE_SENTENCE_GAP and sentence:
            stem = "Choose the missing word or phrase in this sentence."
            return stem, self._mask_sentence(sentence, word) or self._prompt_value_for_options(sentence)
        if prompt_type == self.PROMPT_TYPE_COLLOCATION_CHECK and sentence:
            stem = "Choose the word or phrase that completes this common expression."
            return stem, self._build_collocation_fragment(sentence, word) or self._prompt_value_for_options(sentence)
        if prompt_type == self.PROMPT_TYPE_SITUATION_MATCHING and sentence:
            stem = "Which word or phrase best fits this situation?"
            return stem, self._mask_sentence(sentence, word) or self._prompt_value_for_options(sentence)
        if prompt_type == self.PROMPT_TYPE_TYPED_RECALL:
            stem = "Type the word or phrase that matches this definition."
            return stem, self._prompt_value_for_options(definition)
        if prompt_type == self.PROMPT_TYPE_SPEAK_RECALL:
            stem = "Say the word or phrase that matches this definition."
            return stem, self._prompt_value_for_options(definition)
        if prompt_type == self.PROMPT_TYPE_ENTRY_TO_DEFINITION:
            return "Choose the best definition for this word or phrase.", self._prompt_value_for_options(word)
        return "Listen, then choose the best matching definition.", "Which definition matches the audio?"

    async def _build_mandated_prompt(
        self,
        review_mode: str,
        prompt_type: str,
        word: str,
        definition: str,
        target_is_word: bool,
        distractors: list[str] | None = None,
        sentence: str | None = None,
        alternative_definitions: list[str] | None = None,
        audio: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        stem, question = await self._resolve_prompt_text(
            prompt_type=prompt_type,
            word=word,
            definition=definition,
            sentence=sentence,
        )

        expected_input = None
        sentence_masked = None
        options = None

        if prompt_type == self.PROMPT_TYPE_CONFIDENCE_CHECK:
            return self._build_review_prompt(
                review_mode=review_mode,
                prompt_type=prompt_type,
                stem=stem,
                question=question,
                options=[
                    {
                        "option_id": "A",
                        "label": "I remember it",
                        "is_correct": True,
                    },
                    {
                        "option_id": "B",
                        "label": "Not sure",
                        "is_correct": False,
                    },
                ],
                expected_input=None,
                input_mode="choice",
                sentence_masked=sentence_masked,
                audio_state="ready" if audio else "not_available",
                audio=audio,
            )

        if prompt_type == self.PROMPT_TYPE_TYPED_RECALL:
            expected_input = self._prompt_value_for_options(word)
            return self._build_review_prompt(
                review_mode=review_mode,
                prompt_type=prompt_type,
                stem=stem,
                question=question,
                options=None,
                expected_input=expected_input,
                input_mode="typed",
                sentence_masked=None,
            )
        if prompt_type == self.PROMPT_TYPE_SPEAK_RECALL:
            expected_input = self._prompt_value_for_options(word)
            return self._build_review_prompt(
                review_mode=review_mode,
                prompt_type=prompt_type,
                stem=stem,
                question=question,
                options=None,
                expected_input=expected_input,
                input_mode="speech_placeholder",
                voice_placeholder_text="Voice answer coming soon. Type the answer for now.",
                sentence_masked=None,
                audio_state="ready" if audio else "placeholder",
                audio=audio,
            )

        if review_mode != self.REVIEW_MODE_MCQ:
            return self._build_review_prompt(
                review_mode=review_mode,
                prompt_type=prompt_type,
                stem=stem,
                question=question,
                options=None,
                expected_input=expected_input,
                input_mode="confidence",
                sentence_masked=sentence_masked,
            )

        if prompt_type == self.PROMPT_TYPE_DEFINITION_TO_ENTRY:
            correct = self._prompt_value_for_options(word)
        elif prompt_type == self.PROMPT_TYPE_MEANING_DISCRIMINATION:
            correct = self._prompt_value_for_options(definition)
            question = self._prompt_value_for_options(word)
        elif target_is_word:
            correct = self._prompt_value_for_options(word)
            if prompt_type in {self.PROMPT_TYPE_SENTENCE_GAP, self.PROMPT_TYPE_COLLOCATION_CHECK} and sentence:
                sentence_masked = self._mask_sentence(sentence, word)
                expected_input = self._prompt_value_for_options(word)
        else:
            correct = self._prompt_value_for_options(definition)

        distractors_source = alternative_definitions if prompt_type == self.PROMPT_TYPE_MEANING_DISCRIMINATION else distractors
        distractors = [self._prompt_value_for_options(item) for item in (distractors_source or [])]
        options = self._build_mcq_options(correct=correct, distractors=distractors)
        return self._build_review_prompt(
            review_mode=review_mode,
            prompt_type=prompt_type,
            stem=stem,
            question=question,
            options=options,
            expected_input=expected_input,
            input_mode="choice",
            sentence_masked=sentence_masked,
            audio_state="ready" if prompt_type in {self.PROMPT_TYPE_AUDIO_TO_DEFINITION, self.PROMPT_TYPE_CONFIDENCE_CHECK} and audio else "not_available",
            audio=audio,
        )

    async def _build_card_prompt(
        self,
        *,
        review_mode: str,
        source_text: str,
        definition: str,
        sentence: str | None,
        is_phrase_entry: bool,
        distractor_seed: str,
        meaning_id: uuid.UUID,
        index: int = 0,
        alternative_definitions: list[str] | None = None,
        user_id: uuid.UUID | None = None,
        source_entry_id: uuid.UUID | None = None,
        source_entry_type: str | None = None,
        queue_item_id: uuid.UUID | None = None,
        previous_prompt_type: str | None = None,
        active_target_count: int = 1,
        forced_prompt_type: str | None = None,
        srs_bucket: str | None = None,
        cadence_step: int | None = None,
    ) -> dict[str, Any]:
        return await build_card_prompt_impl(
            self,
            review_mode=review_mode,
            source_text=source_text,
            definition=definition,
            sentence=sentence,
            is_phrase_entry=is_phrase_entry,
            distractor_seed=distractor_seed,
            meaning_id=meaning_id,
            index=index,
            alternative_definitions=alternative_definitions,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_entry_type=source_entry_type,
            queue_item_id=queue_item_id,
            previous_prompt_type=previous_prompt_type,
            active_target_count=active_target_count,
            forced_prompt_type=forced_prompt_type,
            srs_bucket=srs_bucket,
            cadence_step=cadence_step,
        )

    async def _resolve_prompt_preferences(self, user_id: uuid.UUID | None) -> dict[str, Any]:
        return await resolve_prompt_preferences_impl(self, user_id)

    def _build_available_prompt_types(
        self,
        *,
        review_mode: str,
        sentence: str | None,
        alternative_definitions: list[str] | None,
        review_depth_preset: str,
        allow_typed_recall: bool,
        allow_audio_spelling: bool,
        allow_confidence: bool,
        active_target_count: int,
        srs_bucket: str | None = None,
        cadence_step: int | None = None,
    ) -> list[str]:
        return build_available_prompt_types_impl(
            self,
            review_mode=review_mode,
            sentence=sentence,
            alternative_definitions=alternative_definitions,
            review_depth_preset=review_depth_preset,
            allow_typed_recall=allow_typed_recall,
            allow_audio_spelling=allow_audio_spelling,
            allow_confidence=allow_confidence,
            active_target_count=active_target_count,
            srs_bucket=srs_bucket,
            cadence_step=cadence_step,
        )

    async def _load_prompt_distractors(
        self,
        *,
        prompt_type: str,
        user_id: uuid.UUID | None,
        source_entry_id: uuid.UUID | None,
        source_text: str,
        definition: str,
        meaning_id: uuid.UUID,
        normalized_entry_type: str,
        is_phrase_entry: bool,
    ) -> list[str]:
        return await load_prompt_distractors_impl(
            self,
            prompt_type=prompt_type,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_text=source_text,
            definition=definition,
            meaning_id=meaning_id,
            normalized_entry_type=normalized_entry_type,
            is_phrase_entry=is_phrase_entry,
        )

    async def _load_entry_target_distractors(
        self,
        *,
        prompt_type: str,
        user_id: uuid.UUID | None,
        source_entry_id: uuid.UUID | None,
        source_text: str,
        normalized_entry_type: str,
        is_phrase_entry: bool,
    ) -> list[str]:
        return await load_entry_target_distractors_impl(
            self,
            prompt_type=prompt_type,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_text=source_text,
            normalized_entry_type=normalized_entry_type,
            is_phrase_entry=is_phrase_entry,
        )

    async def _load_definition_target_distractors(
        self,
        *,
        user_id: uuid.UUID | None,
        source_entry_id: uuid.UUID | None,
        definition: str,
        meaning_id: uuid.UUID,
        normalized_entry_type: str,
    ) -> list[str]:
        return await load_definition_target_distractors_impl(
            self,
            user_id=user_id,
            source_entry_id=source_entry_id,
            definition=definition,
            meaning_id=meaning_id,
            normalized_entry_type=normalized_entry_type,
        )

    async def _load_prompt_audio_for_type(
        self,
        *,
        prompt_type: str,
        user_id: uuid.UUID | None,
        source_entry_id: uuid.UUID | None,
        source_entry_type: str,
        meaning_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        return await load_prompt_audio_for_type_impl(
            self,
            prompt_type=prompt_type,
            user_id=user_id,
            source_entry_id=source_entry_id,
            source_entry_type=source_entry_type,
            meaning_id=meaning_id,
        )

    @staticmethod
    def _derive_quality(
        review_mode: str,
        quality: int,
        prompt: dict[str, Any] | None,
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> int:
        clamped_quality = max(0, min(5, quality))
        if review_mode != ReviewService.REVIEW_MODE_MCQ:
            return clamped_quality

        return 4 if ReviewService._is_correct_mcq_answer(
            prompt=prompt,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
        ) else 1

    @classmethod
    def _derive_review_grade(
        cls,
        *,
        outcome: str,
        prompt: dict[str, Any] | None,
        quality: int,
        time_spent_ms: int,
    ) -> str:
        del time_spent_ms
        if outcome in {"lookup", "wrong"} or quality < 3:
            return "fail"
        prompt_type = (prompt or {}).get("prompt_type") or cls.PROMPT_TYPE_DEFINITION_TO_ENTRY
        if outcome == "remember":
            return "hard_pass"
        if prompt_type in {cls.PROMPT_TYPE_TYPED_RECALL, cls.PROMPT_TYPE_SPEAK_RECALL}:
            return "good_pass"
        if prompt_type in {
            cls.PROMPT_TYPE_SENTENCE_GAP,
            cls.PROMPT_TYPE_MEANING_DISCRIMINATION,
            cls.PROMPT_TYPE_COLLOCATION_CHECK,
            cls.PROMPT_TYPE_SITUATION_MATCHING,
        }:
            return "good_pass"
        return "good_pass"

    @classmethod
    def _derive_outcome(
        cls,
        *,
        review_mode: str,
        explicit_outcome: str | None,
        quality: int,
        prompt: dict[str, Any] | None,
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> str:
        normalized_outcome = cls._normalize_outcome(explicit_outcome)
        if normalized_outcome is not None:
            return normalized_outcome
        if review_mode != cls.REVIEW_MODE_MCQ:
            return "remember" if quality >= 3 else "lookup"
        return (
            "correct_tested"
            if cls._is_correct_mcq_answer(prompt, selected_option_id, typed_answer)
            else "wrong"
        )

    @classmethod
    def _default_schedule_option_value(cls, interval_days: int) -> str:
        return bucket_for_interval_days(interval_days)

    @classmethod
    def _schedule_option_labels(cls) -> dict[str, str]:
        return {bucket: bucket_to_label(bucket) for bucket in REVIEW_SRS_V1_BUCKETS}

    @classmethod
    def _build_schedule_options_for_value(cls, current_value: str) -> list[dict[str, Any]]:
        labels = cls._schedule_option_labels()
        order = list(REVIEW_SRS_V1_BUCKETS)
        return [
            {"value": value, "label": labels[value], "is_default": value == current_value}
            for value in order
        ]

    @classmethod
    def _build_schedule_options(cls, interval_days: int) -> list[dict[str, Any]]:
        return cls._build_schedule_options_for_value(cls._default_schedule_option_value(interval_days))

    @staticmethod
    def _interval_days_for_schedule_value(schedule_value: str) -> int | None:
        resolved_days = schedule_bucket_days(schedule_value)
        return None if resolved_days is None else int(resolved_days)

    @classmethod
    def _resolve_official_schedule_value(
        cls,
        *,
        resolved_bucket: str,
        resolved_outcome: str | None,
        schedule_override: str | None,
    ) -> str:
        if (
            schedule_override
            and schedule_override in cls.SCHEDULE_OVERRIDE_VALUES
        ):
            return schedule_override
        if resolved_outcome in {"lookup", "wrong"}:
            return "1d"
        return resolved_bucket

    async def _resolve_official_review_schedule(
        self,
        *,
        user_id: uuid.UUID,
        reviewed_at: datetime,
        resolved_bucket: str,
        resolved_outcome: str | None,
        schedule_override: str | None,
    ) -> tuple[int | None, Any, datetime | None, str]:
        prefs = await self._get_user_review_preferences(user_id)
        user_timezone = getattr(prefs, "timezone", None) or "UTC"
        schedule_value = self._resolve_official_schedule_value(
            resolved_bucket=resolved_bucket,
            resolved_outcome=resolved_outcome,
            schedule_override=schedule_override,
        )
        return (
            interval_days_for_bucket(resolved_bucket),
            due_review_date_for_bucket(
                reviewed_at_utc=reviewed_at,
                user_timezone=user_timezone,
                bucket=schedule_value,
            ),
            min_due_at_for_bucket(
                reviewed_at_utc=reviewed_at,
                user_timezone=user_timezone,
                bucket=schedule_value,
            ),
            resolved_bucket,
        )

    @classmethod
    def _schedule_anchor_reviewed_at(
        cls,
        *,
        state: EntryReviewState,
        fallback_now: datetime | None = None,
    ) -> datetime:
        persisted_reviewed_at = cls._normalize_bucket_datetime(
            getattr(state, "last_reviewed_at", None)
        )
        if persisted_reviewed_at is not None:
            return persisted_reviewed_at
        return cls._normalize_bucket_datetime(fallback_now) or datetime.now(timezone.utc)

    @classmethod
    def _resolve_schedule_value_from_due_at(
        cls,
        *,
        due_at: datetime | None,
        now: datetime | None = None,
    ) -> str:
        resolved_due_at = cls._normalize_bucket_datetime(due_at)
        if resolved_due_at is None:
            return "1d"

        resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        delta_days = max((resolved_due_at - resolved_now).days, 1)
        return bucket_for_interval_days(delta_days)

    @classmethod
    def _resolve_schedule_value_from_review_day_delta(cls, day_delta: int) -> str:
        return min(
            [
                item
                for item in cls.SCHEDULE_OVERRIDE_DAYS.items()
                if item[0] != "known"
            ],
            key=lambda item: (abs(item[1] - day_delta), item[1]),
        )[0]

    @classmethod
    def _build_current_schedule_payload(
        cls,
        state: EntryReviewState,
        *,
        now: datetime | None = None,
        user_timezone: str | None = None,
    ) -> dict[str, Any]:
        due_at = cls._effective_due_at(state)
        current_value = cls._resolve_schedule_value_for_state(
            state,
            now=now,
            user_timezone=user_timezone,
        )
        schedule_options = cls._build_schedule_options_for_value(current_value)
        current_label = cls._schedule_option_labels().get(
            current_value,
            "Later today" if current_value == "10m" else "Tomorrow",
        )
        return {
            "queue_item_id": str(state.id),
            "next_review_at": due_at.isoformat() if due_at is not None else None,
            "current_schedule_value": current_value,
            "current_schedule_label": current_label,
            "current_schedule_source": "scheduled_timestamp",
            "schedule_options": schedule_options,
        }

    @staticmethod
    def _normalize_bucket_datetime(value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    @classmethod
    def _uses_official_review_day_schedule(
        cls,
        state: EntryReviewState,
        *,
        user_timezone: str | None = None,
    ) -> bool:
        return (
            state.recheck_due_at is None
            and getattr(state, "due_review_date", None) is not None
            and getattr(state, "min_due_at_utc", None) is not None
            and bool(user_timezone)
        )

    @staticmethod
    def _state_has_official_review_day_fields(state: EntryReviewState) -> bool:
        return (
            state.recheck_due_at is None
            and getattr(state, "due_review_date", None) is not None
            and getattr(state, "min_due_at_utc", None) is not None
        )

    @classmethod
    def _official_due_at(cls, state: EntryReviewState) -> datetime | None:
        if not cls._state_has_official_review_day_fields(state):
            return None
        return cls._normalize_bucket_datetime(getattr(state, "min_due_at_utc", None))

    @classmethod
    def _effective_due_at(cls, state: EntryReviewState) -> datetime | None:
        return (
            cls._normalize_bucket_datetime(getattr(state, "recheck_due_at", None))
            or cls._official_due_at(state)
            or cls._normalize_bucket_datetime(getattr(state, "next_due_at", None))
        )

    @classmethod
    def _has_state_become_due_before(
        cls,
        state: EntryReviewState,
        *,
        now: datetime,
    ) -> bool:
        official_due_at = cls._official_due_at(state)
        resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        return official_due_at is not None and official_due_at <= resolved_now

    @classmethod
    def _is_state_officially_due(
        cls,
        state: EntryReviewState,
        *,
        now: datetime,
        user_timezone: str | None = None,
    ) -> bool:
        if not cls._uses_official_review_day_schedule(state, user_timezone=user_timezone):
            return False

        resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        dynamically_due = due_now(
            now_utc=resolved_now,
            user_timezone=user_timezone or "UTC",
            due_review_date=getattr(state, "due_review_date", None),
            min_due_at_utc=getattr(state, "min_due_at_utc", None),
        )
        return sticky_due(
            already_due=cls._has_state_become_due_before(state, now=resolved_now),
            dynamically_due=dynamically_due,
        )

    @classmethod
    def _is_state_due(
        cls,
        state: EntryReviewState,
        *,
        now: datetime,
        user_timezone: str | None = None,
    ) -> bool:
        resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        recheck_due_at = cls._normalize_bucket_datetime(getattr(state, "recheck_due_at", None))
        if recheck_due_at is not None:
            return recheck_due_at <= resolved_now
        if cls._uses_official_review_day_schedule(state, user_timezone=user_timezone):
            return cls._is_state_officially_due(
                state,
                now=resolved_now,
                user_timezone=user_timezone,
            )
        due_at = cls._normalize_bucket_datetime(getattr(state, "next_due_at", None))
        return due_at is None or due_at <= resolved_now

    @classmethod
    def _due_queue_filter(cls, now: datetime):
        resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        return or_(
            and_(
                EntryReviewState.recheck_due_at.is_not(None),
                EntryReviewState.recheck_due_at <= resolved_now,
            ),
            and_(
                EntryReviewState.recheck_due_at.is_(None),
                EntryReviewState.due_review_date.is_not(None),
                EntryReviewState.min_due_at_utc.is_not(None),
                EntryReviewState.min_due_at_utc <= resolved_now,
            ),
            and_(
                EntryReviewState.recheck_due_at.is_(None),
                or_(
                    EntryReviewState.due_review_date.is_(None),
                    EntryReviewState.min_due_at_utc.is_(None),
                ),
                or_(
                    EntryReviewState.next_due_at.is_(None),
                    EntryReviewState.next_due_at <= resolved_now,
                ),
            ),
        )

    @classmethod
    def _resolve_schedule_value_for_state(
        cls,
        state: EntryReviewState,
        *,
        now: datetime | None = None,
        user_timezone: str | None = None,
    ) -> str:
        if cls._uses_official_review_day_schedule(state, user_timezone=user_timezone):
            resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
            if cls._is_state_officially_due(
                state,
                now=resolved_now,
                user_timezone=user_timezone,
            ):
                return cls._resolve_schedule_value_from_due_at(
                    due_at=state.min_due_at_utc,
                    now=resolved_now,
                )
            current_review_date = effective_review_date(
                instant_utc=resolved_now,
                user_timezone=user_timezone or "UTC",
            )
            day_delta = (state.due_review_date - current_review_date).days
            if day_delta > 0:
                return cls._resolve_schedule_value_from_review_day_delta(day_delta)
            return cls._resolve_schedule_value_from_due_at(
                due_at=state.min_due_at_utc,
                now=resolved_now,
            )
        return cls._resolve_schedule_value_from_due_at(
            due_at=state.recheck_due_at or state.next_due_at,
            now=now,
        )

    @classmethod
    def classify_review_bucket(
        cls,
        due_at: datetime | None,
        now: datetime,
        *,
        due_review_date: Any | None = None,
        min_due_at_utc: datetime | None = None,
        user_timezone: str | None = None,
    ) -> str:
        resolved_now = cls._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        resolved_due_at = cls._normalize_bucket_datetime(due_at)
        resolved_min_due_at = cls._normalize_bucket_datetime(min_due_at_utc)

        if due_review_date is not None and resolved_min_due_at is not None and user_timezone:
            officially_due = sticky_due(
                already_due=resolved_min_due_at <= resolved_now,
                dynamically_due=due_now(
                    now_utc=resolved_now,
                    user_timezone=user_timezone,
                    due_review_date=due_review_date,
                    min_due_at_utc=resolved_min_due_at,
                ),
            )
            if officially_due:
                if resolved_min_due_at <= resolved_now - timedelta(seconds=1):
                    return "overdue"
                return "due_now"

            current_review_date = effective_review_date(
                instant_utc=resolved_now,
                user_timezone=user_timezone,
            )
            day_delta = (due_review_date - current_review_date).days
            if day_delta > 0:
                if day_delta == 1:
                    return "tomorrow"
                if day_delta <= 7:
                    return "this_week"
                if day_delta <= 31:
                    return "this_month"
                if day_delta <= 92:
                    return "one_to_three_months"
                if day_delta <= 183:
                    return "three_to_six_months"
                return "six_plus_months"
            return "later_today"

        if resolved_due_at is None or resolved_due_at <= resolved_now - timedelta(seconds=1):
            return "overdue"
        if resolved_due_at <= resolved_now:
            return "due_now"
        if resolved_due_at.date() == resolved_now.date():
            return "later_today"
        if resolved_due_at.date() == (resolved_now + timedelta(days=1)).date():
            return "tomorrow"
        if resolved_due_at <= resolved_now + timedelta(days=7):
            return "this_week"
        if resolved_due_at <= resolved_now + timedelta(days=31):
            return "this_month"
        if resolved_due_at <= resolved_now + timedelta(days=92):
            return "one_to_three_months"
        if resolved_due_at <= resolved_now + timedelta(days=183):
            return "three_to_six_months"
        return "six_plus_months"

    @staticmethod
    def _resolve_grouped_queue_due_at(state: EntryReviewState) -> datetime | None:
        return ReviewService._effective_due_at(state)

    @classmethod
    def _classify_review_bucket_for_state(
        cls,
        state: EntryReviewState,
        *,
        now: datetime,
        user_timezone: str | None = None,
    ) -> str:
        official_schedule_args: dict[str, Any] = {}
        if cls._uses_official_review_day_schedule(state, user_timezone=user_timezone):
            official_schedule_args = {
                "due_review_date": getattr(state, "due_review_date", None),
                "min_due_at_utc": getattr(state, "min_due_at_utc", None),
                "user_timezone": user_timezone,
            }
        return cls.classify_review_bucket(
            cls._resolve_grouped_queue_due_at(state),
            now,
            **official_schedule_args,
        )

    @classmethod
    def _validate_review_queue_bucket(cls, bucket: str) -> str:
        if bucket not in REVIEW_BUCKET_ORDER:
            raise ValueError(f"Unknown review queue bucket: {bucket}")
        return bucket

    @classmethod
    def _validate_review_queue_sort(cls, sort: str) -> str:
        if sort not in cls.ALLOWED_QUEUE_SORTS:
            raise ValueError(f"Unsupported review queue sort: {sort}")
        return sort

    @classmethod
    def _validate_review_queue_order(cls, order: str) -> str:
        if order not in cls.ALLOWED_QUEUE_ORDERS:
            raise ValueError(f"Unsupported review queue order: {order}")
        return order

    async def _list_active_queue_states(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime | None = None,
    ) -> list[EntryReviewState]:
        state_result = await self.db.execute(
            select(EntryReviewState, LearnerEntryStatus.status)
            .outerjoin(
                LearnerEntryStatus,
                and_(
                    LearnerEntryStatus.user_id == EntryReviewState.user_id,
                    LearnerEntryStatus.entry_type == EntryReviewState.entry_type,
                    LearnerEntryStatus.entry_id == EntryReviewState.entry_id,
                ),
            )
            .where(EntryReviewState.user_id == user_id)
            .where(EntryReviewState.is_suspended.is_(False))
            .order_by(
                EntryReviewState.recheck_due_at.asc().nullsfirst(),
                EntryReviewState.next_due_at.asc().nullsfirst(),
                EntryReviewState.created_at.asc(),
            )
        )
        rows = list(state_result.all())
        states: list[EntryReviewState] = []
        for state, learner_status in rows:
            if learner_status not in {None, "learning"}:
                continue
            self._normalize_active_review_state_schedule(state)
            state.learner_status = learner_status or "learning"
            states.append(state)
        if not states:
            return states

        word_entry_ids = list(
            {
                state.entry_id
                for state in states
                if self._normalize_entry_type(state.entry_type) == "word"
            }
        )
        phrase_entry_ids = list(
            {
                state.entry_id
                for state in states
                if self._normalize_entry_type(state.entry_type) == "phrase"
            }
        )

        word_text_by_id: dict[uuid.UUID, str] = {}
        if word_entry_ids:
            word_result = await self.db.execute(
                select(Word.id, Word.word).where(Word.id.in_(word_entry_ids))
            )
            word_text_by_id = {
                entry_id: text for entry_id, text in word_result.all() if self._normalize_prompt_text(text)
            }

        phrase_text_by_id: dict[uuid.UUID, str] = {}
        if phrase_entry_ids:
            phrase_result = await self.db.execute(
                select(PhraseEntry.id, PhraseEntry.phrase_text).where(PhraseEntry.id.in_(phrase_entry_ids))
            )
            phrase_text_by_id = {
                entry_id: text
                for entry_id, text in phrase_result.all()
                if self._normalize_prompt_text(text)
            }

        hydrated_states: list[EntryReviewState] = []
        for state in states:
            normalized_entry_type = self._normalize_entry_type(state.entry_type)
            if normalized_entry_type == "word":
                entry_text = word_text_by_id.get(state.entry_id)
            else:
                entry_text = phrase_text_by_id.get(state.entry_id)
            if not entry_text:
                continue
            state.entry_text = entry_text

            hydrated_states.append(state)

        return self._apply_sibling_bury_rule(hydrated_states)

    def _serialize_grouped_queue_row(
        self,
        state: EntryReviewState,
        *,
        include_debug_fields: bool = False,
    ) -> dict[str, Any]:
        due_at = self._resolve_grouped_queue_due_at(state)
        bucket = self._resolve_srs_bucket(state=state)
        payload = {
            "queue_item_id": str(state.id),
            "entry_id": str(state.entry_id),
            "entry_type": self._normalize_entry_type(state.entry_type),
            "text": self._normalize_prompt_text(getattr(state, "entry_text", None)) or "Unavailable",
            "status": getattr(state, "learner_status", None) or "learning",
            "next_review_at": due_at.isoformat() if due_at is not None else None,
            "due_review_date": getattr(state, "due_review_date", None).isoformat()
            if getattr(state, "due_review_date", None) is not None
            else None,
            "min_due_at_utc": getattr(state, "min_due_at_utc", None).isoformat()
            if getattr(state, "min_due_at_utc", None) is not None
            else None,
            "last_reviewed_at": state.last_reviewed_at.isoformat()
            if state.last_reviewed_at is not None
            else None,
            "bucket": bucket,
        }
        if include_debug_fields:
            payload.update(
                {
                    "target_type": state.target_type,
                    "target_id": str(state.target_id) if state.target_id is not None else None,
                    "recheck_due_at": state.recheck_due_at.isoformat()
                    if state.recheck_due_at is not None
                    else None,
                    "next_due_at": state.next_due_at.isoformat() if state.next_due_at is not None else None,
                    "last_outcome": state.last_outcome,
                    "relearning": bool(state.relearning),
                    "relearning_trigger": state.relearning_trigger,
                }
            )
        return payload

    @staticmethod
    def _serialize_review_history_event(event: EntryReviewEvent) -> dict[str, Any]:
        return {
            "id": str(event.id),
            "reviewed_at": event.created_at.isoformat(),
            "outcome": event.outcome,
            "prompt_type": event.prompt_type,
            "prompt_family": event.prompt_family,
            "scheduled_by": event.scheduled_by,
            "scheduled_interval_days": event.scheduled_interval_days,
        }

    async def _list_review_history_by_state_ids(
        self,
        state_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, list[dict[str, Any]]]:
        if not state_ids:
            return {}

        event_result = await self.db.execute(
            select(EntryReviewEvent)
            .where(EntryReviewEvent.review_state_id.in_(state_ids))
            .order_by(EntryReviewEvent.created_at.desc(), EntryReviewEvent.id.desc())
        )
        scalars_result = event_result.scalars()
        if isawaitable(scalars_result):
            scalars_result = await scalars_result
        events = scalars_result.all()
        if isawaitable(events):
            events = await events
        events = list(events)
        history_by_state_id: dict[uuid.UUID, list[dict[str, Any]]] = {
            state_id: [] for state_id in state_ids
        }
        for event in events:
            if event.review_state_id is None:
                continue
            history_by_state_id.setdefault(event.review_state_id, []).append(
                self._serialize_review_history_event(event)
            )
        return history_by_state_id

    def _group_review_queue_rows(
        self,
        *,
        states: list[EntryReviewState],
        now: datetime,
        include_debug_fields: bool = False,
    ) -> dict[str, list[dict[str, Any]]]:
        del now
        groups: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in REVIEW_BUCKET_ORDER}
        for state in states:
            bucket = self._resolve_srs_bucket(state=state)
            if bucket == "known":
                continue
            groups[bucket].append(
                self._serialize_grouped_queue_row(
                    state,
                    include_debug_fields=include_debug_fields,
                )
            )
        return groups

    @classmethod
    def _group_review_queue_rows_by_due(
        cls,
        *,
        states: list[EntryReviewState],
        now: datetime,
        user_timezone: str | None = None,
        include_debug_fields: bool = False,
        serialize_row: Callable[[EntryReviewState, bool], dict[str, Any]],
    ) -> list[dict[str, Any]]:
        grouped: dict[int, dict[str, Any]] = {}
        for state in states:
            bucket = cls._resolve_srs_bucket(state=state)
            if bucket == "known":
                continue
            due_bucket = cls._classify_review_bucket_for_state(
                state,
                now=now,
                user_timezone=user_timezone,
            )
            if due_bucket in {"overdue", "due_now"}:
                due_in_days = 0
                label = "Due now"
                group_key = "due_now"
            elif due_bucket == "later_today":
                due_in_days = 0
                label = "Later today"
                group_key = "later_today"
            elif due_bucket == "tomorrow":
                due_in_days = 1
                label = "Tomorrow"
                group_key = "tomorrow"
            else:
                due_at = cls._resolve_grouped_queue_due_at(state)
                due_in_days = max((due_at.date() - now.date()).days, 0) if due_at is not None else 0
                label = f"In {due_in_days} days"
                group_key = f"in_{due_in_days}_days"

            group = grouped.setdefault(
                due_in_days,
                {
                    "group_key": group_key,
                    "label": label,
                    "due_in_days": due_in_days,
                    "count": 0,
                    "items": [],
                },
            )
            group["items"].append(serialize_row(state, include_debug_fields))
            group["count"] += 1

        return [grouped[days] for days in sorted(grouped.keys())]

    @staticmethod
    def _is_queue_state_due_now(
        state: EntryReviewState,
        *,
        now: datetime,
        user_timezone: str | None = None,
    ) -> bool:
        return ReviewService._is_state_due(
            state,
            now=now,
            user_timezone=user_timezone,
        )

    @classmethod
    def _review_queue_sort_key(cls, item: dict[str, Any], sort: str) -> tuple[Any, ...]:
        text_key = (item.get("text") or "").casefold()
        next_review_key = item.get("next_review_at") or ""
        last_reviewed_key = item.get("last_reviewed_at") or ""
        queue_item_key = item.get("queue_item_id") or ""
        if sort == "text":
            return (text_key, next_review_key, queue_item_key)
        if sort == "last_reviewed_at":
            return (last_reviewed_key, text_key, queue_item_key)
        return (next_review_key, text_key, queue_item_key)

    async def get_grouped_review_queue(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        include_debug_fields: bool = False,
    ) -> dict[str, Any]:
        resolved_now = self._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        states = await self._list_active_queue_states(user_id=user_id, now=resolved_now)
        for state in states:
            self._normalize_active_review_state_schedule(state)
        groups = self._group_review_queue_rows(
            states=states,
            now=resolved_now,
            include_debug_fields=include_debug_fields,
        )

        return {
            "generated_at": resolved_now.isoformat(),
            "total_count": sum(len(items) for items in groups.values()),
            "groups": [
                {"bucket": bucket, "count": len(groups[bucket]), "items": groups[bucket]}
                for bucket in REVIEW_BUCKET_ORDER
                if groups[bucket]
            ],
        }

    async def get_grouped_review_queue_by_due(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        include_debug_fields: bool = False,
    ) -> dict[str, Any]:
        resolved_now = self._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        states = await self._list_active_queue_states(user_id=user_id, now=resolved_now)
        user_timezone = None
        if any(self._state_has_official_review_day_fields(state) for state in states):
            prefs = await self._get_user_review_preferences(user_id)
            user_timezone = getattr(prefs, "timezone", None) or "UTC"
        for state in states:
            self._normalize_active_review_state_schedule(state)
        groups = self._group_review_queue_rows_by_due(
            states=states,
            now=resolved_now,
            user_timezone=user_timezone,
            include_debug_fields=include_debug_fields,
            serialize_row=lambda state, include_debug: self._serialize_grouped_queue_row(
                state,
                include_debug_fields=include_debug,
            ),
        )

        return {
            "generated_at": resolved_now.isoformat(),
            "total_count": sum(group["count"] for group in groups),
            "groups": groups,
        }

    async def get_grouped_review_queue_summary(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
    ) -> dict[str, Any]:
        resolved_now = self._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        states = await self._list_active_queue_states(user_id=user_id, now=resolved_now)
        user_timezone = None
        if any(self._state_has_official_review_day_fields(state) for state in states):
            prefs = await self._get_user_review_preferences(user_id)
            user_timezone = getattr(prefs, "timezone", None) or "UTC"
        for state in states:
            self._normalize_active_review_state_schedule(state)
        groups = self._group_review_queue_rows(states=states, now=resolved_now)
        has_due_now_by_bucket = {bucket: False for bucket in REVIEW_BUCKET_ORDER}
        for state in states:
            bucket = self._resolve_srs_bucket(state=state)
            if bucket == "known" or bucket not in has_due_now_by_bucket:
                continue
            if self._is_queue_state_due_now(state, now=resolved_now, user_timezone=user_timezone):
                has_due_now_by_bucket[bucket] = True
        return {
            "generated_at": resolved_now.isoformat(),
            "total_count": sum(len(items) for items in groups.values()),
            "groups": [
                {
                    "bucket": bucket,
                    "count": len(groups[bucket]),
                    "has_due_now": has_due_now_by_bucket[bucket],
                }
                for bucket in REVIEW_BUCKET_ORDER
                if groups[bucket]
            ],
        }

    async def get_grouped_review_queue_bucket_detail(
        self,
        *,
        user_id: uuid.UUID,
        now: datetime,
        bucket: str,
        sort: str = "next_review_at",
        order: str = "asc",
        include_debug_fields: bool = False,
    ) -> dict[str, Any]:
        resolved_now = self._normalize_bucket_datetime(now) or datetime.now(timezone.utc)
        resolved_bucket = self._validate_review_queue_bucket(bucket)
        resolved_sort = self._validate_review_queue_sort(sort)
        resolved_order = self._validate_review_queue_order(order)
        states = await self._list_active_queue_states(user_id=user_id, now=resolved_now)
        bucket_states = [
            state
            for state in states
            if self._resolve_srs_bucket(state=state) == resolved_bucket
        ]
        history_by_state_id = await self._list_review_history_by_state_ids(
            [state.id for state in bucket_states]
        )
        items = sorted(
            [
                {
                    **self._serialize_grouped_queue_row(
                        state,
                        include_debug_fields=include_debug_fields,
                    ),
                    "success_streak": int(state.success_streak or 0),
                    "lapse_count": int(state.lapse_count or 0),
                    "times_remembered": int(state.times_remembered or 0),
                    "exposure_count": int(state.exposure_count or 0),
                    "history": history_by_state_id.get(state.id, []),
                }
                for state in bucket_states
            ],
            key=lambda item: self._review_queue_sort_key(item, resolved_sort),
            reverse=resolved_order == "desc",
        )
        return {
            "generated_at": resolved_now.isoformat(),
            "bucket": resolved_bucket,
            "count": len(items),
            "sort": resolved_sort,
            "order": resolved_order,
            "items": items,
        }

    async def get_entry_queue_schedule(
        self,
        *,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> dict[str, Any] | None:
        status_result = await self.db.execute(
            select(LearnerEntryStatus).where(
                LearnerEntryStatus.user_id == user_id,
                LearnerEntryStatus.entry_type == entry_type,
                LearnerEntryStatus.entry_id == entry_id,
            )
        )
        learner_status = status_result.scalar_one_or_none()
        if learner_status is not None and learner_status.status != "learning":
            return None
        state_result = await self.db.execute(
            select(EntryReviewState)
            .outerjoin(
                LearnerEntryStatus,
                and_(
                    LearnerEntryStatus.user_id == EntryReviewState.user_id,
                    LearnerEntryStatus.entry_type == EntryReviewState.entry_type,
                    LearnerEntryStatus.entry_id == EntryReviewState.entry_id,
                ),
            )
            .where(EntryReviewState.user_id == user_id)
            .where(EntryReviewState.entry_type == entry_type)
            .where(EntryReviewState.entry_id == entry_id)
            .where(EntryReviewState.is_suspended.is_(False))
            .where(or_(LearnerEntryStatus.id.is_(None), LearnerEntryStatus.status == "learning"))
            .order_by(
                EntryReviewState.recheck_due_at.asc().nullsfirst(),
                EntryReviewState.next_due_at.asc().nullsfirst(),
                EntryReviewState.created_at.asc(),
            )
            .limit(1)
        )
        state = state_result.scalar_one_or_none()
        if state is None:
            if learner_status is None or learner_status.status != "learning":
                return None
            state = await self._ensure_entry_review_state(
                user_id=user_id,
                entry_type=entry_type,
                entry_id=entry_id,
            )
            await self.db.commit()
        self._normalize_active_review_state_schedule(state)
        user_timezone = None
        if self._state_has_official_review_day_fields(state):
            prefs = await self._get_user_review_preferences(user_id)
            user_timezone = getattr(prefs, "timezone", None) or "UTC"
        return self._build_current_schedule_payload(state, user_timezone=user_timezone)

    async def update_queue_item_schedule(
        self,
        *,
        user_id: uuid.UUID,
        item_id: uuid.UUID,
        schedule_override: str,
    ) -> dict[str, Any]:
        state_result = await self.db.execute(
            select(EntryReviewState)
            .where(
                EntryReviewState.id == item_id,
                EntryReviewState.user_id == user_id,
                EntryReviewState.is_suspended.is_(False),
            )
            .with_for_update()
        )
        state = state_result.scalar_one_or_none()
        if state is None:
            raise ValueError(f"Queue item {item_id} not found")

        if schedule_override == "10m":
            resolved_now = datetime.now(timezone.utc)
            resolved_next_review = resolved_now + timedelta(minutes=10)
            state.next_due_at = resolved_next_review
            state.next_review = resolved_next_review
            state.last_reviewed_at = resolved_now
            state.relearning = True
            state.relearning_trigger = state.relearning_trigger or "manual_reschedule"
            state.recheck_due_at = resolved_next_review
        else:
            resolved_now = datetime.now(timezone.utc)
            (
                resolved_interval_days,
                resolved_due_review_date,
                resolved_min_due_at_utc,
                resolved_bucket,
            ) = await self._resolve_official_review_schedule(
                user_id=user_id,
                reviewed_at=resolved_now,
                interval_days=int(getattr(state, "interval_days", round(state.stability or 0)) or 0),
                resolved_outcome=getattr(state, "last_outcome", None),
                schedule_override=schedule_override,
            )
            state.interval_days = resolved_interval_days
            state.stability = max(0.15, float(resolved_interval_days))
            state.srs_bucket = resolved_bucket
            state.cadence_step = cadence_step_for_bucket(resolved_bucket)
            state.due_review_date = resolved_due_review_date
            state.min_due_at_utc = resolved_min_due_at_utc
            state.next_due_at = resolved_min_due_at_utc
            state.next_review = resolved_min_due_at_utc
            state.last_reviewed_at = resolved_now
            state.relearning = False
            state.relearning_trigger = None
            state.recheck_due_at = None
            learner_status_result = await self.db.execute(
                select(LearnerEntryStatus).where(
                    LearnerEntryStatus.user_id == user_id,
                    LearnerEntryStatus.entry_type == state.entry_type,
                    LearnerEntryStatus.entry_id == state.entry_id,
                )
            )
            learner_status = learner_status_result.scalar_one_or_none()
            if learner_status is None:
                learner_status = LearnerEntryStatus(
                    user_id=user_id,
                    entry_type=state.entry_type,
                    entry_id=state.entry_id,
                    status="learning",
                )
                self.db.add(learner_status)
            learner_status.status = "known" if resolved_bucket == "known" else "learning"
        await self.db.commit()
        self._invalidate_queue_stats_cache(user_id)
        return self._build_current_schedule_payload(state)

    async def add_to_queue(self, user_id: uuid.UUID, meaning_id: uuid.UUID) -> Any:
        """Add a meaning to a user's queue in an idempotent way."""

        meaning_result = await self.db.execute(
            select(Meaning).where(Meaning.id == meaning_id)
        )
        meaning = meaning_result.scalar_one_or_none()
        if meaning is None:
            raise ValueError(f"Meaning {meaning_id} not found")

        target_state = await self._ensure_target_review_state(
            user_id=user_id,
            target_type="meaning",
            target_id=meaning_id,
            entry_type="word",
            entry_id=meaning.word_id,
        )
        await self.db.commit()
        self._invalidate_queue_stats_cache(user_id)
        target_state.meaning_id = meaning_id
        target_state.word_id = meaning.word_id
        target_state.card_type = "flashcard"
        target_state.next_review = target_state.next_due_at

        logger.info(
            "Queue item created",
            user_id=str(user_id),
            meaning_id=str(meaning_id),
            queue_item_id=str(target_state.id),
        )
        return target_state

    async def get_due_queue_items(
        self,
        user_id: uuid.UUID,
        limit: int = 20,
        hydrate_limit: int | None = 1,
        item_id: uuid.UUID | None = None,
    ) -> list[dict[str, Any]]:
        """Get due queue items scoped to a user including prompt metadata."""
        now = datetime.now(timezone.utc)
        fetch_limit = 1 if item_id is not None else min(max(limit * 8, limit + 32), 200)
        state_query = (
            select(EntryReviewState)
            .outerjoin(
                LearnerEntryStatus,
                and_(
                    LearnerEntryStatus.user_id == EntryReviewState.user_id,
                    LearnerEntryStatus.entry_type == EntryReviewState.entry_type,
                    LearnerEntryStatus.entry_id == EntryReviewState.entry_id,
                ),
            )
            .where(EntryReviewState.user_id == user_id)
            .where(EntryReviewState.is_suspended.is_(False))
            .where(or_(LearnerEntryStatus.id.is_(None), LearnerEntryStatus.status == "learning"))
        )
        if item_id is not None:
            state_query = state_query.where(EntryReviewState.id == item_id)
        else:
            state_query = state_query.where(self._due_queue_filter(now))
        state_result = await self.db.execute(
            state_query
            .order_by(
                EntryReviewState.recheck_due_at.asc().nullsfirst(),
                EntryReviewState.next_due_at.asc().nullsfirst(),
                EntryReviewState.created_at.asc(),
            )
            .limit(fetch_limit)
        )
        due_items: list[dict[str, Any]] = []
        review_states = self._apply_sibling_bury_rule(list(state_result.scalars().all()))
        prefs = None
        if item_id is None and review_states and any(
            self._state_has_official_review_day_fields(state) for state in review_states
        ):
            prefs = await self._get_user_review_preferences(user_id)
            user_timezone = getattr(prefs, "timezone", None) or "UTC"
            review_states = [
                state
                for state in review_states
                if self._is_state_due(
                    state,
                    now=now,
                    user_timezone=user_timezone,
                )
            ]
        review_states = review_states[:limit]
        if review_states:
            accent = await self._get_user_accent_preference(user_id)
            word_entry_ids = list(
                {
                    state.entry_id
                    for state in review_states
                    if self._normalize_entry_type(state.entry_type) == "word"
                }
            )
            phrase_entry_ids = list(
                {
                    state.entry_id
                    for state in review_states
                    if self._normalize_entry_type(state.entry_type) == "phrase"
                }
            )

            words_by_id: dict[uuid.UUID, Word] = {}
            meanings_by_word_id: dict[uuid.UUID, list[Meaning]] = {}
            meaning_sentence_map: dict[uuid.UUID, str | None] = {}
            word_history_count_map: dict[uuid.UUID, int] = {}
            if word_entry_ids:
                word_result = await self.db.execute(select(Word).where(Word.id.in_(word_entry_ids)))
                words_by_id = {word.id: word for word in word_result.scalars().all()}
                meanings_result = await self.db.execute(
                    select(Meaning)
                    .where(Meaning.word_id.in_(list(words_by_id.keys())))
                    .order_by(Meaning.word_id.asc(), Meaning.order_index.asc())
                )
                for meaning in meanings_result.scalars().all():
                    meanings_by_word_id.setdefault(meaning.word_id, []).append(meaning)
                meaning_sentence_map = await self._fetch_first_meaning_sentence_map(
                    [meaning.id for meanings in meanings_by_word_id.values() for meaning in meanings]
                )
                word_history_count_map = await self._fetch_history_count_by_word_id(
                    user_id=user_id,
                    meanings_by_word_id=meanings_by_word_id,
                )

            phrases_by_id: dict[uuid.UUID, PhraseEntry] = {}
            senses_by_phrase_id: dict[uuid.UUID, list[PhraseSense]] = {}
            sense_sentence_map: dict[uuid.UUID, str | None] = {}
            if phrase_entry_ids:
                phrase_result = await self.db.execute(
                    select(PhraseEntry).where(PhraseEntry.id.in_(phrase_entry_ids))
                )
                phrases_by_id = {phrase.id: phrase for phrase in phrase_result.scalars().all()}
                senses_result = await self.db.execute(
                    select(PhraseSense)
                    .where(PhraseSense.phrase_entry_id.in_(list(phrases_by_id.keys())))
                    .order_by(PhraseSense.phrase_entry_id.asc(), PhraseSense.order_index.asc())
                )
                for sense in senses_result.scalars().all():
                    senses_by_phrase_id.setdefault(sense.phrase_entry_id, []).append(sense)
                sense_sentence_map = await self._fetch_first_sense_sentence_map(
                    [sense.id for senses in senses_by_phrase_id.values() for sense in senses]
                )

            for index, state in enumerate(review_states):
                self._normalize_active_review_state_schedule(state)
                should_hydrate = hydrate_limit is None or index < hydrate_limit
                if state.entry_type == "word":
                    word = words_by_id.get(state.entry_id)
                    if word is None:
                        continue
                    meanings = meanings_by_word_id.get(word.id, [])
                    if not meanings:
                        continue
                    meaning = meanings[0]
                    sentence = meaning_sentence_map.get(meaning.id)
                    review_mode = None
                    prompt = None
                    detail = None
                    if should_hydrate:
                        forced_prompt_type = self._extract_prompt_type_override(state)
                        prompt = await self._build_card_prompt(
                            review_mode=self.REVIEW_MODE_MCQ,
                            source_text=self._normalize_prompt_text(word.word) or "Unavailable",
                            definition=self._normalize_prompt_text(meaning.definition) or "No definition available.",
                            sentence=sentence,
                            is_phrase_entry=False,
                            distractor_seed=str(meaning.id),
                            meaning_id=meaning.id,
                            index=index,
                            alternative_definitions=None,
                            user_id=user_id,
                            source_entry_id=word.id,
                            source_entry_type="word",
                            queue_item_id=state.id,
                            previous_prompt_type=state.last_prompt_type,
                            forced_prompt_type=forced_prompt_type,
                            active_target_count=1,
                            srs_bucket=getattr(state, "srs_bucket", None),
                            cadence_step=getattr(state, "cadence_step", None),
                        )
                        prompt_type = (prompt or {}).get("prompt_type") or forced_prompt_type
                        review_mode = (prompt or {}).get("mode") or self._review_mode_for_prompt_type(prompt_type)
                        detail = await self._build_word_detail_payload(
                            user_id=user_id,
                            word=word,
                            meanings=meanings,
                            example_by_meaning_id=meaning_sentence_map,
                            remembered_count=word_history_count_map.get(word.id, 0),
                            accent=accent,
                        )
                    state.meaning_id = meaning.id
                    due_items.append(
                        {
                            "id": state.id,
                            "item": state,
                            "word": word.word,
                            "definition": meaning.definition,
                            "target_type": "meaning",
                            "target_id": str(meaning.id),
                            "next_review": state.next_due_at,
                            "review_mode": review_mode,
                            "source_entry_type": "word",
                            "source_entry_id": str(word.id),
                            "prompt": prompt,
                            "detail": detail,
                            "schedule_options": self._build_schedule_options_for_value(
                                self._resolve_srs_bucket(state=state)
                            ),
                            "source_word_id": str(word.id),
                            "source_meaning_id": str(meaning.id),
                        }
                    )
                    continue

                phrase = phrases_by_id.get(state.entry_id)
                if phrase is None:
                    continue
                senses = senses_by_phrase_id.get(phrase.id, [])
                if not senses:
                    continue
                sense = senses[0]
                sentence = sense_sentence_map.get(sense.id)
                review_mode = None
                prompt = None
                detail = None
                if should_hydrate:
                    forced_prompt_type = self._extract_prompt_type_override(state)
                    prompt = await self._build_card_prompt(
                        review_mode=self.REVIEW_MODE_MCQ,
                        source_text=self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
                        definition=self._normalize_prompt_text(sense.definition) or "No definition available.",
                        sentence=sentence,
                        is_phrase_entry=True,
                        distractor_seed=str(sense.id),
                        meaning_id=sense.id,
                        index=index,
                        alternative_definitions=None,
                        user_id=user_id,
                        source_entry_id=phrase.id,
                        source_entry_type="phrase",
                        queue_item_id=state.id,
                        previous_prompt_type=state.last_prompt_type,
                        forced_prompt_type=forced_prompt_type,
                        active_target_count=1,
                        srs_bucket=getattr(state, "srs_bucket", None),
                        cadence_step=getattr(state, "cadence_step", None),
                    )
                    prompt_type = (prompt or {}).get("prompt_type") or forced_prompt_type
                    review_mode = (prompt or {}).get("mode") or self._review_mode_for_prompt_type(prompt_type)
                    detail = await self._build_phrase_detail_payload(
                        user_id=user_id,
                        phrase=phrase,
                        senses=senses,
                        example_by_sense_id=sense_sentence_map,
                    )
                state.meaning_id = sense.id
                due_items.append(
                    {
                        "id": state.id,
                        "item": state,
                        "word": phrase.phrase_text,
                        "definition": sense.definition,
                        "target_type": "phrase_sense",
                        "target_id": str(sense.id),
                        "next_review": state.next_due_at,
                        "review_mode": review_mode,
                        "source_entry_type": "phrase",
                        "source_entry_id": str(phrase.id),
                        "prompt": prompt,
                        "detail": detail,
                        "schedule_options": self._build_schedule_options_for_value(
                            self._resolve_srs_bucket(state=state)
                        ),
                        "source_word_id": None,
                        "source_meaning_id": str(sense.id),
                    }
                )

            if due_items:
                return due_items

        return due_items

    async def get_queue_item(self, user_id: uuid.UUID, item_id: uuid.UUID) -> dict[str, Any]:
        due_items = await self.get_due_queue_items(
            user_id=user_id,
            limit=1,
            hydrate_limit=1,
            item_id=item_id,
        )
        if not due_items:
            raise ValueError(f"Queue item {item_id} not found")
        return due_items[0]

    async def _build_learning_cards_for_word(
        self,
        user_id: uuid.UUID,
        word: Word,
        meanings: list[Meaning],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any], EntryReviewState | None]:
        primary_meaning = meanings[0]
        accent = await self._get_user_accent_preference(user_id)
        meaning_sentence_map = await self._fetch_first_meaning_sentence_map(
            [primary_meaning.id]
        )
        remembered_count_map = await self._fetch_history_count_by_word_id(
            user_id=user_id,
            meanings_by_word_id={word.id: meanings},
        )
        detail = await self._build_word_detail_payload(
            user_id=user_id,
            word=word,
            meanings=meanings,
            example_by_meaning_id=meaning_sentence_map,
            remembered_count=remembered_count_map.get(word.id, 0),
            accent=accent,
        )

        source_text = self._normalize_prompt_text(word.word) or "Unavailable"
        sentence = meaning_sentence_map.get(primary_meaning.id)
        target_state = await self._ensure_target_review_state(
            user_id=user_id,
            target_type="meaning",
            target_id=primary_meaning.id,
            entry_type="word",
            entry_id=word.id,
        )
        queue_item_id = str(target_state.id)
        prompt = await self._build_card_prompt(
            review_mode=self.REVIEW_MODE_MCQ,
            source_text=source_text,
            definition=self._normalize_prompt_text(primary_meaning.definition) or "No definition available.",
            sentence=sentence,
            is_phrase_entry=False,
            distractor_seed=str(primary_meaning.id),
            meaning_id=primary_meaning.id,
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=word.id,
            source_entry_type="word",
            queue_item_id=target_state.id,
            previous_prompt_type=getattr(target_state, "last_prompt_type", None),
            active_target_count=1,
            srs_bucket=getattr(target_state, "srs_bucket", None),
            cadence_step=getattr(target_state, "cadence_step", None),
        )

        cards = [
            {
                "queue_item_id": queue_item_id,
                "meaning_id": str(primary_meaning.id),
                "word": source_text,
                "definition": self._normalize_prompt_text(primary_meaning.definition)
                or "No definition available.",
                "prompt": prompt,
                "detail": detail,
            }
        ]
        return cards, [str(primary_meaning.id)], [queue_item_id], detail, target_state

    async def _build_learning_cards_for_phrase(
        self,
        user_id: uuid.UUID,
        phrase: PhraseEntry,
        senses: list[PhraseSense],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any], EntryReviewState | None]:
        primary_sense = senses[0]
        sense_sentence_map = await self._fetch_first_sense_sentence_map(
            [primary_sense.id]
        )
        source_text = self._normalize_prompt_text(phrase.phrase_text) or "Unavailable"
        detail = await self._build_phrase_detail_payload(
            user_id=user_id,
            phrase=phrase,
            senses=senses,
            example_by_sense_id=sense_sentence_map,
        )
        sentence = sense_sentence_map.get(primary_sense.id)
        target_state = await self._ensure_target_review_state(
            user_id=user_id,
            target_type="phrase_sense",
            target_id=primary_sense.id,
            entry_type="phrase",
            entry_id=phrase.id,
        )
        prompt = await self._build_card_prompt(
            review_mode=self.REVIEW_MODE_MCQ,
            source_text=source_text,
            definition=self._normalize_prompt_text(primary_sense.definition) or "No definition available.",
            sentence=sentence,
            is_phrase_entry=True,
            distractor_seed=str(primary_sense.id),
            meaning_id=primary_sense.id,
            index=0,
            alternative_definitions=None,
            user_id=user_id,
            source_entry_id=phrase.id,
            source_entry_type="phrase",
            queue_item_id=target_state.id,
            previous_prompt_type=getattr(target_state, "last_prompt_type", None),
            active_target_count=1,
            srs_bucket=getattr(target_state, "srs_bucket", None),
            cadence_step=getattr(target_state, "cadence_step", None),
        )

        cards = [
            {
                "queue_item_id": str(target_state.id),
                "meaning_id": str(primary_sense.id),
                "word": source_text,
                "definition": self._normalize_prompt_text(primary_sense.definition)
                or "No definition available.",
                "prompt": prompt,
                "detail": detail,
            }
        ]
        return cards, [str(primary_sense.id)], [str(target_state.id)], detail, target_state

    async def start_learning_entry(
        self,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> dict[str, Any]:
        normalized_entry_type = self._normalize_entry_type(entry_type)
        status_result = await self.db.execute(
            select(LearnerEntryStatus).where(
                LearnerEntryStatus.user_id == user_id,
                LearnerEntryStatus.entry_type == normalized_entry_type,
                LearnerEntryStatus.entry_id == entry_id,
            )
        )
        learner_status = status_result.scalar_one_or_none()
        if learner_status is None:
            learner_status = LearnerEntryStatus(
                user_id=user_id,
                entry_type=normalized_entry_type,
                entry_id=entry_id,
                status="learning",
            )
            self.db.add(learner_status)
        else:
            learner_status.status = "learning"

        if normalized_entry_type == "word":
            result = await self.db.execute(select(Word).where(Word.id == entry_id))
            word = result.scalar_one_or_none()
            if word is None:
                raise ValueError(f"Word {entry_id} not found")
            meaning_result = await self.db.execute(
                select(Meaning).where(Meaning.word_id == word.id).order_by(Meaning.order_index.asc())
            )
            meanings = meaning_result.scalars().all()
            if not meanings:
                raise ValueError(f"Word {word.id} has no meanings to learn")

            cards, meaning_ids, queue_item_ids, detail, first_target_state = await self._build_learning_cards_for_word(
                user_id=user_id,
                word=word,
                meanings=meanings,
            )
            await self.db.commit()

            return {
                "entry_type": "word",
                "entry_id": str(word.id),
                "entry_word": self._normalize_prompt_text(word.word) or "Unavailable",
                "meaning_ids": meaning_ids,
                "queue_item_ids": queue_item_ids,
                "cards": cards,
                "detail": detail,
                "schedule_options": self._build_schedule_options_for_value(
                    self._resolve_srs_bucket(state=first_target_state)
                ),
                "requires_lookup_hint": False,
            }

        result = await self.db.execute(select(PhraseEntry).where(PhraseEntry.id == entry_id))
        phrase = result.scalar_one_or_none()
        if phrase is None:
            raise ValueError(f"Phrase {entry_id} not found")

        sense_result = await self.db.execute(
            select(PhraseSense)
            .where(PhraseSense.phrase_entry_id == phrase.id)
            .order_by(PhraseSense.order_index.asc())
        )
        senses = sense_result.scalars().all()
        if not senses:
            raise ValueError(f"Phrase {phrase.id} has no senses to learn")

        cards, meaning_ids, queue_item_ids, detail, first_target_state = await self._build_learning_cards_for_phrase(
            user_id=user_id,
            phrase=phrase,
            senses=senses,
        )
        await self.db.commit()

        return {
            "entry_type": "phrase",
            "entry_id": str(phrase.id),
            "entry_word": self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
            "meaning_ids": meaning_ids,
            "queue_item_ids": queue_item_ids,
            "cards": cards,
            "detail": detail,
            "schedule_options": self._build_schedule_options_for_value(
                self._resolve_srs_bucket(state=first_target_state)
            ),
            "requires_lookup_hint": False,
        }

    async def submit_queue_review(
        self,
        item_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
        confirm: bool = False,
        card_type: str | None = None,
        prompt_token: str | None = None,
        review_mode: str | None = None,
        outcome: str | None = None,
        selected_option_id: str | None = None,
        typed_answer: str | None = None,
        audio_replay_count: int = 0,
        prompt: dict[str, Any] | None = None,
        schedule_override: str | None = None,
    ) -> Any:
        result = await submit_queue_review_impl(
            self,
            item_id=item_id,
            quality=quality,
            time_spent_ms=time_spent_ms,
            user_id=user_id,
            confirm=confirm,
            card_type=card_type,
            prompt_token=prompt_token,
            review_mode=review_mode,
            outcome=outcome,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
            audio_replay_count=audio_replay_count,
            prompt=prompt,
            schedule_override=schedule_override,
        )
        self._invalidate_queue_stats_cache(user_id)
        return result

    async def _submit_entry_state_review(
        self,
        *,
        entry_state: EntryReviewState,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
        confirm: bool,
        review_mode: str | None,
        outcome: str | None,
        selected_option_id: str | None,
        typed_answer: str | None,
        audio_replay_count: int,
        prompt: dict[str, Any] | None,
        schedule_override: str | None,
    ) -> EntryReviewState:
        return await submit_entry_state_review_impl(
            self,
            entry_state=entry_state,
            quality=quality,
            time_spent_ms=time_spent_ms,
            user_id=user_id,
            confirm=confirm,
            review_mode=review_mode,
            outcome=outcome,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
            audio_replay_count=audio_replay_count,
            prompt=prompt,
            schedule_override=schedule_override,
        )

    def _apply_entry_state_review_result(
        self,
        *,
        entry_state: EntryReviewState,
        review_result: Any,
        resolved_outcome: str,
        prompt: dict[str, Any] | None,
        resolved_interval_days: int,
        resolved_next_review: datetime,
        reviewed_at: datetime,
        due_review_date: Any,
        min_due_at_utc: datetime | None,
    ) -> None:
        return apply_entry_state_review_result_impl(
            self,
            entry_state=entry_state,
            review_result=review_result,
            resolved_outcome=resolved_outcome,
            prompt=prompt,
            resolved_interval_days=resolved_interval_days,
            resolved_next_review=resolved_next_review,
            reviewed_at=reviewed_at,
            due_review_date=due_review_date,
            min_due_at_utc=min_due_at_utc,
        )

    async def _build_entry_state_detail(
        self,
        *,
        user_id: uuid.UUID,
        entry_state: EntryReviewState,
    ) -> dict[str, Any] | None:
        return await build_entry_state_detail_impl(
            self,
            user_id=user_id,
            entry_state=entry_state,
        )

    async def get_queue_stats(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Get queue totals, due counts, and aggregate performance stats."""
        cached = self._get_cached_queue_stats(user_id)
        if cached is not None:
            return cached
        now = datetime.now(timezone.utc)
        visible_states = await self._list_active_queue_states(user_id=user_id, now=now)
        for state in visible_states:
            self._normalize_active_review_state_schedule(state)
        total_items = len(visible_states)
        due_items = sum(1 for state in visible_states if self._is_queue_state_due_now(state, now=now))

        aggregate_result = await self.db.execute(
            select(
                func.count(EntryReviewEvent.id),
                func.count(EntryReviewEvent.id).filter(
                    EntryReviewEvent.outcome.in_(["correct_tested", "remember"])
                ),
            ).where(EntryReviewEvent.user_id == user_id)
        )
        review_count, correct_count = aggregate_result.one()

        review_count = int(review_count or 0)
        correct_count = int(correct_count or 0)
        accuracy = (correct_count / review_count) if review_count > 0 else 0.0

        stats = {
            "total_items": total_items,
            "due_items": due_items,
            "review_count": review_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
        }
        self._store_cached_queue_stats(user_id, stats)
        return stats

    async def get_review_analytics_summary(
        self,
        user_id: uuid.UUID,
        days: int = 30,
    ) -> dict[str, Any]:
        """Summarize recent entry-review events for lightweight reporting/debugging."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)

        total_result = await self.db.execute(
            select(func.count(EntryReviewEvent.id)).where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
            )
        )
        total_events = int(total_result.scalar_one() or 0)

        placeholder_result = await self.db.execute(
            select(func.count(EntryReviewEvent.id)).where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
                EntryReviewEvent.used_audio_placeholder.is_(True),
            )
        )
        audio_placeholder_events = int(placeholder_result.scalar_one() or 0)

        prompt_family_expr = func.coalesce(EntryReviewEvent.prompt_family, literal("unknown"))
        prompt_family_result = await self.db.execute(
            select(
                prompt_family_expr.label("value"),
                func.count(EntryReviewEvent.id).label("count"),
            )
            .where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
            )
            .group_by(prompt_family_expr)
            .order_by(func.count(EntryReviewEvent.id).desc(), prompt_family_expr.asc())
        )

        outcome_result = await self.db.execute(
            select(
                EntryReviewEvent.outcome.label("value"),
                func.count(EntryReviewEvent.id).label("count"),
            )
            .where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
            )
            .group_by(EntryReviewEvent.outcome)
            .order_by(func.count(EntryReviewEvent.id).desc(), EntryReviewEvent.outcome.asc())
        )

        input_mode_expr = func.coalesce(
            EntryReviewEvent.response_input_mode,
            literal("unknown"),
        )
        input_mode_result = await self.db.execute(
            select(
                input_mode_expr.label("value"),
                func.count(EntryReviewEvent.id).label("count"),
            )
            .where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
            )
            .group_by(input_mode_expr)
            .order_by(func.count(EntryReviewEvent.id).desc(), input_mode_expr.asc())
        )

        audio_replay_total_result = await self.db.execute(
            select(func.coalesce(func.sum(EntryReviewEvent.audio_replay_count), 0)).where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
            )
        )
        total_audio_replays = int(audio_replay_total_result.scalar_one() or 0)

        audio_replay_count_expr = func.coalesce(EntryReviewEvent.audio_replay_count, literal(0))
        audio_replay_count_result = await self.db.execute(
            select(
                audio_replay_count_expr.label("value"),
                func.count(EntryReviewEvent.id).label("count"),
            )
            .where(
                EntryReviewEvent.user_id == user_id,
                EntryReviewEvent.created_at >= cutoff,
            )
            .group_by(audio_replay_count_expr)
            .order_by(func.count(EntryReviewEvent.id).desc(), audio_replay_count_expr.asc())
        )

        return {
            "days": days,
            "total_events": total_events,
            "audio_placeholder_events": audio_placeholder_events,
            "total_audio_replays": total_audio_replays,
            "audio_replay_counts": [
                {"value": str(row.value), "count": int(row.count)}
                for row in audio_replay_count_result.all()
            ],
            "prompt_families": [
                {"value": row.value, "count": int(row.count)}
                for row in prompt_family_result.all()
            ],
            "outcomes": [
                {"value": row.value, "count": int(row.count)}
                for row in outcome_result.all()
            ],
            "response_input_modes": [
                {"value": row.value, "count": int(row.count)}
                for row in input_mode_result.all()
            ],
        }
