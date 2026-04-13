"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  createKnowledgeMapSearchHistory,
  getKnowledgeMapSearchHistory,
  searchKnowledgeMap,
  type KnowledgeMapEntrySummary,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

type SearchHistoryItem = {
  query: string;
  entry_type: "word" | "phrase" | null;
  entry_id: string | null;
};

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<KnowledgeMapEntrySummary[]>([]);
  const [history, setHistory] = useState<SearchHistoryItem[]>([]);
  const [showTranslations, setShowTranslations] = useState(true);
  const trimmedQuery = query.trim();
  const visibleResults = trimmedQuery.length < 2 ? [] : results;

  useEffect(() => {
    let active = true;

    Promise.all([getKnowledgeMapSearchHistory(), getUserPreferences()])
      .then(([historyResponse, preferences]) => {
        if (!active) {
          return;
        }
        setHistory(
          historyResponse.items.map((item) => ({
            query: item.query,
            entry_type: item.entry_type,
            entry_id: item.entry_id,
          })),
        );
        setShowTranslations(preferences.show_translations_by_default);
      })
      .catch(() => undefined);

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    if (trimmedQuery.length < 2) {
      return;
    }

    const timer = setTimeout(() => {
      searchKnowledgeMap(trimmedQuery)
        .then((response) => {
          if (active) {
            setResults(response.items);
          }
        })
        .catch(() => {
          if (active) {
            setResults([]);
          }
        });
    }, 250);

    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [trimmedQuery]);

  const rememberSearch = async (item: KnowledgeMapEntrySummary) => {
    const historyItem = await createKnowledgeMapSearchHistory({
      query: item.display_text,
      entry_type: item.entry_type,
      entry_id: item.entry_id,
    });
    setHistory((current) => [
      {
        query: historyItem.query,
        entry_type: historyItem.entry_type ?? null,
        entry_id: historyItem.entry_id ?? null,
      },
      ...current.filter((entry) => entry.query !== historyItem.query).slice(0, 7),
    ]);
  };

  return (
    <section className="mx-auto max-w-[46rem] space-y-3 pb-10 text-[#482060]">
      <div className="overflow-hidden rounded-[0.9rem] bg-[linear-gradient(135deg,#6f2bff,#38c5da)] px-4 py-4 text-white shadow-[0_16px_34px_rgba(89,44,145,0.18)]">
        <p className="text-sm font-semibold uppercase tracking-[0.28em] text-white/75">Learner Search</p>
        <h1 className="mt-3 text-[2.1rem] font-semibold tracking-tight">Search</h1>
        <p className="mt-3 text-sm leading-6 text-white/85">
          Search the catalog, reopen recent lookups, and jump straight into a word or phrase card.
        </p>
      </div>

      <div className="rounded-[0.9rem] bg-white/90 p-4 shadow-[0_12px_28px_rgba(109,78,140,0.10)]">
        <input
          type="text"
          value={query}
          onChange={(event) => {
            const nextQuery = event.target.value;
            if (nextQuery.trim().length < 2) {
              setResults([]);
            }
            setQuery(nextQuery);
          }}
          placeholder="Search words and phrases"
          className="w-full rounded-[1rem] border border-[#ddd8ee] bg-white px-4 py-3 text-sm text-[#3d2456] outline-none placeholder:text-[#a199b3]"
        />

        <div className="mt-4 flex items-center justify-between gap-3">
          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[#84789b]">Recent Searches</p>
          <span className="text-xs font-semibold text-[#8f2fff]">
            Translation {showTranslations ? "On" : "Off"}
          </span>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          {history.map((item) =>
            item.entry_type && item.entry_id ? (
              <Link
                key={`${item.query}-${item.entry_id ?? "none"}`}
                href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
                className="rounded-full bg-[#f1e8fb] px-3 py-1.5 text-sm font-semibold text-[#7345ab]"
              >
                {item.query}
              </Link>
            ) : (
              <button
                key={`${item.query}-${item.entry_id ?? "none"}`}
                type="button"
                onClick={() => setQuery(item.query)}
                className="rounded-full bg-[#f1e8fb] px-3 py-1.5 text-sm font-semibold text-[#7345ab]"
              >
                {item.query}
              </button>
            ),
          )}
        </div>
      </div>

      {results.length > 0 && (
        <div className="space-y-3">
          {visibleResults.map((item) => {
            const summaryTranslation = showTranslations
              ? item.translation ?? item.primary_definition ?? null
              : null;
            const definitionText =
              item.primary_definition && item.primary_definition !== summaryTranslation
                ? item.primary_definition
                : item.primary_definition && !summaryTranslation
                  ? item.primary_definition
                  : null;

            return (
              <Link
                key={`${item.entry_type}-${item.entry_id}`}
                href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
                onClick={() => void rememberSearch(item)}
                className="block rounded-[0.9rem] bg-white/94 px-4 py-4 shadow-[0_10px_20px_rgba(94,53,177,0.08)]"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[1.5rem] font-semibold leading-none text-[#572a80]">
                      {item.display_text}
                    </p>
                    <p className="mt-2 text-sm font-semibold text-[#8f82a1]">
                      {item.pronunciation ? `${item.pronunciation} ` : ""}
                      #{item.browse_rank.toLocaleString()}
                    </p>
                  </div>
                  <span className="rounded-full bg-[#f3ebff] px-3 py-1 text-xs font-semibold text-[#7d2cff]">
                    {item.entry_type}
                  </span>
                </div>

                {summaryTranslation && (
                  <p className="mt-3 text-sm font-semibold text-[#9c3af2]">{summaryTranslation}</p>
                )}
                {definitionText ? (
                  <p className="mt-2 text-[1rem] font-semibold leading-6 text-[#4d295f]">{definitionText}</p>
                ) : null}
              </Link>
            );
          })}
        </div>
      )}
    </section>
  );
}
