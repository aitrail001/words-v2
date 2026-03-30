"use client";

import { useEffect, useMemo, useRef, useState } from "react";

import { LexiconSectionNav } from "@/components/lexicon/section-nav";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  browseLexiconInspectorEntries,
  getLexiconInspectorDetail,
  LexiconInspectorDetail,
  LexiconInspectorFamily,
  LexiconInspectorFamilyFilter,
  LexiconInspectorListEntry,
  LexiconInspectorSort,
  LexiconInspectorVoiceAsset,
} from "@/lib/lexicon-inspector-client";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

const PAGE_LIMIT = 10;

function phoneticPreview(phonetics: Record<string, unknown> | null | undefined): string {
  if (!phonetics) return "—";
  for (const locale of ["us", "uk", "au"]) {
    const entry = phonetics[locale];
    if (entry && typeof entry === "object" && !Array.isArray(entry)) {
      const ipa = (entry as { ipa?: string }).ipa;
      if (ipa) return ipa;
    }
  }
  return "—";
}

function phoneticEntries(phonetics: Record<string, unknown> | null | undefined): Array<{
  label: string;
  ipa: string;
  confidence: string | null;
}> {
  if (!phonetics) return [];
  return [
    ["au", "AU"],
    ["us", "US"],
    ["uk", "UK"],
  ]
    .map(([key, label]) => {
      const entry = phonetics[key];
      if (!entry || typeof entry !== "object" || Array.isArray(entry)) return null;
      const ipa = typeof (entry as { ipa?: unknown }).ipa === "string" ? (entry as { ipa: string }).ipa : null;
      if (!ipa) return null;
      const confidenceValue = (entry as { confidence?: unknown }).confidence;
      return {
        label,
        ipa,
        confidence: typeof confidenceValue === "number" ? confidenceValue.toFixed(2) : null,
      };
    })
    .filter((value): value is { label: string; ipa: string; confidence: string | null } => value !== null);
}

function voiceScopeLabel(value: string): string {
  if (value === "word") return "Word";
  if (value === "definition") return "Definition";
  if (value === "example") return "Example";
  return value;
}

function joinResolvedTarget(base: string | null | undefined, relativePath: string | null | undefined): string | null {
  const normalizedBase = String(base ?? "").trim();
  const normalizedRelativePath = String(relativePath ?? "").trim().replace(/^\/+/, "");
  if (!normalizedBase || !normalizedRelativePath) return null;
  return `${normalizedBase.replace(/\/+$/, "")}/${normalizedRelativePath}`;
}

function resolveVoiceAssetTarget(asset: LexiconInspectorVoiceAsset): string {
  return asset.resolved_target_url ?? joinResolvedTarget(asset.primary_target_base, asset.relative_path) ?? asset.playback_url;
}

function VoiceAssetPlaybackButton({ asset }: { asset: LexiconInspectorVoiceAsset }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const [loading, setLoading] = useState(false);

  const playLabel = `Play ${voiceScopeLabel(asset.content_scope)} voice asset ${asset.locale} ${asset.voice_role}`;

  useEffect(() => () => {
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
  }, []);

  return (
    <div className="flex items-center justify-start gap-2 md:justify-end">
      <audio ref={audioRef} preload="none" className="hidden" />
      <button
        type="button"
        aria-label={playLabel}
        disabled={loading}
        onClick={async () => {
          const player = audioRef.current;
          if (!player) return;
          if (!player.src) {
            const token = readAccessToken();
            if (!token) {
              redirectToLogin("/lexicon/db-inspector");
              return;
            }
            setLoading(true);
            try {
              const response = await fetch(asset.playback_url, {
                headers: {
                  Authorization: `Bearer ${token}`,
                },
              });
              if (response.status === 401) {
                redirectToLogin("/lexicon/db-inspector");
                return;
              }
              if (!response.ok) {
                return;
              }
              const audioBlob = await response.blob();
              if (objectUrlRef.current) {
                URL.revokeObjectURL(objectUrlRef.current);
              }
              objectUrlRef.current = URL.createObjectURL(audioBlob);
              player.src = objectUrlRef.current;
            } finally {
              setLoading(false);
            }
          }
          player.currentTime = 0;
          const playback = player.play();
          if (playback && typeof playback.catch === "function") {
            void playback.catch(() => {});
          }
        }}
        className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
      >
        {loading ? "Loading…" : "Play"}
      </button>
    </div>
  );
}

function VoiceAssetRows({ assets }: { assets: LexiconInspectorVoiceAsset[] }) {
  return (
    <section className="rounded-lg border border-gray-200 p-4">
      <p className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Voice assets</p>
      <div className="mt-3 space-y-3 text-sm text-gray-900">
        {assets.length ? assets.map((asset) => (
          <div
            key={asset.id}
            className="grid gap-3 rounded-lg border border-gray-200 bg-gray-50 p-4 md:grid-cols-[12rem_minmax(0,1fr)_7rem] md:items-center"
          >
            <div className="space-y-1">
              <p className="font-medium text-gray-900">
                {voiceScopeLabel(asset.content_scope)} · {asset.locale} · {asset.voice_role}
              </p>
              <p className="text-xs text-gray-500">
                {asset.provider}/{asset.family} · {asset.voice_id}
              </p>
              <p className="text-xs text-gray-500">
                {asset.profile_key} · {asset.audio_format} · {asset.status}
              </p>
            </div>
            <div className="space-y-1 text-xs">
              <p className="font-mono text-gray-700">relative: {asset.relative_path ?? "—"}</p>
              <p className="font-mono text-gray-700">resolved: {resolveVoiceAssetTarget(asset)}</p>
              <p className="text-gray-500">
                route: {asset.playback_route_kind} · target: {asset.primary_target_kind}
              </p>
            </div>
            <VoiceAssetPlaybackButton asset={asset} />
          </div>
        )) : <p>—</p>}
      </div>
    </section>
  );
}

export default function LexiconDbInspectorPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [familyFilter, setFamilyFilter] = useState<LexiconInspectorFamilyFilter>("all");
  const [sort, setSort] = useState<LexiconInspectorSort>("updated_desc");
  const [offset, setOffset] = useState(0);
  const [entries, setEntries] = useState<LexiconInspectorListEntry[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [selectedEntryKey, setSelectedEntryKey] = useState("");
  const [detail, setDetail] = useState<LexiconInspectorDetail | null>(null);
  const [browseLoading, setBrowseLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const snapshotContext = searchParam("snapshot");

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/db-inspector");
    }
  }, []);

  const selectedEntry = useMemo(
    () => entries.find((item) => `${item.family}:${item.id}` === selectedEntryKey) ?? entries[0] ?? null,
    [entries, selectedEntryKey],
  );

  useEffect(() => {
    setSelectedEntryKey(selectedEntry ? `${selectedEntry.family}:${selectedEntry.id}` : "");
  }, [selectedEntry]);

  useEffect(() => {
    let active = true;
    setBrowseLoading(true);
    setMessage(null);
    void (async () => {
      try {
        const response = await browseLexiconInspectorEntries({
          family: familyFilter,
          q: searchQuery || undefined,
          sort,
          limit: PAGE_LIMIT,
          offset,
        });
        if (!active) return;
        setEntries(response.items);
        setTotal(response.total);
        setHasMore(response.has_more);
      } catch (error) {
        if (active) setMessage(error instanceof Error ? error.message : "Failed to browse DB entries.");
      } finally {
        if (active) setBrowseLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [familyFilter, offset, searchQuery, sort]);

  useEffect(() => {
    if (!selectedEntry) {
      setDetail(null);
      return;
    }
    let active = true;
    setDetailLoading(true);
    setMessage(null);
    void (async () => {
      try {
        const nextDetail = await getLexiconInspectorDetail(selectedEntry.family as LexiconInspectorFamily, selectedEntry.id);
        if (active) setDetail(nextDetail);
      } catch (error) {
        if (active) setMessage(error instanceof Error ? error.message : "Failed to load lexicon detail.");
      } finally {
        if (active) setDetailLoading(false);
      }
    })();
    return () => {
      active = false;
    };
  }, [selectedEntry]);

  return (
    <div className="space-y-6" data-testid="lexicon-db-inspector-page">
      {snapshotContext ? (
        <section className="rounded-lg border border-gray-200 bg-slate-50 p-4 text-sm text-slate-800" data-testid="lexicon-db-inspector-context">
          <p className="font-medium">Workflow context</p>
          <p className="mt-1">Snapshot: {snapshotContext}</p>
          <p>Stage: Final DB verification</p>
          <p>Browse imported DB rows for this snapshot after import completes.</p>
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div>
          <h3 className="text-2xl font-semibold text-gray-900">DB Inspector</h3>
          <p className="mt-1 text-sm text-gray-600">
            Browse and inspect final DB entries across words, phrases, and references.
          </p>
        </div>
        <div className="mt-4">
          <LexiconSectionNav
            testId="lexicon-db-section-nav"
            items={[
              { label: "Enrichment Import", href: "/lexicon/import-db" },
              { label: "DB Inspector", href: "/lexicon/db-inspector", active: true },
            ]}
          />
        </div>

        <div className="mt-6 grid gap-3 md:grid-cols-[minmax(0,1fr)_12rem_12rem]">
          <input
            data-testid="lexicon-db-inspector-search-input"
            value={searchQuery}
            onChange={(event) => {
              setSearchQuery(event.target.value);
              setOffset(0);
            }}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            placeholder="Search imported entries"
          />
          <select
            data-testid="lexicon-db-inspector-family-filter"
            value={familyFilter}
            onChange={(event) => {
              setFamilyFilter(event.target.value as LexiconInspectorFamilyFilter);
              setOffset(0);
            }}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="all">All families</option>
            <option value="word">Words</option>
            <option value="phrase">Phrases</option>
            <option value="reference">References</option>
          </select>
          <select
            data-testid="lexicon-db-inspector-sort"
            value={sort}
            onChange={(event) => {
              setSort(event.target.value as LexiconInspectorSort);
              setOffset(0);
            }}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm"
          >
            <option value="updated_desc">Newest first</option>
            <option value="rank_asc">Rank ascending</option>
            <option value="alpha_asc">Alphabetical</option>
          </select>
        </div>
        {message ? <p className="mt-3 text-sm text-gray-700">{message}</p> : null}
      </section>

      <section className="grid gap-6 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Entries</h4>
            <span className="text-xs text-gray-500">{total} total</span>
          </div>
          <div className="mt-4 space-y-2" data-testid="lexicon-db-inspector-results">
            {entries.map((item) => (
              <button
                key={`${item.family}:${item.id}`}
                type="button"
                onClick={() => setSelectedEntryKey(`${item.family}:${item.id}`)}
                className={`w-full rounded-lg border p-3 text-left ${item.id === selectedEntry?.id && item.family === selectedEntry?.family ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
              >
                <div className="flex items-center justify-between gap-2">
                  <p className="font-medium text-gray-900">{item.display_text}</p>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">{item.family}</span>
                </div>
                <p className="mt-1 text-xs text-gray-500">
                  {item.language}
                  {item.secondary_label ? ` · ${item.secondary_label}` : ""}
                  {item.frequency_rank ? ` · rank ${item.frequency_rank}` : ""}
                </p>
                <p className="text-xs text-gray-500">
                  {item.source_reference ?? "—"} · {formatDateTime(item.created_at)}
                </p>
              </button>
            ))}
            {!browseLoading && entries.length === 0 ? (
              <p className="text-sm text-gray-500">No imported entries matched the current filters.</p>
            ) : null}
          </div>
          <div className="mt-4 flex items-center justify-between gap-3">
            <button
              type="button"
              data-testid="lexicon-db-inspector-prev-button"
              onClick={() => setOffset((current) => Math.max(0, current - PAGE_LIMIT))}
              disabled={offset === 0 || browseLoading}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
            >
              Previous
            </button>
            <span className="text-xs text-gray-500">offset {offset}</span>
            <button
              type="button"
              data-testid="lexicon-db-inspector-next-button"
              onClick={() => setOffset((current) => current + PAGE_LIMIT)}
              disabled={!hasMore || browseLoading}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>

        <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" data-testid="lexicon-db-inspector-detail">
          {detailLoading ? <p className="text-sm text-gray-500">Loading detail...</p> : null}
          {detail?.family === "word" ? (
            <div className="space-y-4">
              <div>
                <h4 className="text-xl font-semibold text-gray-900">{detail.display_text}</h4>
                <p className="mt-1 text-sm text-gray-500">
                  word · {detail.language} · CEFR {detail.cefr_level ?? "—"} · rank {detail.frequency_rank ?? "—"}
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Meanings</p>
                  <p className="font-medium">{detail.meanings.length}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Runs</p>
                  <p className="font-medium">{detail.enrichment_runs.length}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Phonetic</p>
                  <p className="font-medium">{detail.phonetic ?? "—"}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Voice assets</p>
                  <p className="font-medium">{detail.voice_assets.length}</p>
                </div>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Stored phonetics</p>
                  <div className="mt-1 space-y-1 text-sm text-gray-900">
                    {phoneticEntries(detail.phonetics).length ? phoneticEntries(detail.phonetics).map((entry) => (
                      <p key={entry.label}>
                        {entry.label}: {entry.ipa}
                        {entry.confidence ? ` (${entry.confidence})` : ""}
                      </p>
                    )) : <p>{phoneticPreview(detail.phonetics)}</p>}
                  </div>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Source</p>
                  <p className="font-medium">{detail.source_type ?? "—"}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Parts of speech</p>
                  <p className="font-medium">{detail.learner_part_of_speech?.join(", ") || "—"}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Generated</p>
                  <p className="font-medium">{formatDateTime(detail.learner_generated_at)}</p>
                </div>
              </div>
              <div className="space-y-3">
                <VoiceAssetRows assets={detail.voice_assets} />
                {detail.meanings.map((meaning) => (
                  <article key={meaning.id} className="rounded-lg border border-gray-200 p-4">
                    <p className="font-medium text-gray-900">{meaning.definition}</p>
                    <p className="mt-1 text-sm text-gray-500">
                      {meaning.part_of_speech ?? "—"}
                      {meaning.primary_domain ? ` · ${meaning.primary_domain}` : ""}
                      {meaning.register_label ? ` · ${meaning.register_label}` : ""}
                    </p>
                    <p className="mt-2 text-sm text-gray-600">usage: {meaning.usage_note ?? "—"}</p>
                    <p className="mt-1 text-sm text-gray-600">example: {meaning.example_sentence ?? "—"}</p>
                    <div className="mt-3 grid gap-3 md:grid-cols-3">
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Grammar</p>
                        <p className="mt-1 text-sm text-gray-900">{meaning.grammar_patterns?.join(", ") || "—"}</p>
                      </div>
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Examples</p>
                        <div className="mt-1 space-y-1 text-sm text-gray-900">
                          {meaning.examples.length ? meaning.examples.map((example) => (
                            <p key={example.id}>{example.sentence}</p>
                          )) : <p>—</p>}
                        </div>
                      </div>
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Translations</p>
                        <div className="mt-1 space-y-1 text-sm text-gray-900">
                          {meaning.translations.length ? meaning.translations.map((translation) => (
                            <p key={translation.id}>
                              {translation.language}: {translation.translation}
                            </p>
                          )) : <p>—</p>}
                        </div>
                      </div>
                    </div>
                  </article>
                ))}
              </div>
            </div>
          ) : null}

          {detail?.family === "phrase" ? (
            <div className="space-y-4">
              <div>
                <h4 className="text-xl font-semibold text-gray-900">{detail.display_text}</h4>
                <p className="mt-1 text-sm text-gray-500">
                  phrase · {detail.language} · {detail.phrase_kind}
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Normalized</p>
                  <p className="font-medium">{detail.normalized_form}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">CEFR</p>
                  <p className="font-medium">{detail.cefr_level ?? "—"}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Source</p>
                  <p className="font-medium">{detail.source_type ?? "—"}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Generated</p>
                  <p className="font-medium">{formatDateTime(detail.generated_at)}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Confidence</p>
                  <p className="font-medium">{detail.confidence_score ?? "—"}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Register</p>
                  <p className="font-medium">{detail.register_label ?? "—"}</p>
                </div>
              </div>
              <div className="rounded border border-gray-200 p-3">
                <p className="text-gray-500">Usage note</p>
                <p className="font-medium">{detail.brief_usage_note ?? "—"}</p>
              </div>
              <div className="rounded border border-gray-200 p-3">
                <p className="text-gray-500">Seed metadata</p>
                <pre className="mt-2 overflow-x-auto text-xs text-gray-700">{JSON.stringify(detail.seed_metadata ?? {}, null, 2)}</pre>
              </div>
              <VoiceAssetRows assets={detail.voice_assets} />
              <div className="space-y-3">
                {detail.senses.length ? detail.senses.map((sense, index) => (
                  <article key={sense.sense_id ?? `${detail.id}-sense-${index + 1}`} className="rounded-lg border border-gray-200 p-4">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-gray-900">{sense.definition}</p>
                        <p className="mt-1 text-sm text-gray-500">
                          {sense.part_of_speech ?? detail.phrase_kind}
                        </p>
                      </div>
                      <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[11px] text-slate-700">Sense {index + 1}</span>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Usage</p>
                        <p className="mt-1 text-sm text-gray-900">{sense.usage_note ?? "—"}</p>
                      </div>
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Grammar</p>
                        <p className="mt-1 text-sm text-gray-900">{sense.grammar_patterns?.join(", ") || "—"}</p>
                      </div>
                    </div>
                    <div className="mt-3 grid gap-3 md:grid-cols-2">
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Examples</p>
                        <div className="mt-1 space-y-1 text-sm text-gray-900">
                          {sense.examples.length ? sense.examples.map((example) => (
                            <p key={example.id}>{example.sentence}</p>
                          )) : <p>—</p>}
                        </div>
                      </div>
                      <div className="rounded border border-gray-100 bg-gray-50 p-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-gray-500">Translations</p>
                        <div className="mt-1 space-y-2 text-sm text-gray-900">
                          {sense.translations.length ? sense.translations.map((translation) => (
                            <div key={translation.locale}>
                              <p className="font-medium">{translation.locale}: {translation.definition ?? "—"}</p>
                              <p>{translation.usage_note ?? "—"}</p>
                              {translation.examples.length ? <p>{translation.examples.join(" | ")}</p> : null}
                            </div>
                          )) : <p>—</p>}
                        </div>
                      </div>
                    </div>
                  </article>
                )) : (
                  <p className="text-sm text-gray-500">No structured sense detail stored for this phrase.</p>
                )}
              </div>
            </div>
          ) : null}

          {detail?.family === "reference" ? (
            <div className="space-y-4">
              <div>
                <h4 className="text-xl font-semibold text-gray-900">{detail.display_text}</h4>
                <p className="mt-1 text-sm text-gray-500">
                  reference · {detail.language} · {detail.reference_type}
                </p>
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Translation mode</p>
                  <p className="font-medium">{detail.translation_mode}</p>
                </div>
                <div className="rounded border border-gray-200 p-3">
                  <p className="text-gray-500">Pronunciation</p>
                  <p className="font-medium">{detail.pronunciation}</p>
                </div>
              </div>
              <div className="rounded border border-gray-200 p-3">
                <p className="text-gray-500">Description</p>
                <p className="font-medium">{detail.brief_description}</p>
              </div>
              <div className="space-y-2">
                {detail.localizations.map((localization) => (
                  <div key={localization.id} className="rounded border border-gray-200 p-3">
                    <p className="font-medium text-gray-900">{localization.locale}</p>
                    <p className="text-sm text-gray-600">{localization.display_form}</p>
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          {!detail && !detailLoading ? (
            <p className="text-sm text-gray-500">Select an imported entry to inspect final DB state.</p>
          ) : null}
        </div>
      </section>
    </div>
  );
}
