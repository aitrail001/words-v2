"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { startTransition, useEffect, useState } from "react";
import {
  createKnowledgeMapSearchHistory,
  getKnowledgeMapEntryDetail,
  getKnowledgeMapSearchHistory,
  type KnowledgeMapEntryDetail,
  searchKnowledgeMap,
  type KnowledgeMapEntrySummary,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";

const STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "Undecided",
  to_learn: "Should Learn",
  learning: "Learning",
  known: "Known",
};

const STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "Should Learn" },
  { status: "known", label: "Known" },
  { status: "learning", label: "Learning" },
];

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

export default function KnowledgeEntryPage() {
  const params = useParams<{ entryType: "word" | "phrase"; entryId: string }>();
  const [detail, setDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [searchHistory, setSearchHistory] = useState<Array<{ query: string; entry_type: "word" | "phrase" | null; entry_id: string | null }>>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<KnowledgeMapEntrySummary[]>([]);

  useEffect(() => {
    let active = true;

    Promise.all([
      getKnowledgeMapEntryDetail(params.entryType, params.entryId),
      getKnowledgeMapSearchHistory(),
    ])
      .then(([detailResponse, historyResponse]) => {
        if (!active) {
          return;
        }
        setDetail(detailResponse);
        setSearchHistory(historyResponse.items);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setDetail(null);
      });

    return () => {
      active = false;
    };
  }, [params.entryId, params.entryType]);

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

  const updateStatus = async (status: KnowledgeStatus) => {
    if (!detail) {
      return;
    }
    const response = await updateKnowledgeEntryStatus(detail.entry_type, detail.entry_id, status);
    startTransition(() => {
      setDetail((current) => (current ? { ...current, status: response.status } : current));
    });
  };

  const rememberSearch = async (item: KnowledgeMapEntrySummary) => {
    const historyItem = await createKnowledgeMapSearchHistory({
      query: item.display_text,
      entry_type: item.entry_type,
      entry_id: item.entry_id,
    });
    setSearchHistory((current) => [
      {
        query: historyItem.query,
        entry_type: historyItem.entry_type ?? null,
        entry_id: historyItem.entry_id ?? null,
      },
      ...current.filter((entry) => entry.query !== historyItem.query).slice(0, 5),
    ]);
  };

  if (!detail) {
    return <p className="text-sm text-slate-500">Loading learner detail…</p>;
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1.2fr_0.8fr]">
      <section className="space-y-6">
        <div className="overflow-hidden rounded-[2rem] border border-slate-200 bg-[linear-gradient(160deg,#0f3d3e_0%,#2f6d66_45%,#f4d9a7_100%)] p-6 text-white shadow-[0_24px_80px_rgba(37,64,74,0.1)]">
          <div className="flex items-center justify-between">
            <Link href="/" className="rounded-full bg-white/10 px-4 py-2 text-sm font-semibold">
              Back To Map
            </Link>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusBadgeClass(detail.status)}`}>
              Status: {STATUS_LABELS[detail.status]}
            </span>
          </div>

          <div className="mt-8 grid gap-6 lg:grid-cols-[1fr_0.95fr]">
            <div className="rounded-[1.8rem] border border-white/20 bg-white/12 p-5 backdrop-blur">
              <p className="text-xs uppercase tracking-[0.24em] text-white/70">Hero Placeholder</p>
              <div className="mt-6 h-64 rounded-[1.4rem] border border-white/20 bg-[radial-gradient(circle_at_top_left,rgba(255,255,255,0.24),transparent_32%),radial-gradient(circle_at_bottom_right,rgba(244,217,167,0.5),transparent_36%),rgba(255,255,255,0.08)]" />
            </div>

            <div className="rounded-[1.8rem] border border-white/20 bg-white/12 p-6 backdrop-blur">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-white/70">
                #{detail.browse_rank} · {detail.entry_type}
              </p>
              <h1 className="mt-2 text-4xl font-semibold">{detail.display_text}</h1>
              {detail.pronunciation && <p className="mt-2 text-lg text-white/85">{detail.pronunciation}</p>}
              {detail.translation && <p className="mt-3 text-lg text-[#f4d9a7]">{detail.translation}</p>}
              <p className="mt-6 text-xl leading-8 text-white/95">{detail.primary_definition}</p>

              <div className="mt-8 flex flex-wrap gap-3">
                {STATUS_ACTIONS.map((action) => (
                  <button
                    key={action.status}
                    type="button"
                    onClick={() => updateStatus(action.status)}
                    className="rounded-full border border-white/30 bg-white/10 px-4 py-2 text-sm font-semibold"
                  >
                    {action.label}
                  </button>
                ))}
              </div>

              <div className="mt-8 flex gap-3">
                {detail.previous_entry && (
                  <Link href={`/knowledge/${detail.previous_entry.entry_type}/${detail.previous_entry.entry_id}`} className="rounded-full bg-white/10 px-4 py-2 text-sm font-semibold">
                    Previous
                  </Link>
                )}
                {detail.next_entry && (
                  <Link href={`/knowledge/${detail.next_entry.entry_type}/${detail.next_entry.entry_id}`} className="rounded-full bg-white/10 px-4 py-2 text-sm font-semibold">
                    Next
                  </Link>
                )}
              </div>
            </div>
          </div>
        </div>

        <div className="space-y-4 rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-[0_24px_80px_rgba(37,64,74,0.08)]">
          <h2 className="text-xl font-semibold text-slate-900">
            {detail.entry_type === "word" ? "Definitions and examples" : "Phrase senses and examples"}
          </h2>

          {detail.meanings.length > 0 &&
            detail.meanings.map((meaning) => (
              <article key={meaning.id} className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                  {meaning.part_of_speech ?? "Meaning"}
                </p>
                <p className="mt-2 text-2xl font-semibold text-slate-900">{meaning.definition}</p>
                {meaning.examples.map((example) => (
                  <p key={example.id} className="mt-4 text-sm text-slate-600">
                    {example.sentence}
                  </p>
                ))}
              </article>
            ))}

          {detail.senses.length > 0 &&
            detail.senses.map((sense, index) => (
              <article key={sense.sense_id ?? index} className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-5">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-500">
                  {sense.part_of_speech ?? `Sense ${index + 1}`}
                </p>
                <p className="mt-2 text-2xl font-semibold text-slate-900">{sense.definition}</p>
                {sense.examples.map((example) => (
                  <p key={example.id} className="mt-4 text-sm text-slate-600">
                    {example.sentence}
                  </p>
                ))}
              </article>
            ))}
        </div>
      </section>

      <aside className="space-y-6 rounded-[2rem] border border-slate-200 bg-white/85 p-6 shadow-[0_24px_80px_rgba(37,64,74,0.08)]">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">Search</h2>
          <p className="mt-1 text-sm text-slate-600">
            Search the catalog from within the detail screen and reopen what you searched recently.
          </p>
        </div>

        <input
          type="text"
          value={searchQuery}
          onChange={(event) => setSearchQuery(event.target.value)}
          placeholder="Search your knowledge map"
          className="w-full rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-sm text-slate-900 placeholder:text-slate-400"
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
            {searchResults.map((item) => (
              <Link
                key={`${item.entry_type}-${item.entry_id}`}
                href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                onClick={() => void rememberSearch(item)}
                className="block rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3"
              >
                <p className="font-semibold text-slate-900">{item.display_text}</p>
                <p className="text-sm text-slate-500">{item.translation ?? item.primary_definition ?? "No summary yet"}</p>
              </Link>
            ))}
          </div>
        )}
      </aside>
    </div>
  );
}
