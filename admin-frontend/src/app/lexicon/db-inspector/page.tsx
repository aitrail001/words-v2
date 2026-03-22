"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { WordEnrichmentDetail, WordSearchResult, getWordEnrichmentDetail, searchWords } from "@/lib/words-client";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

export default function LexiconDbInspectorPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<WordSearchResult[]>([]);
  const [selectedWordId, setSelectedWordId] = useState("");
  const [wordDetail, setWordDetail] = useState<WordEnrichmentDetail | null>(null);
  const [searchLoading, setSearchLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const snapshotContext = searchParam("snapshot");

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/db-inspector");
    }
  }, []);

  const selectedWord = useMemo(
    () => searchResults.find((item) => item.id === selectedWordId) ?? searchResults[0] ?? null,
    [searchResults, selectedWordId],
  );

  useEffect(() => {
    setSelectedWordId(selectedWord?.id ?? "");
  }, [selectedWord?.id]);

  useEffect(() => {
    if (!selectedWordId) {
      setWordDetail(null);
      return;
    }
    let active = true;
    setDetailLoading(true);
    void (async () => {
      try {
        const detail = await getWordEnrichmentDetail(selectedWordId);
        if (active) setWordDetail(detail);
      } catch (error) {
        if (active) setMessage(error instanceof Error ? error.message : "Failed to load word detail.");
      } finally {
        if (active) setDetailLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedWordId]);

  const handleSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSearchLoading(true);
    setMessage(null);
    try {
      const results = await searchWords(searchQuery.trim());
      setSearchResults(results);
      setSelectedWordId(results[0]?.id ?? "");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to search words.");
    } finally {
      setSearchLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="lexicon-db-inspector-page">
      {snapshotContext ? (
        <section className="rounded-lg border border-gray-200 bg-slate-50 p-4 text-sm text-slate-800" data-testid="lexicon-db-inspector-context">
          <p className="font-medium">Workflow context</p>
          <p className="mt-1">Snapshot: {snapshotContext}</p>
          <p>Stage: Final DB verification</p>
          <p>Inspect imported DB rows for this snapshot after import completes.</p>
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div>
          <h3 className="text-2xl font-semibold text-gray-900">DB Inspector</h3>
          <p className="mt-1 text-sm text-gray-600">
            Inspect learner-facing lexicon rows that are already present in the final DB.
          </p>
        </div>

        <form onSubmit={handleSearch} className="mt-6 flex flex-wrap gap-3">
          <input
            data-testid="lexicon-db-inspector-search-input"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            className="min-w-[22rem] flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Search imported word"
          />
          <button
            type="submit"
            data-testid="lexicon-db-inspector-search-button"
            disabled={searchLoading || searchQuery.trim().length < 2}
            className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {searchLoading ? "Searching..." : "Search"}
          </button>
        </form>
        {message ? <p className="mt-3 text-sm text-gray-700">{message}</p> : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Search results</h4>
          <div className="mt-4 space-y-2">
            {searchResults.map((item) => (
              <button
                key={item.id}
                type="button"
                onClick={() => setSelectedWordId(item.id)}
                className={`w-full rounded-lg border p-3 text-left ${item.id === selectedWord?.id ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
              >
                <p className="font-medium text-gray-900">{item.word}</p>
                <p className="text-xs text-gray-500">{item.language} · rank {item.frequency_rank ?? "—"}</p>
              </button>
            ))}
            {!searchLoading && searchResults.length === 0 ? (
              <p className="text-sm text-gray-500">Search for an imported word to inspect.</p>
            ) : null}
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          {detailLoading ? <p className="text-sm text-gray-500">Loading word detail...</p> : null}
          {wordDetail ? (
            <div className="space-y-4">
              <div>
                <h4 className="text-xl font-semibold text-gray-900">{wordDetail.word}</h4>
                <p className="mt-1 text-sm text-gray-500">
                  {wordDetail.language} · CEFR {wordDetail.cefr_level ?? "—"} · rank {wordDetail.frequency_rank ?? "—"}
                </p>
                <p className="mt-1 text-sm text-gray-500">
                  generated {formatDateTime(wordDetail.learner_generated_at)} · phonetic source {wordDetail.phonetic_source ?? "—"}
                </p>
              </div>

              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Meanings</p>
                  <p className="font-medium">{wordDetail.meanings.length}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Runs</p>
                  <p className="font-medium">{wordDetail.enrichment_runs.length}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Phonetic</p>
                  <p className="font-medium">{wordDetail.phonetic ?? "—"}</p>
                </div>
              </div>

              <div className="space-y-3">
                {wordDetail.meanings.map((meaning) => (
                  <article key={meaning.id} className="rounded-lg border border-gray-200 p-4">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-gray-900">{meaning.definition}</p>
                      {meaning.part_of_speech ? <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-600">{meaning.part_of_speech}</span> : null}
                    </div>
                    <p className="mt-2 text-sm text-gray-600">example: {meaning.example_sentence ?? "—"}</p>
                    {meaning.examples.length > 0 ? (
                      <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-gray-600">
                        {meaning.examples.map((example) => (
                          <li key={example.id}>{example.sentence}</li>
                        ))}
                      </ul>
                    ) : null}
                  </article>
                ))}
              </div>
            </div>
          ) : !detailLoading ? (
            <p className="text-sm text-gray-500">Select a result to inspect final DB state.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
