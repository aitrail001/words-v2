import uuid
import re
import random
from datetime import datetime, timezone, timedelta
from typing import Any

from sqlalchemy import and_, func, literal, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.core.logging import get_logger
from app.models import review as review_models
from app.models.meaning_example import MeaningExample
from app.models.meaning import Meaning
from app.models.entry_review import EntryReviewEvent, EntryReviewState
from app.models.review import ReviewCard, ReviewSession
from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.word import Word
from app.spaced_repetition import calculate_next_review

logger = get_logger(__name__)


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

    @staticmethod
    def _normalize_prompt_text(value: str | None) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        trimmed = value.strip()
        return trimmed or None

    @staticmethod
    def _prompt_value_for_options(value: str | None) -> str:
        normalized = (value or "").strip()
        return normalized if normalized else "Unavailable"

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

        while len(unique_values) < len(option_labels):
            unique_values.append(f"Option {len(unique_values) + 1}")

        rng = random.Random((correct or "").__hash__())
        rng.shuffle(unique_values)
        unique_values = unique_values[: len(option_labels)]

        return [
            {
                "option_id": label,
                "label": value,
                "is_correct": value == correct,
            }
            for label, value in zip(option_labels, unique_values)
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
    ) -> dict[str, Any]:
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
            "audio_state": audio_state,
        }

    async def _fetch_word_distractors(self, correct_word: str, limit: int = 3) -> list[str]:
        if not correct_word:
            return []

        result = await self.db.execute(
            select(Word.word)
            .where(func.lower(Word.word) != correct_word.lower())
            .order_by(func.random())
            .limit(limit + 5)
        )

        candidates = [word for word in result.scalars().all() if self._normalize_prompt_text(word)]
        return candidates[:limit]

    async def _fetch_definition_distractors(
        self,
        correct_meaning_id: uuid.UUID,
        limit: int = 3,
    ) -> list[str]:
        result = await self.db.execute(
            select(Meaning.definition)
            .where(Meaning.id != correct_meaning_id)
            .order_by(func.random())
            .limit(limit + 5)
        )
        candidates = [definition for definition in result.scalars().all() if self._normalize_prompt_text(definition)]
        return candidates[:limit]

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
            .order_by(func.random())
            .limit(limit + 5)
        )
        candidates = [
            phrase
            for phrase in result.scalars().all()
            if self._normalize_prompt_text(phrase)
        ]
        return candidates[:limit]

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

    async def _fetch_first_sense_sentence(self, sense_id: uuid.UUID) -> str | None:
        result = await self.db.execute(
            select(PhraseSenseExample.sentence)
            .where(PhraseSenseExample.phrase_sense_id == sense_id)
            .order_by(PhraseSenseExample.order_index.asc())
            .limit(1)
        )
        return self._normalize_prompt_text(result.scalar_one_or_none())

    async def _build_word_detail_payload(
        self,
        *,
        user_id: uuid.UUID,
        word: Word,
        meanings: list[Meaning],
    ) -> dict[str, Any]:
        primary = meanings[0] if meanings else None
        meaning_items: list[dict[str, Any]] = []
        for meaning in meanings[:5]:
            meaning_items.append(
                {
                    "id": str(meaning.id),
                    "definition": self._normalize_prompt_text(meaning.definition)
                    or "No definition available.",
                    "example": await self._fetch_first_meaning_sentence(meaning.id),
                    "part_of_speech": self._normalize_prompt_text(meaning.part_of_speech),
                }
            )

        history_count = 0
        if self.history_model is not None and hasattr(self.history_model, "user_id"):
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
            "pronunciation": self._normalize_prompt_text(
                getattr(word, "phonetic", None) or getattr(word, "phonetics", None)
            ),
            "part_of_speech": primary.part_of_speech if primary is not None else None,
            "primary_definition": primary.definition if primary is not None else None,
            "primary_example": meaning_items[0]["example"] if meaning_items else None,
            "meaning_count": len(meanings),
            "remembered_count": history_count,
            "pro_tip": primary.usage_note if primary is not None else None,
            "compare_with": [],
            "meanings": meaning_items,
            "audio_state": "not_available",
        }

    async def _build_phrase_detail_payload(
        self,
        *,
        user_id: uuid.UUID,
        phrase: PhraseEntry,
        senses: list[PhraseSense],
    ) -> dict[str, Any]:
        primary = senses[0] if senses else None
        meaning_items: list[dict[str, Any]] = []
        for sense in senses[:5]:
            meaning_items.append(
                {
                    "id": str(sense.id),
                    "definition": self._normalize_prompt_text(sense.definition)
                    or "No definition available.",
                    "example": await self._fetch_first_sense_sentence(sense.id),
                    "part_of_speech": self._normalize_prompt_text(sense.part_of_speech),
                }
            )

        return {
            "entry_type": "phrase",
            "entry_id": str(phrase.id),
            "display_text": self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
            "pronunciation": None,
            "part_of_speech": primary.part_of_speech if primary is not None else None,
            "primary_definition": primary.definition if primary is not None else None,
            "primary_example": meaning_items[0]["example"] if meaning_items else None,
            "meaning_count": len(senses),
            "remembered_count": 0,
            "pro_tip": primary.usage_note if primary is not None else None,
            "compare_with": [],
            "meanings": meaning_items,
            "audio_state": "not_available",
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

    async def _record_entry_review_event(
        self,
        *,
        user_id: uuid.UUID,
        state: EntryReviewState,
        prompt_type: str,
        outcome: str,
        selected_option_id: str | None,
        typed_answer: str | None,
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
            entry_type=state.entry_type,
            entry_id=state.entry_id,
            prompt_type=prompt_type,
            prompt_family=prompt_family,
            outcome=outcome,
            response_input_mode=response_input_mode,
            response_value=self._normalize_prompt_text(typed_answer) or selected_option_id,
            used_audio_placeholder=((prompt or {}).get("audio_state") == "placeholder"),
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
    ) -> str:
        if not word:
            return self.REVIEW_MODE_CONFIDENCE
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

    @staticmethod
    def _is_correct_mcq_answer(
        prompt: dict[str, Any] | None,
        selected_option_id: str | None,
        typed_answer: str | None,
    ) -> bool:
        if prompt is None:
            return False

        selected = selected_option_id
        if selected is None and typed_answer:
            normalized_typed = typed_answer.strip().lower()
            expected_input = (prompt.get("expected_input") or "").strip().lower()
            return bool(normalized_typed and expected_input and normalized_typed == expected_input)

        if selected is None:
            return False

        for option in prompt.get("options") or []:
            if str(option.get("option_id")) == str(selected):
                return bool(option.get("is_correct"))

        return False

    @staticmethod
    def _resolve_interval_days_or_zero(value: int | None) -> int:
        return int(value or 0)

    def _select_prompt_type(self, prompt_candidates: list[str], index: int = 0) -> str:
        if not prompt_candidates:
            return self.PROMPT_TYPE_DEFINITION_TO_ENTRY
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
    ) -> dict[str, Any]:
        available_prompt_types: list[str] = []
        if sentence:
            available_prompt_types.extend(
                [
                    self.PROMPT_TYPE_SENTENCE_GAP,
                    self.PROMPT_TYPE_COLLOCATION_CHECK,
                    self.PROMPT_TYPE_SITUATION_MATCHING,
                ]
            )
        if alternative_definitions and len(alternative_definitions) >= 2:
            available_prompt_types.append(self.PROMPT_TYPE_MEANING_DISCRIMINATION)
        if review_mode == self.REVIEW_MODE_MCQ:
            available_prompt_types.append(self.PROMPT_TYPE_TYPED_RECALL)
            available_prompt_types.append(self.PROMPT_TYPE_SPEAK_RECALL)
        available_prompt_types.extend(
            [
                self.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                self.PROMPT_TYPE_ENTRY_TO_DEFINITION,
                self.PROMPT_TYPE_AUDIO_TO_DEFINITION,
            ]
        )

        prompt_type = self._select_prompt_type(available_prompt_types, index=index)
        target_is_word = prompt_type in {
            self.PROMPT_TYPE_DEFINITION_TO_ENTRY,
            self.PROMPT_TYPE_SENTENCE_GAP,
            self.PROMPT_TYPE_COLLOCATION_CHECK,
            self.PROMPT_TYPE_SITUATION_MATCHING,
        }

        distractors: list[str] = []
        if prompt_type in {
            self.PROMPT_TYPE_DEFINITION_TO_ENTRY,
            self.PROMPT_TYPE_SENTENCE_GAP,
            self.PROMPT_TYPE_COLLOCATION_CHECK,
            self.PROMPT_TYPE_SITUATION_MATCHING,
        }:
            if is_phrase_entry:
                distractors = await self._fetch_phrase_distractors(
                    correct_phrase=source_text,
                    limit=3,
                )
            else:
                distractors = await self._fetch_word_distractors(
                    correct_word=source_text,
                    limit=3,
                )
            if prompt_type in {self.PROMPT_TYPE_COLLOCATION_CHECK, self.PROMPT_TYPE_SITUATION_MATCHING}:
                distractors = self._rank_entry_distractors(
                    correct_text=source_text,
                    candidates=distractors,
                    contextual=True,
                )[:3]
        elif prompt_type in {
            self.PROMPT_TYPE_MEANING_DISCRIMINATION,
            self.PROMPT_TYPE_TYPED_RECALL,
            self.PROMPT_TYPE_SPEAK_RECALL,
        }:
            distractors = []
        else:
            distractors = await self._fetch_definition_distractors(
                correct_meaning_id=meaning_id,
                limit=3,
            )

        prompt = await self._build_mandated_prompt(
            review_mode=review_mode,
            prompt_type=prompt_type,
            word=source_text,
            definition=self._prompt_value_for_options(definition),
            target_is_word=target_is_word,
            distractors=distractors,
            sentence=self._prompt_value_for_options(sentence),
            alternative_definitions=alternative_definitions,
        )
        if prompt_type == self.PROMPT_TYPE_SENTENCE_GAP:
            prompt["sentence_masked"] = self._mask_sentence(
                self._prompt_value_for_options(sentence),
                self._prompt_value_for_options(source_text),
            )
        elif prompt_type == self.PROMPT_TYPE_COLLOCATION_CHECK:
            prompt["sentence_masked"] = self._build_collocation_fragment(
                self._prompt_value_for_options(sentence),
                self._prompt_value_for_options(source_text),
            )

        prompt["source_seed"] = self._normalize_prompt_text(distractor_seed) or "review"
        return prompt

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
        self, user_id: uuid.UUID, limit: int = 20
    ) -> list[dict[str, Any]]:
        """Get due queue items scoped to a user including prompt metadata."""
        now = datetime.now(timezone.utc)
        state_result = await self.db.execute(
            select(EntryReviewState)
            .where(EntryReviewState.user_id == user_id)
            .where(EntryReviewState.is_suspended.is_(False))
            .where(
                (EntryReviewState.recheck_due_at.is_not(None) & (EntryReviewState.recheck_due_at <= now))
                | (EntryReviewState.next_due_at.is_(None))
                | (EntryReviewState.next_due_at <= now)
            )
            .order_by(
                EntryReviewState.recheck_due_at.asc().nullsfirst(),
                EntryReviewState.next_due_at.asc().nullsfirst(),
                EntryReviewState.created_at.asc(),
            )
            .limit(limit)
        )
        review_states = state_result.scalars().all()
        if review_states:
            due_items: list[dict[str, Any]] = []
            for index, state in enumerate(review_states):
                if state.entry_type == "word":
                    word_result = await self.db.execute(select(Word).where(Word.id == state.entry_id))
                    word = word_result.scalar_one_or_none()
                    if word is None:
                        continue
                    meanings_result = await self.db.execute(
                        select(Meaning).where(Meaning.word_id == word.id).order_by(Meaning.order_index.asc())
                    )
                    meanings = meanings_result.scalars().all()
                    if not meanings:
                        continue
                    meaning = meanings[0]
                    sentence = await self._fetch_first_meaning_sentence(meaning.id)
                    review_mode = self._select_review_mode(
                        item=state,
                        word=word.word,
                        index=index,
                        sentence=sentence,
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
                            for item in meanings
                            if item.id != meaning.id
                        ],
                    )
                    detail = await self._build_word_detail_payload(
                        user_id=user_id,
                        word=word,
                        meanings=meanings,
                    )
                    state.meaning_id = meaning.id
                    due_items.append(
                        {
                            "id": state.id,
                            "item": state,
                            "word": word.word,
                            "definition": meaning.definition,
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

                phrase_result = await self.db.execute(
                    select(PhraseEntry).where(PhraseEntry.id == state.entry_id)
                )
                phrase = phrase_result.scalar_one_or_none()
                if phrase is None:
                    continue
                senses_result = await self.db.execute(
                    select(PhraseSense)
                    .where(PhraseSense.phrase_entry_id == phrase.id)
                    .order_by(PhraseSense.order_index.asc())
                )
                senses = senses_result.scalars().all()
                if not senses:
                    continue
                sense = senses[0]
                sentence = await self._fetch_first_sense_sentence(sense.id)
                review_mode = self._select_review_mode(
                    item=state,
                    word=phrase.phrase_text,
                    index=index,
                    sentence=sentence,
                )
                prompt = await self._build_card_prompt(
                    review_mode=review_mode,
                    source_text=self._normalize_prompt_text(phrase.phrase_text) or "Unavailable",
                    definition=self._normalize_prompt_text(sense.definition) or "No definition available.",
                    sentence=sentence,
                    is_phrase_entry=True,
                    distractor_seed=str(sense.id),
                    meaning_id=uuid.uuid4(),
                    index=index,
                    alternative_definitions=[
                        self._normalize_prompt_text(item.definition) or "No definition available."
                        for item in senses
                        if item.id != sense.id
                    ],
                )
                detail = await self._build_phrase_detail_payload(
                    user_id=user_id,
                    phrase=phrase,
                    senses=senses,
                )
                state.meaning_id = sense.id
                due_items.append(
                    {
                        "id": state.id,
                        "item": state,
                        "word": phrase.phrase_text,
                        "definition": sense.definition,
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
                .where((ReviewCard.next_review.is_(None)) | (ReviewCard.next_review <= now))
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
                    (self.queue_model.next_review.is_(None))
                    | (self.queue_model.next_review <= now)
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
                .where(due_condition)
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
                .limit(limit)
            )
            result = await self.db.execute(query)
            rows = result.all()

        due_items: list[dict[str, Any]] = []
        for row in rows:
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
            if meaning_id is not None:
                source_sentence = await self._fetch_first_meaning_sentence(meaning_id)
            review_mode = self._select_review_mode(
                item=item,
                word=self._normalize_prompt_text(word),
                index=len(due_items),
                sentence=source_sentence,
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
            )
            detail = None
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
        )
        return result.scalar_one_or_none()

    async def _build_learning_cards_for_word(
        self,
        user_id: uuid.UUID,
        word: Word,
        meanings: list[Meaning],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        meaning_ids: list[str] = []
        queue_item_ids: list[str] = []
        detail = await self._build_word_detail_payload(user_id=user_id, word=word, meanings=meanings)

        source_text = self._normalize_prompt_text(word.word) or "Unavailable"
        alternative_definitions = [
            self._normalize_prompt_text(meaning.definition) or "No definition available."
            for meaning in meanings
        ]
        for index, meaning in enumerate(meanings):
            sentence = await self._fetch_first_meaning_sentence(meaning.id)
            queue_item = await self.add_to_queue(user_id=user_id, meaning_id=meaning.id)
            queue_item_id = str(queue_item.id)
            review_mode = self._select_review_mode(
                item=meaning,
                word=source_text,
                index=index,
                sentence=sentence,
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
                    for definition in alternative_definitions
                    if definition != (self._normalize_prompt_text(meaning.definition) or "No definition available.")
                ],
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

        return cards, meaning_ids, queue_item_ids, detail

    async def _build_learning_cards_for_phrase(
        self,
        user_id: uuid.UUID,
        entry_state_id: uuid.UUID,
        phrase: PhraseEntry,
        senses: list[PhraseSense],
    ) -> tuple[list[dict[str, Any]], list[str], list[str], dict[str, Any]]:
        cards: list[dict[str, Any]] = []
        meaning_ids: list[str] = []
        queue_item_ids: list[str] = []
        source_text = self._normalize_prompt_text(phrase.phrase_text) or "Unavailable"
        alternative_definitions = [
            self._normalize_prompt_text(sense.definition) or "No definition available."
            for sense in senses
        ]
        detail = await self._build_phrase_detail_payload(user_id=user_id, phrase=phrase, senses=senses)

        for index, sense in enumerate(senses):
            sentence = await self._fetch_first_sense_sentence(sense.id)
            review_mode = self._select_review_mode(
                item=sense,
                word=source_text,
                index=index,
                sentence=sentence,
            )
            prompt = await self._build_card_prompt(
                review_mode=review_mode,
                source_text=source_text,
                definition=self._normalize_prompt_text(sense.definition) or "No definition available.",
                sentence=sentence,
                is_phrase_entry=True,
                distractor_seed=str(sense.id),
                meaning_id=uuid.uuid4(),
                index=index,
                alternative_definitions=[
                    definition
                    for definition in alternative_definitions
                    if definition != (self._normalize_prompt_text(sense.definition) or "No definition available.")
                ],
            )

            cards.append(
                {
                    "queue_item_id": str(entry_state_id),
                    "meaning_id": str(sense.id),
                    "word": source_text,
                    "definition": self._normalize_prompt_text(sense.definition)
                    or "No definition available.",
                    "prompt": prompt,
                    "detail": detail,
                }
            )
            meaning_ids.append(str(sense.id))
            queue_item_ids.append(str(entry_state_id))

        return cards, meaning_ids, queue_item_ids, detail

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
            state = await self._ensure_entry_review_state(
                user_id=user_id,
                entry_type="word",
                entry_id=word.id,
            )

            meaning_result = await self.db.execute(
                select(Meaning).where(Meaning.word_id == word.id).order_by(Meaning.order_index.asc())
            )
            meanings = meaning_result.scalars().all()
            if not meanings:
                raise ValueError(f"Word {word.id} has no meanings to learn")

            cards, meaning_ids, queue_item_ids, detail = await self._build_learning_cards_for_word(
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
                "schedule_options": self._build_schedule_options(int(round(state.stability or 0))),
                "requires_lookup_hint": False,
            }

        result = await self.db.execute(select(PhraseEntry).where(PhraseEntry.id == entry_id))
        phrase = result.scalar_one_or_none()
        if phrase is None:
            raise ValueError(f"Phrase {entry_id} not found")
        state = await self._ensure_entry_review_state(
            user_id=user_id,
            entry_type="phrase",
            entry_id=phrase.id,
        )

        sense_result = await self.db.execute(
            select(PhraseSense)
            .where(PhraseSense.phrase_entry_id == phrase.id)
            .order_by(PhraseSense.order_index.asc())
        )
        senses = sense_result.scalars().all()
        if not senses:
            raise ValueError(f"Phrase {phrase.id} has no senses to learn")

        cards, meaning_ids, queue_item_ids, detail = await self._build_learning_cards_for_phrase(
            user_id=user_id,
            entry_state_id=state.id,
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
            "schedule_options": self._build_schedule_options(int(round(state.stability or 0))),
            "requires_lookup_hint": False,
        }

    async def submit_queue_review(
        self,
        item_id: uuid.UUID,
        quality: int,
        time_spent_ms: int,
        user_id: uuid.UUID,
        card_type: str | None = None,
        review_mode: str | None = None,
        outcome: str | None = None,
        selected_option_id: str | None = None,
        typed_answer: str | None = None,
        prompt: dict[str, Any] | None = None,
        schedule_override: str | None = None,
    ) -> Any:
        """Submit a queue review and update scheduling via entry-review semantics."""
        state_lookup = await self.db.execute(
            select(EntryReviewState).where(
                EntryReviewState.id == item_id,
                EntryReviewState.user_id == user_id,
            )
        )
        entry_state = state_lookup.scalar_one_or_none()
        if isinstance(entry_state, EntryReviewState):
            normalized_review_mode = self._normalize_review_mode(review_mode)
            resolved_outcome = self._derive_outcome(
                review_mode=normalized_review_mode,
                explicit_outcome=outcome,
                quality=quality,
                prompt=prompt,
                selected_option_id=selected_option_id,
                typed_answer=typed_answer,
            )
            review_result = calculate_next_review(
                outcome=resolved_outcome,
                prompt_type=(prompt or {}).get("prompt_type") or self.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                stability=float(entry_state.stability or 0.3),
                difficulty=float(entry_state.difficulty or 0.5),
            )
            scheduled_by = "manual_override" if schedule_override else "recommended"
            resolved_interval_days, resolved_next_review, _ = self._derive_interval_from_override(
                original_interval_days=review_result.interval_days,
                override_value=schedule_override,
                base_next_review=review_result.next_review,
            )

            entry_state.stability = max(0.15, float(resolved_interval_days or review_result.stability))
            entry_state.difficulty = review_result.difficulty
            entry_state.last_prompt_type = (prompt or {}).get("prompt_type")
            entry_state.last_outcome = resolved_outcome
            entry_state.is_fragile = review_result.is_fragile
            entry_state.last_reviewed_at = datetime.now(timezone.utc)
            entry_state.next_due_at = resolved_next_review
            entry_state.exposure_count = int(entry_state.exposure_count or 0) + 1
            if resolved_outcome in {"correct_tested", "remember"}:
                entry_state.success_streak = int(entry_state.success_streak or 0) + 1
                entry_state.times_remembered = int(entry_state.times_remembered or 0) + 1
                entry_state.relearning = False
                entry_state.relearning_trigger = None
                entry_state.recheck_due_at = None
            else:
                entry_state.success_streak = 0
                if resolved_outcome == "wrong":
                    entry_state.lapse_count = int(entry_state.lapse_count or 0) + 1
                entry_state.relearning = True
                entry_state.relearning_trigger = resolved_outcome
                entry_state.recheck_due_at = datetime.now(timezone.utc) + timedelta(minutes=10)

            if entry_state.entry_type == "word":
                detail = await self._build_detail_payload_for_word_id(
                    user_id=user_id,
                    word_id=entry_state.entry_id,
                )
            else:
                phrase_result = await self.db.execute(
                    select(PhraseEntry).where(PhraseEntry.id == entry_state.entry_id)
                )
                phrase = phrase_result.scalar_one_or_none()
                senses_result = await self.db.execute(
                    select(PhraseSense)
                    .where(PhraseSense.phrase_entry_id == entry_state.entry_id)
                    .order_by(PhraseSense.order_index.asc())
                )
                senses = senses_result.scalars().all()
                detail = (
                    await self._build_phrase_detail_payload(user_id=user_id, phrase=phrase, senses=senses)
                    if phrase is not None and senses
                    else None
                )

            await self._record_entry_review_event(
                user_id=user_id,
                state=entry_state,
                prompt_type=(prompt or {}).get("prompt_type") or self.PROMPT_TYPE_DEFINITION_TO_ENTRY,
                outcome=resolved_outcome,
                selected_option_id=selected_option_id,
                typed_answer=typed_answer,
                scheduled_interval_days=resolved_interval_days,
                scheduled_by=scheduled_by,
                time_spent_ms=time_spent_ms,
                prompt=prompt,
            )
            entry_state.quality_rating = self._derive_quality(
                review_mode=normalized_review_mode,
                quality=quality,
                prompt=prompt,
                selected_option_id=selected_option_id,
                typed_answer=typed_answer,
            )
            entry_state.time_spent_ms = time_spent_ms
            entry_state.interval_days = resolved_interval_days
            entry_state.outcome = resolved_outcome
            entry_state.needs_relearn = resolved_outcome in {"lookup", "wrong"}
            entry_state.recheck_planned = resolved_outcome in {"lookup", "wrong"}
            entry_state.detail = detail
            entry_state.schedule_options = self._build_schedule_options(resolved_interval_days)
            await self.db.commit()
            return entry_state

        if self.uses_legacy_queue:
            result = await self.db.execute(
                select(ReviewCard)
                .join(ReviewSession)
                .where(ReviewCard.id == item_id, ReviewSession.user_id == user_id)
            )
        else:
            result = await self.db.execute(
                select(self.queue_model).where(
                    self.queue_model.id == item_id,
                    self.queue_model.user_id == user_id,
                )
            )

        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError(f"Queue item {item_id} not found")

        normalized_review_mode = self._normalize_review_mode(review_mode)
        resolved_outcome = self._derive_outcome(
            review_mode=normalized_review_mode,
            explicit_outcome=outcome,
            quality=quality,
            prompt=prompt,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
        )
        resolved_quality = self._derive_quality(
            review_mode=normalized_review_mode,
            quality=quality,
            prompt=prompt,
            selected_option_id=selected_option_id,
            typed_answer=typed_answer,
        )
        latest_history = None
        if (
            not self.uses_legacy_queue
            and not hasattr(self.queue_model, "next_review")
            and self._history_supports_schedule()
        ):
            latest_history = await self._get_latest_history_for_meaning(
                user_id=user_id,
                meaning_id=item.meaning_id,
            )

        previous_difficulty = float(
            getattr(latest_history, "ease_factor", None)
            or getattr(item, "ease_factor", None)
            or 0.5
        )
        previous_stability = float(
            getattr(latest_history, "interval_days", None)
            or getattr(item, "interval_days", None)
            or 0.3
        )
        previous_repetitions = int(
            getattr(latest_history, "repetitions", None)
            or getattr(item, "repetitions", None)
            or 0
        )

        review_result = calculate_next_review(
            outcome=resolved_outcome,
            prompt_type=(prompt or {}).get("prompt_type") or self.PROMPT_TYPE_DEFINITION_TO_ENTRY,
            stability=previous_stability,
            difficulty=previous_difficulty,
        )
        compatibility_interval_days = review_result.interval_days
        if resolved_outcome in {"correct_tested", "remember"}:
            if previous_repetitions == 0:
                compatibility_interval_days = max(1, compatibility_interval_days)
            elif previous_repetitions == 1:
                compatibility_interval_days = max(6, compatibility_interval_days)
            else:
                compatibility_interval_days = max(
                    max(1, round(previous_stability * max(previous_difficulty, 1.3))),
                    compatibility_interval_days,
                )
        legacy_ease_factor = previous_difficulty
        if resolved_outcome in {"correct_tested", "remember"}:
            legacy_ease_factor = round(max(1.3, previous_difficulty + 0.1), 2)
        elif resolved_outcome in {"lookup", "wrong"}:
            legacy_ease_factor = round(max(1.3, previous_difficulty - 0.2), 2)
        resolved_interval_days, resolved_next_review, _ = self._derive_interval_from_override(
            original_interval_days=compatibility_interval_days,
            override_value=schedule_override,
            base_next_review=datetime.now(timezone.utc) + timedelta(days=compatibility_interval_days),
        )

        effective_card_type = card_type or getattr(item, "card_type", None) or "flashcard"

        # Set runtime attributes so API responses include scheduling fields
        # even for queue models that don't persist these columns directly.
        item.quality_rating = resolved_quality
        item.time_spent_ms = time_spent_ms
        item.ease_factor = legacy_ease_factor
        item.review_difficulty = review_result.difficulty
        item.interval_days = resolved_interval_days
        item.repetitions = previous_repetitions + (
            1 if resolved_outcome in {"correct_tested", "remember"} else 0
        )
        item.next_review = resolved_next_review
        item.card_type = effective_card_type
        item.outcome = resolved_outcome
        item.needs_relearn = resolved_outcome in {"lookup", "wrong"}
        item.recheck_planned = resolved_outcome in {"lookup", "wrong"}
        item.schedule_options = self._build_schedule_options(resolved_interval_days)

        if hasattr(type(item), "last_reviewed_at") or hasattr(item, "last_reviewed_at"):
            item.last_reviewed_at = datetime.now(timezone.utc)
        if hasattr(type(item), "review_count") or hasattr(item, "review_count"):
            item.review_count = int(getattr(item, "review_count", 0) or 0) + 1
        if resolved_outcome in {"correct_tested", "remember"} and (
            hasattr(type(item), "correct_count") or hasattr(item, "correct_count")
        ):
            item.correct_count = int(getattr(item, "correct_count", 0) or 0) + 1

        source_word_id = getattr(item, "word_id", None)
        if source_word_id is not None:
            item.detail = await self._build_detail_payload_for_word_id(
                user_id=user_id,
                word_id=source_word_id,
            )
        else:
            item.detail = None

        history_record = self._build_history_record(
            item=item,
            user_id=user_id,
            quality=resolved_quality,
            time_spent_ms=time_spent_ms,
            card_type=effective_card_type,
            previous_ease_factor=previous_difficulty,
            previous_interval_days=int(round(previous_stability)),
            previous_repetitions=previous_repetitions,
        )
        if history_record is not None:
            self.db.add(history_record)

        await self.db.commit()
        return item

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

        return {
            "total_items": total_items,
            "due_items": due_items,
            "review_count": review_count,
            "correct_count": correct_count,
            "accuracy": accuracy,
        }

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

        return {
            "days": days,
            "total_events": total_events,
            "audio_placeholder_events": audio_placeholder_events,
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
