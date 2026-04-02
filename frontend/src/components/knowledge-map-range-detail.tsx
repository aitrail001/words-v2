"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { startTransition, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getKnowledgeMapEntryDetail,
  getKnowledgeMapRange,
  normalizeLearnerTranslation,
  type KnowledgeMapEntryDetail,
  type KnowledgeMapRange,
  type KnowledgeMapEntrySummary,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import {
  getEntryLevelVoiceAssets,
  getPlayableLearnerAccents,
  playLearnerEntryAudio,
  resolveDisplayedPronunciation,
} from "@/lib/learner-audio";
import {
  DEFAULT_USER_PREFERENCES,
  getUserPreferences,
  updateUserPreferences,
  type UserPreferences,
} from "@/lib/user-preferences-client";

type ViewMode = "cards" | "tags" | "list";

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "To Learn",
  learning: "Learning",
  known: "Known",
};

const STATUS_COLORS: Record<KnowledgeStatus, string> = {
  undecided: "#d8dced",
  to_learn: "#a62cff",
  learning: "#c563ff",
  known: "#36c3de",
};

const VIEW_OPTIONS: Array<{ mode: ViewMode; label: string }> = [
  { mode: "cards", label: "Cards view" },
  { mode: "tags", label: "Tags view" },
  { mode: "list", label: "List view" },
];

const PRIMARY_STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "Should Learn" },
  { status: "known", label: "Already Know" },
];

const READY_TO_LEARN_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "learning", label: "Learn Now" },
  { status: "known", label: "Already Know" },
];

const SECONDARY_STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "learning", label: "Learning" },
  { status: "known", label: "Known" },
];

function getCardActions(status: KnowledgeStatus): Array<{ status: KnowledgeStatus; label: string }> {
  if (status === "undecided") {
    return PRIMARY_STATUS_ACTIONS;
  }
  if (status === "to_learn") {
    return READY_TO_LEARN_ACTIONS;
  }
  return SECONDARY_STATUS_ACTIONS;
}

function buildHeroStyle(seed: string): CSSProperties {
  const palettes = [
    ["#27124f", "#5a1fb6", "#38c6df"],
    ["#3a1762", "#9f27ff", "#44d6c8"],
    ["#2b165f", "#7040ff", "#59c9f3"],
    ["#34114f", "#bf31ff", "#32bbdf"],
  ];
  const hash = Array.from(seed).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  const palette = palettes[hash % palettes.length];

  return {
    backgroundImage: [
      `radial-gradient(circle at 25% 20%, rgba(255,255,255,0.28), transparent 18%)`,
      `radial-gradient(circle at 78% 14%, rgba(255,255,255,0.22), transparent 14%)`,
      `radial-gradient(circle at 70% 75%, ${palette[2]}aa, transparent 28%)`,
      `linear-gradient(145deg, ${palette[0]} 0%, ${palette[1]} 58%, ${palette[2]} 100%)`,
    ].join(", "),
  };
}

function statusChipClass(status: KnowledgeStatus): string {
  switch (status) {
    case "known":
      return "bg-[#dcfbff] text-[#1485a5]";
    case "learning":
      return "bg-[#f0d9ff] text-[#8d3cff]";
    case "to_learn":
      return "bg-[#ecd6ff] text-[#8e26ff]";
    default:
      return "bg-[#e4e7f3] text-[#59607d]";
  }
}

function primaryStatusButtonClass(status: KnowledgeStatus): string {
  if (status === "known") {
    return "bg-[#45c5dd] text-white";
  }
  return "bg-[#a52fff] text-white";
}

function MiniRangeStrip({
  selectedRange,
  activeIndex,
  onSelectIndex,
  onNavigateRange,
}: {
  selectedRange: KnowledgeMapRange | null;
  activeIndex: number;
  onSelectIndex: (index: number) => void;
  onNavigateRange: (rangeStart: number) => void;
}) {
  if (!selectedRange) {
    return null;
  }

  return (
    <div
      data-testid="knowledge-range-strip"
      className="rounded-[1.55rem] bg-white/88 px-3 py-3 shadow-[0_18px_42px_rgba(84,46,135,0.12)]"
    >
      <div className="flex items-center justify-between gap-4">
        {selectedRange.previous_range_start ? (
          <button
            type="button"
            aria-label="Previous range"
            onClick={() => onNavigateRange(selectedRange.previous_range_start as number)}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#efe8fb] text-xl font-semibold text-[#6d35cb]"
          >
            {"<"}
          </button>
        ) : (
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f4eefc] text-xl font-semibold text-[#b7adc8]">
            {"<"}
          </span>
        )}
        <p className="text-center text-sm font-semibold text-[#5f4f78]">
          Range {selectedRange.range_start.toLocaleString()} - {selectedRange.range_end.toLocaleString()}
        </p>
        {selectedRange.next_range_start ? (
          <button
            type="button"
            aria-label="Next range"
            onClick={() => onNavigateRange(selectedRange.next_range_start as number)}
            className="flex h-10 w-10 items-center justify-center rounded-full bg-[#efe8fb] text-xl font-semibold text-[#6d35cb]"
          >
            {">"}
          </button>
        ) : (
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-[#f4eefc] text-xl font-semibold text-[#b7adc8]">
            {">"}
          </span>
        )}
      </div>

      <div
        className="mt-3 grid gap-[2px] rounded-[0.95rem] bg-[#f4eefc] p-2"
        style={{ gridTemplateColumns: "repeat(25, minmax(0, 1fr))" }}
      >
        {selectedRange.items.map((item, index) => (
          <button
            key={`${item.entry_type}-${item.entry_id}`}
            type="button"
            onClick={() => onSelectIndex(index)}
            aria-label={item.display_text}
            className={`h-2.5 rounded-[3px] transition ${
              index === activeIndex ? "ring-2 ring-[#ffffff]" : ""
            }`}
            style={{ backgroundColor: STATUS_COLORS[item.status] }}
          />
        ))}
      </div>
    </div>
  );
}

function EntryPager({
  canGoPrevious,
  canGoNext,
  onPrevious,
  onNext,
}: {
  canGoPrevious: boolean;
  canGoNext: boolean;
  onPrevious: () => void;
  onNext: () => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 rounded-[0.8rem] bg-white/88 px-3 py-2 shadow-[0_10px_24px_rgba(84,46,135,0.08)]">
      <button
        type="button"
        aria-label="Previous entry"
        onClick={onPrevious}
        disabled={!canGoPrevious}
        className="flex items-center gap-2 rounded-full bg-[#efe8fb] px-3 py-2 text-[0.78rem] font-semibold text-[#6d35cb] disabled:bg-[#f4eefc] disabled:text-[#b7adc8]"
      >
        <span>{"<"}</span>
        <span>Previous Word</span>
      </button>
      <button
        type="button"
        aria-label="Next entry"
        onClick={onNext}
        disabled={!canGoNext}
        className="flex items-center gap-2 rounded-full bg-[#efe8fb] px-3 py-2 text-[0.78rem] font-semibold text-[#6d35cb] disabled:bg-[#f4eefc] disabled:text-[#b7adc8]"
      >
        <span>Next Word</span>
        <span>{">"}</span>
      </button>
    </div>
  );
}

export function KnowledgeMapRangeDetail({ initialRangeStart }: { initialRangeStart: number }) {
  const router = useRouter();
  const [selectedRange, setSelectedRange] = useState<KnowledgeMapRange | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const [showTranslations, setShowTranslations] = useState(true);
  const [translationLocale, setTranslationLocale] = useState<UserPreferences["translation_locale"]>("zh-Hans");
  const [accentPreference, setAccentPreference] = useState<UserPreferences["accent_preference"]>("us");
  const [loadingRange, setLoadingRange] = useState(true);
  const [rangeError, setRangeError] = useState(false);
  const [activeEntryDetail, setActiveEntryDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [entryDetailCache, setEntryDetailCache] = useState<Record<string, KnowledgeMapEntryDetail>>({});
  const [activeMeaningIndex, setActiveMeaningIndex] = useState(0);
  const dragStartXRef = useRef<number | null>(null);
  const activeRangeItems = useMemo(() => selectedRange?.items ?? [], [selectedRange]);
  const normalizedRangeItems = useMemo(
    () =>
      activeRangeItems.map((item) => ({
        ...item,
        normalizedTranslation: normalizeLearnerTranslation(item.translation),
      })),
    [activeRangeItems],
  );
  const activeRangeEntry = activeRangeItems[activeIndex] ?? null;
  const activeEntryId = activeRangeEntry?.entry_id ?? null;
  const activeEntryType = activeRangeEntry?.entry_type ?? null;
  const activeEntryKey = activeRangeEntry
    ? `${activeRangeEntry.entry_type}:${activeRangeEntry.entry_id}`
    : null;

  useEffect(() => {
    let active = true;

    getUserPreferences()
      .then((preferences) => {
        if (!active) {
          return;
        }
        setViewMode(preferences.knowledge_view_preference);
        setShowTranslations(preferences.show_translations_by_default);
        setTranslationLocale(preferences.translation_locale);
        setAccentPreference(preferences.accent_preference);
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, []);

  const loadRange = async (rangeStart: number) => {
    setLoadingRange(true);
    setRangeError(false);
    setActiveEntryDetail(null);

    try {
      const range = await getKnowledgeMapRange(rangeStart);
      setSelectedRange(range);
      setActiveIndex(0);
    } catch {
      setSelectedRange(null);
      setRangeError(true);
    } finally {
      setLoadingRange(false);
    }
  };

  useEffect(() => {
    void loadRange(initialRangeStart);
  }, [initialRangeStart]);

  useEffect(() => {
    let active = true;
    setActiveMeaningIndex(0);

    if (!activeEntryId || !activeEntryType || !activeEntryKey) {
      setActiveEntryDetail(null);
      return () => {
        active = false;
      };
    }

    const cachedDetail = entryDetailCache[activeEntryKey];
    if (cachedDetail) {
      setActiveEntryDetail(cachedDetail);
      return () => {
        active = false;
      };
    }

    setActiveEntryDetail(null);
    getKnowledgeMapEntryDetail(activeEntryType, activeEntryId)
      .then((detail) => {
        if (!active) {
          return;
        }
        setEntryDetailCache((current) => ({ ...current, [activeEntryKey]: detail }));
        setActiveEntryDetail(detail);
        setSelectedRange((current) => {
          if (!current) {
            return current;
          }
          let changed = false;
          const nextItems = current.items.map((item) => {
            if (!(item.entry_id === detail.entry_id && item.entry_type === detail.entry_type)) {
              return item;
            }

            const nextPartOfSpeech =
              detail.entry_type === "word"
                ? detail.meanings[0]?.part_of_speech ?? item.part_of_speech
                : detail.senses[0]?.part_of_speech ?? item.part_of_speech;

            if (
              item.pronunciation === detail.pronunciation &&
              JSON.stringify(item.pronunciations ?? {}) === JSON.stringify(detail.pronunciations ?? {}) &&
              item.translation === detail.translation &&
              item.primary_definition === detail.primary_definition &&
              item.part_of_speech === nextPartOfSpeech &&
              item.voice_assets === detail.voice_assets
            ) {
              return item;
            }

            changed = true;
            return {
              ...item,
              pronunciation: detail.pronunciation,
              pronunciations: detail.pronunciations,
              translation: detail.translation,
              primary_definition: detail.primary_definition,
              part_of_speech: nextPartOfSpeech,
              voice_assets: detail.voice_assets ?? item.voice_assets,
            };
          });

          return changed ? { ...current, items: nextItems } : current;
        });
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [activeEntryId, activeEntryKey, activeEntryType, entryDetailCache]);

  const activeEntry = activeRangeEntry;
  const selectedEntryDetail =
    activeEntry && activeEntryDetail &&
    activeEntry.entry_id === activeEntryDetail.entry_id &&
    activeEntry.entry_type === activeEntryDetail.entry_type
      ? activeEntryDetail
      : null;
  const activeContentItems = selectedEntryDetail
    ? selectedEntryDetail.entry_type === "word"
      ? selectedEntryDetail.meanings
      : selectedEntryDetail.senses
    : [];
  const activeContentCount = activeContentItems.length;
  const activeCardContent =
    activeContentItems[Math.min(activeMeaningIndex, Math.max(activeContentCount - 1, 0))] ?? null;
  const activeCardTranslation =
    selectedEntryDetail?.entry_type === "word"
      ? selectedEntryDetail.meanings[
          Math.min(activeMeaningIndex, Math.max(selectedEntryDetail.meanings.length - 1, 0))
        ]?.translations?.find((translation) => translation.language === translationLocale)?.translation ??
        selectedEntryDetail.meanings[
          Math.min(activeMeaningIndex, Math.max(selectedEntryDetail.meanings.length - 1, 0))
        ]?.translations?.[0]?.translation ??
        activeEntry?.translation
      : activeEntry?.translation;
  const normalizedActiveCardTranslation = useMemo(
    () => normalizeLearnerTranslation(activeCardTranslation),
    [activeCardTranslation],
  );

  const moveMeaning = (direction: -1 | 1) => {
    if (activeContentCount <= 1) {
      return;
    }
    setActiveMeaningIndex((current) =>
      Math.max(0, Math.min(current + direction, activeContentCount - 1)),
    );
  };

  const handleMeaningPointerDown = (clientX: number) => {
    dragStartXRef.current = clientX;
  };

  const handleMeaningPointerUp = (clientX: number) => {
    if (dragStartXRef.current == null) {
      return;
    }
    const delta = clientX - dragStartXRef.current;
    dragStartXRef.current = null;
    if (Math.abs(delta) < 30) {
      return;
    }
    moveMeaning(delta < 0 ? 1 : -1);
  };

  const updateStatus = async (entry: KnowledgeMapEntrySummary, status: KnowledgeStatus) => {
    const response = await updateKnowledgeEntryStatus(entry.entry_type, entry.entry_id, status);

    startTransition(() => {
      setSelectedRange((current) => {
        if (!current) {
          return current;
        }
        return {
          ...current,
          items: current.items.map((item) =>
            item.entry_id === entry.entry_id && item.entry_type === entry.entry_type
              ? { ...item, status: response.status }
              : item,
          ),
        };
      });
    });
  };

  const activeRangeLabel = selectedRange
    ? `Range ${selectedRange.range_start.toLocaleString()}-${selectedRange.range_end.toLocaleString()}`
    : "Pick a tile to begin";
  const canGoPreviousEntry = activeIndex > 0;
  const canGoNextEntry = selectedRange ? activeIndex < selectedRange.items.length - 1 : false;
  const activeCardActions = activeEntry ? getCardActions(activeEntry.status) : [];
  const activeEntryVoiceAssets = getEntryLevelVoiceAssets(
    selectedEntryDetail?.voice_assets ?? activeEntry?.voice_assets ?? [],
  );
  const activeDisplayedPronunciation = activeEntry
    ? resolveDisplayedPronunciation(
        selectedEntryDetail?.pronunciation ?? activeEntry.pronunciation,
        selectedEntryDetail?.pronunciations ?? activeEntry.pronunciations,
        accentPreference,
      )
    : null;
  const playableAccents = (() => {
    const activeAccents = getPlayableLearnerAccents(activeEntryVoiceAssets);
    if (activeAccents.length > 0) {
      return activeAccents;
    }
    return getPlayableLearnerAccents(activeRangeItems.flatMap((item) => item.voice_assets ?? []));
  })();

  const updateAccentPreference = (accent: UserPreferences["accent_preference"]) => {
    if (accent === accentPreference) {
      return;
    }
    setAccentPreference(accent);
    void updateUserPreferences({
      ...DEFAULT_USER_PREFERENCES,
      accent_preference: accent,
      translation_locale: translationLocale,
      knowledge_view_preference: viewMode,
      show_translations_by_default: showTranslations,
    }).catch(() => undefined);
  };

  const handlePlayAudio = (voiceAssets: KnowledgeMapEntrySummary["voice_assets"] | undefined) => {
    void playLearnerEntryAudio(getEntryLevelVoiceAssets(voiceAssets), accentPreference, {
      contentScope: "word",
    }).catch(() => undefined);
  };

  return (
    <section className="space-y-3 rounded-[0.8rem] bg-[#f1f2f8] px-2 py-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h3 className="text-[1.55rem] font-semibold tracking-tight text-[#53287c]">Knowledge Map</h3>
          <h4 className="mt-1 text-sm font-semibold text-[#766389]">{activeRangeLabel}</h4>
        </div>
        <div className="flex items-center gap-1.5">
          {playableAccents.map((accent) => (
            <button
              key={accent}
              type="button"
              aria-label={`Use ${accent.toUpperCase()} accent`}
              aria-pressed={accentPreference === accent}
              onClick={() => updateAccentPreference(accent)}
              className={`rounded-full px-2.5 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.12em] transition ${
                accentPreference === accent
                  ? "bg-[#1485a5] text-white"
                  : "bg-[#e8f5fb] text-[#1687a6]"
              }`}
            >
              {accent.toUpperCase()}
            </button>
          ))}
          {VIEW_OPTIONS.map((option) => (
            <button
              key={option.mode}
              type="button"
              onClick={() => setViewMode(option.mode)}
              className={`rounded-full px-2.5 py-1.5 text-[0.68rem] font-semibold uppercase tracking-[0.12em] transition ${
                viewMode === option.mode
                  ? "bg-[#5b238c] text-white"
                  : "bg-[#f0eafb] text-[#6d42a9]"
              }`}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      {loadingRange && <p className="text-sm text-[#7e7293]">Loading range...</p>}
      {!loadingRange && rangeError && (
        <p className="text-sm font-semibold text-[#7f5170]">Unable to load this range.</p>
      )}

      {!loadingRange && selectedRange && viewMode === "cards" && activeEntry && (
        <div data-testid="knowledge-card-view" className="space-y-2">
          <div className="overflow-hidden rounded-[0.35rem] border border-[#dce0ee] bg-white shadow-[0_6px_14px_rgba(94,53,177,0.06)]">
            <div className="relative h-64 overflow-hidden" style={buildHeroStyle(activeEntry.display_text)}>
              <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 py-4 text-white">
                <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]">
                  {activeEntry.entry_type}
                </span>
                <button
                  type="button"
                  className="flex h-7 w-7 items-center justify-center rounded-full bg-white/20 text-xs font-semibold"
                  aria-label="Card options"
                >
                  •••
                </button>
              </div>
            </div>

            <div className="space-y-2 px-3 py-3">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h4 className="text-[1.25rem] font-semibold leading-none text-[#572a80]">
                    {activeEntry.display_text}
                  </h4>
                  <div className="mt-1 flex flex-wrap items-center gap-2 text-[0.8rem] font-semibold text-[#8f82a1]">
                    {activeEntryVoiceAssets.length > 0 && (
                      <button
                        type="button"
                        aria-label={`Play audio for ${activeEntry.display_text}`}
                        onClick={() => handlePlayAudio(activeEntryVoiceAssets)}
                        className="rounded-full bg-[#eef8ff] px-2.5 py-1 text-[0.72rem] text-[#1687a6]"
                      >
                        Play
                      </button>
                    )}
                    <span>{activeDisplayedPronunciation ?? "/.../"}</span>
                    <span>#{activeEntry.browse_rank.toLocaleString()}</span>
                  </div>
                </div>
                <span className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-[#87bed4]">
                  {activeEntry.part_of_speech ?? activeEntry.entry_type}
                </span>
                <span className="sr-only">Status: {STATUS_LABELS[activeEntry.status]}</span>
              </div>

              {showTranslations && (
                <p className="text-sm font-semibold text-[#9c3af2]">
                  {normalizedActiveCardTranslation}
                </p>
              )}
              <div
                className="space-y-2"
                onMouseDown={(event) => handleMeaningPointerDown(event.clientX)}
                onMouseUp={(event) => handleMeaningPointerUp(event.clientX)}
                onTouchStart={(event) => handleMeaningPointerDown(event.touches[0]?.clientX ?? 0)}
                onTouchEnd={(event) => handleMeaningPointerUp(event.changedTouches[0]?.clientX ?? 0)}
              >
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    aria-label="Previous definition"
                    onClick={() => moveMeaning(-1)}
                    disabled={activeContentCount <= 1 || activeMeaningIndex === 0}
                    className="flex h-7 w-7 items-center justify-center rounded-[0.25rem] border border-[#d7d7ea] bg-white text-[0.8rem] font-semibold text-[#6e5d87] disabled:opacity-40"
                  >
                    ←
                  </button>
                  <div className="min-w-0 flex-1 rounded-[0.3rem] bg-[#f8f7fb] px-3 py-2">
                    <p className="text-[0.92rem] leading-6 text-[#4e3564]">
                      {activeCardContent?.definition ??
                        activeEntry.primary_definition ??
                        "No learner definition has been generated yet."}
                    </p>
                  </div>
                  <button
                    type="button"
                    aria-label="Next definition"
                    onClick={() => moveMeaning(1)}
                    disabled={activeContentCount <= 1 || activeMeaningIndex >= activeContentCount - 1}
                    className="flex h-7 w-7 items-center justify-center rounded-[0.25rem] border border-[#d7d7ea] bg-white text-[0.8rem] font-semibold text-[#6e5d87] disabled:opacity-40"
                  >
                    →
                  </button>
                </div>
                {activeContentCount > 1 && (
                  <p className="text-center text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-[#998eb0]">
                    Definition {activeMeaningIndex + 1} of {activeContentCount}
                  </p>
                )}
              </div>

              <div className="pt-0.5 text-right">
                <Link
                  href={getKnowledgeEntryHref(activeEntry.entry_type, activeEntry.entry_id)}
                  className="text-[0.8rem] font-semibold text-[#9a86b5]"
                >
                  Learn More
                </Link>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1.5">
                {activeCardActions.map((action) => (
                  <button
                    key={`${activeEntry.entry_id}-${action.status}-${action.label}`}
                    type="button"
                    onClick={() => void updateStatus(activeEntry, action.status)}
                    className={`rounded-[0.3rem] px-3 py-2.5 text-sm font-semibold ${primaryStatusButtonClass(action.status)}`}
                  >
                    {action.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          <EntryPager
            canGoPrevious={canGoPreviousEntry}
            canGoNext={canGoNextEntry}
            onPrevious={() => setActiveIndex((current) => Math.max(current - 1, 0))}
            onNext={() =>
              setActiveIndex((current) =>
                selectedRange ? Math.min(current + 1, selectedRange.items.length - 1) : current,
              )
            }
          />
        </div>
      )}

      {!loadingRange && selectedRange && viewMode === "tags" && (
        <div data-testid="knowledge-tags-view" className="grid grid-cols-4 gap-1.5">
          {selectedRange.items.map((item) => (
            <Link
              key={`${item.entry_type}-${item.entry_id}`}
              href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
              className="rounded-[0.45rem] px-2 py-3 text-center text-[0.72rem] font-semibold text-white shadow-sm"
              style={{ backgroundColor: STATUS_COLORS[item.status] }}
            >
              {item.display_text}
            </Link>
          ))}
        </div>
      )}

      {!loadingRange && selectedRange && viewMode === "list" && (
        <div data-testid="knowledge-list-view" className="space-y-2">
          {normalizedRangeItems.map((item) => (
            <div
              key={`${item.entry_type}-${item.entry_id}`}
              className="grid grid-cols-[4.2rem_1fr] gap-2 overflow-hidden rounded-[0.25rem] border border-[#dce0ee] bg-white px-2 py-2"
            >
              <div className="min-h-[4.4rem] rounded-[0.15rem]" style={buildHeroStyle(item.display_text)} />
              <div className="space-y-1 py-0.5 pr-1">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[1.02rem] font-semibold text-[#562c7f]">{item.display_text}</p>
                    <p className="text-[0.8rem] font-semibold leading-5 text-[#a141ef]">
                      {item.primary_definition ?? "No summary yet"}
                    </p>
                    {item.normalizedTranslation && (
                      <p className="text-[0.8rem] font-semibold leading-5 text-[#a141ef]">
                        {item.normalizedTranslation}
                      </p>
                    )}
                  </div>
                  <span className={`rounded-[0.25rem] px-2 py-1 text-[0.68rem] font-semibold ${statusChipClass(item.status)}`}>
                    {STATUS_LABELS[item.status]}
                  </span>
                </div>
                <Link
                  href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
                  className="inline-flex rounded-[0.25rem] bg-[#f1ddff] px-2.5 py-1 text-[0.7rem] font-semibold text-[#7c2cff]"
                >
                  Open
                </Link>
                {getEntryLevelVoiceAssets(item.voice_assets).length > 0 && (
                  <button
                    type="button"
                    aria-label={`Play audio for ${item.display_text}`}
                    onClick={() => handlePlayAudio(item.voice_assets)}
                    className="ml-2 inline-flex rounded-[0.25rem] bg-[#eef8ff] px-2.5 py-1 text-[0.7rem] font-semibold text-[#1687a6]"
                  >
                    Play
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {!loadingRange && !rangeError && (
        <MiniRangeStrip
          selectedRange={selectedRange}
          activeIndex={activeIndex}
          onSelectIndex={setActiveIndex}
          onNavigateRange={(rangeStart) => {
            void loadRange(rangeStart);
            router.push(`/knowledge-map/range/${rangeStart}`);
          }}
        />
      )}
    </section>
  );
}
