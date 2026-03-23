"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { startTransition, useEffect, useState, type CSSProperties } from "react";
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

const STATUS_ACTIONS: Array<{ status: KnowledgeStatus; label: string }> = [
  { status: "to_learn", label: "Should Learn" },
  { status: "learning", label: "Learning" },
  { status: "known", label: "Known" },
];

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

function actionButtonClass(status: KnowledgeStatus, activeStatus: KnowledgeStatus): string {
  if (status === activeStatus) {
    return status === "known"
      ? "bg-[#45c5dd] text-white"
      : "bg-[#a52fff] text-white";
  }

  return "bg-white text-[#684f85]";
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
      `radial-gradient(circle at 22% 18%, rgba(255,255,255,0.30), transparent 18%)`,
      `radial-gradient(circle at 80% 15%, rgba(255,255,255,0.18), transparent 12%)`,
      `radial-gradient(circle at 70% 72%, ${palette[2]}aa, transparent 30%)`,
      `linear-gradient(160deg, ${palette[0]} 0%, ${palette[1]} 55%, ${palette[2]} 100%)`,
    ].join(", "),
  };
}

export default function KnowledgeEntryPage() {
  const params = useParams<{ entryType: "word" | "phrase"; entryId: string }>();
  const [detail, setDetail] = useState<KnowledgeMapEntryDetail | null>(null);
  const [searchHistory, setSearchHistory] = useState<SearchHistoryItem[]>([]);
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
    return <p className="text-sm text-slate-500">Loading learner detail...</p>;
  }

  const firstMeaning = detail.meanings[0];
  const firstSense = detail.senses[0];
  const topPartOfSpeech = firstMeaning?.part_of_speech ?? firstSense?.part_of_speech ?? null;
  const topExample =
    firstMeaning?.examples[0]?.sentence ??
    firstSense?.examples[0]?.sentence ??
    null;
  const tips = detail.entry_type === "word"
    ? detail.meanings.slice(0, 3).map((meaning, index) => ({
        id: meaning.id,
        title: meaning.part_of_speech
          ? `${meaning.part_of_speech[0].toUpperCase()}${meaning.part_of_speech.slice(1)} Context`
          : `Tip ${index + 1}`,
        body: meaning.definition,
        example: meaning.examples[0]?.sentence ?? null,
      }))
    : detail.senses.slice(0, 3).map((sense, index) => ({
        id: sense.sense_id ?? `${index}`,
        title: sense.part_of_speech
          ? `${sense.part_of_speech[0].toUpperCase()}${sense.part_of_speech.slice(1)} Tip`
          : `Tip ${index + 1}`,
        body: sense.definition,
        example: sense.examples[0]?.sentence ?? null,
      }));

  return (
    <div
      data-testid="knowledge-detail-mobile-shell"
      className="mx-auto max-w-[27rem] space-y-5 pb-28 text-[#43235f]"
    >
      <section data-testid="knowledge-detail-hero" className="relative overflow-hidden rounded-[2.2rem] shadow-[0_20px_46px_rgba(84,46,135,0.16)]">
        <div className="h-[24rem]" style={buildHeroStyle(detail.display_text)} />

        <div className="absolute inset-x-0 top-0 flex items-center justify-between px-4 py-4">
          <Link
            href="/"
            className="flex h-12 w-12 items-center justify-center rounded-full bg-white/75 text-xl font-semibold text-[#62368f] backdrop-blur"
          >
            x
          </Link>
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/75 text-xl font-semibold text-[#62368f] backdrop-blur">
            ...
          </span>
        </div>

        <div className="absolute inset-x-0 bottom-0 h-36 bg-[linear-gradient(180deg,transparent,rgba(34,12,66,0.72))]" />
      </section>

      <section className="-mt-20 px-3">
        <div className="space-y-4 rounded-[2rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.98),rgba(247,242,255,0.96))] px-5 py-5 shadow-[0_20px_44px_rgba(85,48,139,0.18)]">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h1 className="text-[2rem] font-semibold leading-none text-[#572c80]">
                {detail.display_text}
              </h1>
                  <p className="mt-2 flex flex-wrap items-center gap-2 text-sm font-semibold text-[#7c7395]">
                    <span>{detail.pronunciation ?? "/.../"}</span>
                    <span>#{detail.browse_rank.toLocaleString()}</span>
                  </p>
            </div>
            <span className={`rounded-full px-3 py-1 text-xs font-semibold ${statusChipClass(detail.status)}`}>
              Status: {STATUS_LABELS[detail.status]}
            </span>
          </div>

          <div className="flex items-center justify-between gap-3">
            <div>
              {topPartOfSpeech && (
                <p className="text-sm font-semibold uppercase tracking-[0.16em] text-[#38bfd8]">
                  {topPartOfSpeech}
                </p>
              )}
            </div>
            {detail.translation && (
              <p className="text-lg font-semibold text-[#9a39f2]">{detail.translation}</p>
            )}
          </div>

          <p className="text-[1.9rem] font-semibold leading-[1.2] text-[#4d295f]">
            {detail.primary_definition}
          </p>
          {topExample && (
            <p className="text-lg leading-8 text-[#6e5d82]">{topExample}</p>
          )}

          <div className="flex items-center justify-between gap-3">
            <span className="flex h-11 w-11 items-center justify-center rounded-full bg-[#5f238d] text-lg font-semibold text-white">
              &gt;
            </span>
            {detail.previous_entry && (
              <Link
                href={`/knowledge/${detail.previous_entry.entry_type}/${detail.previous_entry.entry_id}`}
                className="rounded-full bg-[#f1ddff] px-4 py-2 text-sm font-semibold text-[#7d2cff]"
              >
                Previous
              </Link>
            )}
            {detail.next_entry && (
              <Link
                href={`/knowledge/${detail.next_entry.entry_type}/${detail.next_entry.entry_id}`}
                className="rounded-full bg-[#e0f9ff] px-4 py-2 text-sm font-semibold text-[#1687a6]"
              >
                Next
              </Link>
            )}
          </div>
        </div>
      </section>

      <section data-testid="knowledge-detail-pro-tips" className="space-y-4 rounded-[2rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(245,240,252,0.94))] px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div className="text-center">
          <p className="text-sm font-semibold tracking-[0.12em] text-[#8e38f2]">Pro Tips</p>
        </div>

        {tips.length === 0 && (
          <article className="rounded-[1.6rem] bg-white px-5 py-5 shadow-[0_10px_24px_rgba(86,54,145,0.08)]">
            <h2 className="text-2xl font-semibold text-[#572c80]">Usage Tip</h2>
            <p className="mt-3 text-lg leading-8 text-[#5c476f]">
              Search nearby entries or move to the next card to compare similar words and phrases.
            </p>
          </article>
        )}

        {tips.map((tip) => (
          <article
            key={tip.id}
            className="rounded-[1.6rem] bg-white px-5 py-5 shadow-[0_10px_24px_rgba(86,54,145,0.08)]"
          >
            <div className="flex items-start justify-between gap-4">
              <h2 className="text-2xl font-semibold text-[#572c80]">{tip.title}</h2>
              <span className="rounded-full bg-[#f1ddff] px-3 py-2 text-xs font-semibold text-[#7d2cff]">
                Tip
              </span>
            </div>
            <p className="mt-3 text-lg leading-8 text-[#5c476f]">{tip.body}</p>
            {tip.example && (
              <p className="mt-4 text-base leading-7 text-[#8b7a9c]">{tip.example}</p>
            )}
          </article>
        ))}
      </section>

      <section className="space-y-4 rounded-[2rem] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(245,240,252,0.94))] px-5 py-5 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div>
          <h2 className="text-lg font-semibold text-[#53287c]">Search</h2>
          <p className="mt-1 text-sm leading-6 text-[#726682]">
            Search the catalog from within the detail screen and reopen what you searched recently.
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
            {searchResults.map((item) => (
              <Link
                key={`${item.entry_type}-${item.entry_id}`}
                href={`/knowledge/${item.entry_type}/${item.entry_id}`}
                onClick={() => void rememberSearch(item)}
                className="block rounded-[1rem] bg-white px-4 py-3 shadow-[0_10px_20px_rgba(86,54,145,0.08)]"
              >
                <p className="font-semibold text-[#572b80]">{item.display_text}</p>
                <p className="text-sm text-[#7d6f95]">
                  {item.translation ?? item.primary_definition ?? "No summary yet"}
                </p>
              </Link>
            ))}
          </div>
        )}
      </section>

      <div
        data-testid="knowledge-detail-bottom-bar"
        className="fixed bottom-4 left-1/2 z-20 flex w-[min(27rem,calc(100vw-2rem))] -translate-x-1/2 gap-3 rounded-[1.3rem] bg-[rgba(245,240,252,0.96)] p-3 shadow-[0_18px_42px_rgba(84,46,135,0.18)] backdrop-blur"
      >
        {STATUS_ACTIONS.map((action) => (
          <button
            key={action.status}
            type="button"
            onClick={() => void updateStatus(action.status)}
            className={`flex-1 rounded-[0.95rem] px-3 py-3 text-sm font-semibold ${actionButtonClass(action.status, detail.status)}`}
          >
            {action.label}
          </button>
        ))}
      </div>
    </div>
  );
}
