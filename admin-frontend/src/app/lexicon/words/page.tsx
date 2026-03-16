"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  type EnrichedMeaning,
  type WordEnrichmentDetail,
  type WordSearchResult,
  getWordEnrichmentDetail,
  searchWords,
} from "@/lib/words-client";

const formatDateTime = (value: string | null | undefined): string => {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
};

const formatJson = (value: unknown): string => {
  if (value === null || value === undefined) return "—";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
};

const FieldCard = ({ label, value }: { label: string; value: string }) => (
  <div className="rounded border border-gray-200 bg-white p-3">
    <p className="text-gray-500">{label}</p>
    <p className="font-medium text-gray-900">{value || "—"}</p>
  </div>
);

const MeaningSection = ({ meaning }: { meaning: EnrichedMeaning }) => (
  <article className="space-y-3 rounded-lg border border-gray-200 bg-white p-4 text-sm">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h4 className="text-base font-semibold text-gray-900">
          {meaning.order_index + 1}. {meaning.definition}
        </h4>
        <p className="mt-1 text-xs text-gray-500">
          synset: {meaning.wn_synset_id ?? "—"} · pos: {meaning.part_of_speech ?? "—"}
        </p>
      </div>
      <div className="text-right text-xs text-gray-500">
        <p>source: {meaning.source ?? "—"}</p>
        <p>created: {formatDateTime(meaning.created_at)}</p>
      </div>
    </div>

    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      <FieldCard label="Primary domain" value={meaning.primary_domain ?? "—"} />
      <FieldCard label="Register" value={meaning.register ?? "—"} />
      <FieldCard label="Source reference" value={meaning.source_reference ?? "—"} />
      <FieldCard label="Generated at" value={formatDateTime(meaning.learner_generated_at)} />
    </div>

    <div className="space-y-2 text-gray-700">
      <p><span className="font-medium text-gray-900">Usage note:</span> {meaning.usage_note ?? "—"}</p>
      <p><span className="font-medium text-gray-900">Secondary domains:</span> {meaning.secondary_domains?.join(", ") || "—"}</p>
      <p><span className="font-medium text-gray-900">Grammar patterns:</span> {meaning.grammar_patterns?.join(", ") || "—"}</p>
    </div>

    <div className="grid gap-4 lg:grid-cols-3">
      <section>
        <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Translations</h5>
        {meaning.translations.length > 0 ? (
          <ul className="mt-2 space-y-1 text-gray-700">
            {meaning.translations.map((translation) => (
              <li key={translation.id}>
                {translation.language}: {translation.translation}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-gray-500">No translations.</p>
        )}
      </section>

      <section>
        <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Examples</h5>
        {meaning.examples.length > 0 ? (
          <ul className="mt-2 space-y-1 text-gray-700">
            {meaning.examples.map((example) => (
              <li key={example.id}>{example.sentence}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-gray-500">No examples.</p>
        )}
      </section>

      <section>
        <h5 className="text-xs font-semibold uppercase tracking-wide text-gray-500">Relations</h5>
        {meaning.relations.length > 0 ? (
          <ul className="mt-2 space-y-1 text-gray-700">
            {meaning.relations.map((relation) => (
              <li key={relation.id}>
                {relation.relation_type}: {relation.related_word}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-gray-500">No relations.</p>
        )}
      </section>
    </div>
  </article>
);

export default function LexiconWordsPage() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<WordSearchResult[]>([]);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [selectedWordId, setSelectedWordId] = useState("");
  const [wordDetail, setWordDetail] = useState<WordEnrichmentDetail | null>(null);
  const [wordDetailLoading, setWordDetailLoading] = useState(false);
  const [wordDetailError, setWordDetailError] = useState<string | null>(null);

  useEffect(() => {
    const hasToken = Boolean(readAccessToken());
    setIsAuthenticated(hasToken);
    if (!hasToken) {
      redirectToLogin("/lexicon/words");
    }
  }, []);

  const selectedWord = useMemo(
    () => searchResults.find((word) => word.id === selectedWordId) ?? null,
    [searchResults, selectedWordId],
  );

  const handleWordSearch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (searchQuery.trim().length < 2) {
      setSearchResults([]);
      setSearchError("Enter at least 2 characters.");
      return;
    }
    setSearchLoading(true);
    setSearchError(null);
    try {
      const results = await searchWords(searchQuery.trim());
      setSearchResults(results);
      setSelectedWordId((current) => (
        results.some((word) => word.id === current) ? current : (results[0]?.id ?? "")
      ));
    } catch (error) {
      console.error("Failed to search imported words", error);
      setSearchResults([]);
      setSelectedWordId("");
      setSearchError("Failed to search imported words.");
    } finally {
      setSearchLoading(false);
    }
  };

  useEffect(() => {
    if (!selectedWordId) {
      setWordDetail(null);
      return;
    }
    let active = true;
    setWordDetailLoading(true);
    setWordDetailError(null);
    void (async () => {
      try {
        const detail = await getWordEnrichmentDetail(selectedWordId);
        if (!active) return;
        setWordDetail(detail);
      } catch (error) {
        console.error("Failed to load word detail", error);
        if (!active) return;
        setWordDetail(null);
        setWordDetailError("Failed to load word enrichment detail.");
      } finally {
        if (active) setWordDetailLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedWordId]);

  if (!isAuthenticated) {
    return <div data-testid="admin-auth-loading" className="text-sm text-gray-500">Checking authentication…</div>;
  }

  return (
    <div className="space-y-6" data-testid="lexicon-words-page">
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h2 className="text-2xl font-semibold text-gray-900">Lexicon Words</h2>
        <p className="mt-2 text-sm text-gray-600">
          Search imported words already present in the main DB and inspect the full stored lexicon
          record, including provenance, forms, translations, examples, relations, and enrichment runs.
        </p>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-4">
        <form className="flex flex-col gap-3 md:flex-row" onSubmit={handleWordSearch}>
          <input
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search imported words..."
            className="flex-1 rounded-md border border-gray-300 px-3 py-2"
            data-testid="lexicon-words-search-input"
          />
          <button
            type="submit"
            disabled={searchLoading}
            className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
            data-testid="lexicon-words-search-button"
          >
            {searchLoading ? "Searching..." : "Search"}
          </button>
        </form>
        {searchError ? <p className="mt-3 text-sm text-red-600">{searchError}</p> : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="space-y-2" data-testid="lexicon-words-results-list">
          {searchResults.length === 0 ? (
            <p className="text-sm text-gray-500">No search results yet.</p>
          ) : (
            searchResults.map((word) => (
              <button
                key={word.id}
                type="button"
                onClick={() => setSelectedWordId(word.id)}
                className={`w-full rounded-md border p-3 text-left ${
                  selectedWordId === word.id ? "border-blue-500 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"
                }`}
                data-testid={`lexicon-words-word-${word.id}`}
              >
                <p className="font-medium">{word.word}</p>
                <p className="text-xs text-gray-500">rank: {word.frequency_rank ?? "—"}</p>
              </button>
            ))
          )}
        </div>

        <div className="rounded-lg border border-gray-200 bg-gray-50 p-4" data-testid="lexicon-words-detail-panel">
          {wordDetailLoading ? <p className="text-sm text-gray-500">Loading word detail...</p> : null}
          {wordDetailError ? <p className="text-sm text-red-600">{wordDetailError}</p> : null}
          {wordDetail ? (
            <div className="space-y-4">
              <div>
                <h3 className="text-xl font-semibold text-gray-900">{wordDetail.word}</h3>
                <p className="text-sm text-gray-500">
                  phonetic: {wordDetail.phonetic ?? "—"} · CEFR: {wordDetail.cefr_level ?? "—"} · POS: {wordDetail.part_of_speech?.join(", ") || "—"}
                </p>
                <p className="text-xs text-gray-500">
                  selected result: {selectedWord?.word ?? wordDetail.word}
                </p>
              </div>

              <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-4">
                <FieldCard label="Frequency rank" value={String(wordDetail.frequency_rank ?? "—")} />
                <FieldCard label="Phonetic source" value={wordDetail.phonetic_source ?? "—"} />
                <FieldCard label="Source type" value={wordDetail.source_type ?? "—"} />
                <FieldCard label="Source reference" value={wordDetail.source_reference ?? "—"} />
                <FieldCard label="Created at" value={formatDateTime(wordDetail.created_at)} />
                <FieldCard label="Generated at" value={formatDateTime(wordDetail.learner_generated_at)} />
                <FieldCard label="Meanings" value={String(wordDetail.meanings.length)} />
                <FieldCard label="Enrichment runs" value={String(wordDetail.enrichment_runs.length)} />
              </div>

              <section className="rounded-lg border border-gray-200 bg-white p-4">
                <h4 className="text-base font-semibold text-gray-900">Word record</h4>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Confusable words</p>
                    <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 text-xs text-gray-700">{formatJson(wordDetail.confusable_words)}</pre>
                  </div>
                  <div>
                    <p className="text-xs font-semibold uppercase tracking-wide text-gray-500">Word forms</p>
                    <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 text-xs text-gray-700">{formatJson(wordDetail.word_forms)}</pre>
                  </div>
                </div>
              </section>

              <section className="space-y-3">
                <h4 className="text-base font-semibold text-gray-900">Meanings</h4>
                {wordDetail.meanings.map((meaning) => (
                  <MeaningSection key={meaning.id} meaning={meaning} />
                ))}
              </section>

              <section className="rounded-lg border border-gray-200 bg-white p-4">
                <h4 className="text-base font-semibold text-gray-900">Enrichment provenance</h4>
                {wordDetail.enrichment_runs.length > 0 ? (
                  <ul className="mt-3 space-y-2 text-sm text-gray-700">
                    {wordDetail.enrichment_runs.map((run) => (
                      <li key={run.id} className="rounded border border-gray-200 bg-gray-50 p-3">
                        {run.generator_provider ?? "—"} / {run.generator_model ?? "—"} · verdict: {run.verdict ?? "—"} · created: {formatDateTime(run.created_at)}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-3 text-sm text-gray-500">No enrichment runs recorded.</p>
                )}
              </section>
            </div>
          ) : !wordDetailLoading ? (
            <p className="text-sm text-gray-500">Search and select a word to inspect imported learner-facing data.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
