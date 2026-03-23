"use client";

import Link from "next/link";
import { startTransition, useEffect, useState } from "react";
import {
  createKnowledgeMapSearchHistory,
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

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "Should Learn",
  learning: "Learning",
  known: "Known",
};

const STATUS_COLORS: Record<KnowledgeStatus, string> = {
  undecided: "#d7d9e6",
  to_learn: "#e35d5b",
  learning: "#f0b449",
  known: "#19a886",
};

const STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "Should Learn" },
  { status: "known", label: "Already Know" },
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
  return `linear-gradient(135deg, ${stops.join(", ")})`;
}

function statusBadgeClass(status: KnowledgeStatus): string {
  switch (status) {
    case "known":
      return "bg-emerald-100 text-emerald-800";
    case "learning":
      return "bg-amber-100 text-amber-800";
    case "to_learn":
      return "bg-rose-100 text-rose-800";
    default:
      return "bg-slate-200 text-slate-700";
  }
}

export default function HomePage() {
  const [overview, setOverview] = useState<KnowledgeMapOverview | null>(null);
  const [selectedRange, setSelectedRange] = useState<KnowledgeMapRange | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const [searchHistory, setSearchHistory] = useState<Array<{ query: string; entry_type: "word" | "phrase" | null; entry_id: string | null }>>([]);
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

      const firstRange = overviewPayload.ranges[0];
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

  return (
    <div className="space-y-8">
      <section className="grid gap-6 lg:grid-cols-[1.4fr_0.9fr]">
        <div className="rounded-[2rem] border border-white/60 bg-[linear-gradient(140deg,#fff8ef_0%,#f7f4ea_45%,#eef8f5_100%)] p-6 shadow-[0_24px_80px_rgba(37,64,74,0.08)]">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-teal-700">
                Learner Graph
              </p>
              <h2 className="text-4xl font-semibold tracking-tight text-slate-900">
                Full Knowledge Map
              </h2>
              <p className="max-w-2xl text-sm leading-6 text-slate-600">
                Every tile covers 100 entries. Colors show what you already know,
                what you are learning, what you should learn next, and what is still undecided.
              </p>
            </div>
            <div className="rounded-2xl border border-slate-200/80 bg-white/80 px-4 py-3 text-sm text-slate-600 backdrop-blur">
              <p>Total entries</p>
              <p className="text-2xl font-semibold text-slate-900">
                {overview?.total_entries ?? "…"}
              </p>
            </div>
          </div>

          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
            {overview?.ranges.map((range) => (
              <button
                key={range.range_start}
                type="button"
                onClick={() => loadRange(range.range_start)}
                className="rounded-2xl border border-white/60 px-3 py-4 text-left shadow-sm transition hover:-translate-y-0.5"
                style={{ backgroundImage: buildTileGradient(range.counts) }}
                aria-label={`${range.range_start}-${range.range_end}`}
              >
                <span className="block text-xs font-semibold uppercase tracking-[0.18em] text-slate-900/80">
                  Tile
                </span>
                <span className="mt-2 block text-lg font-semibold text-slate-950">
                  {range.range_start}-{range.range_end}
                </span>
                <span className="mt-3 block text-xs text-slate-900/80">
                  {range.total_entries} entries
                </span>
              </button>
            ))}
          </div>

          <div className="mt-6 flex flex-wrap gap-3 text-xs text-slate-600">
            {Object.entries(STATUS_LABELS).map(([status, label]) => (
              <span key={status} className="inline-flex items-center gap-2 rounded-full bg-white/70 px-3 py-1.5">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: STATUS_COLORS[status as KnowledgeStatus] }}
                />
                {label}
              </span>
            ))}
          </div>
        </div>

        <aside className="rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-[0_24px_80px_rgba(37,64,74,0.08)] backdrop-blur">
          <div className="space-y-4">
            <div>
              <h3 className="text-lg font-semibold text-slate-900">Search The Graph</h3>
              <p className="mt-1 text-sm text-slate-600">
                Jump to a word or phrase, or revisit what you searched recently.
              </p>
            </div>
            <input
              type="text"
              value={searchQuery}
              onChange={(event) => setSearchQuery(event.target.value)}
              placeholder="Search your knowledge map"
              className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 outline-none ring-0 placeholder:text-slate-400"
            />

            <div className="space-y-2">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                Recent Searches
              </p>
              <div className="flex flex-wrap gap-2">
                {searchHistory.map((item) => (
                  <span key={`${item.query}-${item.entry_id ?? "none"}`} className="rounded-full bg-slate-100 px-3 py-1.5 text-sm text-slate-700">
                    {item.query}
                  </span>
                ))}
              </div>
            </div>

            {searchResults.length > 0 && (
              <div className="space-y-2">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                  Results
                </p>
                <div className="space-y-2">
                  {searchResults.map((item) => (
                    <Link
                      key={`${item.entry_type}-${item.entry_id}`}
                      href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                      onClick={() => void rememberSearch(item)}
                      className="block rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 transition hover:border-teal-300 hover:bg-white"
                    >
                      <div className="flex items-center justify-between gap-4">
                        <div>
                          <p className="font-semibold text-slate-900">{item.display_text}</p>
                          <p className="text-sm text-slate-500">{item.translation ?? item.primary_definition ?? "No summary yet"}</p>
                        </div>
                        <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadgeClass(item.status)}`}>
                          {STATUS_LABELS[item.status]}
                        </span>
                      </div>
                    </Link>
                  ))}
                </div>
              </div>
            )}
          </div>
        </aside>
      </section>

      <section className="rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-[0_24px_80px_rgba(37,64,74,0.08)] backdrop-blur">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
              Selected Range
            </p>
            <h3 className="text-2xl font-semibold text-slate-900">
              {selectedRange ? `Range ${selectedRange.range_start}-${selectedRange.range_end}` : "Pick a tile to begin"}
            </h3>
          </div>
          <div className="flex flex-wrap gap-2">
            {(["cards", "tags", "list"] as ViewMode[]).map((mode) => (
              <button
                key={mode}
                type="button"
                onClick={() => setViewMode(mode)}
                className={`rounded-full px-4 py-2 text-sm font-semibold transition ${
                  viewMode === mode
                    ? "bg-slate-900 text-white"
                    : "bg-slate-100 text-slate-600"
                }`}
              >
                {mode === "cards" ? "Cards view" : mode === "tags" ? "Tags view" : "List view"}
              </button>
            ))}
          </div>
        </div>

        {loadingRange && <p className="mt-6 text-sm text-slate-500">Loading range…</p>}

        {!loadingRange && selectedRange && viewMode === "cards" && activeEntry && (
          <div className="mt-6 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
            <div className="overflow-hidden rounded-[2rem] border border-slate-200 bg-[linear-gradient(160deg,#1c4c4b_0%,#2f6d66_40%,#f7d6a3_100%)] p-5 text-white">
              <div className="flex items-center justify-between">
                <span className="rounded-full bg-white/15 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em]">
                  {activeEntry.entry_type}
                </span>
                <span className="text-sm font-medium">#{activeEntry.browse_rank}</span>
              </div>
              <div className="mt-8 rounded-[1.5rem] bg-white/12 p-6 backdrop-blur">
                <p className="text-xs uppercase tracking-[0.22em] text-white/70">Hero Placeholder</p>
                <div className="mt-8 h-44 rounded-[1.4rem] border border-white/20 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.24),transparent_38%),radial-gradient(circle_at_bottom_right,rgba(247,214,163,0.45),transparent_42%),rgba(255,255,255,0.08)]" />
              </div>
            </div>

            <div className="rounded-[2rem] border border-slate-200 bg-slate-50 p-6">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                    Status: {STATUS_LABELS[activeEntry.status]}
                  </p>
                  <h4 className="mt-2 text-3xl font-semibold text-slate-900">
                    {activeEntry.display_text}
                  </h4>
                  <p className="mt-2 text-sm text-slate-500">
                    {activeEntry.pronunciation ?? "Pronunciation follows your preference when available"}
                  </p>
                </div>
                <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadgeClass(activeEntry.status)}`}>
                  {STATUS_LABELS[activeEntry.status]}
                </span>
              </div>

              <p className="mt-6 text-lg leading-8 text-slate-800">
                {activeEntry.primary_definition ?? "No learner definition has been generated yet."}
              </p>
              <p className="mt-3 text-sm text-slate-500">
                {activeEntry.translation ?? "Translation not available for the selected locale."}
              </p>

              <div className="mt-8 flex flex-wrap gap-3">
                {STATUS_ACTIONS.map((action) => (
                  <button
                    key={`${activeEntry.entry_id}-${action.status}-${action.label}`}
                    type="button"
                    onClick={() => updateStatus(activeEntry, action.status)}
                    className="rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-semibold text-slate-700 transition hover:border-teal-300 hover:text-teal-700"
                  >
                    {action.label}
                  </button>
                ))}
                <Link
                  href={`/knowledge/${activeEntry.entry_type}/${activeEntry.entry_id}`}
                  onClick={() => void rememberSearch(activeEntry)}
                  className="rounded-full bg-slate-900 px-4 py-2 text-sm font-semibold text-white"
                >
                  Learn More
                </Link>
              </div>

              {selectedRange.items.length > 1 && (
                <div className="mt-8 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setActiveIndex((index) => Math.max(index - 1, 0))}
                    className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-700"
                  >
                    Previous
                  </button>
                  <p className="text-sm text-slate-500">
                    Card {activeIndex + 1} of {selectedRange.items.length}
                  </p>
                  <button
                    type="button"
                    onClick={() => setActiveIndex((index) => Math.min(index + 1, selectedRange.items.length - 1))}
                    className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-700"
                  >
                    Next
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {!loadingRange && selectedRange && viewMode === "tags" && (
          <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4" data-testid="knowledge-tags-view">
            {selectedRange.items.map((item) => (
              <Link
                key={`${item.entry_type}-${item.entry_id}`}
                href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                onClick={() => void rememberSearch(item)}
                className="rounded-2xl px-4 py-5 text-center text-sm font-semibold text-slate-900"
                style={{ backgroundColor: STATUS_COLORS[item.status] }}
              >
                {item.display_text}
              </Link>
            ))}
          </div>
        )}

        {!loadingRange && selectedRange && viewMode === "list" && (
          <div className="mt-6 space-y-3" data-testid="knowledge-list-view">
            {selectedRange.items.map((item) => (
              <div key={`${item.entry_type}-${item.entry_id}`} className="flex flex-col gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 md:flex-row md:items-center md:justify-between">
                <div>
                  <p className="text-lg font-semibold text-slate-900">{item.display_text}</p>
                  <p className="text-sm text-slate-500">{item.translation ?? item.primary_definition ?? "No summary yet"}</p>
                </div>
                <div className="flex items-center gap-3">
                  <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadgeClass(item.status)}`}>
                    {STATUS_LABELS[item.status]}
                  </span>
                  <Link
                    href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                    onClick={() => void rememberSearch(item)}
                    className="rounded-full bg-white px-4 py-2 text-sm font-semibold text-slate-700"
                  >
                    Open
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
