"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { startTransition, useEffect, useMemo, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { ApiError, apiClient } from "@/lib/api-client";
import {
  formatReviewQueueDueLabel,
  formatReviewQueueTime,
} from "@/components/review-queue/review-queue-utils";
import {
  getKnowledgeMapEntryDetail,
  normalizeLearnerTranslation,
  updateReviewQueueSchedule,
  type KnowledgeEntryType,
  type KnowledgeMapEntryDetail,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import {
  getKnowledgeStatusActions,
  shouldOpenLearningFlow,
} from "@/lib/knowledge-status-policy";
import {
  advanceStoredReviewSession,
  loadStoredReviewSession,
  persistReviewSession,
  type StoredReviewSession,
} from "@/lib/review-session-storage";
import {
  DEFAULT_USER_PREFERENCES,
  getUserPreferences,
  TRANSLATION_LANGUAGE_LABELS,
  updateUserPreferences,
  type UserPreferences,
} from "@/lib/user-preferences-client";
import {
  getEntryLevelVoiceAssets,
  getPlayableLearnerAccents,
  playLearnerEntryAudio,
  resolveDisplayedPronunciation,
  resolveLearnerVoiceAsset,
} from "@/lib/learner-audio";

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "To Learn",
  learning: "Learning",
  known: "Known",
};

const ACCENT_LABELS: Record<UserPreferences["accent_preference"], string> = {
  us: "US",
  uk: "UK",
  au: "AU",
};

type DetailReviewQueue = NonNullable<KnowledgeMapEntryDetail["review_queue"]>;

type LinkedEntryTarget = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text?: string;
};

function actionButtonClass(status: KnowledgeStatus, activeStatus: KnowledgeStatus): string {
  if (activeStatus === "to_learn" && status === "learning") {
    return "bg-[#a52fff] text-white";
  }
  if (activeStatus === "to_learn" && status === "known") {
    return "bg-white text-[#684f85]";
  }
  if (status === activeStatus) {
    return status === "known"
      ? "bg-[#45c5dd] text-white"
      : "bg-[#a52fff] text-white";
  }

  return "bg-white text-[#684f85]";
}

function resolveScheduledReviewInstant(reviewQueue: DetailReviewQueue | null | undefined): string | null {
  return reviewQueue?.min_due_at_utc ?? reviewQueue?.next_review_at ?? null;
}

function formatScheduledReviewTime(reviewQueue: DetailReviewQueue | null | undefined): string {
  return formatReviewQueueTime(resolveScheduledReviewInstant(reviewQueue), {
    emptyLabel: "Scheduled time not set yet",
    invalidLabel: "Time unavailable",
  });
}

function buildScheduledReviewMessage(
  reviewQueue: DetailReviewQueue | null | undefined,
  fallbackLabel: string | null | undefined,
): string {
  const formattedTime = formatScheduledReviewTime(reviewQueue);
  if ((!resolveScheduledReviewInstant(reviewQueue) || formattedTime === "Scheduled time not set yet") && fallbackLabel) {
    return fallbackLabel;
  }
  return formattedTime;
}

function formatLegacyApproximateScheduledReviewTime(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }

  const target = new Date(value);
  if (Number.isNaN(target.getTime())) {
    return null;
  }

  const now = new Date();
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfTargetDay = new Date(target.getFullYear(), target.getMonth(), target.getDate());
  const dayDelta = Math.round(
    (startOfTargetDay.getTime() - startOfToday.getTime()) / (24 * 60 * 60 * 1000),
  );

  if (dayDelta < 0) {
    return "Overdue";
  }
  if (dayDelta === 0) {
    return target.getTime() <= now.getTime() ? "Due now" : "Later today";
  }
  if (dayDelta === 1) {
    return "Tomorrow";
  }
  if (dayDelta < 7) {
    return `In ${dayDelta} days`;
  }
  if (dayDelta < 14) {
    return "In a week";
  }
  if (dayDelta < 21) {
    return "In 2 weeks";
  }
  if (dayDelta < 45) {
    return "In a month";
  }

  return `In ${Math.max(2, Math.round(dayDelta / 30))} months`;
}

function formatApproximateScheduledReviewTime(reviewQueue: DetailReviewQueue | null | undefined): string | null {
  if (!reviewQueue) {
    return null;
  }

  const dueLabel = formatReviewQueueDueLabel({
    next_review_at: reviewQueue.next_review_at,
    due_review_date: reviewQueue.due_review_date,
    min_due_at_utc: reviewQueue.min_due_at_utc,
  });
  if (dueLabel) {
    return dueLabel;
  }

  return formatLegacyApproximateScheduledReviewTime(resolveScheduledReviewInstant(reviewQueue));
}

function getStatusActionErrorMessage(error: unknown): string {
  if (error instanceof ApiError && error.message) {
    return error.message;
  }
  if (error instanceof Error && error.message) {
    return error.message;
  }
  return "We could not update this entry right now.";
}

function findScheduleLabel(
  options: Array<{ value: string; label: string }>,
  value: string | null | undefined,
): string | null {
  if (!value) {
    return null;
  }
  return options.find((option) => option.value === value)?.label ?? value;
}

function isManualScheduleOverride(
  options: Array<{ value: string; is_default?: boolean }>,
  value: string | null | undefined,
): boolean {
  if (!value) {
    return false;
  }

  const defaultValue = options.find((option) => option.is_default)?.value ?? null;
  return defaultValue !== null && value !== defaultValue;
}

function buildHeroStyle(seed: string): CSSProperties {
  const palettes = [
    ["#2f1450", "#8f2fff", "#4bc6de"],
    ["#211243", "#5d28bf", "#38d1c8"],
    ["#38155d", "#bf2dff", "#63c7ff"],
    ["#2b1247", "#7c3bff", "#46cddd"],
  ];
  const hash = Array.from(seed).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const palette = palettes[hash % palettes.length];

  return {
    backgroundImage: [
      "radial-gradient(circle at 22% 18%, rgba(255,255,255,0.30), transparent 18%)",
      "radial-gradient(circle at 80% 15%, rgba(255,255,255,0.18), transparent 12%)",
      `radial-gradient(circle at 70% 72%, ${palette[2]}aa, transparent 30%)`,
      `linear-gradient(160deg, ${palette[0]} 0%, ${palette[1]} 55%, ${palette[2]} 100%)`,
    ].join(", "),
  };
}

function renderLinkPill(
  item: { text: string; target: LinkedEntryTarget | null },
  key: string,
  onOpenEntry: (target: LinkedEntryTarget) => void,
) {
  if (!item.target) {
    return (
      <span
        key={key}
        className="rounded-full bg-[#f1ddff] px-3 py-2 text-sm font-semibold text-[#7d2cff]"
      >
        {item.text}
      </span>
    );
  }

  return (
    <button
      key={key}
      type="button"
      onClick={() => onOpenEntry(item.target!)}
      className="rounded-full bg-[#f1ddff] px-3 py-2 text-sm font-semibold text-[#7d2cff]"
    >
      {item.text}
    </button>
  );
}

function renderInlineLinkedSentence(
  sentence: string,
  linkedEntries: Array<{ text: string; entry_type: KnowledgeEntryType; entry_id: string }>,
  onOpenEntry: (target: LinkedEntryTarget) => void,
): ReactNode {
  if (!sentence || linkedEntries.length === 0) {
    return sentence;
  }

  const loweredSentence = sentence.toLocaleLowerCase();
  const matches = linkedEntries
    .map((entry) => ({
      text: entry.text,
      entry_type: entry.entry_type,
      entry_id: entry.entry_id,
      index: loweredSentence.indexOf(entry.text.toLocaleLowerCase()),
    }))
    .filter((entry) => entry.index >= 0)
    .sort((left, right) => left.index - right.index || right.text.length - left.text.length);

  if (matches.length === 0) {
    return sentence;
  }

  const parts: ReactNode[] = [];
  let cursor = 0;

  matches.forEach((match, index) => {
    if (match.index < cursor) {
      return;
    }

    if (match.index > cursor) {
      parts.push(<span key={`text-${index}`}>{sentence.slice(cursor, match.index)}</span>);
    }

    const matchedText = sentence.slice(match.index, match.index + match.text.length);
    parts.push(
      <button
        key={`link-${match.entry_type}-${match.entry_id}-${index}`}
        type="button"
        onClick={() =>
          onOpenEntry({
            entry_type: match.entry_type,
            entry_id: match.entry_id,
            display_text: matchedText,
          })
        }
        className="font-semibold text-[#1687a6] underline decoration-[#8cd4e2] underline-offset-2"
      >
        {matchedText}
      </button>,
    );
    cursor = match.index + match.text.length;
  });

  if (cursor < sentence.length) {
    parts.push(<span key="text-tail">{sentence.slice(cursor)}</span>);
  }

  return parts;
}

function getTranslationForOverlay(
  detail: KnowledgeMapEntryDetail,
  translationLocale: UserPreferences["translation_locale"],
) {
  if (detail.entry_type === "word") {
    return normalizeLearnerTranslation(
      detail.meanings[0]?.translations.find((translation) => translation.language === translationLocale)
        ?.translation ??
      detail.meanings[0]?.localized_definition ??
      detail.translation
    );
  }

  return normalizeLearnerTranslation(detail.senses[0]?.localized_definition ?? detail.translation);
}

export function getKnowledgeEntryHref(entryType: KnowledgeEntryType, entryId: string): string {
  return entryType === "word" ? `/word/${entryId}` : `/phrase/${entryId}`;
}

export function KnowledgeEntryDetailPage({
  entryType,
  entryId,
}: {
  entryType: KnowledgeEntryType;
  entryId: string;
}) {
  const router = useRouter();
  const [detail, setDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [preferences, setPreferences] = useState<UserPreferences>(DEFAULT_USER_PREFERENCES);
  const [showTranslations, setShowTranslations] = useState(true);
  const [meaningIndex, setMeaningIndex] = useState(0);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">("loading");
  const [overlayTarget, setOverlayTarget] = useState<LinkedEntryTarget | null>(null);
  const [overlayDetail, setOverlayDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [overlayState, setOverlayState] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [overlayCache, setOverlayCache] = useState<Record<string, KnowledgeMapEntryDetail>>({});
  const [reviewSession, setReviewSession] = useState<StoredReviewSession | null>(null);
  const [reviewSaving, setReviewSaving] = useState(false);
  const [queueScheduleSaving, setQueueScheduleSaving] = useState(false);
  const [statusActionSaving, setStatusActionSaving] = useState(false);
  const [statusActionError, setStatusActionError] = useState<string | null>(null);
  const [isScheduleSheetOpen, setIsScheduleSheetOpen] = useState(false);
  const [scheduleDraftValue, setScheduleDraftValue] = useState("");
  const autoPlayedReviewAudioRef = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoadState("loading");
    setDetail(null);
    setMeaningIndex(0);
    setOverlayTarget(null);
    setOverlayDetail(null);
    setOverlayState("idle");

    Promise.all([getKnowledgeMapEntryDetail(entryType, entryId), getUserPreferences()])
      .then(([detailResponse, preferencesResponse]) => {
        if (!active) {
          return;
        }
        setPreferences(preferencesResponse);
        setShowTranslations(preferencesResponse.show_translations_by_default);
        setDetail(detailResponse);
        setReviewSession(loadStoredReviewSession());
        setLoadState("ready");
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setLoadState("error");
      });

    return () => {
      active = false;
    };
  }, [entryId, entryType]);

  const activeTranslation = useMemo(() => {
    if (!detail) {
      return null;
    }

    const activeIndex = Math.min(meaningIndex, Math.max(detail.entry_type === "word" ? detail.meanings.length : detail.senses.length, 1) - 1);

    if (detail.entry_type === "word") {
      const activeWordMeaning = detail.meanings[activeIndex] ?? null;
      return normalizeLearnerTranslation(
        activeWordMeaning?.translations.find(
          (translation) => translation.language === preferences.translation_locale,
        )?.translation ??
          activeWordMeaning?.localized_definition ??
          detail.translation,
      );
    }

    const activePhraseSense = detail.senses[activeIndex] ?? null;
    return normalizeLearnerTranslation(activePhraseSense?.localized_definition ?? detail.translation);
  }, [detail, meaningIndex, preferences.translation_locale]);

  const activeUsageNote = useMemo(() => {
    if (!detail) {
      return null;
    }

    const activeIndex = Math.min(
      meaningIndex,
      Math.max(detail.entry_type === "word" ? detail.meanings.length : detail.senses.length, 1) - 1,
    );
    const activeContent =
      detail.entry_type === "word" ? detail.meanings[activeIndex] ?? null : detail.senses[activeIndex] ?? null;

    if (showTranslations) {
      return activeContent?.localized_usage_note ?? activeContent?.usage_note ?? null;
    }

    return activeContent?.usage_note ?? null;
  }, [detail, meaningIndex, showTranslations]);

  const overlayTranslation = useMemo(() => {
    if (!overlayDetail) {
      return null;
    }

    return getTranslationForOverlay(overlayDetail, preferences.translation_locale);
  }, [overlayDetail, preferences.translation_locale]);

  const overlayUsageNote = useMemo(() => {
    if (!overlayDetail) {
      return null;
    }

    const overlayContent =
      overlayDetail.entry_type === "word" ? overlayDetail.meanings[0] ?? null : overlayDetail.senses[0] ?? null;

    if (showTranslations) {
      return overlayContent?.localized_usage_note ?? overlayContent?.usage_note ?? null;
    }

    return overlayContent?.usage_note ?? null;
  }, [overlayDetail, showTranslations]);

  const openOverlay = (target: LinkedEntryTarget) => {
    const cacheKey = `${target.entry_type}:${target.entry_id}`;
    setOverlayTarget(target);
    const cached = overlayCache[cacheKey];
    if (cached) {
      setOverlayDetail(cached);
      setOverlayState("ready");
      return;
    }

    setOverlayDetail(null);
    setOverlayState("loading");
    void getKnowledgeMapEntryDetail(target.entry_type, target.entry_id)
      .then((response) => {
        setOverlayCache((current) => ({ ...current, [cacheKey]: response }));
        setOverlayDetail(response);
        setOverlayState("ready");
      })
      .catch(() => {
        setOverlayState("error");
      });
  };

  const closeOverlay = () => {
    setOverlayTarget(null);
    setOverlayDetail(null);
    setOverlayState("idle");
  };

  const updateStatus = async (status: KnowledgeStatus) => {
    if (!detail) {
      return;
    }
    const previousStatus = detail.status;
    if (
      previousStatus === "learning"
      && status === "known"
      && typeof window !== "undefined"
      && !window.confirm("Mark this learning entry as Already Knew? Review history will be kept, but it will leave the review queue.")
    ) {
      return;
    }
    setStatusActionSaving(true);
    setStatusActionError(null);
    try {
      const response = await updateKnowledgeEntryStatus(detail.entry_type, detail.entry_id, status);
      startTransition(() => {
        setDetail((current) =>
          current
            ? {
                ...current,
                status: response.status,
                review_queue: response.status === "learning" ? current.review_queue : null,
              }
            : current,
        );
      });
      if (shouldOpenLearningFlow(previousStatus, status)) {
        router.push(`/review?entry_type=${detail.entry_type}&entry_id=${detail.entry_id}`);
      }
    } catch (error) {
      setStatusActionError(getStatusActionErrorMessage(error));
    } finally {
      setStatusActionSaving(false);
    }
  };

  useEffect(() => {
    if (!detail) {
      return;
    }
    const launchedFromReviewContext =
      typeof window !== "undefined"
        && new URLSearchParams(window.location.search).get("return_to") === "review";
    const reviewVoiceAssets = getEntryLevelVoiceAssets(detail.voice_assets);
    const canAutoPlayReviewAudio = getPlayableLearnerAccents(reviewVoiceAssets).length > 0;
    if (
      !launchedFromReviewContext ||
      !canAutoPlayReviewAudio ||
      autoPlayedReviewAudioRef.current === detail.entry_id
    ) {
      return;
    }
    autoPlayedReviewAudioRef.current = detail.entry_id;
    void playLearnerEntryAudio(reviewVoiceAssets, preferences.accent_preference, {
      contentScope: "word",
    }).catch(() => undefined);
  }, [detail, preferences.accent_preference]);

  useEffect(() => {
    const launchedFromReviewContext =
      typeof window !== "undefined"
        && new URLSearchParams(window.location.search).get("return_to") === "review";
    const matchingRevealSchedule =
      launchedFromReviewContext
      && detail
      && reviewSession?.phase === "reveal"
      && reviewSession.revealState
      && reviewSession.revealState.detail?.entry_type === detail.entry_type
      && reviewSession.revealState.detail?.entry_id === detail.entry_id
        ? reviewSession.revealState.selectedSchedule
        : null;
    setScheduleDraftValue(matchingRevealSchedule ?? detail?.review_queue?.current_schedule_value ?? "");
  }, [detail, reviewSession]);

  if (loadState === "loading") {
    return <p className="text-sm text-slate-500">Loading learner detail...</p>;
  }

  if (loadState === "error" || !detail) {
    return (
      <section className="mx-auto max-w-[46rem] rounded-[2rem] bg-white/94 px-5 py-6 text-[#43235f] shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <h1 className="text-[1.7rem] font-semibold text-[#572c80]">Unable to load this entry</h1>
        <p className="mt-3 text-sm leading-6 text-[#6d6084]">
          The learner card could not be loaded right now.
        </p>
        <Link
          href="/knowledge-map"
          className="mt-5 inline-flex rounded-[1rem] bg-[#f1ddff] px-4 py-3 text-sm font-semibold text-[#7d2cff]"
        >
          Back to Knowledge Map
        </Link>
      </section>
    );
  }

  const contentItems = detail.entry_type === "word" ? detail.meanings : detail.senses;
  const activeContent = contentItems[Math.min(meaningIndex, Math.max(contentItems.length - 1, 0))] ?? null;
  const activeWordMeaning =
    detail.entry_type === "word"
      ? detail.meanings[Math.min(meaningIndex, Math.max(detail.meanings.length - 1, 0))] ?? null
      : null;
  const activePhraseSense =
    detail.entry_type === "phrase"
      ? detail.senses[Math.min(meaningIndex, Math.max(detail.senses.length - 1, 0))] ?? null
      : null;
  const contentCount = Math.max(contentItems.length, 1);
  const activeDefinition =
    activeContent?.definition ?? detail.primary_definition ?? "No learner definition has been generated yet.";
  const activePartOfSpeech = activeContent?.part_of_speech ?? null;
  const activeExamples = activeContent?.examples.slice(0, 2) ?? [];
  const activeRegister = activeContent?.register ?? null;
  const activePrimaryDomain = activeContent?.primary_domain ?? null;
  const activeSecondaryDomains = activeContent?.secondary_domains ?? [];
  const activeGrammarPatterns = activeContent?.grammar_patterns ?? [];
  const activeSynonyms = activeWordMeaning?.synonyms ?? activePhraseSense?.synonyms ?? [];
  const activeAntonyms = activeWordMeaning?.antonyms ?? activePhraseSense?.antonyms ?? [];
  const activeCollocations = activeWordMeaning?.collocations ?? activePhraseSense?.collocations ?? [];
  const translationLanguageLabel = TRANSLATION_LANGUAGE_LABELS[preferences.translation_locale];
  const displayedPronunciation = resolveDisplayedPronunciation(
    detail.pronunciation,
    detail.pronunciations,
    preferences.accent_preference,
  );
  const accentLabel = displayedPronunciation ? `${ACCENT_LABELS[preferences.accent_preference]} Accent` : null;
  const entryLevelVoiceAssets = getEntryLevelVoiceAssets(detail.voice_assets);
  const playableAccents = getPlayableLearnerAccents(entryLevelVoiceAssets);
  const statusActions = getKnowledgeStatusActions(detail.status, "detail");
  const overlayContentItems = overlayDetail
    ? overlayDetail.entry_type === "word"
      ? overlayDetail.meanings
      : overlayDetail.senses
    : [];
  const overlayContent = overlayContentItems[0] ?? null;
  const overlayExample = overlayContent?.examples[0] ?? null;
  const hasWordLevelForms = Boolean(
    detail.forms &&
      (
        Object.values(detail.forms.verb_forms).some((value) => Boolean(value)) ||
        detail.forms.plural_forms.length > 0 ||
        detail.forms.derivations.length > 0 ||
        detail.forms.comparative ||
        detail.forms.superlative
      ),
  );
  const translationToggleLabel = `${translationLanguageLabel} ${showTranslations ? "On" : "Off"}`;
  const canPlayAudio = playableAccents.length > 0;
  const canPlayDefinitionAudio = Boolean(
    resolveLearnerVoiceAsset(detail.voice_assets, preferences.accent_preference, {
      contentScope: "definition",
      meaningId: activeWordMeaning?.id ?? undefined,
      phraseSenseId: activePhraseSense?.sense_id ?? undefined,
    }),
  );
  const launchedFromReview =
    typeof window !== "undefined"
      && new URLSearchParams(window.location.search).get("return_to") === "review";
  const reviewReturnHref = "/review?resume=1";
  const matchingReviewReveal =
    launchedFromReview &&
    reviewSession?.phase === "reveal" &&
    reviewSession.revealState &&
    reviewSession.revealState.detail?.entry_type === detail.entry_type &&
    reviewSession.revealState.detail?.entry_id === detail.entry_id
      ? reviewSession.revealState
      : null;
  const detailReviewQueue = detail.review_queue ?? null;
  const activeReviewScheduleOptions =
    matchingReviewReveal?.scheduleOptions ?? detailReviewQueue?.schedule_options ?? [];
  const activeReviewScheduleValue =
    matchingReviewReveal?.selectedSchedule ?? detailReviewQueue?.current_schedule_value ?? "";
  const activeReviewScheduleLabel = findScheduleLabel(activeReviewScheduleOptions, activeReviewScheduleValue);
  const hasManualScheduleOverride = isManualScheduleOverride(
    activeReviewScheduleOptions,
    activeReviewScheduleValue,
  );
  const approximateScheduledReview = matchingReviewReveal
    ? null
    : formatApproximateScheduledReviewTime(detailReviewQueue);
  const scheduleSheetApproximateReview =
    approximateScheduledReview ?? activeReviewScheduleLabel;
  const scheduledReviewMessage = matchingReviewReveal
    ? "Next review scheduled: Scheduled time will be set when you continue review."
    : `Next review scheduled: ${buildScheduledReviewMessage(
        detailReviewQueue,
        detailReviewQueue?.current_schedule_label ?? activeReviewScheduleLabel,
      )}`;

  const updateAccentPreference = (accent: UserPreferences["accent_preference"]) => {
    setPreferences((current) => {
      if (current.accent_preference === accent) {
        return current;
      }
      const next = { ...current, accent_preference: accent };
      void updateUserPreferences(next).catch(() => undefined);
      return next;
    });
  };

  const handlePlayAudio = () => {
    void playLearnerEntryAudio(entryLevelVoiceAssets, preferences.accent_preference, {
      contentScope: "word",
    }).catch(() => undefined);
  };

  const handlePlayDefinitionAudio = () => {
    void playLearnerEntryAudio(detail.voice_assets, preferences.accent_preference, {
      contentScope: "definition",
      meaningId: activeWordMeaning?.id ?? undefined,
      phraseSenseId: activePhraseSense?.sense_id ?? undefined,
    }).catch(() => undefined);
  };

  const handlePlayExampleAudio = (exampleId: string) => {
    void playLearnerEntryAudio(detail.voice_assets, preferences.accent_preference, {
      contentScope: "example",
      meaningExampleId: detail.entry_type === "word" ? exampleId : undefined,
      phraseSenseExampleId: detail.entry_type === "phrase" ? exampleId : undefined,
    }).catch(() => undefined);
  };

  const handleContinueReview = async () => {
    if (!reviewSession || !matchingReviewReveal) {
      return;
    }
    const activeReviewCard = reviewSession.cards[reviewSession.currentIndex];
    if (!activeReviewCard) {
      router.push(reviewReturnHref);
      return;
    }
    setReviewSaving(true);
    try {
      if (
        activeReviewCard.queue_item_id &&
        !matchingReviewReveal.persisted &&
        matchingReviewReveal.outcome !== "wrong" &&
        matchingReviewReveal.outcome !== "lookup"
      ) {
        const defaultSchedule =
          matchingReviewReveal.scheduleOptions.find((option) => option.is_default)?.value ?? "";
        await apiClient.post(`/reviews/queue/${activeReviewCard.queue_item_id}/submit`, {
          confirm: true,
          quality: 4,
          time_spent_ms: 0,
          audio_replay_count: 0,
          card_type: activeReviewCard.card_type,
          prompt_token: activeReviewCard.prompt?.prompt_token,
          review_mode: activeReviewCard.review_mode,
          outcome: matchingReviewReveal.outcome,
          selected_option_id: matchingReviewReveal.selectedOptionId,
          typed_answer: matchingReviewReveal.typedResponseValue,
          schedule_override:
            matchingReviewReveal.selectedSchedule !== defaultSchedule
              ? matchingReviewReveal.selectedSchedule
              : undefined,
        });
      }

      const nextSession = advanceStoredReviewSession(reviewSession);
      persistReviewSession(nextSession);
      router.push(reviewReturnHref);
    } finally {
      setReviewSaving(false);
    }
  };

  const handleUpdateDetailReviewSchedule = async (scheduleValue: string) => {
    if (!detailReviewQueue?.queue_item_id) {
      return;
    }
    setQueueScheduleSaving(true);
    try {
      const updatedQueue = await updateReviewQueueSchedule(detailReviewQueue.queue_item_id, scheduleValue);
      setDetail((current) => (current ? { ...current, review_queue: updatedQueue } : current));
    } finally {
      setQueueScheduleSaving(false);
    }
  };

  const handleConfirmScheduleDraft = async () => {
    if (!scheduleDraftValue) {
      setIsScheduleSheetOpen(false);
      return;
    }

    if (matchingReviewReveal) {
      setReviewSession((current) => {
        if (!current?.revealState) {
          return current;
        }
        const next = {
          ...current,
          revealState: { ...current.revealState, selectedSchedule: scheduleDraftValue },
        };
        persistReviewSession(next);
        return next;
      });
      setIsScheduleSheetOpen(false);
      return;
    }

    if (!detailReviewQueue || scheduleDraftValue === detailReviewQueue.current_schedule_value) {
      setIsScheduleSheetOpen(false);
      return;
    }

    await handleUpdateDetailReviewSchedule(scheduleDraftValue);
    setIsScheduleSheetOpen(false);
  };

  return (
    <>
      <div
        data-testid="knowledge-detail-mobile-shell"
        className="mx-auto max-w-[46rem] space-y-3 pb-32 text-[#43235f]"
      >
        <section
          data-testid="knowledge-detail-hero"
          className="relative overflow-hidden rounded-[0.75rem] shadow-[0_10px_24px_rgba(84,46,135,0.10)]"
        >
          <div className="h-[18rem]" style={buildHeroStyle(detail.display_text)} />

          <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 py-4">
            <button
              type="button"
              onClick={() => {
                if (window.history.length > 1) {
                  router.back();
                  return;
                }
                router.push("/knowledge-map");
              }}
              className="flex h-8 w-8 items-center justify-center rounded-full bg-white/75 text-sm font-semibold text-[#62368f] backdrop-blur"
            >
              ←
            </button>
            <button
              type="button"
              aria-label="Detail options"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-white/75 text-sm font-semibold text-[#62368f] backdrop-blur"
            >
              •••
            </button>
          </div>
          <div className="absolute inset-x-0 bottom-0 h-20 bg-[linear-gradient(180deg,transparent,rgba(34,12,66,0.32))]" />
        </section>

        <section>
          <div className="space-y-3 rounded-[0.55rem] bg-white px-4 py-4 shadow-[0_8px_20px_rgba(85,48,139,0.08)]">
            {matchingReviewReveal ? (
              <div className="rounded-[0.65rem] border border-[#e6dcf3] bg-[#faf7ff] px-3 py-3">
                <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
                  Review Decision
                </p>
                <p className="mt-2 text-sm font-semibold text-[#5a357b]">
                  Scheduled time will be set when you continue review.
                </p>
                <p className="mt-1 text-sm text-[#6e5a86]">
                  Use the override control below to keep the default next-review window or choose a different one.
                </p>
                <div className="mt-3">
                  <button
                    type="button"
                    onClick={() => void handleContinueReview()}
                    disabled={reviewSaving}
                    className="w-full rounded-[0.8rem] bg-[#45c5dd] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
                  >
                    {reviewSaving ? "Saving..." : "Continue review"}
                  </button>
                </div>
              </div>
            ) : null}

            <div className="flex items-start justify-between gap-4">
              <div>
                <h1 className="text-[1.55rem] font-semibold leading-none text-[#572c80]">
                  {detail.display_text}
                </h1>
                <div className="mt-2 flex flex-wrap items-center gap-2 text-sm font-semibold text-[#7c7395]">
                  {canPlayAudio && (
                    <button
                      type="button"
                      aria-label={`Play audio for ${detail.display_text}`}
                      onClick={handlePlayAudio}
                      className="rounded-full bg-[#eef8ff] px-3 py-1 text-[#1687a6]"
                    >
                      Play
                    </button>
                  )}
                  {playableAccents.map((accent) => (
                    <button
                      key={accent}
                      type="button"
                      aria-label={`Use ${ACCENT_LABELS[accent]} accent`}
                      aria-pressed={preferences.accent_preference === accent}
                      onClick={() => updateAccentPreference(accent)}
                      className={`rounded-full px-3 py-1 ${
                        preferences.accent_preference === accent
                          ? "bg-[#eef8ff] text-[#1687a6]"
                          : "bg-[#f4eefc] text-[#684f85]"
                      }`}
                    >
                      {ACCENT_LABELS[accent]}
                    </button>
                  ))}
                  {!canPlayAudio && accentLabel && displayedPronunciation && (
                    <span className="rounded-full bg-[#eef8ff] px-3 py-1 text-[#1687a6]">
                      {accentLabel}
                    </span>
                  )}
                  {displayedPronunciation ? <span>{displayedPronunciation}</span> : null}
                  <span>#{detail.browse_rank.toLocaleString()}</span>
                </div>
              </div>
              <span className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[#7ebed7]">
                {activePartOfSpeech ?? detail.entry_type}
              </span>
              <span className="sr-only">Status: {STATUS_LABELS[detail.status]}</span>
            </div>

            <div className="flex flex-wrap items-center gap-2 text-[0.74rem] font-semibold text-[#7c7395]">
              {detail.cefr_level && <span>{detail.cefr_level}</span>}
              {detail.entry_type === "phrase" && detail.normalized_form && <span>{detail.normalized_form}</span>}
            </div>

            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-start gap-3">
                  <p className="min-w-0 flex-1 text-[1.04rem] font-semibold leading-6 text-[#4d295f]">
                    {activeDefinition}
                  </p>
                  {canPlayDefinitionAudio ? (
                    <button
                      type="button"
                      aria-label={`Play definition audio for ${detail.display_text}`}
                      onClick={handlePlayDefinitionAudio}
                      className="shrink-0 rounded-full bg-[#eef8ff] px-3 py-1 text-sm font-semibold text-[#1687a6]"
                    >
                      Play
                    </button>
                  ) : null}
                </div>
                {activeTranslation && (
                  <p className="mt-2 text-sm font-semibold text-[#9a39f2]">{activeTranslation}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => setShowTranslations((current) => !current)}
                className={`shrink-0 rounded-full px-3 py-1.5 text-[0.72rem] font-semibold ${
                  showTranslations ? "bg-[#f1ddff] text-[#7d2cff]" : "bg-[#f3f4f8] text-[#6f6485]"
                }`}
              >
                {translationToggleLabel}
              </button>
            </div>

            {activeExamples.length > 0 && (
              <div className="border-t border-[#ebedf5] pt-2">
                <div className="space-y-3">
                  {activeExamples.map((example) => {
                    const exampleTranslation = showTranslations
                      ? normalizeLearnerTranslation(example.translation ?? null)
                      : null;
                    const canPlayExampleAudio = Boolean(
                      resolveLearnerVoiceAsset(detail.voice_assets, preferences.accent_preference, {
                        contentScope: "example",
                        meaningExampleId: detail.entry_type === "word" ? example.id : undefined,
                        phraseSenseExampleId: detail.entry_type === "phrase" ? example.id : undefined,
                      }),
                    );
                    return (
                      <div key={example.id} className="space-y-2">
                        <div className="flex items-start gap-3">
                          <p className="min-w-0 flex-1 text-[0.92rem] italic leading-6 text-[#5e4a74]">
                            {renderInlineLinkedSentence(
                              example.sentence,
                              example.linked_entries ?? [],
                              openOverlay,
                            )}
                          </p>
                          {canPlayExampleAudio ? (
                            <button
                              type="button"
                              aria-label={`Play example audio for ${detail.display_text}`}
                              onClick={() => handlePlayExampleAudio(example.id)}
                              className="shrink-0 rounded-full bg-[#eef8ff] px-3 py-1 text-sm font-semibold text-[#1687a6]"
                            >
                              Play
                            </button>
                          ) : null}
                        </div>
                        {exampleTranslation && (
                          <p className="text-sm leading-6 text-[#9a39f2]">{exampleTranslation}</p>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {activeUsageNote && (
              <div className="border-t border-[#ebedf5] pt-2">
                <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
                  Usage Note
                </p>
                <p className="mt-2 text-sm leading-6 text-[#5e4a74]">{activeUsageNote}</p>
              </div>
            )}

            {(activeRegister || activePrimaryDomain || activeSecondaryDomains.length > 0) && (
              <div className="flex flex-wrap gap-2 border-t border-[#ebedf5] pt-2">
                {activeRegister && (
                  <span className="rounded-full bg-[#eef8ff] px-3 py-1.5 text-xs font-semibold text-[#1687a6]">
                    {activeRegister}
                  </span>
                )}
                {activePrimaryDomain && (
                  <span className="rounded-full bg-[#f1ddff] px-3 py-1.5 text-xs font-semibold text-[#7d2cff]">
                    {activePrimaryDomain}
                  </span>
                )}
                {activeSecondaryDomains.map((domain) => (
                  <span
                    key={domain}
                    className="rounded-full bg-[#f6f4fb] px-3 py-1.5 text-xs font-semibold text-[#684f85]"
                  >
                    {domain}
                  </span>
                ))}
              </div>
            )}

            {activeGrammarPatterns.length > 0 && (
              <div className="space-y-2 border-t border-[#ebedf5] pt-2">
                <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
                  Grammar Patterns
                </h2>
                <div className="flex flex-wrap gap-2">
                  {activeGrammarPatterns.map((pattern) => (
                    <span
                      key={pattern}
                      className="rounded-full bg-[#f6f4fb] px-3 py-2 text-sm font-semibold text-[#684f85]"
                    >
                      {pattern}
                    </span>
                  ))}
                </div>
              </div>
            )}

            {(activeSynonyms.length > 0 || activeAntonyms.length > 0 || activeCollocations.length > 0) && (
              <div className="space-y-3 border-t border-[#ebedf5] pt-2">
                <h2 className="text-sm font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
                  Sense Links
                </h2>
                <div className="space-y-3">
                  {activeSynonyms.length > 0 && (
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                        Synonyms
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {activeSynonyms.map((item) =>
                          renderLinkPill(item, `synonym-${item.text}`, openOverlay),
                        )}
                      </div>
                    </div>
                  )}
                  {activeAntonyms.length > 0 && (
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                        Antonyms
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {activeAntonyms.map((item) =>
                          renderLinkPill(item, `antonym-${item.text}`, openOverlay),
                        )}
                      </div>
                    </div>
                  )}
                  {activeCollocations.length > 0 && (
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                        Collocations
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {activeCollocations.map((item) =>
                          renderLinkPill(item, `collocation-${item.text}`, openOverlay),
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {contentCount > 1 && (
              <div className="flex items-center justify-between gap-3 rounded-[0.45rem] bg-[#f6f4fb] px-3 py-2.5">
                <button
                  type="button"
                  onClick={() => setMeaningIndex((current) => Math.max(current - 1, 0))}
                  disabled={meaningIndex === 0}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-xl font-semibold text-[#6d35cb] disabled:opacity-40"
                >
                  {"<"}
                </button>
                <p className="text-sm font-semibold text-[#5f4f78]">
                  Meaning {meaningIndex + 1} of {contentCount}
                </p>
                <button
                  type="button"
                  onClick={() => setMeaningIndex((current) => Math.min(current + 1, contentCount - 1))}
                  disabled={meaningIndex >= contentCount - 1}
                  className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-xl font-semibold text-[#6d35cb] disabled:opacity-40"
                >
                  {">"}
                </button>
              </div>
            )}
          </div>
        </section>

        {(detail.confusable_words.length > 0 || hasWordLevelForms) && (
          <section className="space-y-3 rounded-[0.55rem] bg-[#f5f6fb] px-3 py-3">
            <div className="text-center">
              <p className="text-sm font-semibold tracking-[0.12em] text-[#8e38f2]">Pro Tips</p>
            </div>

            {detail.confusable_words.length > 0 && (
              <article className="rounded-[0.45rem] bg-white px-4 py-4 shadow-[0_6px_16px_rgba(86,54,145,0.06)]">
                <h2 className="text-lg font-semibold text-[#572c80]">Confusing Words</h2>
                <p className="mt-1 text-sm leading-6 text-[#7a6d90]">
                  Watch these nearby forms before you mark the word as fully known.
                </p>
                <div className="mt-3 space-y-3">
                  {detail.confusable_words.map((item) => (
                    <div
                      key={`${item.word}-${item.note ?? "note"}`}
                      className="rounded-[0.4rem] bg-[#f8f5fc] px-4 py-3"
                    >
                      {item.target ? (
                        <button
                          type="button"
                          onClick={() => openOverlay(item.target!)}
                          className="font-semibold text-[#53287c]"
                        >
                          {item.word}
                        </button>
                      ) : (
                        <p className="font-semibold text-[#53287c]">{item.word}</p>
                      )}
                      {item.note && (
                        <p className="mt-1 text-sm leading-6 text-[#75698a]">{item.note}</p>
                      )}
                    </div>
                  ))}
                </div>
              </article>
            )}

            {hasWordLevelForms && detail.forms && Object.values(detail.forms.verb_forms).some((value) => Boolean(value)) && (
              <article className="rounded-[0.45rem] bg-white px-4 py-4 shadow-[0_6px_16px_rgba(86,54,145,0.06)]">
                <h2 className="text-lg font-semibold text-[#572c80]">Verb Forms</h2>
                <div className="mt-3 grid grid-cols-2 gap-2 text-sm text-[#5e4a74]">
                  {Object.entries(detail.forms.verb_forms)
                    .filter(([, value]) => value)
                    .map(([label, value]) => (
                      <div key={label} className="rounded-[0.45rem] bg-[#f8f5fc] px-3 py-2">
                        <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                          {label.replaceAll("_", " ")}
                        </p>
                        <p className="mt-1 font-semibold text-[#53287c]">{value}</p>
                      </div>
                    ))}
                </div>
              </article>
            )}

            {hasWordLevelForms && detail.forms && (detail.forms.plural_forms.length > 0 || detail.forms.comparative || detail.forms.superlative) && (
              <article className="rounded-[0.45rem] bg-white px-4 py-4 shadow-[0_6px_16px_rgba(86,54,145,0.06)]">
                <h2 className="text-lg font-semibold text-[#572c80]">Word Variants</h2>
                <div className="mt-3 space-y-3">
                  {detail.forms.plural_forms.length > 0 && (
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                        Plural Forms
                      </p>
                      <div className="mt-2 flex flex-wrap gap-2">
                        {detail.forms.plural_forms.map((item) => (
                          <span
                            key={item}
                            className="rounded-full bg-[#f6f4fb] px-3 py-1.5 text-sm font-semibold text-[#684f85]"
                          >
                            {item}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {detail.forms.comparative && (
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                        Comparative
                      </p>
                      <p className="mt-2 text-sm font-semibold text-[#53287c]">{detail.forms.comparative}</p>
                    </div>
                  )}

                  {detail.forms.superlative && (
                    <div>
                      <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                        Superlative
                      </p>
                      <p className="mt-2 text-sm font-semibold text-[#53287c]">{detail.forms.superlative}</p>
                    </div>
                  )}
                </div>
              </article>
            )}

            {hasWordLevelForms && detail.forms && detail.forms.derivations.length > 0 && (
              <article className="rounded-[0.45rem] bg-white px-4 py-4 shadow-[0_6px_16px_rgba(86,54,145,0.06)]">
                <h2 className="text-lg font-semibold text-[#572c80]">Derivations</h2>
                <div className="mt-3 flex flex-wrap gap-2">
                  {detail.forms.derivations.map((item) =>
                    renderLinkPill(item, `derivation-${item.text}`, openOverlay),
                  )}
                </div>
              </article>
            )}
          </section>
        )}

        <div
          data-testid="knowledge-detail-bottom-bar"
          className="fixed bottom-[calc(env(safe-area-inset-bottom,0px)+5.85rem)] left-1/2 z-30 flex w-[min(46rem,calc(100vw-1rem))] -translate-x-1/2 flex-col gap-2 rounded-[0.65rem] bg-[rgba(245,240,252,0.96)] p-2.5 shadow-[0_12px_26px_rgba(84,46,135,0.14)] backdrop-blur"
        >
          {statusActionError ? (
            <p className="rounded-[0.75rem] border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
              {statusActionError}
            </p>
          ) : null}
          <div className="flex items-stretch gap-3">
            <div className={`grid flex-1 gap-3 ${statusActions.length === 2 ? "grid-cols-2" : "grid-cols-3"}`}>
              {statusActions.map((action) => (
                <button
                  key={action.status}
                  type="button"
                  onClick={() => void updateStatus(action.status)}
                  disabled={statusActionSaving}
                  className={`rounded-[0.95rem] px-3 py-3 text-sm font-semibold disabled:opacity-60 ${actionButtonClass(action.status, detail.status)}`}
                >
                  {action.label}
                </button>
              ))}
            </div>
            {activeReviewScheduleOptions.length > 0 ? (
              <div className="w-[11.5rem] shrink-0 rounded-[0.95rem] border border-[#d9dcec] bg-white px-3 py-2.5">
                <p className="text-[0.68rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]">
                  Next Review
                </p>
                <p className="mt-2 text-sm font-semibold text-[#53287c]">{scheduledReviewMessage}</p>
                {approximateScheduledReview ? (
                  <p className="mt-2 text-[0.72rem] text-[#6e5a86]">
                    Approximately: {approximateScheduledReview}
                  </p>
                ) : null}
                <button
                  type="button"
                  onClick={() => {
                    setScheduleDraftValue(activeReviewScheduleValue);
                    setIsScheduleSheetOpen(true);
                  }}
                  disabled={queueScheduleSaving || reviewSaving}
                  className="mt-2 w-full rounded-[0.6rem] border border-[#d9dcec] px-3 py-2 text-sm font-semibold text-[#684f85] disabled:opacity-50"
                >
                  Override{hasManualScheduleOverride ? " (manual override)" : ""}
                </button>
              </div>
            ) : null}
          </div>
        </div>
      </div>

      {isScheduleSheetOpen && activeReviewScheduleOptions.length > 0 ? (
        <div className="fixed inset-0 z-40 flex items-end justify-center bg-[rgba(16,10,34,0.38)] px-4 pb-6 sm:items-center">
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Override next review"
            className="w-full max-w-[24rem] rounded-[1rem] bg-white p-4 text-[#43235f] shadow-[0_20px_42px_rgba(21,12,46,0.35)]"
          >
            <p className="text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8e38f2]">
              Override next review
            </p>
            <p className="mt-2 text-sm font-semibold text-[#53287c]">
              {matchingReviewReveal
                ? "Next review scheduled: Scheduled time will be set when you continue review."
                : `Next review scheduled: ${buildScheduledReviewMessage(
                    detailReviewQueue,
                    detailReviewQueue?.current_schedule_label ?? activeReviewScheduleLabel,
                  )}`}
            </p>
            {scheduleSheetApproximateReview ? (
              <p className="mt-1 text-sm text-[#6e5a86]">
                Approximately: {scheduleSheetApproximateReview}
              </p>
            ) : null}
            <p className="mt-2 text-sm leading-6 text-[#6e5a86]">
              {matchingReviewReveal
                ? "Choose a manual override for this review result before you continue."
                : "Choose a manual override or keep the current scheduled time."}
            </p>
            <label
              htmlFor="detail-review-override"
              className="mt-4 block text-[0.72rem] font-semibold uppercase tracking-[0.08em] text-[#8c7aa7]"
            >
              Choose next review timing
            </label>
            <select
              id="detail-review-override"
              value={scheduleDraftValue}
              onChange={(event) => setScheduleDraftValue(event.target.value)}
              disabled={queueScheduleSaving || reviewSaving}
              className="mt-2 w-full rounded-[0.6rem] border border-[#d9dcec] bg-white px-3 py-2 text-sm text-[#43235f] disabled:opacity-50"
              aria-label="Choose next review timing"
            >
              {activeReviewScheduleOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <div className="mt-4 grid grid-cols-2 gap-3">
              <button
                type="button"
                onClick={() => {
                  setScheduleDraftValue(activeReviewScheduleValue);
                  setIsScheduleSheetOpen(false);
                }}
                className="rounded-[0.8rem] border border-[#d9dcec] px-3 py-2 text-sm font-semibold text-[#684f85]"
              >
                Leave current schedule
              </button>
              <button
                type="button"
                onClick={() => void handleConfirmScheduleDraft()}
                disabled={queueScheduleSaving || reviewSaving}
                className="rounded-[0.8rem] bg-[#45c5dd] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {queueScheduleSaving ? "Saving..." : "Confirm next review change"}
              </button>
            </div>
          </div>
        </div>
      ) : null}

      {overlayTarget && (
        <div className="fixed inset-0 z-40 flex items-center justify-center bg-[rgba(16,10,34,0.52)] px-4">
          <div
            role="dialog"
            aria-modal="true"
            aria-label={overlayTarget.display_text ?? "Quick lookup"}
            className="w-full max-w-[25rem] overflow-hidden rounded-[1rem] bg-white shadow-[0_20px_42px_rgba(21,12,46,0.35)]"
          >
            <div className="h-40" style={buildHeroStyle(overlayTarget.display_text ?? overlayTarget.entry_id)} />
            <div className="space-y-3 px-4 py-4 text-[#43235f]">
              {overlayState === "loading" && (
                <p className="text-sm text-[#6d6084]">Loading quick detail...</p>
              )}
              {overlayState === "error" && (
                <p className="text-sm text-[#6d6084]">This quick lookup is unavailable right now.</p>
              )}
              {overlayState === "ready" && overlayDetail && (
                <>
                  <div className="space-y-1">
                    <div className="flex items-start justify-between gap-3">
                      <h2 className="text-[1.4rem] font-semibold text-[#572c80]">
                        {overlayDetail.display_text}
                      </h2>
                      <span className="text-[0.7rem] font-semibold uppercase tracking-[0.12em] text-[#7ebed7]">
                        {overlayContent?.part_of_speech ?? overlayDetail.entry_type}
                      </span>
                    </div>
                    {overlayDetail.pronunciation ? (
                      <p className="text-sm font-semibold text-[#7c7395]">
                        {overlayDetail.pronunciation}
                      </p>
                    ) : null}
                  </div>

                  <p className="text-[0.98rem] font-semibold leading-6 text-[#4d295f]">
                    {overlayContent?.definition ?? overlayDetail.primary_definition}
                  </p>

                  {showTranslations && overlayTranslation && (
                    <p className="text-sm font-semibold text-[#9a39f2]">{overlayTranslation}</p>
                  )}

                  {overlayUsageNote && (
                    <p className="rounded-[0.65rem] bg-[#f8f5fc] px-3 py-2 text-sm leading-6 text-[#5e4a74]">
                      {overlayUsageNote}
                    </p>
                  )}

                  {overlayExample && (
                    <div className="rounded-[0.65rem] bg-[#eef8ff] px-3 py-3">
                      <p className="text-sm italic leading-6 text-[#4c4f72]">{overlayExample.sentence}</p>
                      {showTranslations && normalizeLearnerTranslation(overlayExample.translation) && (
                        <p className="mt-2 text-sm leading-6 text-[#1687a6]">
                          {normalizeLearnerTranslation(overlayExample.translation)}
                        </p>
                      )}
                    </div>
                  )}
                </>
              )}

              <div className="grid grid-cols-2 gap-3 pt-1">
                <Link
                  href={getKnowledgeEntryHref(overlayTarget.entry_type, overlayTarget.entry_id)}
                  className="rounded-[0.95rem] bg-[#f1ddff] px-4 py-3 text-center text-sm font-semibold text-[#7d2cff]"
                >
                  Look up
                </Link>
                <button
                  type="button"
                  onClick={closeOverlay}
                  className="rounded-[0.95rem] bg-[#45c5dd] px-4 py-3 text-sm font-semibold text-white"
                >
                  Got it!
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
