"use client";

import Link from "next/link";
import { startTransition, useEffect, useState, type CSSProperties } from "react";
import {
  createKnowledgeMapSearchHistory,
  getKnowledgeMapEntryDetail,
  getKnowledgeMapOverview,
  getKnowledgeMapRange,
  getKnowledgeMapSearchHistory,
  type KnowledgeMapEntrySummary,
  type KnowledgeMapOverview,
  type KnowledgeMapRange,
  searchKnowledgeMap,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

type ViewMode = "cards" | "tags" | "list";

type SearchHistoryItem = {
  query: string;
  entry_type: "word" | "phrase" | null;
  entry_id: string | null;
};

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
      className="rounded-[1.7rem] bg-white/90 px-4 py-4 shadow-[0_18px_42px_rgba(84,46,135,0.12)]"
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

      <div className="mt-3 grid grid-cols-10 gap-[3px] rounded-[1rem] bg-[#f4eefc] p-2">
        {selectedRange.items.map((item, index) => (
          <button
            key={`${item.entry_type}-${item.entry_id}`}
            type="button"
            onClick={() => onSelectIndex(index)}
            aria-label={item.display_text}
            className={`h-4 rounded-[3px] transition ${
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
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<KnowledgeMapEntrySummary[]>([]);
  const [loadingRange, setLoadingRange] = useState(false);

  useEffect(() => {
    let active = true;

    (async () => {
      const [preferences, overviewPayload, historyPayload] = await Promise.all([
        getUserPreferences(),
        getKnowledgeMapOverview(),
        getKnowledgeMapSearchHistory(),
      ]);

      if (!active) {
        return;
      }

      setViewMode(preferences.knowledge_view_preference);
      setOverview(overviewPayload);
      setSearchHistory(historyPayload.items);

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
    const trimmed = searchQuery.trim();
    if (trimmed.length < 2) {
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(() => {
      searchKnowledgeMap(trimmed)
        .then((response) => {
          if (active) {
            setSearchResults(response.items);
          }
        })
        .catch(() => {
          if (active) {
            setSearchResults([]);
          }
        });
    }, 250);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [searchQuery]);

  useEffect(() => {
    let active = true;
    const currentEntry = selectedRange?.items[activeIndex];
    if (!currentEntry) {
      return () => {
        active = false;
      };
    }

    const needsDetailHydration =
      !currentEntry.primary_definition ||
      (!currentEntry.translation && currentEntry.entry_type === "word") ||
      (!currentEntry.pronunciation && currentEntry.entry_type === "word");

    if (!needsDetailHydration) {
      return () => {
        active = false;
      };
    }

    getKnowledgeMapEntryDetail(currentEntry.entry_type, currentEntry.entry_id)
      .then((detail) => {
        if (!active) {
          return;
        }
        setSelectedRange((current) => {
          if (!current) {
            return current;
          }
          return {
            ...current,
            items: current.items.map((item) =>
              item.entry_id === detail.entry_id && item.entry_type === detail.entry_type
                ? {
                    ...item,
                    pronunciation: detail.pronunciation,
                    translation: detail.translation,
                    primary_definition: detail.primary_definition,
                  }
                : item,
            ),
          };
        });
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, [activeIndex, selectedRange]);

  const activeEntry = selectedRange?.items[activeIndex] ?? null;

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

  const rememberSearch = async (entry: KnowledgeMapEntrySummary) => {
    const historyItem = await createKnowledgeMapSearchHistory({
      query: entry.display_text,
      entry_type: entry.entry_type,
      entry_id: entry.entry_id,
    });
    setSearchHistory((current) => [
      {
        query: historyItem.query,
        entry_type: historyItem.entry_type ?? null,
        entry_id: historyItem.entry_id ?? null,
      },
      ...current.filter((item) => item.query !== historyItem.query).slice(0, 5),
    ]);
  };

  const activeRangeLabel = selectedRange
    ? `Range ${selectedRange.range_start.toLocaleString()}-${selectedRange.range_end.toLocaleString()}`
    : "Pick a tile to begin";

  return (
    <div
      data-testid="knowledge-map-mobile-shell"
      className="mx-auto max-w-[27rem] space-y-5 pb-10 text-[#43235f]"
    >
      <section className="rounded-[2rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.92),rgba(247,242,255,0.92))] px-5 py-6 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div className="flex items-center justify-between">
          <span className="w-8 text-xl text-[#7d52c7]">{""}</span>
          <h2 className="text-center text-[2rem] font-semibold tracking-tight text-[#502a7d]">
            Full Knowledge Map
          </h2>
          <span className="w-8 text-right text-sm font-semibold text-[#7d52c7]">
            {overview?.total_entries ?? "..."}
          </span>
        </div>
        <p className="mt-4 text-sm leading-6 text-[#6b5d86]">
          This is a map of your English knowledge. Each box shows 100 words and phrases.
          They are sorted by relevance to your life. Discover them all, starting from the top.
        </p>

        <div data-testid="knowledge-map-tile-grid" className="mt-5 grid grid-cols-4 gap-2">
          {overview?.ranges.map((range) => (
            <button
              key={range.range_start}
              type="button"
              onClick={() => void loadRange(range.range_start)}
              aria-label={`${range.range_start}-${range.range_end}`}
              className={`rounded-[0.45rem] border px-2 py-2 text-center text-sm font-semibold shadow-sm transition ${
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

      <section className="space-y-4 rounded-[2rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(244,238,252,0.95))] px-4 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <h3 className="text-[1.8rem] font-semibold tracking-tight text-[#53287c]">Knowledge Map</h3>
            <h4 className="mt-1 text-sm font-semibold text-[#766389]">{activeRangeLabel}</h4>
          </div>
          <div className="flex items-center gap-2">
            {VIEW_OPTIONS.map((option) => (
              <button
                key={option.mode}
                type="button"
                onClick={() => setViewMode(option.mode)}
                className={`rounded-full px-3 py-2 text-xs font-semibold transition ${
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
          <div data-testid="knowledge-card-view" className="space-y-4">
            <div className="overflow-hidden rounded-[1.9rem] bg-white shadow-[0_14px_30px_rgba(94,53,177,0.12)]">
              <div className="relative h-56 overflow-hidden" style={buildHeroStyle(activeEntry.display_text)}>
                <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 py-4 text-white">
                  <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.16em]">
                    {activeEntry.entry_type}
                  </span>
                  <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold">
                    {VIEW_OPTIONS.find((option) => option.mode === viewMode)?.shortLabel}
                  </span>
                </div>
                <div className="absolute inset-x-0 bottom-0 h-24 bg-[linear-gradient(180deg,transparent,rgba(39,12,74,0.68))]" />
              </div>

              <div className="space-y-3 px-5 py-5">
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <h4 className="text-[2rem] font-semibold leading-none text-[#572a80]">
                      {activeEntry.display_text}
                    </h4>
                    <p className="mt-2 text-sm font-semibold text-[#8f82a1]">
                      {activeEntry.pronunciation ?? "/.../"} #{activeEntry.browse_rank.toLocaleString()}
                    </p>
                  </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusChipClass(activeEntry.status)}`}>
                      Status: {STATUS_LABELS[activeEntry.status]}
                    </span>
                </div>

                <p className="text-xl font-semibold text-[#9c3af2]">
                  {activeEntry.translation ?? "Translation unavailable"}
                </p>
                <p className="text-[1.05rem] leading-8 text-[#4e3564]">
                  {activeEntry.primary_definition ?? "No learner definition has been generated yet."}
                </p>

                <div className="pt-1 text-right">
                  <Link
                    href={`/knowledge/${activeEntry.entry_type}/${activeEntry.entry_id}`}
                    onClick={() => void rememberSearch(activeEntry)}
                    className="text-sm font-semibold text-[#9a86b5] underline underline-offset-4"
                  >
                    Learn More
                  </Link>
                </div>

                <div className="grid grid-cols-2 gap-3 pt-2">
                  {PRIMARY_STATUS_ACTIONS.map((action) => (
                    <button
                      key={`${activeEntry.entry_id}-${action.status}-${action.label}`}
                      type="button"
                      onClick={() => void updateStatus(activeEntry, action.status)}
                      className={`rounded-[0.9rem] px-4 py-3 text-sm font-semibold ${primaryStatusButtonClass(action.status)}`}
                    >
                      {action.label}
                    </button>
                  ))}
                </div>

                <div className="flex flex-wrap gap-2">
                  {SECONDARY_STATUS_ACTIONS.map((action) => (
                    <button
                      key={`${activeEntry.entry_id}-${action.status}-secondary`}
                      type="button"
                      onClick={() => void updateStatus(activeEntry, action.status)}
                      className={`rounded-full border px-3 py-2 text-xs font-semibold ${secondaryStatusButtonClass(activeEntry.status === action.status)}`}
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
          <div data-testid="knowledge-tags-view" className="grid grid-cols-3 gap-2">
            {selectedRange.items.map((item) => (
              <Link
                key={`${item.entry_type}-${item.entry_id}`}
                href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                onClick={() => void rememberSearch(item)}
                className="rounded-[0.45rem] px-3 py-4 text-center text-sm font-semibold text-white shadow-sm"
                style={{ backgroundColor: STATUS_COLORS[item.status] }}
              >
                {item.display_text}
              </Link>
            ))}
          </div>
        )}

        {!loadingRange && selectedRange && viewMode === "list" && (
          <div data-testid="knowledge-list-view" className="space-y-3">
            {selectedRange.items.map((item) => (
              <div
                key={`${item.entry_type}-${item.entry_id}`}
                className="grid grid-cols-[5.5rem_1fr] gap-3 overflow-hidden rounded-[1.3rem] bg-white shadow-[0_10px_24px_rgba(86,54,145,0.08)]"
              >
                <div className="min-h-24" style={buildHeroStyle(item.display_text)} />
                <div className="space-y-2 px-1 py-3 pr-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-[1.35rem] font-semibold text-[#562c7f]">{item.display_text}</p>
                      <p className="text-sm font-semibold text-[#a141ef]">
                        {item.translation ?? item.primary_definition ?? "No summary yet"}
                      </p>
                    </div>
                    <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusChipClass(item.status)}`}>
                      {STATUS_LABELS[item.status]}
                    </span>
                  </div>
                  <Link
                    href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                    onClick={() => void rememberSearch(item)}
                    className="inline-flex rounded-[0.8rem] bg-[#f1ddff] px-3 py-2 text-xs font-semibold text-[#7c2cff]"
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

      <section className="space-y-4 rounded-[2rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(245,240,252,0.94))] px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div>
          <h3 className="text-xl font-semibold text-[#53287c]">Search The Graph</h3>
          <p className="mt-1 text-sm leading-6 text-[#726682]">
            Jump to a word or phrase, or revisit what you searched recently.
          </p>
        </div>

        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search your knowledge map"
          className="w-full rounded-[1rem] border border-[#ddd8ee] bg-white px-4 py-3 text-sm text-[#3d2456] outline-none placeholder:text-[#a199b3]"
        />

        <div className="space-y-2">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#84789b]">Recent Searches</p>
          <div className="flex flex-wrap gap-2">
            {searchHistory.map((item) => (
              <span
                key={`${item.query}-${item.entry_id ?? "none"}`}
                className="rounded-full bg-[#f1e8fb] px-3 py-1.5 text-sm font-semibold text-[#7345ab]"
              >
                {item.query}
              </span>
            ))}
          </div>
        </div>

        {searchResults.length > 0 && (
          <div className="space-y-2">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#84789b]">Results</p>
            <div className="space-y-2">
              {searchResults.map((item) => (
                <Link
                  key={`${item.entry_type}-${item.entry_id}`}
                  href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                  onClick={() => void rememberSearch(item)}
                  className="flex items-center justify-between gap-4 rounded-[1rem] bg-white px-4 py-3 shadow-[0_10px_20px_rgba(86,54,145,0.08)]"
                >
                  <div>
                    <p className="font-semibold text-[#572b80]">{item.display_text}</p>
                    <p className="text-sm text-[#7d6f95]">
                      {item.translation ?? item.primary_definition ?? "No summary yet"}
                    </p>
                  </div>
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusChipClass(item.status)}`}>
                    {STATUS_LABELS[item.status]}
                  </span>
                </Link>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}
