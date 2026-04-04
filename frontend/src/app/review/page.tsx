"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
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
import {
  clearStoredReviewSession,
  loadStoredReviewSession,
  persistReviewSession,
  type StoredRevealState as RevealState,
  type StoredReviewCard as ReviewQueueCard,
} from "@/lib/review-session-storage";
import { getUserPreferences, type UserPreferences } from "@/lib/user-preferences-client";

type ReviewPhase = "learning" | "challenge" | "relearn" | "reveal";
type ReviewOutcome = "correct_tested" | "remember" | "lookup" | "wrong";

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

const getRequestedQueueItemId = (): string | null => {
  if (typeof window === "undefined") {
    return null;
  }
  return new URLSearchParams(window.location.search).get("queue_item_id");
};

const buildReviewDetailHref = (detail: ReviewDetailPayload | null): string | null => {
  if (!detail) {
    return null;
  }
  return `${detail.entry_type === "word" ? "/word" : "/phrase"}/${detail.entry_id}?return_to=review&resume=1`;
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

const escapeRegExp = (value: string): string =>
  value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

const renderHighlightedPrompt = (text: string, target: string): ReactNode => {
  const normalizedText = text.trim();
  const normalizedTarget = target.trim();
  if (!normalizedText || !normalizedTarget) {
    return normalizedText;
  }
  const matcher = new RegExp(`(${escapeRegExp(normalizedTarget)})`, "ig");
  const segments = normalizedText.split(matcher);
  if (segments.length <= 1) {
    return normalizedText;
  }
  return segments.map((segment, index) =>
    segment.toLowerCase() === normalizedTarget.toLowerCase() ? (
      <mark key={`${segment}-${index}`} className="rounded bg-amber-200 px-1 text-slate-900">
        {segment}
      </mark>
    ) : (
      <span key={`${segment}-${index}`}>{segment}</span>
    ),
  );
};

const toLearningCards = (payload: LearningStartResponse): ReviewQueueCard[] =>
  payload.cards.map((card, index) => ({
    id:
      card.queue_item_id ||
      payload.queue_item_ids[index] ||
      payload.queue_item_ids[0] ||
      `${payload.entry_type}-${payload.entry_id}-${index}`,
    queue_item_id: card.queue_item_id || payload.queue_item_ids[index] || payload.queue_item_ids[0] || null,
    meaning_id: card.meaning_id,
    word: card.word,
    definition: card.definition,
    prompt: card.prompt,
    source_entry_type: payload.entry_type,
    source_entry_id: payload.entry_id,
    detail: card.detail ?? payload.detail ?? null,
    schedule_options: payload.schedule_options ?? [],
  }));

const exitReview = (router: ReturnType<typeof useRouter>) => {
  router.push("/");
};

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
  const [typedAnswerNudge, setTypedAnswerNudge] = useState<string | null>(null);
  const [resumeReady, setResumeReady] = useState(false);
  const [reviewPreferences, setReviewPreferences] = useState<UserPreferences | null>(null);
  const [audioReplayCount, setAudioReplayCount] = useState(0);
  const [challengeStartedAtMs, setChallengeStartedAtMs] = useState<number | null>(null);
  const [relearnMeaningIndex, setRelearnMeaningIndex] = useState(0);
  const autoPlayedAudioKeyRef = useRef<string | null>(null);
  const { play, loadingUrl } = useLearnerAudio();

  useEffect(() => {
    const storedSession = isResumeRequested() ? loadStoredReviewSession() : null;
    if (storedSession) {
      setCards(normalizeCards(storedSession.cards));
      setCurrentIndex(storedSession.currentIndex);
      setPhase(storedSession.phase);
      setRevealState(storedSession.revealState);
      setTypedAnswer(storedSession.typedAnswer);
      setCompleted(Boolean(storedSession.completed));
      setStarted(true);
      setChallengeStartedAtMs(Date.now());
      setRelearnMeaningIndex(0);
    }
    setResumeReady(true);
  }, []);

  useEffect(() => {
    setRelearnMeaningIndex(0);
  }, [currentIndex, phase]);

  useEffect(() => {
    setTypedAnswerNudge(null);
  }, [currentIndex, phase]);

  useEffect(() => {
    const source = getLearningEntryFromUrl();
    if (!resumeReady) {
      return;
    }
    if (!started && !loading) {
      if (source) {
        void startLearningMode(source.entryType, source.entryId);
        return;
      }
      void startQueueReview();
    }
  }, [started, loading, resumeReady]);

  useEffect(() => {
    let active = true;
    void getUserPreferences()
      .then((preferences) => {
        if (active) {
          setReviewPreferences(preferences);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

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
  const isConfidencePrompt = prompt?.prompt_type === "confidence_check";
  const isSpeechPlaceholderPrompt = prompt?.input_mode === "speech_placeholder";
  const isTypedPrompt = ["typed", "speech_placeholder"].includes(prompt?.input_mode ?? "");
  const scheduleOptions = useMemo(
    () => currentCard?.schedule_options ?? [],
    [currentCard],
  );
  const promptAudioUrl = prompt?.audio?.preferred_playback_url ?? null;
  const reviewDepthPreset = reviewPreferences?.review_depth_preset ?? "balanced";
  const reviewDepthBanner = (
    <div className="flex items-center justify-between rounded-xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-700">
      <span>Current review depth</span>
      <span className="font-semibold capitalize">{reviewDepthPreset}</span>
    </div>
  );

  const buildQueueSubmitPayload = (
    card: ReviewQueueCard,
    extras: Record<string, unknown>,
  ): Record<string, unknown> => ({
    time_spent_ms:
      challengeStartedAtMs === null ? 0 : Math.max(0, Date.now() - challengeStartedAtMs),
    audio_replay_count: Math.max(0, audioReplayCount - 1),
    card_type: card.card_type,
    prompt_token: card.prompt?.prompt_token,
    review_mode: card.review_mode,
    ...extras,
  });

  const playPromptAudio = () => {
    if (!promptAudioUrl) {
      return;
    }
    setAudioReplayCount((value) => value + 1);
    void play(promptAudioUrl);
  };

  useEffect(() => {
    const shouldAutoPlayChallengePromptAudio =
      phase === "challenge"
      && Boolean(promptAudioUrl)
      && (isTypedPrompt || prompt?.prompt_type === "audio_to_definition" || isConfidencePrompt);
    const autoPlayKey =
      phase === "learning"
        ? currentCard?.queue_item_id ?? currentCard?.meaning_id ?? null
        : phase === "relearn"
          ? `${currentCard?.queue_item_id ?? currentCard?.meaning_id ?? ""}:${relearnMeaningIndex}`
        : phase === "reveal"
          ? revealState?.detail?.entry_id ?? currentCard?.queue_item_id ?? null
          : shouldAutoPlayChallengePromptAudio
            ? currentCard?.queue_item_id ?? currentCard?.meaning_id ?? null
            : null;
    const autoPlayUrl =
      phase === "learning"
        ? currentCard?.detail?.audio?.preferred_playback_url ?? null
        : phase === "relearn"
          ? revealState?.detail?.audio?.preferred_playback_url ?? currentCard?.detail?.audio?.preferred_playback_url ?? null
        : phase === "reveal"
          ? revealState?.detail?.audio?.preferred_playback_url ?? null
          : shouldAutoPlayChallengePromptAudio
            ? promptAudioUrl
            : null;

    if (!autoPlayKey || !autoPlayUrl) {
      return;
    }
    const playbackKey = `${phase}:${autoPlayKey}`;
    if (autoPlayedAudioKeyRef.current === playbackKey) {
      return;
    }
    autoPlayedAudioKeyRef.current = playbackKey;
    void play(autoPlayUrl);
  }, [
    currentCard?.detail?.audio?.preferred_playback_url,
    currentCard?.meaning_id,
    currentCard?.queue_item_id,
    isConfidencePrompt,
    isTypedPrompt,
    phase,
    play,
    prompt?.prompt_type,
    promptAudioUrl,
    relearnMeaningIndex,
    revealState?.detail?.audio?.preferred_playback_url,
    revealState?.detail?.entry_id,
  ]);

  useEffect(() => {
    if (phase !== "reveal" || !revealState) {
      return;
    }
    const detailHref = buildReviewDetailHref(revealState.detail);
    if (detailHref) {
      router.push(detailHref);
    }
  }, [phase, revealState, router]);

  const startQueueReview = async () => {
    clearStoredReviewSession();
    setAudioReplayCount(0);
    setLoading(true);
    try {
      const dueCards = await apiClient.get<ReviewQueueCard[]>("/reviews/queue/due");
      const normalizedCards = normalizeCards(dueCards);
      const requestedQueueItemId = getRequestedQueueItemId();
      const requestedIndex = requestedQueueItemId
        ? normalizedCards.findIndex(
            (card) => (card.queue_item_id ?? card.id ?? null) === requestedQueueItemId,
          )
        : -1;
      setCards(normalizedCards);
      setCurrentIndex(requestedIndex >= 0 ? requestedIndex : 0);
      setPhase("challenge");
      setRevealState(null);
      setTypedAnswer("");
      setTypedAnswerNudge(null);
      setCompleted(false);
      setStarted(true);
      setChallengeStartedAtMs(Date.now());
      setRelearnMeaningIndex(0);
    } finally {
      setLoading(false);
    }
  };

  const startLearningMode = async (entryType: "word" | "phrase", entryId: string) => {
    clearStoredReviewSession();
    setAudioReplayCount(0);
    setLoading(true);
    try {
      const payload = await startLearningEntry(entryType, entryId);
      setCards(normalizeCards(toLearningCards(payload)));
      setCurrentIndex(0);
      setPhase("learning");
      setRevealState(null);
      setTypedAnswer("");
      setTypedAnswerNudge(null);
      setCompleted(false);
      setStarted(true);
      setChallengeStartedAtMs(Date.now());
      setRelearnMeaningIndex(0);
    } finally {
      setLoading(false);
    }
  };

  const advanceCard = () => {
    if (currentIndex + 1 < cards.length) {
      setCurrentIndex((value) => value + 1);
      setPhase("challenge");
      setRevealState(null);
      setTypedAnswer("");
      setTypedAnswerNudge(null);
      setAudioReplayCount(0);
      setRelearnMeaningIndex(0);
      setChallengeStartedAtMs(Date.now());
      return;
    }
    clearStoredReviewSession();
    setCompleted(true);
    setChallengeStartedAtMs(null);
  };

  const buildRevealState = (
    card: ReviewQueueCard,
    outcome: ReviewOutcome,
    detail: ReviewDetailPayload | null,
    options: ReviewScheduleOption[],
    answerState?: {
      selectedOptionId?: string;
      typedResponseValue?: string;
      persisted?: boolean;
    },
  ): RevealState => ({
    outcome,
    detail,
    scheduleOptions: options,
    selectedSchedule: defaultScheduleValue(options),
    selectedOptionId: answerState?.selectedOptionId,
    typedResponseValue: answerState?.typedResponseValue,
    persisted: answerState?.persisted ?? false,
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
      ...buildQueueSubmitPayload(card, {
        quality: outcome === "wrong" || outcome === "lookup" ? 1 : 4,
        confirm: false,
      }),
      outcome,
      typed_answer: typedAnswer.trim() || undefined,
    });
  };

  const redirectToReviewDetail = (nextRevealState: RevealState) => {
    persistReviewSession({
      cards,
      currentIndex,
      phase: "reveal",
      revealState: nextRevealState,
      typedAnswer,
      completed: false,
    });
    const detailHref = buildReviewDetailHref(nextRevealState.detail);
    if (detailHref) {
      router.push(detailHref);
    }
  };

  const onSubmitTypedAnswer = async () => {
    if (
      !currentCard?.prompt ||
      !["typed", "speech_placeholder"].includes(currentCard.prompt.input_mode ?? "") ||
      loading
    ) {
      return;
    }
    const rawTypedAnswer = typedAnswer;
    const normalizedTyped = rawTypedAnswer.trim().toLowerCase();
    if (!normalizedTyped) {
      setTypedAnswerNudge("Type your answer before checking.");
      return;
    }
    if (!currentCard.queue_item_id) {
      return;
    }

    setLoading(true);
    try {
      const response = await apiClient.post<{
        outcome?: ReviewOutcome;
        detail?: ReviewDetailPayload | null;
        schedule_options?: ReviewScheduleOption[];
      }>(`/reviews/queue/${currentCard.queue_item_id}/submit`, buildQueueSubmitPayload(currentCard, {
        quality: 4,
        confirm: false,
        typed_answer: rawTypedAnswer,
      }));
      const detail = response.detail ?? currentCard.detail ?? null;
      const options = response.schedule_options ?? currentCard.schedule_options ?? [];
      const outcome = response.outcome ?? "wrong";
      const nextRevealState = buildRevealState(currentCard, outcome, detail, options, {
        typedResponseValue: rawTypedAnswer,
        persisted: outcome !== "correct_tested",
      });
      setRevealState(nextRevealState);
      setPhase(outcome === "correct_tested" ? "reveal" : "relearn");
      if (outcome === "correct_tested") {
        redirectToReviewDetail(nextRevealState);
      }
    } finally {
      setLoading(false);
    }
  };

  const onChooseOption = async (optionId: string) => {
    if (!currentCard?.prompt?.options || loading) {
      return;
    }
    if (!currentCard.queue_item_id) {
      return;
    }
    setLoading(true);
    try {
      const response = await apiClient.post<{
        outcome?: ReviewOutcome;
        detail?: ReviewDetailPayload | null;
        schedule_options?: ReviewScheduleOption[];
      }>(`/reviews/queue/${currentCard.queue_item_id}/submit`, buildQueueSubmitPayload(currentCard, {
        quality: 4,
        confirm: false,
        selected_option_id: optionId,
      }));
      const detail = response.detail ?? currentCard.detail ?? null;
      const options = response.schedule_options ?? currentCard.schedule_options ?? [];
      const outcome = response.outcome ?? "wrong";
      const nextRevealState = buildRevealState(currentCard, outcome, detail, options, {
        selectedOptionId: optionId,
        persisted: outcome === "wrong" || outcome === "lookup",
      });
      setRevealState(nextRevealState);
      setPhase(outcome === "correct_tested" ? "reveal" : "relearn");
      if (outcome === "correct_tested") {
        redirectToReviewDetail(nextRevealState);
      }
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

  const onContinueReveal = async () => {
    if (!currentCard || !revealState) {
      return;
    }
    if (
      currentCard.queue_item_id &&
      !revealState.persisted &&
      revealState.selectedSchedule &&
      revealState.outcome !== "wrong" &&
      revealState.outcome !== "lookup"
    ) {
      setLoading(true);
      try {
        const defaultSchedule = defaultScheduleValue(revealState.scheduleOptions);
        await apiClient.post(`/reviews/queue/${currentCard.queue_item_id}/submit`, buildQueueSubmitPayload(currentCard, {
          quality: 4,
          outcome: revealState.outcome,
          selected_option_id: revealState.selectedOptionId,
          typed_answer: revealState.typedResponseValue,
          schedule_override:
            revealState.selectedSchedule !== defaultSchedule
              ? revealState.selectedSchedule
              : undefined,
        }));
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
        <p className="text-sm text-slate-600">
          {loading ? "Loading your review queue..." : "Preparing your review queue..."}
        </p>
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
    return (
      <div className="space-y-4" data-testid="review-redirecting-state">
        <div className="flex items-center justify-between">
          <button
            type="button"
            aria-label="Exit review"
            onClick={() => exitReview(router)}
            className="rounded-full border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
          >
            ← Home
          </button>
          <div className="text-sm text-slate-500">
            Review {currentIndex + 1}/{cards.length}
          </div>
        </div>
        {reviewDepthBanner}
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-600 shadow-sm">
          Opening the full detail page...
        </div>
      </div>
    );
  }

  if (phase === "learning") {
    const detail = currentCard.detail ?? null;
    const activeMeaning =
      detail?.meanings.find((meaning) => meaning.id === currentCard.meaning_id)
      ?? detail?.meanings[currentIndex]
      ?? null;

    return (
      <div className="space-y-4" data-testid="review-learning-state">
        <div className="flex items-center justify-between">
          <button
            type="button"
            aria-label="Exit review"
            onClick={() => exitReview(router)}
            className="rounded-full border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
          >
            ← Home
          </button>
          <h2 className="text-2xl font-bold">Learning</h2>
          <span className="text-sm text-slate-500">
            Learn {currentIndex + 1}/{cards.length}
          </span>
        </div>
        {reviewDepthBanner}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs uppercase tracking-wide text-cyan-600">Learn this meaning</div>
          <h2 className="mt-2 text-2xl font-semibold">{detail?.display_text ?? currentCard.word}</h2>
          {detail?.pronunciation ? <p className="text-sm text-slate-500">{detail.pronunciation}</p> : null}
          <p className="mt-3 text-base text-slate-800">
            {activeMeaning?.definition ?? detail?.primary_definition ?? currentCard.definition}
          </p>
          {activeMeaning?.part_of_speech ? (
            <p className="mt-2 text-sm text-slate-500">{activeMeaning.part_of_speech}</p>
          ) : null}
          {activeMeaning?.example ? (
            <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm italic text-slate-700">
              {activeMeaning.example}
            </p>
          ) : null}
          {detail?.pro_tip ? (
            <div className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              {detail.pro_tip}
            </div>
          ) : null}
        </div>
        <button
          onClick={advanceCard}
          className="w-full rounded-md bg-fuchsia-600 px-4 py-2 text-white"
        >
          {currentIndex + 1 < cards.length ? "Next meaning" : "Finish learning"}
        </button>
      </div>
    );
  }

  if (phase === "relearn" && revealState) {
    const detail = revealState.detail;
    const relearnMeanings = detail?.meanings ?? [];
    const activeRelearnMeaning =
      relearnMeanings[Math.min(relearnMeaningIndex, Math.max(relearnMeanings.length - 1, 0))] ?? null;
    const hasMoreRelearnMeanings = relearnMeaningIndex + 1 < relearnMeanings.length;
    return (
      <div className="space-y-4" data-testid="review-relearn-state">
        <div className="flex items-center justify-between">
          <button
            type="button"
            aria-label="Exit review"
            onClick={() => exitReview(router)}
            className="rounded-full border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
          >
            ← Home
          </button>
          <div className="text-sm text-slate-500">
            Review {currentIndex + 1}/{cards.length}
          </div>
        </div>
        {reviewDepthBanner}
        <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
          <div className="text-xs uppercase tracking-wide text-cyan-600">Learn this meaning</div>
          <h2 className="mt-2 text-2xl font-semibold">{detail?.display_text ?? currentCard.word}</h2>
          {detail?.pronunciation ? <p className="text-sm text-slate-500">{detail.pronunciation}</p> : null}
          <p className="mt-3 text-base text-slate-800">
            {activeRelearnMeaning?.definition ?? detail?.primary_definition ?? currentCard.definition}
          </p>
          {activeRelearnMeaning?.part_of_speech ? (
            <p className="mt-2 text-sm text-slate-500">{activeRelearnMeaning.part_of_speech}</p>
          ) : null}
          {activeRelearnMeaning?.example ? (
            <p className="mt-4 rounded-xl bg-slate-50 p-3 text-sm italic text-slate-700">
              {activeRelearnMeaning.example}
            </p>
          ) : null}
          {detail?.pro_tip ? (
            <div className="mt-4 rounded-xl bg-amber-50 p-3 text-sm text-amber-900">
              {detail.pro_tip}
            </div>
          ) : null}
          {detail?.coverage_summary ? (
            <div className="mt-4 rounded-xl bg-slate-50 p-3 text-sm text-slate-600">
              Coverage: {detail.coverage_summary.replaceAll("_", " ")}
            </div>
          ) : null}
          <p className="mt-4 text-sm text-slate-500">We will bring this entry back sooner.</p>
        </div>
        <button
          onClick={() => {
            if (hasMoreRelearnMeanings) {
              setRelearnMeaningIndex((value) => value + 1);
              return;
            }
            advanceCard();
          }}
          className="w-full rounded-md bg-fuchsia-600 px-4 py-2 text-white"
        >
          {hasMoreRelearnMeanings ? "Next meaning" : "Finish learning"}
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-4" data-testid="review-active-state">
      <div className="flex items-center justify-between">
        <button
          type="button"
          aria-label="Exit review"
          onClick={() => exitReview(router)}
          className="rounded-full border border-slate-300 px-3 py-2 text-sm font-semibold text-slate-700"
        >
          ← Home
        </button>
        <h2 className="text-2xl font-bold">Review Session</h2>
        <span className="text-sm text-slate-500">
          Review {currentIndex + 1}/{cards.length}
        </span>
      </div>
      {reviewDepthBanner}

      {!prompt ? (
        <div className="rounded-2xl border border-slate-200 bg-white p-6 text-sm text-slate-500 shadow-sm">
          Loading review item...
        </div>
      ) : null}

      {prompt ? (
      <div className="rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
        {prompt?.stem ? <p className="mb-2 text-sm text-slate-500">{prompt.stem}</p> : null}
        {prompt?.prompt_type === "audio_to_definition" && promptAudioUrl ? (
          <div className="mb-4 flex justify-center">
            <button
              type="button"
              onClick={playPromptAudio}
              className="rounded-full bg-cyan-500 px-5 py-4 text-sm font-semibold text-white"
            >
              {loadingUrl === promptAudioUrl ? "Loading..." : "Replay audio"}
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
        ) : isConfidencePrompt ? (
          <div className="space-y-3" data-testid="review-confidence-prompt">
            <div className="text-xs font-semibold uppercase tracking-wide text-amber-700">
              Confidence check
            </div>
            <button
              type="button"
              onClick={playPromptAudio}
              className="w-full rounded-xl bg-amber-50 p-4 text-left text-lg text-slate-900"
            >
              {renderHighlightedPrompt(promptText, currentCard.word ?? "")}
            </button>
            <p className="text-sm text-slate-500">Tap the sentence to replay the audio.</p>
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
        {isTypedPrompt && promptAudioUrl ? (
          <div className="mt-4 flex items-center justify-between gap-3 rounded-xl bg-slate-50 px-4 py-3">
            <p className="text-sm text-slate-600">
              Listen again if the definition could match more than one answer.
            </p>
            <button
              type="button"
              onClick={playPromptAudio}
              className="rounded-full border border-cyan-300 px-4 py-2 text-sm font-semibold text-cyan-700"
            >
              Replay audio
            </button>
          </div>
        ) : null}
      </div>
      ) : null}

      {prompt && reviewPreferences?.show_pictures_in_questions ? (
        <div
          className="rounded-2xl border border-dashed border-slate-300 bg-slate-50 p-5 text-sm text-slate-600"
          data-testid="review-picture-placeholder"
        >
          Picture hint placeholder
        </div>
      ) : null}

      {prompt ? (
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
        {!prompt?.options?.length && ["typed", "speech_placeholder"].includes(prompt?.input_mode ?? "") ? (
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
              onChange={(event) => {
                setTypedAnswer(event.target.value);
                if (typedAnswerNudge) {
                  setTypedAnswerNudge(null);
                }
              }}
              placeholder="Type the word or phrase"
              className="w-full rounded-xl border border-slate-300 bg-white px-4 py-3 text-slate-900"
            />
            {typedAnswerNudge ? (
              <p className="text-sm font-medium text-amber-700" role="alert">
                {typedAnswerNudge}
              </p>
            ) : null}
            <button
              onClick={() => void onSubmitTypedAnswer()}
              disabled={loading}
              className="w-full rounded-md bg-fuchsia-600 px-4 py-2 text-white disabled:opacity-50"
            >
              {loading ? "Checking..." : "Check answer"}
            </button>
          </div>
        ) : null}
      </div>
      ) : null}

      <div className="space-y-2 pt-2">
        {!isConfidencePrompt ? (
          <button
            onClick={() => void onLookup()}
            disabled={loading || !prompt}
            className="w-full rounded-md bg-amber-500 px-4 py-2 text-white disabled:opacity-50"
          >
            Show meaning
          </button>
        ) : null}
      </div>

      {scheduleOptions.length > 0 ? (
        <p className="text-center text-xs text-slate-500">
          Default next review: {scheduleOptions.find((option) => option.is_default)?.label}
        </p>
      ) : null}
    </div>
  );
}
