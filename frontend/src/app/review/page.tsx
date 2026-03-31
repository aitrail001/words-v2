"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  startLearningEntry,
  type LearningStartResponse,
  type ReviewDetailPayload,
  type ReviewPromptPayload,
  type ReviewScheduleOption,
} from "@/lib/knowledge-map-client";
import { apiClient } from "@/lib/api-client";
import { useLearnerAudio } from "@/lib/learner-audio";

type ReviewQueueCard = {
  id?: string;
  queue_item_id?: string | null;
  word?: string;
  definition?: string | null;
  card_type?: string;
  review_mode?: string | null;
  prompt?: ReviewPromptPayload | null;
  source_entry_type?: "word" | "phrase" | null;
  source_entry_id?: string | null;
  detail?: ReviewDetailPayload | null;
  schedule_options?: ReviewScheduleOption[];
};

type ReviewPhase = "challenge" | "relearn" | "reveal";
type ReviewOutcome = "correct_tested" | "remember" | "lookup" | "wrong";

type RevealState = {
  outcome: ReviewOutcome;
  detail: ReviewDetailPayload | null;
  scheduleOptions: ReviewScheduleOption[];
  selectedSchedule: string;
  selectedOptionId?: string;
  typedResponseValue?: string;
};

const TIME_SPENT_MS = 5000;
const REVIEW_RESUME_STORAGE_KEY = "learner-review-session-v1";

const normalizeCards = (items: ReviewQueueCard[]): ReviewQueueCard[] =>
  items.map((item) => ({
    ...item,
    queue_item_id: item.queue_item_id ?? item.id ?? null,
    detail: item.detail ?? null,
    schedule_options: item.schedule_options ?? [],
  }));

const getLearningEntryFromUrl = (): { entryType: "word" | "phrase"; entryId: string } | null => {
  if (typeof window === "undefined") {
    return null;
  }

  const search = new URLSearchParams(window.location.search);
  const entryType = search.get("entry_type");
  const entryId = search.get("entry_id");
  if ((entryType === "word" || entryType === "phrase") && entryId) {
    return { entryType, entryId };
  }
  return null;
};

const isResumeRequested = (): boolean => {
  if (typeof window === "undefined") {
    return false;
  }
  return new URLSearchParams(window.location.search).get("resume") === "1";
};

type StoredReviewSession = {
  cards: ReviewQueueCard[];
  currentIndex: number;
  phase: ReviewPhase;
  revealState: RevealState | null;
  typedAnswer: string;
};

const loadStoredReviewSession = (): StoredReviewSession | null => {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.sessionStorage.getItem(REVIEW_RESUME_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw) as StoredReviewSession | null;
    if (!parsed || !Array.isArray(parsed.cards) || parsed.cards.length === 0) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
};

const persistReviewSession = (payload: StoredReviewSession): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.setItem(REVIEW_RESUME_STORAGE_KEY, JSON.stringify(payload));
};

const clearStoredReviewSession = (): void => {
  if (typeof window === "undefined") {
    return;
  }
  window.sessionStorage.removeItem(REVIEW_RESUME_STORAGE_KEY);
};

const formatPromptQuestion = (card: ReviewQueueCard): string => {
  const prompt = card.prompt;
  if (!prompt) {
    return card.definition ?? card.word ?? "Review item";
  }
  if (prompt.prompt_type === "sentence_gap" && prompt.sentence_masked) {
    return prompt.sentence_masked;
  }
  return prompt.question || card.definition || card.word || "Review item";
};

const defaultScheduleValue = (options: ReviewScheduleOption[]): string =>
  options.find((option) => option.is_default)?.value ?? "";

const toLearningCards = (payload: LearningStartResponse): ReviewQueueCard[] =>
  payload.cards.map((card, index) => ({
    id:
      card.queue_item_id ||
      payload.queue_item_ids[index] ||
      payload.queue_item_ids[0] ||
      `${payload.entry_type}-${payload.entry_id}-${index}`,
    queue_item_id: card.queue_item_id || payload.queue_item_ids[index] || payload.queue_item_ids[0] || null,
    word: card.word,
    definition: card.definition,
    prompt: card.prompt,
    source_entry_type: payload.entry_type,
    source_entry_id: payload.entry_id,
    detail: card.detail ?? payload.detail ?? null,
    schedule_options: payload.schedule_options ?? [],
  }));

export default function ReviewPage() {
  const router = useRouter();
  const [started, setStarted] = useState(false);
  const [cards, setCards] = useState<ReviewQueueCard[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [loading, setLoading] = useState(false);
  const [completed, setCompleted] = useState(false);
  const [phase, setPhase] = useState<ReviewPhase>("challenge");
  const [revealState, setRevealState] = useState<RevealState | null>(null);
  const [typedAnswer, setTypedAnswer] = useState("");
  const [resumeReady, setResumeReady] = useState(false);
  const { play, loadingUrl } = useLearnerAudio();

  useEffect(() => {
    const storedSession = isResumeRequested() ? loadStoredReviewSession() : null;
    if (storedSession) {
      setCards(normalizeCards(storedSession.cards));
      setCurrentIndex(storedSession.currentIndex);
      setPhase(storedSession.phase);
      setRevealState(storedSession.revealState);
      setTypedAnswer(storedSession.typedAnswer);
      setCompleted(false);
      setStarted(true);
    }
    setResumeReady(true);
  }, []);

  useEffect(() => {
    const source = getLearningEntryFromUrl();
    if (!resumeReady) {
      return;
    }
    if (!started && !loading && source) {
      void startLearningMode(source.entryType, source.entryId);
    }
  }, [started, loading, resumeReady]);

  useEffect(() => {
    if (!started || completed || cards.length === 0) {
      clearStoredReviewSession();
      return;
    }
    persistReviewSession({
      cards,
      currentIndex,
      phase,
      revealState,
      typedAnswer,
    });
  }, [cards, completed, currentIndex, phase, revealState, started, typedAnswer]);

  const currentCard = cards[currentIndex] ?? null;
  const prompt = currentCard?.prompt ?? null;
  const promptText = currentCard ? formatPromptQuestion(currentCard) : "";
  const isCollocationPrompt = prompt?.prompt_type === "collocation_check";
  const isSituationPrompt = prompt?.prompt_type === "situation_matching";
  const isSpeechPlaceholderPrompt = prompt?.input_mode === "speech_placeholder";
  const scheduleOptions = useMemo(
    () => currentCard?.schedule_options ?? [],
    [currentCard],
  );
  const promptAudioUrl = prompt?.audio?.preferred_playback_url ?? null;

  const startQueueReview = async () => {
    clearStoredReviewSession();
    setLoading(true);
    try {
      const dueCards = await apiClient.get<ReviewQueueCard[]>("/reviews/queue/due");
      setCards(normalizeCards(dueCards));
      setCurrentIndex(0);
      setPhase("challenge");
      setRevealState(null);
      setTypedAnswer("");
      setCompleted(false);
      setStarted(true);
    } finally {
      setLoading(false);
    }
  };

  const startLearningMode = async (entryType: "word" | "phrase", entryId: string) => {
    clearStoredReviewSession();
    setLoading(true);
    try {
      const payload = await startLearningEntry(entryType, entryId);
      setCards(normalizeCards(toLearningCards(payload)));
      setCurrentIndex(0);
      setPhase("challenge");
      setRevealState(null);
      setTypedAnswer("");
      setCompleted(false);
      setStarted(true);
    } finally {
      setLoading(false);
    }
  };

  const startReview = async () => {
    const source = getLearningEntryFromUrl();
    if (source) {
      await startLearningMode(source.entryType, source.entryId);
      return;
    }
    await startQueueReview();
  };

  const advanceCard = () => {
    if (currentIndex + 1 < cards.length) {
      setCurrentIndex((value) => value + 1);
      setPhase("challenge");
      setRevealState(null);
      setTypedAnswer("");
      return;
    }
    clearStoredReviewSession();
    setCompleted(true);
  };

  const buildRevealState = (
    card: ReviewQueueCard,
    outcome: ReviewOutcome,
    detail: ReviewDetailPayload | null,
    options: ReviewScheduleOption[],
    answerState?: {
      selectedOptionId?: string;
      typedResponseValue?: string;
    },
  ): RevealState => ({
    outcome,
    detail,
    scheduleOptions: options,
    selectedSchedule: defaultScheduleValue(options),
    selectedOptionId: answerState?.selectedOptionId,
    typedResponseValue: answerState?.typedResponseValue,
  });

  const submitOutcome = async (card: ReviewQueueCard, outcome: ReviewOutcome) => {
    if (!card.queue_item_id) {
      return {
        detail: card.detail ?? null,
        schedule_options: card.schedule_options ?? [],
      };
    }

    return apiClient.post<{
      detail?: ReviewDetailPayload | null;
      schedule_options?: ReviewScheduleOption[];
    }>(`/reviews/queue/${card.queue_item_id}/submit`, {
      quality: outcome === "wrong" || outcome === "lookup" ? 1 : 4,
      time_spent_ms: TIME_SPENT_MS,
      card_type: card.card_type,
        review_mode: card.review_mode,
        prompt: card.prompt,
        outcome,
        typed_answer: typedAnswer.trim() || undefined,
      });
  };

  const onSubmitTypedAnswer = async () => {
    if (!currentCard?.prompt?.expected_input || loading) {
      return;
    }
    const normalizedTyped = typedAnswer.trim().toLowerCase();
    const normalizedExpected = currentCard.prompt.expected_input.trim().toLowerCase();
    if (!normalizedTyped) {
      return;
    }

    const outcome: ReviewOutcome =
      normalizedTyped === normalizedExpected ? "correct_tested" : "wrong";

    if (outcome === "correct_tested") {
      setRevealState(
        buildRevealState(
          currentCard,
          outcome,
          currentCard.detail ?? null,
          currentCard.schedule_options ?? [],
          { typedResponseValue: typedAnswer.trim() || undefined },
        ),
      );
      setPhase("reveal");
      return;
    }

    setLoading(true);
    try {
      const response = await submitOutcome(currentCard, outcome);
      const detail = response.detail ?? currentCard.detail ?? null;
      const options = response.schedule_options ?? currentCard.schedule_options ?? [];
      setRevealState(buildRevealState(currentCard, outcome, detail, options));
      setPhase("relearn");
    } finally {
      setLoading(false);
    }
  };

  const onChooseOption = async (optionId: string) => {
    if (!currentCard?.prompt?.options || loading) {
      return;
    }
    const matched = currentCard.prompt.options.find((option) => option.option_id === optionId);
    const outcome: ReviewOutcome = matched?.is_correct ? "correct_tested" : "wrong";
    if (outcome === "correct_tested") {
      setRevealState(
        buildRevealState(
          currentCard,
          outcome,
          currentCard.detail ?? null,
          currentCard.schedule_options ?? [],
          { selectedOptionId: optionId },
        ),
      );
      setPhase("reveal");
      return;
    }
    setLoading(true);
    try {
      const response = await submitOutcome(currentCard, outcome);
      const detail = response.detail ?? currentCard.detail ?? null;
      const options = response.schedule_options ?? currentCard.schedule_options ?? [];
      setRevealState(buildRevealState(currentCard, outcome, detail, options));
      setPhase("relearn");
    } finally {
      setLoading(false);
    }
  };

  const onLookup = async () => {
    if (!currentCard || loading) {
      return;
    }
    setLoading(true);
    try {
      const response = await submitOutcome(currentCard, "lookup");
      setRevealState(
        buildRevealState(
          currentCard,
          "lookup",
          response.detail ?? currentCard.detail ?? null,
          response.schedule_options ?? currentCard.schedule_options ?? [],
        ),
      );
      setPhase("relearn");
    } finally {
      setLoading(false);
    }
  };

  const onRemember = async () => {
    if (!currentCard || loading) {
      return;
    }
    setRevealState(
      buildRevealState(
        currentCard,
        "remember",
        currentCard.detail ?? null,
        currentCard.schedule_options ?? [],
      ),
    );
    setPhase("reveal");
  };

  const onContinueReveal = async () => {
    if (!currentCard || !revealState) {
      return;
    }
    if (
      currentCard.queue_item_id &&
      revealState.selectedSchedule &&
      revealState.outcome !== "wrong" &&
      revealState.outcome !== "lookup"
    ) {
      setLoading(true);
      try {
        await apiClient.post(`/reviews/queue/${currentCard.queue_item_id}/submit`, {
          quality: 4,
          time_spent_ms: TIME_SPENT_MS,
          card_type: currentCard.card_type,
          review_mode: currentCard.review_mode,
          prompt: currentCard.prompt,
          outcome: revealState.outcome,
          selected_option_id: revealState.selectedOptionId,
          typed_answer: revealState.typedResponseValue,
          schedule_override: revealState.selectedSchedule,
        });
      } finally {
        setLoading(false);
      }
    }
    advanceCard();
  };

  if (completed) {
    return (
      <div className="space-y-4" data-testid="review-complete-state">
        <h2 className="text-2xl font-bold">Session Complete</h2>
        <p className="text-sm text-slate-600">You reviewed {cards.length} entries.</p>
        <button
          onClick={() => router.push("/")}
          className="rounded-md bg-fuchsia-600 px-4 py-2 text-white"
        >
          Back to Home
        </button>
      </div>
    );
  }

  if (!started) {
    return (
      <div className="space-y-4" data-testid="review-start-state">
        <h2 className="text-2xl font-bold">Review Session</h2>
        <button
          data-testid="review-start-button"
          onClick={() => void startReview()}
          disabled={loading}
          className="rounded-md bg-fuchsia-600 px-4 py-2 text-white disabled:opacity-50"
        >
          {loading ? "Starting..." : "Start Review"}
        </button>
      </div>
    );
  }

  if (!currentCard) {
    return (
      <div className="space-y-4" data-testid="review-empty-state">
        <h2 className="text-2xl font-bold" data-testid="review-empty-title">No Entries Due</h2>
        <p className="text-sm text-slate-600" data-testid="review-empty-description">
          There are no cards to review right now.
        </p>
        <button
          onClick={() => router.push("/")}
          className="rounded-md bg-fuchsia-600 px-4 py-2 text-white"
        >
          Back to Home
        </button>
      </div>
    );
  }

  if (phase === "reveal" && revealState) {
    const detail = revealState.detail;
    return (
      <div className="space-y-4" data-testid="review-reveal-state">
        <div className="text-sm text-slate-500">
          Review {currentIndex + 1}/{cards.length}
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs uppercase tracking-wide text-slate-500">
            {revealState.outcome === "correct_tested" ? "Remembered" : "Kept in memory"}
          </div>
          <h2 className="mt-2 text-2xl font-semibold">{detail?.display_text ?? currentCard.word}</h2>
          {detail?.pronunciation ? <p className="text-sm text-slate-500">{detail.pronunciation}</p> : null}
          <p className="mt-3 text-base text-slate-800">{detail?.primary_definition ?? currentCard.definition}</p>
          {detail?.primary_example ? (
            <p className="mt-2 text-sm italic text-slate-600">{detail.primary_example}</p>
          ) : null}
          {detail?.meaning_count ? (
            <p className="mt-3 text-sm text-slate-500">
              {detail.meaning_count} meanings, remembered {detail.remembered_count} times
            </p>
          ) : null}
          {detail?.pro_tip ? (
            <div className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              {detail.pro_tip}
            </div>
          ) : null}
          {detail?.compare_with?.length ? (
            <div className="mt-4 text-sm text-slate-700">
              Compare with: {detail.compare_with.join(", ")}
            </div>
          ) : null}
        </div>

        <div className="space-y-2">
          <label htmlFor="review-override" className="text-sm font-medium text-slate-700">
            Review in
          </label>
          <select
            id="review-override"
            value={revealState.selectedSchedule}
            onChange={(event) =>
              setRevealState((state) =>
                state ? { ...state, selectedSchedule: event.target.value } : state,
              )
            }
            className="w-full rounded-md border border-slate-300 px-3 py-2"
          >
            {revealState.scheduleOptions.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <button
            onClick={() => void onContinueReveal()}
            disabled={loading}
            className="w-full rounded-md bg-fuchsia-600 px-4 py-2 text-white disabled:opacity-50"
          >
            {loading ? "Saving..." : "Continue"}
          </button>
        </div>
      </div>
    );
  }

  if (phase === "relearn" && revealState) {
    const detail = revealState.detail;
    const detailHref = detail
      ? `${detail.entry_type === "word" ? "/word" : "/phrase"}/${detail.entry_id}?return_to=review&resume=1`
      : null;
    return (
      <div className="space-y-4" data-testid="review-relearn-state">
        <div className="text-sm text-slate-500">
          Review {currentIndex + 1}/{cards.length}
        </div>
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs uppercase tracking-wide text-amber-600">Relearn</div>
          <h2 className="mt-2 text-2xl font-semibold">{detail?.display_text ?? currentCard.word}</h2>
          <p className="mt-3 text-base text-slate-800">{detail?.primary_definition ?? currentCard.definition}</p>
          <div className="mt-4 space-y-3">
            {detail?.meanings?.map((meaning, index) => (
              <div key={meaning.id} className="rounded-xl bg-slate-50 p-3">
                <div className="text-sm font-medium text-slate-900">
                  Meaning {index + 1}
                  {meaning.part_of_speech ? ` · ${meaning.part_of_speech}` : ""}
                </div>
                <div className="mt-1 text-sm text-slate-700">{meaning.definition}</div>
                {meaning.example ? (
                  <div className="mt-1 text-xs italic text-slate-500">{meaning.example}</div>
                ) : null}
              </div>
            ))}
          </div>
          {detail?.pro_tip ? (
            <div className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              {detail.pro_tip}
            </div>
          ) : null}
          <p className="mt-4 text-sm text-slate-500">We will bring this entry back sooner.</p>
        </div>
        <button
          onClick={advanceCard}
          className="w-full rounded-md bg-fuchsia-600 px-4 py-2 text-white"
        >
          Continue
        </button>
        {detailHref ? (
          <Link
            href={detailHref}
            className="block w-full rounded-md border border-slate-300 px-4 py-2 text-center text-slate-800"
          >
            Open full word details
          </Link>
        ) : null}
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="review-active-state">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-bold">Review Session</h2>
        <span className="text-sm text-slate-500">
          Review {currentIndex + 1}/{cards.length}
        </span>
      </div>

      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {prompt?.stem ? <p className="mb-2 text-sm text-slate-500">{prompt.stem}</p> : null}
        {prompt?.prompt_type === "audio_to_definition" && promptAudioUrl ? (
          <div className="mb-4 flex justify-center gap-3">
            <button
              type="button"
              onClick={() => void play(promptAudioUrl)}
              className="rounded-full bg-cyan-500 px-5 py-4 text-sm font-semibold text-white"
            >
              {loadingUrl === promptAudioUrl ? "Loading..." : "Play audio"}
            </button>
            <button
              type="button"
              onClick={() => void play(promptAudioUrl)}
              className="rounded-full border border-cyan-300 px-5 py-4 text-sm font-semibold text-cyan-700"
            >
              Play again
            </button>
          </div>
        ) : null}
        {isCollocationPrompt ? (
          <div className="space-y-3" data-testid="review-collocation-prompt">
            <div className="text-xs font-semibold uppercase tracking-wide text-cyan-700">
              Common expression
            </div>
            <p className="text-xl font-semibold text-slate-900">{promptText}</p>
          </div>
        ) : isSituationPrompt ? (
          <div className="space-y-3" data-testid="review-situation-prompt">
            <div className="text-xs font-semibold uppercase tracking-wide text-emerald-700">
              Situation
            </div>
            <p className="rounded-xl bg-emerald-50 p-4 text-lg text-slate-900">{promptText}</p>
          </div>
        ) : (
          <p className="text-xl font-semibold text-slate-900">{promptText}</p>
        )}
      </div>

      <div className="space-y-2">
        {prompt?.options?.map((option) => (
          <button
            key={option.option_id}
            onClick={() => void onChooseOption(option.option_id)}
            disabled={loading}
            className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-left text-slate-800 disabled:opacity-50"
          >
            <span className="mr-2 font-semibold">{option.option_id}</span>
            {option.label}
          </button>
        ))}
        {!prompt?.options?.length && prompt?.expected_input ? (
          <div className="space-y-2">
            {isSpeechPlaceholderPrompt ? (
              <div
                className="rounded-xl border border-dashed border-slate-300 bg-slate-50 p-4"
                data-testid="review-speech-placeholder"
              >
                <button
                  type="button"
                  disabled
                  className="mb-3 w-full rounded-md bg-slate-300 px-4 py-2 text-slate-700"
                >
                  Voice answer coming soon
                </button>
                <p className="text-sm text-slate-600">
                  {prompt?.voice_placeholder_text ?? "Type the answer for now."}
                </p>
              </div>
            ) : null}
            <input
              type="text"
              value={typedAnswer}
              onChange={(event) => setTypedAnswer(event.target.value)}
              placeholder="Type the word or phrase"
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900"
            />
            <button
              onClick={() => void onSubmitTypedAnswer()}
              disabled={loading || !typedAnswer.trim()}
              className="w-full rounded-md bg-fuchsia-600 px-4 py-2 text-white disabled:opacity-50"
            >
              {loading ? "Checking..." : "Check answer"}
            </button>
          </div>
        ) : null}
      </div>

      <div className="space-y-2 pt-2">
        <button
          onClick={() => void onRemember()}
          disabled={loading}
          className="w-full rounded-md bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"
        >
          I remember it
        </button>
        <button
          onClick={() => void onLookup()}
          disabled={loading}
          className="w-full rounded-md bg-amber-500 px-4 py-2 text-white disabled:opacity-50"
        >
          Show meaning
        </button>
      </div>

      {scheduleOptions.length > 0 ? (
        <p className="text-center text-xs text-slate-500">
          Default next review: {scheduleOptions.find((option) => option.is_default)?.label}
        </p>
      ) : null}
    </div>
  );
}
