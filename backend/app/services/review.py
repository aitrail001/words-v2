import base64
import hashlib
import json
import uuid
import re
import random
from time import monotonic
from datetime import datetime, timezone, timedelta
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import and_, func, literal, literal_column, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased, selectinload

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import review as review_models
from app.models.meaning_example import MeaningExample
from app.models.meaning import Meaning
from app.models.entry_review import EntryReviewEvent, EntryReviewState
from app.models.lexicon_voice_asset import LexiconVoiceAsset
from app.models.review import ReviewCard, ReviewSession
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.user_preference import UserPreference
from app.models.word import Word
from app.spaced_repetition import calculate_next_review
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
from app.services.review_submission import (
    apply_entry_state_review_result as apply_entry_state_review_result_impl,
    build_entry_state_detail as build_entry_state_detail_impl,
    submit_entry_state_review as submit_entry_state_review_impl,
    submit_legacy_queue_review as submit_legacy_queue_review_impl,
    submit_queue_review as submit_queue_review_impl,
)
from app.services.voice_assets import (
    build_voice_asset_playback_url,
    load_phrase_voice_assets,
    load_word_voice_assets,
)

logger = get_logger(__name__)
settings = get_settings()


class ReviewService:
    SCHEDULE_OVERRIDE_DAYS = {
        "10m": 10 / (24 * 60),
        "1d": 1,
        "3d": 3,
        "7d": 7,
        "14d": 14,
        "1m": 30,
        "3m": 90,
        "6m": 180,
        "never_for_now": 365,
    }
    SCHEDULE_OVERRIDE_VALUES = set(SCHEDULE_OVERRIDE_DAYS.keys())
    REVIEW_MODE_CONFIDENCE = "confidence"
    REVIEW_MODE_MCQ = "mcq"
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

    def __init__(
        self,
        db: AsyncSession,
        queue_model: type[Any] | None = None,
        history_model: type[Any] | None = None,
    ):
        self.db = db
        self.queue_model = queue_model or self._resolve_queue_model()
        self.history_model = (
            history_model if history_model is not None else self._resolve_history_model()
        )
        self.uses_legacy_queue = self.queue_model is ReviewCard
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
    def _mask_sentence(sentence: str, target: str) -> str | None:
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
        if (
            self.history_model is None
            or not hasattr(self.history_model, "user_id")
            or not hasattr(self.history_model, "meaning_id")
        ):
            return {}

        meaning_to_word_id: dict[uuid.UUID, uuid.UUID] = {}
        for word_id, meanings in meanings_by_word_id.items():
            for meaning in meanings:
                meaning_to_word_id[meaning.id] = word_id

        if not meaning_to_word_id:
            return {}

        result = await self.db.execute(
            select(self.history_model.meaning_id, func.count(self.history_model.id))
            .where(self.history_model.user_id == user_id)
            .where(self.history_model.meaning_id.in_(list(meaning_to_word_id.keys())))
            .group_by(self.history_model.meaning_id)
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

        def sort_key(asset: LexiconVoiceAsset) -> tuple[int, str, str]:
            locale = getattr(asset, "locale", "") or ""
            profile_key = getattr(asset, "profile_key", "") or ""
            if normalized_entry_type == "phrase":
                if example_id is not None and getattr(asset, "phrase_sense_example_id", None) == example_id:
                    return (0, locale, profile_key)
                if target_id is not None and getattr(asset, "phrase_sense_id", None) == target_id:
                    return (1, locale, profile_key)
                if getattr(asset, "phrase_entry_id", None) is not None:
                    return (2, locale, profile_key)
            else:
                if example_id is not None and getattr(asset, "meaning_example_id", None) == example_id:
                    return (0, locale, profile_key)
                if target_id is not None and getattr(asset, "meaning_id", None) == target_id:
                    return (1, locale, profile_key)
                if getattr(asset, "word_id", None) is not None:
                    return (2, locale, profile_key)
            return (3, locale, profile_key)

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
        if remembered_count is None and self.history_model is not None and hasattr(self.history_model, "user_id"):
            history_result = await self.db.execute(
                select(func.count(self.history_model.id))
                .where(self.history_model.user_id == user_id)
                .where(self.history_model.meaning_id.in_([meaning.id for meaning in meanings]))
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
            )
        )
        return result.scalar_one_or_none()

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
        return result.scalar_one_or_none()

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
            stability=0.3,
            difficulty=0.5,
            success_streak=0,
            lapse_count=0,
            exposure_count=0,
            times_remembered=0,
            is_fragile=False,
            is_suspended=False,
        )
        self.db.add(state)
        await self.db.flush()
        return state

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
            stability=0.3,
            difficulty=0.5,
            success_streak=0,
            lapse_count=0,
            exposure_count=0,
            times_remembered=0,
            is_fragile=False,
            is_suspended=False,
        )
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

    def _select_prompt_type(
        self,
        prompt_candidates: list[str],
        index: int = 0,
        previous_prompt_type: str | None = None,
    ) -> str:
        if not prompt_candidates:
            return self.PROMPT_TYPE_DEFINITION_TO_ENTRY
        if previous_prompt_type:
            for candidate in prompt_candidates:
                if candidate != previous_prompt_type:
                    return candidate
        if len(prompt_candidates) == 1:
            return prompt_candidates[0]
        return prompt_candidates[index % len(prompt_candidates)]

    async def _resolve_prompt_text(
        self,
        prompt_type: str,
        word: str,
        definition: str,
        sentence: str | None = None,
    ) -> tuple[str, str]:
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
            return stem, self._prompt_value_for_options(sentence)
        if prompt_type == self.PROMPT_TYPE_TYPED_RECALL:
            stem = "Type the word or phrase that matches this definition."
            return stem, self._prompt_value_for_options(definition)
        if prompt_type == self.PROMPT_TYPE_SPEAK_RECALL:
            stem = "Say the word or phrase that matches this definition."
            return stem, self._prompt_value_for_options(definition)
        if prompt_type == self.PROMPT_TYPE_ENTRY_TO_DEFINITION:
            return "Choose the best definition for this word or phrase.", self._prompt_value_for_options(word)
        return "Listen, then choose the best matching definition.", self._prompt_value_for_options(word)

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
                audio_state="placeholder",
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
            audio_state="ready" if prompt_type == self.PROMPT_TYPE_AUDIO_TO_DEFINITION and audio else "not_available",
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

    @staticmethod
    def _derive_interval_from_override(
        original_interval_days: int | None,
        override_value: str | None,
        base_next_review: datetime | None = None,
    ) -> tuple[int, datetime, int | None]:
        if override_value is None:
            return (
                ReviewService._resolve_interval_days_or_zero(original_interval_days),
                base_next_review if base_next_review is not None else datetime.now(timezone.utc),
                None,
            )

        mapped_days = ReviewService.SCHEDULE_OVERRIDE_DAYS.get(override_value)
        if mapped_days is None:
            return (
                ReviewService._resolve_interval_days_or_zero(original_interval_days),
                base_next_review if base_next_review is not None else datetime.now(timezone.utc),
                None,
            )

        return (
            int(mapped_days),
            datetime.now(timezone.utc) + timedelta(days=mapped_days),
            original_interval_days,
        )

    @classmethod
    def _default_schedule_option_value(cls, interval_days: int) -> str:
        if interval_days <= 0:
            return "10m"
        if interval_days <= 1:
            return "1d"
        if interval_days <= 3:
            return "3d"
        if interval_days <= 7:
            return "7d"
        if interval_days <= 14:
            return "14d"
        if interval_days <= 30:
            return "1m"
        if interval_days <= 90:
            return "3m"
        if interval_days <= 180:
            return "6m"
        return "never_for_now"

    @classmethod
    def _build_schedule_options(cls, interval_days: int) -> list[dict[str, Any]]:
        default_value = cls._default_schedule_option_value(interval_days)
        labels = {
            "10m": "Later today",
            "1d": "Tomorrow",
            "3d": "In 3 days",
            "7d": "In a week",
            "14d": "In 2 weeks",
            "1m": "In a month",
            "3m": "In 3 months",
            "6m": "In 6 months",
            "never_for_now": "Stop reviewing",
        }
        order = ["10m", "1d", "3d", "7d", "14d", "1m", "3m", "6m", "never_for_now"]
        return [
            {"value": value, "label": labels[value], "is_default": value == default_value}
            for value in order
        ]

    @staticmethod
    def _resolve_queue_model() -> type[Any]:
        for model_name in (
            "LearningQueueItem",
            "UserMeaning",
            "ReviewQueueItem",
            "UserMeaningQueue",
        ):
            model = getattr(review_models, model_name, None)
            if model is not None:
                return model

        for model in vars(review_models).values():
            if not isinstance(model, type):
                continue
            table = getattr(model, "__table__", None)
            if table is None:
                continue
            columns = {column.name for column in table.columns}
            if {"user_id", "meaning_id"}.issubset(columns):
                return model

        return ReviewCard

    @staticmethod
    def _resolve_history_model() -> type[Any] | None:
        for model_name in ("ReviewHistory", "QueueReviewHistory"):
            model = getattr(review_models, model_name, None)
            if model is not None:
                return model

        for model in vars(review_models).values():
            if not isinstance(model, type):
                continue
            table = getattr(model, "__table__", None)
            if table is None:
                continue
            columns = {column.name for column in table.columns}
            if "user_id" in columns and "time_spent_ms" in columns and (
                "quality" in columns or "quality_rating" in columns
            ):
                return model

        return None

    @staticmethod
    def _build_model_instance(model: type[Any], values: dict[str, Any]) -> Any | None:
        table = getattr(model, "__table__", None)
        if table is None:
            return model(**values)

        available_columns = {column.name: column for column in table.columns}
        payload = {
            key: value for key, value in values.items() if key in available_columns
        }

        for column in table.columns:
            if column.primary_key or column.name in payload:
                continue
            has_default = column.default is not None or column.server_default is not None
            if not column.nullable and not has_default:
                return None

        return model(**payload)

    def _history_supports_schedule(self) -> bool:
        if self.history_model is None or not hasattr(self.history_model, "__table__"):
            return False
        columns = {column.name for column in self.history_model.__table__.columns}
        return {"meaning_id", "created_at", "interval_days", "user_id"}.issubset(columns)

    async def create_session(self, user_id: uuid.UUID) -> ReviewSession:
        """Create a new review session for a user."""
        session = ReviewSession(user_id=user_id)
        self.db.add(session)
        await self.db.commit()

        logger.info("Review session created", session_id=str(session.id), user_id=str(user_id))
        return session

    async def get_due_cards(self, user_id: uuid.UUID, limit: int = 20) -> list[ReviewCard]:
        """Get cards due for review for a user."""
        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewSession.user_id == user_id)
            .where((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
            .order_by(ReviewCard.next_review.asc().nullsfirst())
            .limit(limit)
        )
        cards = result.scalars().all()

        logger.info("Retrieved due cards", user_id=str(user_id), count=len(cards))
        return list(cards)

    async def add_card_to_session(
        self,
        session_id: uuid.UUID,
        word_id: uuid.UUID,
        meaning_id: uuid.UUID,
        card_type: str,
    ) -> ReviewCard:
        """Add a card to a review session."""
        card = ReviewCard(
            session_id=session_id,
            word_id=word_id,
            meaning_id=meaning_id,
            card_type=card_type,
        )
        self.db.add(card)
        await self.db.commit()

        logger.info(
            "Card added to session",
            session_id=str(session_id),
            card_id=str(card.id),
            card_type=card_type,
        )
        return card

    async def add_to_queue(self, user_id: uuid.UUID, meaning_id: uuid.UUID) -> Any:
        """Add a meaning to a user's queue in an idempotent way."""
        if self.uses_legacy_queue:
            return await self._add_to_legacy_queue(user_id, meaning_id)

        result = await self.db.execute(
            select(self.queue_model).where(
                self.queue_model.user_id == user_id,
                self.queue_model.meaning_id == meaning_id,
            )
        )
        existing_item = result.scalar_one_or_none()
        if existing_item is not None:
            return existing_item

        meaning_result = await self.db.execute(
            select(Meaning).where(Meaning.id == meaning_id)
        )
        meaning = meaning_result.scalar_one_or_none()
        if meaning is None:
            raise ValueError(f"Meaning {meaning_id} not found")

        new_item = self._build_model_instance(
            self.queue_model,
            {
                "user_id": user_id,
                "meaning_id": meaning_id,
                "word_id": meaning.word_id,
                "card_type": "flashcard",
                "priority": 0,
                "review_count": 0,
                "correct_count": 0,
                "next_review": None,
            },
        )
        if new_item is None:
            raise ValueError("Queue model is missing required fields for queue creation")

        # Keep API responses consistent across schemas that may not persist these fields.
        if getattr(new_item, "card_type", None) is None:
            setattr(new_item, "card_type", "flashcard")
        if getattr(new_item, "word_id", None) is None:
            setattr(new_item, "word_id", meaning.word_id)
        if not hasattr(new_item, "next_review"):
            setattr(new_item, "next_review", None)

        self.db.add(new_item)
        await self.db.commit()
        self._invalidate_queue_stats_cache(user_id)

        logger.info(
            "Queue item created",
            user_id=str(user_id),
            meaning_id=str(meaning_id),
            queue_item_id=str(getattr(new_item, "id", "")),
        )
        return new_item

    async def _add_to_legacy_queue(
        self, user_id: uuid.UUID, meaning_id: uuid.UUID
    ) -> ReviewCard:
        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewSession.user_id == user_id, ReviewCard.meaning_id == meaning_id)
        )
        existing_item = result.scalar_one_or_none()
        if existing_item is not None:
            return existing_item

        meaning_result = await self.db.execute(
            select(Meaning).where(Meaning.id == meaning_id)
        )
        meaning = meaning_result.scalar_one_or_none()
        if meaning is None:
            raise ValueError(f"Meaning {meaning_id} not found")

        session_result = await self.db.execute(
            select(ReviewSession)
            .where(ReviewSession.user_id == user_id, ReviewSession.completed_at.is_(None))
            .order_by(ReviewSession.started_at.desc())
        )
        session = session_result.scalar_one_or_none()
        if session is None:
            session = ReviewSession(id=uuid.uuid4(), user_id=user_id)
            self.db.add(session)

        card = ReviewCard(
            session_id=session.id,
            word_id=meaning.word_id,
            meaning_id=meaning_id,
            card_type="flashcard",
            next_review=None,
        )
        self.db.add(card)
        await self.db.commit()
        self._invalidate_queue_stats_cache(user_id)

        logger.info(
            "Legacy queue item created",
            user_id=str(user_id),
            meaning_id=str(meaning_id),
            queue_item_id=str(card.id),
        )
        return card

    def _build_history_due_query(self, user_id: uuid.UUID, now: datetime):
        latest_history_subquery = (
            select(
                self.history_model.meaning_id.label("meaning_id"),
                func.max(self.history_model.created_at).label("latest_created_at"),
            )
            .where(self.history_model.user_id == user_id)
            .group_by(self.history_model.meaning_id)
            .subquery()
        )

        latest_history = aliased(self.history_model)
        next_review_expr = (
            latest_history.created_at
            + (latest_history.interval_days * literal_column("interval '1 day'"))
        ).label("next_review")

        due_condition = (
            (latest_history.id.is_(None))
            | (latest_history.interval_days.is_(None))
            | (next_review_expr <= now)
        )

        return latest_history_subquery, latest_history, next_review_expr, due_condition

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
            .where(EntryReviewState.user_id == user_id)
            .where(EntryReviewState.is_suspended.is_(False))
        )
        if item_id is not None:
            state_query = state_query.where(EntryReviewState.id == item_id)
        else:
            state_query = state_query.where(
                (EntryReviewState.recheck_due_at.is_not(None) & (EntryReviewState.recheck_due_at <= now))
                | (EntryReviewState.next_due_at.is_(None))
                | (EntryReviewState.next_due_at <= now)
            )
        state_result = await self.db.execute(
            state_query
            .order_by(
                EntryReviewState.recheck_due_at.asc().nullsfirst(),
                EntryReviewState.next_due_at.asc().nullsfirst(),
                EntryReviewState.created_at.asc(),
            )
            .limit(fetch_limit)
        )
        review_states = self._apply_sibling_bury_rule(list(state_result.scalars().all()))[:limit]
        if review_states:
            prefs = await self._get_user_review_preferences(user_id)
            active_cap = self._review_depth_cap(getattr(prefs, "review_depth_preset", None))
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

            due_items: list[dict[str, Any]] = []
            for index, state in enumerate(review_states):
                should_hydrate = hydrate_limit is None or index < hydrate_limit
                if state.entry_type == "word":
                    word = words_by_id.get(state.entry_id)
                    if word is None:
                        continue
                    meanings = meanings_by_word_id.get(word.id, [])
                    if not meanings:
                        continue
                    if state.target_type == "meaning" and state.target_id is not None:
                        meaning = next((item for item in meanings if item.id == state.target_id), None)
                        active_meanings = [
                            item
                            for item in meanings[: max(1, min(len(meanings), active_cap))]
                        ]
                        if meaning is not None and meaning not in active_meanings:
                            active_meanings.append(meaning)
                    else:
                        active_meanings = meanings[: max(1, min(len(meanings), active_cap))]
                        target_index = self._select_active_target_index(
                            total_targets=len(active_meanings),
                            active_cap=active_cap,
                            success_streak=int(state.success_streak or 0),
                            lapse_count=int(state.lapse_count or 0),
                            entry_type="word",
                            is_fragile=bool(state.is_fragile),
                        )
                        meaning = active_meanings[target_index]
                    if meaning is None:
                        continue
                    sentence = meaning_sentence_map.get(meaning.id)
                    review_mode = None
                    prompt = None
                    detail = None
                    if should_hydrate:
                        review_mode = self._select_review_mode(
                            item=state,
                            word=word.word,
                            index=index,
                            sentence=sentence,
                            allow_confidence=bool(getattr(prefs, "enable_confidence_check", True)),
                        )
                        prompt = await self._build_card_prompt(
                            review_mode=review_mode,
                            source_text=self._normalize_prompt_text(word.word) or "Unavailable",
                            definition=self._normalize_prompt_text(meaning.definition) or "No definition available.",
                            sentence=sentence,
                            is_phrase_entry=False,
                            distractor_seed=str(meaning.id),
                            meaning_id=meaning.id,
                            index=index,
                            alternative_definitions=[
                                self._normalize_prompt_text(item.definition) or "No definition available."
                                for item in active_meanings
                                if item.id != meaning.id
                            ],
                            user_id=user_id,
                            source_entry_id=word.id,
                            source_entry_type="word",
                            queue_item_id=state.id,
                            previous_prompt_type=state.last_prompt_type,
                        )
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
                            "target_type": state.target_type or "meaning",
                            "target_id": str(state.target_id or meaning.id),
                            "next_review": state.next_due_at,
                            "review_mode": review_mode,
                            "source_entry_type": "word",
                            "source_entry_id": str(word.id),
                            "prompt": prompt,
                            "detail": detail,
                            "schedule_options": self._build_schedule_options(int(round(state.stability or 0))),
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
                if state.target_type == "phrase_sense" and state.target_id is not None:
                    sense = next((item for item in senses if item.id == state.target_id), None)
                    active_senses = [
                        item for item in senses[: max(1, min(len(senses), active_cap))]
                    ]
                    if sense is not None and sense not in active_senses:
                        active_senses.append(sense)
                else:
                    active_senses = senses[: max(1, min(len(senses), active_cap))]
                    target_index = self._select_active_target_index(
                        total_targets=len(active_senses),
                        active_cap=active_cap,
                        success_streak=int(state.success_streak or 0),
                        lapse_count=int(state.lapse_count or 0),
                        entry_type="phrase",
                        is_fragile=bool(state.is_fragile),
                    )
                    sense = active_senses[target_index]
                if sense is None:
                    continue
                sentence = sense_sentence_map.get(sense.id)
                review_mode = None
                prompt = None
                detail = None
                if should_hydrate:
                    review_mode = self._select_review_mode(
                        item=state,
                        word=phrase.phrase_text,
                        index=index,
                        sentence=sentence,
                        allow_confidence=bool(getattr(prefs, "enable_confidence_check", True)),
                    )
                    prompt = await self._build_card_prompt(
                        review_mode=review_mode,
                        source_text=self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
                        definition=self._normalize_prompt_text(sense.definition) or "No definition available.",
                        sentence=sentence,
                        is_phrase_entry=True,
                        distractor_seed=str(sense.id),
                        meaning_id=sense.id,
                        index=index,
                        alternative_definitions=[
                            self._normalize_prompt_text(item.definition) or "No definition available."
                            for item in active_senses
                            if item.id != sense.id
                        ],
                        user_id=user_id,
                        source_entry_id=phrase.id,
                        source_entry_type="phrase",
                        queue_item_id=state.id,
                        previous_prompt_type=state.last_prompt_type,
                    )
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
                        "target_type": state.target_type or "phrase_sense",
                        "target_id": str(state.target_id or sense.id),
                        "next_review": state.next_due_at,
                        "review_mode": review_mode,
                        "source_entry_type": "phrase",
                        "source_entry_id": str(phrase.id),
                        "prompt": prompt,
                        "detail": detail,
                        "schedule_options": self._build_schedule_options(int(round(state.stability or 0))),
                        "source_word_id": None,
                        "source_meaning_id": str(sense.id),
                    }
                )

            if due_items:
                return due_items

        if self.uses_legacy_queue:
            query = (
                select(ReviewCard, Word.word, Meaning.definition)
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .join(Meaning, ReviewCard.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .where(ReviewSession.user_id == user_id)
                .where(
                    ReviewCard.id == item_id
                    if item_id is not None
                    else ((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
                )
                .order_by(ReviewCard.next_review.asc().nullsfirst())
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()
        elif hasattr(self.queue_model, "next_review"):
            query = (
                select(self.queue_model, Word.word, Meaning.definition)
                .join(Meaning, self.queue_model.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .where(self.queue_model.user_id == user_id)
                .where(
                    self.queue_model.id == item_id
                    if item_id is not None
                    else (
                        (self.queue_model.next_review.is_(None))
                        | (self.queue_model.next_review <= now)
                    )
                )
                .order_by(self.queue_model.next_review.asc().nullsfirst())
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()
        elif self._history_supports_schedule():
            (
                latest_history_subquery,
                latest_history,
                next_review_expr,
                due_condition,
            ) = self._build_history_due_query(user_id=user_id, now=now)

            query = (
                select(self.queue_model, Word.word, Meaning.definition, next_review_expr)
                .join(Meaning, self.queue_model.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .outerjoin(
                    latest_history_subquery,
                    latest_history_subquery.c.meaning_id == self.queue_model.meaning_id,
                )
                .outerjoin(
                    latest_history,
                    and_(
                        latest_history.meaning_id == latest_history_subquery.c.meaning_id,
                        latest_history.created_at
                        == latest_history_subquery.c.latest_created_at,
                        latest_history.user_id == user_id,
                    ),
                )
                .where(self.queue_model.user_id == user_id)
                .where(self.queue_model.id == item_id if item_id is not None else due_condition)
                .order_by(next_review_expr.asc().nullsfirst(), self.queue_model.created_at.asc())
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()
        else:
            query = (
                select(self.queue_model, Word.word, Meaning.definition)
                .join(Meaning, self.queue_model.meaning_id == Meaning.id)
                .join(Word, Meaning.word_id == Word.id)
                .where(self.queue_model.user_id == user_id)
                .where(self.queue_model.id == item_id if item_id is not None else literal(True))
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()

        due_items: list[dict[str, Any]] = []
        prefs = await self._get_user_review_preferences(user_id)
        allow_confidence = bool(getattr(prefs, "enable_confidence_check", True))
        for row in rows:
            should_hydrate = hydrate_limit is None or len(due_items) < hydrate_limit
            if len(row) == 4:
                item, word, definition, next_review = row
            else:
                item, word, definition = row
                next_review = getattr(item, "next_review", None)

            if next_review is not None:
                setattr(item, "next_review", next_review)

            meaning_id = getattr(item, "meaning_id", None)
            source_word_id = getattr(item, "word_id", None)
            source_sentence = None
            review_mode = None
            prompt = None
            detail = None
            if should_hydrate:
                if meaning_id is not None:
                    source_sentence = await self._fetch_first_meaning_sentence(meaning_id)
                review_mode = self._select_review_mode(
                    item=item,
                    word=self._normalize_prompt_text(word),
                    index=len(due_items),
                    sentence=source_sentence,
                    allow_confidence=allow_confidence,
                )

                prompt = await self._build_card_prompt(
                    review_mode=review_mode,
                    source_text=self._normalize_prompt_text(word) or "Unavailable",
                    definition=self._normalize_prompt_text(definition) or "No definition available.",
                    sentence=source_sentence,
                    is_phrase_entry=False,
                    distractor_seed=str(getattr(item, "meaning_id", "")),
                    meaning_id=meaning_id or uuid.uuid4(),
                    index=len(due_items),
                    user_id=user_id,
                    source_entry_id=source_word_id,
                    source_entry_type="word",
                    queue_item_id=getattr(item, "id", None),
                    previous_prompt_type=getattr(item, "last_prompt_type", None),
                )
                if source_word_id is not None:
                    detail = await self._build_detail_payload_for_word_id(
                        user_id=user_id,
                        word_id=source_word_id,
                    )

            due_items.append(
                {
                    "id": item.id,
                    "item": item,
                    "word": word,
                    "definition": definition,
                    "target_type": "meaning",
                    "target_id": str(meaning_id) if meaning_id else None,
                    "next_review": next_review,
                    "review_mode": review_mode,
                    "source_entry_type": "word",
                    "source_entry_id": str(source_word_id) if source_word_id else None,
                    "prompt": prompt,
                    "detail": detail,
                    "schedule_options": self._build_schedule_options(
                        self._resolve_interval_days_or_zero(getattr(item, "interval_days", None))
                    ),
                    "source_word_id": str(source_word_id) if source_word_id else None,
                    "source_meaning_id": str(meaning_id) if meaning_id else None,
                }
            )

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

    async def _get_latest_history_for_meaning(
        self, user_id: uuid.UUID, meaning_id: uuid.UUID
    ) -> Any | None:
        if self.history_model is None:
            return None
        if not hasattr(self.history_model, "meaning_id"):
            return None
        if not hasattr(self.history_model, "user_id"):
            return None
        if not hasattr(self.history_model, "created_at"):
            return None

        result = await self.db.execute(
            select(self.history_model)
            .where(
                self.history_model.user_id == user_id,
                self.history_model.meaning_id == meaning_id,
            )
            .order_by(self.history_model.created_at.desc())
            .limit(1)
        )
        return result.scalars().first()

    async def _build_learning_cards_for_word(
        self,
        user_id: uuid.UUID,
        word: Word,
        meanings: list[Meaning],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any], EntryReviewState | None]:
        prefs = await self._get_user_review_preferences(user_id)
        active_cap = self._review_depth_cap(getattr(prefs, "review_depth_preset", None))
        active_meanings = meanings[: max(1, min(len(meanings), active_cap))]
        accent = await self._get_user_accent_preference(user_id)
        meaning_sentence_map = await self._fetch_first_meaning_sentence_map(
            [meaning.id for meaning in active_meanings]
        )
        remembered_count_map = await self._fetch_history_count_by_word_id(
            user_id=user_id,
            meanings_by_word_id={word.id: meanings},
        )
        cards: list[dict[str, Any]] = []
        meaning_ids: list[str] = []
        queue_item_ids: list[str] = []
        detail = await self._build_word_detail_payload(
            user_id=user_id,
            word=word,
            meanings=meanings,
            example_by_meaning_id=meaning_sentence_map,
            remembered_count=remembered_count_map.get(word.id, 0),
            accent=accent,
        )
        first_target_state: EntryReviewState | None = None

        source_text = self._normalize_prompt_text(word.word) or "Unavailable"
        alternative_definitions = [
            self._normalize_prompt_text(meaning.definition) or "No definition available."
            for meaning in meanings
        ]
        for index, meaning in enumerate(active_meanings):
            sentence = meaning_sentence_map.get(meaning.id)
            target_state = await self._ensure_target_review_state(
                user_id=user_id,
                target_type="meaning",
                target_id=meaning.id,
                entry_type="word",
                entry_id=word.id,
            )
            if first_target_state is None:
                first_target_state = target_state
            queue_item_id = str(target_state.id)
            review_mode = self._select_review_mode(
                item=target_state,
                word=source_text,
                index=index,
                sentence=sentence,
                allow_confidence=bool(getattr(prefs, "enable_confidence_check", True)),
            )
            prompt = await self._build_card_prompt(
                review_mode=review_mode,
                source_text=source_text,
                definition=self._normalize_prompt_text(meaning.definition) or "No definition available.",
                sentence=sentence,
                is_phrase_entry=False,
                distractor_seed=str(meaning.id),
                meaning_id=meaning.id,
                index=index,
                alternative_definitions=[
                    definition
                    for definition in alternative_definitions[: len(active_meanings)]
                    if definition != (self._normalize_prompt_text(meaning.definition) or "No definition available.")
                ],
                user_id=user_id,
                source_entry_id=word.id,
                source_entry_type="word",
                queue_item_id=target_state.id,
                previous_prompt_type=getattr(target_state, "last_prompt_type", None),
                active_target_count=len(active_meanings),
            )

            cards.append(
                {
                    "queue_item_id": queue_item_id,
                    "meaning_id": str(meaning.id),
                    "word": source_text,
                    "definition": self._normalize_prompt_text(meaning.definition)
                    or "No definition available.",
                    "prompt": prompt,
                    "detail": detail,
                }
            )
            meaning_ids.append(str(meaning.id))
            queue_item_ids.append(queue_item_id)

        return cards, meaning_ids, queue_item_ids, detail, first_target_state

    async def _build_learning_cards_for_phrase(
        self,
        user_id: uuid.UUID,
        phrase: PhraseEntry,
        senses: list[PhraseSense],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any], EntryReviewState | None]:
        prefs = await self._get_user_review_preferences(user_id)
        active_cap = self._review_depth_cap(getattr(prefs, "review_depth_preset", None))
        active_senses = senses[: max(1, min(len(senses), active_cap))]
        sense_sentence_map = await self._fetch_first_sense_sentence_map(
            [sense.id for sense in active_senses]
        )
        cards: list[dict[str, Any]] = []
        meaning_ids: list[str] = []
        queue_item_ids: list[str] = []
        source_text = self._normalize_prompt_text(phrase.phrase_text) or "Unavailable"
        alternative_definitions = [
            self._normalize_prompt_text(sense.definition) or "No definition available."
            for sense in active_senses
        ]
        detail = await self._build_phrase_detail_payload(
            user_id=user_id,
            phrase=phrase,
            senses=senses,
            example_by_sense_id=sense_sentence_map,
        )
        first_target_state: EntryReviewState | None = None

        for index, sense in enumerate(active_senses):
            sentence = sense_sentence_map.get(sense.id)
            target_state = await self._ensure_target_review_state(
                user_id=user_id,
                target_type="phrase_sense",
                target_id=sense.id,
                entry_type="phrase",
                entry_id=phrase.id,
            )
            if first_target_state is None:
                first_target_state = target_state
            review_mode = self._select_review_mode(
                item=target_state,
                word=source_text,
                index=index,
                sentence=sentence,
                allow_confidence=bool(getattr(prefs, "enable_confidence_check", True)),
            )
            prompt = await self._build_card_prompt(
                review_mode=review_mode,
                source_text=source_text,
                definition=self._normalize_prompt_text(sense.definition) or "No definition available.",
                sentence=sentence,
                is_phrase_entry=True,
                distractor_seed=str(sense.id),
                meaning_id=sense.id,
                index=index,
                alternative_definitions=[
                    definition
                    for definition in alternative_definitions
                    if definition != (self._normalize_prompt_text(sense.definition) or "No definition available.")
                ],
                user_id=user_id,
                source_entry_id=phrase.id,
                source_entry_type="phrase",
                queue_item_id=target_state.id,
                previous_prompt_type=getattr(target_state, "last_prompt_type", None),
                active_target_count=len(active_senses),
            )

            cards.append(
                {
                    "queue_item_id": str(target_state.id),
                    "meaning_id": str(sense.id),
                    "word": source_text,
                    "definition": self._normalize_prompt_text(sense.definition)
                    or "No definition available.",
                    "prompt": prompt,
                    "detail": detail,
                }
            )
            meaning_ids.append(str(sense.id))
            queue_item_ids.append(str(target_state.id))

        return cards, meaning_ids, queue_item_ids, detail, first_target_state

    async def start_learning_entry(
        self,
        user_id: uuid.UUID,
        entry_type: str,
        entry_id: uuid.UUID,
    ) -> dict[str, Any]:
        normalized_entry_type = self._normalize_entry_type(entry_type)

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

            return {
                "entry_type": "word",
                "entry_id": str(word.id),
                "entry_word": self._normalize_prompt_text(word.word) or "Unavailable",
                "meaning_ids": meaning_ids,
                "queue_item_ids": queue_item_ids,
                "cards": cards,
                "detail": detail,
                "schedule_options": self._build_schedule_options(
                    int(round((first_target_state.stability if first_target_state is not None else 0) or 0))
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

        return {
            "entry_type": "phrase",
            "entry_id": str(phrase.id),
            "entry_word": self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
            "meaning_ids": meaning_ids,
            "queue_item_ids": queue_item_ids,
            "cards": cards,
            "detail": detail,
            "schedule_options": self._build_schedule_options(
                int(round((first_target_state.stability if first_target_state is not None else 0) or 0))
            ),
            "requires_lookup_hint": False,
        }

    async def submit_queue_review(
        self,
        item_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
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
    ) -> None:
        return apply_entry_state_review_result_impl(
            self,
            entry_state=entry_state,
            review_result=review_result,
            resolved_outcome=resolved_outcome,
            prompt=prompt,
            resolved_interval_days=resolved_interval_days,
            resolved_next_review=resolved_next_review,
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

    async def _submit_legacy_queue_review(
        self,
        *,
        item: Any,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
        card_type: str | None,
        review_mode: str | None,
        outcome: str | None,
        selected_option_id: str | None,
        typed_answer: str | None,
        prompt: dict[str, Any] | None,
        schedule_override: str | None,
    ) -> Any:
        return await submit_legacy_queue_review_impl(
            self,
            item=item,
            quality=quality,
            time_spent_ms=time_spent_ms,
            user_id=user_id,
            card_type=card_type,
            review_mode=review_mode,
            outcome=outcome,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
            prompt=prompt,
            schedule_override=schedule_override,
        )

    def _build_history_record(
        self,
        item: Any,
        user_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        card_type: str,
        previous_ease_factor: float,
        previous_interval_days: int,
        previous_repetitions: int,
    ) -> Any | None:
        if self.history_model is None:
            return None

        payload = {
            "user_id": user_id,
            "queue_item_id": getattr(item, "id", None),
            "item_id": getattr(item, "id", None),
            "review_card_id": getattr(item, "id", None),
            "meaning_id": getattr(item, "meaning_id", None),
            "quality": quality,
            "quality_rating": quality,
            "time_spent_ms": time_spent_ms,
            "card_type": card_type,
            "reviewed_at": datetime.now(timezone.utc),
            "is_correct": quality >= 3,
            "ease_factor_before": previous_ease_factor,
            "ease_factor_after": getattr(item, "ease_factor", None),
            "ease_factor": getattr(item, "ease_factor", None),
            "interval_days_before": previous_interval_days,
            "interval_days_after": getattr(item, "interval_days", None),
            "interval_days": getattr(item, "interval_days", None),
            "repetitions_before": previous_repetitions,
            "repetitions_after": getattr(item, "repetitions", None),
            "repetitions": getattr(item, "repetitions", None),
            "next_review": getattr(item, "next_review", None),
        }
        return self._build_model_instance(self.history_model, payload)

    async def get_queue_stats(self, user_id: uuid.UUID) -> dict[str, Any]:
        """Get queue totals, due counts, and aggregate performance stats."""
        cached = self._get_cached_queue_stats(user_id)
        if cached is not None:
            return cached
        now = datetime.now(timezone.utc)

        if self.uses_legacy_queue:
            total_result = await self.db.execute(
                select(func.count(ReviewCard.id))
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .where(ReviewSession.user_id == user_id)
            )
            total_items = int(total_result.scalar_one() or 0)

            due_result = await self.db.execute(
                select(func.count(ReviewCard.id))
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .where(ReviewSession.user_id == user_id)
                .where((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
            )
            due_items = int(due_result.scalar_one() or 0)

            aggregate_result = await self.db.execute(
                select(
                    func.count(ReviewCard.id).filter(ReviewCard.quality_rating.is_not(None)),
                    func.count(ReviewCard.id).filter(ReviewCard.quality_rating >= 3),
                )
                .join(ReviewSession, ReviewCard.session_id == ReviewSession.id)
                .where(ReviewSession.user_id == user_id)
            )
            review_count, correct_count = aggregate_result.one()
        else:
            total_result = await self.db.execute(
                select(func.count(self.queue_model.id)).where(
                    self.queue_model.user_id == user_id
                )
            )
            total_items = int(total_result.scalar_one() or 0)

            if hasattr(self.queue_model, "next_review"):
                due_result = await self.db.execute(
                    select(func.count(self.queue_model.id))
                    .where(self.queue_model.user_id == user_id)
                    .where(
                        (self.queue_model.next_review.is_(None))
                        | (self.queue_model.next_review <= now)
                    )
                )
            elif self._history_supports_schedule():
                (
                    latest_history_subquery,
                    latest_history,
                    next_review_expr,
                    due_condition,
                ) = self._build_history_due_query(user_id=user_id, now=now)

                due_result = await self.db.execute(
                    select(func.count(self.queue_model.id))
                    .outerjoin(
                        latest_history_subquery,
                        latest_history_subquery.c.meaning_id == self.queue_model.meaning_id,
                    )
                    .outerjoin(
                        latest_history,
                        and_(
                            latest_history.meaning_id == latest_history_subquery.c.meaning_id,
                            latest_history.created_at
                            == latest_history_subquery.c.latest_created_at,
                            latest_history.user_id == user_id,
                        ),
                    )
                    .where(self.queue_model.user_id == user_id)
                    .where(due_condition)
                )
            else:
                due_result = await self.db.execute(
                    select(func.count(self.queue_model.id)).where(
                        self.queue_model.user_id == user_id
                    )
                )

            due_items = int(due_result.scalar_one() or 0)

            if self.history_model is not None and hasattr(self.history_model, "user_id"):
                if hasattr(self.history_model, "quality_rating"):
                    aggregate_result = await self.db.execute(
                        select(
                            func.count(self.history_model.id),
                            func.count(self.history_model.id).filter(
                                self.history_model.quality_rating >= 3
                            ),
                        ).where(self.history_model.user_id == user_id)
                    )
                elif hasattr(self.history_model, "quality"):
                    aggregate_result = await self.db.execute(
                        select(
                            func.count(self.history_model.id),
                            func.count(self.history_model.id).filter(
                                self.history_model.quality >= 3
                            ),
                        ).where(self.history_model.user_id == user_id)
                    )
                else:
                    aggregate_result = await self.db.execute(select(literal(0), literal(0)))
            elif hasattr(self.queue_model, "review_count") and hasattr(
                self.queue_model, "correct_count"
            ):
                aggregate_result = await self.db.execute(
                    select(
                        func.coalesce(func.sum(self.queue_model.review_count), 0),
                        func.coalesce(func.sum(self.queue_model.correct_count), 0),
                    ).where(self.queue_model.user_id == user_id)
                )
            elif hasattr(self.queue_model, "review_count"):
                aggregate_result = await self.db.execute(
                    select(func.coalesce(func.sum(self.queue_model.review_count), 0), literal(0))
                    .where(self.queue_model.user_id == user_id)
                )
            else:
                aggregate_result = await self.db.execute(select(literal(0), literal(0)))

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

    async def submit_review(
        self,
        card_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
    ) -> ReviewCard:
        """Submit a review for a card and update SM-2 parameters."""
        result = await self.db.execute(
            select(ReviewCard)
            .join(ReviewSession)
            .where(ReviewCard.id == card_id, ReviewSession.user_id == user_id)
        )
        card = result.scalar_one_or_none()
        if card is None:
            raise ValueError(f"Review card {card_id} not found")

        previous_ease = float(card.ease_factor or 2.5)
        previous_interval = int(card.interval_days or 0)
        previous_repetitions = int(card.repetitions or 0)

        if quality >= 3:
            if previous_repetitions == 0:
                next_interval = 1
            elif previous_repetitions == 1:
                next_interval = 6
            else:
                next_interval = max(1, round(previous_interval * previous_ease))
            next_repetitions = previous_repetitions + 1
            next_ease = previous_ease + (
                0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)
            )
        else:
            next_interval = 1
            next_repetitions = 0
            next_ease = max(1.3, previous_ease - 0.2)

        card.quality_rating = quality
        card.time_spent_ms = time_spent_ms
        card.ease_factor = max(1.3, round(next_ease, 2))
        card.interval_days = next_interval
        card.repetitions = next_repetitions
        card.next_review = datetime.now(timezone.utc) + timedelta(days=next_interval)

        await self.db.commit()
        self._invalidate_queue_stats_cache(user_id)

        logger.info(
            "Review submitted",
            card_id=str(card_id),
            quality=quality,
            new_interval=next_interval,
            new_ease_factor=card.ease_factor,
        )

        return card

    async def complete_session(
        self, session_id: uuid.UUID, user_id: uuid.UUID
    ) -> ReviewSession:
        """Mark a review session as completed."""
        result = await self.db.execute(
            select(ReviewSession).where(
                ReviewSession.id == session_id, ReviewSession.user_id == user_id
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise ValueError(f"Review session {session_id} not found")

        session.completed_at = datetime.now(timezone.utc)
        await self.db.commit()

        logger.info("Review session completed", session_id=str(session_id))
        return session
