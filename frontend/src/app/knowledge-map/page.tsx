"use client";

import Link from "next/link";
import { startTransition, useEffect, useRef, useState, type CSSProperties } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getKnowledgeMapEntryDetail,
  type KnowledgeMapEntryDetail,
  getKnowledgeMapOverview,
  getKnowledgeMapRange,
  type KnowledgeMapEntrySummary,
  type KnowledgeMapOverview,
  type KnowledgeMapRange,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

type ViewMode = "cards" | "tags" | "list";

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "Should Learn",
  learning: "Learning",
  known: "Known",
};

const STATUS_COLORS: Record<KnowledgeStatus, string> = {
  undecided: "#d8dced",
  to_learn: "#a62cff",
  learning: "#c563ff",
  known: "#36c3de",
};

const VIEW_OPTIONS: Array<{ mode: ViewMode; label: string; shortLabel: string }> = [
  { mode: "cards", label: "Cards view", shortLabel: "Cards" },
  { mode: "tags", label: "Tags view", shortLabel: "Tags" },
  { mode: "list", label: "List view", shortLabel: "List" },
];

const PRIMARY_STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "Should Learn" },
  { status: "known", label: "Already Know" },
];

const SECONDARY_STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "learning", label: "Learning" },
  { status: "known", label: "Known" },
];

function buildTileGradient(counts: Record<KnowledgeStatus, number>): string {
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  if (total <= 0) {
    return STATUS_COLORS.undecided;
  }

  const orderedStatuses: KnowledgeStatus[] = ["known", "learning", "to_learn", "undecided"];
  let offset = 0;
  const stops = orderedStatuses.map((status) => {
    const start = offset;
    offset += (counts[status] / total) * 100;
    return `${STATUS_COLORS[status]} ${start}% ${offset}%`;
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
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

function secondaryStatusButtonClass(active: boolean): string {
  return active
    ? "border-[#8f2fff] bg-[#f1ddff] text-[#7f22ff]"
    : "border-[#d7d7ea] bg-white text-[#6e5d87]";
}

function MiniRangeStrip({
  selectedRange,
  activeIndex,
  onPrevious,
  onNext,
  onSelectIndex,
}: {
  selectedRange: KnowledgeMapRange | null;
  activeIndex: number;
  onPrevious: () => void;
  onNext: () => void;
  onSelectIndex: (index: number) => void;
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
        <button
          type="button"
          onClick={onPrevious}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[#efe8fb] text-xl font-semibold text-[#6d35cb]"
        >
          {"<"}
        </button>
        <p className="text-center text-sm font-semibold text-[#5f4f78]">
          Range {selectedRange.range_start.toLocaleString()} - {selectedRange.range_end.toLocaleString()}
        </p>
        <button
          type="button"
          onClick={onNext}
          className="flex h-10 w-10 items-center justify-center rounded-full bg-[#efe8fb] text-xl font-semibold text-[#6d35cb]"
        >
          {">"}
        </button>
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

export default function HomePage() {
  const [overview, setOverview] = useState<KnowledgeMapOverview | null>(null);
  const [selectedRange, setSelectedRange] = useState<KnowledgeMapRange | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const [showTranslations, setShowTranslations] = useState(true);
  const [loadingRange, setLoadingRange] = useState(false);
  const [activeEntryDetail, setActiveEntryDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [activeMeaningIndex, setActiveMeaningIndex] = useState(0);
  const dragStartXRef = useRef<number | null>(null);
  const activeRangeStart = selectedRange?.range_start ?? null;
  const activeRangeItems = selectedRange?.items ?? [];
  const activeRangeEntry = activeRangeItems[activeIndex] ?? null;

  useEffect(() => {
    let active = true;

    (async () => {
      const [preferences, overviewPayload] = await Promise.all([
        getUserPreferences(),
        getKnowledgeMapOverview(),
      ]);

      if (!active) {
        return;
      }

      setViewMode(preferences.knowledge_view_preference);
      setShowTranslations(preferences.show_translations_by_default);
      setOverview(overviewPayload);

      const requestedRangeStart = Number(
        typeof window === "undefined"
          ? null
          : new URLSearchParams(window.location.search).get("rangeStart"),
      );
      const preferredRangeStart = Number.isFinite(requestedRangeStart) && requestedRangeStart > 0
        ? requestedRangeStart
        : overviewPayload.ranges[0]?.range_start;
      const firstRange = overviewPayload.ranges.find((range) => range.range_start === preferredRangeStart)
        ?? overviewPayload.ranges[0];
      if (firstRange) {
        setLoadingRange(true);
        const range = await getKnowledgeMapRange(firstRange.range_start);
        if (!active) {
          return;
        }
        setSelectedRange(range);
        setActiveIndex(0);
        setLoadingRange(false);
      }
    })().catch(() => {
      if (!active) {
        return;
      }
      setOverview({ bucket_size: 100, total_entries: 0, ranges: [] });
      setSelectedRange(null);
      setLoadingRange(false);
    });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    const currentEntry = activeRangeEntry;
    if (!currentEntry) {
      setActiveEntryDetail(null);
      setActiveMeaningIndex(0);
      return () => {
        active = false;
      };
    }

    getKnowledgeMapEntryDetail(currentEntry.entry_type, currentEntry.entry_id)
      .then((detail) => {
        if (!active) {
          return;
        }
        setActiveEntryDetail(detail);
        setActiveMeaningIndex(0);
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
              item.translation === detail.translation &&
              item.primary_definition === detail.primary_definition &&
              item.part_of_speech === nextPartOfSpeech
            ) {
              return item;
            }

            changed = true;
            return {
              ...item,
              pronunciation: detail.pronunciation,
              translation: detail.translation,
              primary_definition: detail.primary_definition,
              part_of_speech: nextPartOfSpeech,
            };
          });

          if (!changed) {
            return current;
          }

          return {
            ...current,
            items: nextItems,
          };
        });
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [
    activeIndex,
    activeRangeEntry,
    activeRangeStart,
  ]);

  const activeEntry = activeRangeEntry;
  const activeContentItems = activeEntryDetail
    ? activeEntryDetail.entry_type === "word"
      ? activeEntryDetail.meanings
      : activeEntryDetail.senses
    : [];
  const activeContentCount = activeContentItems.length;
  const activeCardContent =
    activeContentItems[Math.min(activeMeaningIndex, Math.max(activeContentCount - 1, 0))] ?? null;
  const activeCardTranslation =
    activeEntryDetail?.entry_type === "word"
      ? activeEntryDetail.meanings[
          Math.min(activeMeaningIndex, Math.max(activeEntryDetail.meanings.length - 1, 0))
        ]?.translations?.[0]?.translation ??
        activeEntry?.translation
      : activeEntry?.translation;

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

  const loadRange = async (rangeStart: number) => {
    setLoadingRange(true);
    const range = await getKnowledgeMapRange(rangeStart);
    setSelectedRange(range);
    setActiveIndex(0);
    setLoadingRange(false);
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

  return (
    <div
      data-testid="knowledge-map-mobile-shell"
      className="mx-auto max-w-[46rem] space-y-3 pb-10 text-[#43235f]"
    >
      <section className="rounded-[0.8rem] bg-[#f1f2f8] px-2 py-2">
        <div className="flex items-center justify-between">
          <span className="w-8 text-xl text-[#7d52c7]">{""}</span>
          <h2 className="text-center text-[1.8rem] font-semibold tracking-tight text-[#502a7d]">
            Full Knowledge Map
          </h2>
          <span className="w-8 text-right text-sm font-semibold text-[#7d52c7]">
            {overview?.total_entries ?? "..."}
          </span>
        </div>
        <p className="mt-3 text-sm leading-6 text-[#6b5d86]">
          This is a map of your English knowledge. Each box shows 100 words and phrases.
          They are sorted by relevance to your life. Discover them all, starting from the top.
        </p>

        <div data-testid="knowledge-map-tile-grid" className="mt-3 grid grid-cols-5 gap-1">
          {overview?.ranges.map((range) => (
            <button
              key={range.range_start}
              type="button"
              onClick={() => void loadRange(range.range_start)}
              aria-label={`${range.range_start}-${range.range_end}`}
              className={`rounded-[0.18rem] border px-1 py-1.5 text-center text-[0.68rem] font-semibold shadow-sm transition ${
                selectedRange?.range_start === range.range_start
                  ? "border-[#7c4dff] ring-2 ring-[#ddcbff]"
                  : "border-white/70"
              }`}
              style={{ backgroundImage: buildTileGradient(range.counts) }}
            >
              {range.range_end.toLocaleString()}
            </button>
          ))}
        </div>
      </section>

      <section className="space-y-3 rounded-[0.8rem] bg-[#f1f2f8] px-2 py-2">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-[1.55rem] font-semibold tracking-tight text-[#53287c]">Knowledge Map</h3>
            <h4 className="mt-1 text-sm font-semibold text-[#766389]">{activeRangeLabel}</h4>
          </div>
          <div className="flex items-center gap-1.5">
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
                    <p className="mt-1 text-[0.8rem] font-semibold text-[#8f82a1]">
                      {activeEntry.pronunciation ?? "/.../"} #{activeEntry.browse_rank.toLocaleString()}
                    </p>
                  </div>
                  <span className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-[#87bed4]">
                    {activeEntry.part_of_speech ?? activeEntry.entry_type}
                  </span>
                  <span className="sr-only">Status: {STATUS_LABELS[activeEntry.status]}</span>
                </div>

                {showTranslations && (
                  <p className="text-sm font-semibold text-[#9c3af2]">
                    {activeCardTranslation ?? activeEntry.translation ?? "Translation unavailable"}
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
                  {PRIMARY_STATUS_ACTIONS.map((action) => (
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

                <div className="flex flex-wrap gap-1.5">
                  {SECONDARY_STATUS_ACTIONS.map((action) => (
                    <button
                      key={`${activeEntry.entry_id}-${action.status}-secondary`}
                      type="button"
                      onClick={() => void updateStatus(activeEntry, action.status)}
                      className={`rounded-[0.3rem] border px-2.5 py-1.5 text-[0.72rem] font-semibold ${secondaryStatusButtonClass(activeEntry.status === action.status)}`}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>
              </div>
            </div>
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
            {selectedRange.items.map((item) => (
              <div
                key={`${item.entry_type}-${item.entry_id}`}
                className="grid grid-cols-[4.2rem_1fr] gap-2 overflow-hidden rounded-[0.25rem] border border-[#dce0ee] bg-white px-2 py-2"
              >
                <div className="min-h-[4.4rem] rounded-[0.15rem]" style={buildHeroStyle(item.display_text)} />
                <div className="space-y-1 py-0.5 pr-1">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[1.02rem] font-semibold text-[#562c7f]">{item.display_text}</p>
                      {showTranslations && (
                        <p className="text-[0.8rem] font-semibold leading-5 text-[#a141ef]">
                          {item.translation ?? item.primary_definition ?? "No summary yet"}
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
                </div>
              </div>
            ))}
          </div>
        )}

        <MiniRangeStrip
          selectedRange={selectedRange}
          activeIndex={activeIndex}
          onPrevious={() => setActiveIndex((index) => Math.max(index - 1, 0))}
          onNext={() =>
            setActiveIndex((index) =>
              selectedRange ? Math.min(index + 1, selectedRange.items.length - 1) : index,
            )
          }
          onSelectIndex={setActiveIndex}
        />
      </section>
    </div>
  );
}
