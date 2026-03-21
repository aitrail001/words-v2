"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  LexiconJsonlReviewItem,
  LexiconJsonlReviewMaterializeResult,
  LexiconJsonlReviewSession,
  loadLexiconJsonlReviewSession,
  materializeLexiconJsonlReviewOutputs,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

function compareReviewItems(a: LexiconJsonlReviewItem, b: LexiconJsonlReviewItem): number {
  const warningDelta = (b.warning_count ?? 0) - (a.warning_count ?? 0);
  if (warningDelta !== 0) return warningDelta;

  const pendingA = a.review_status === "pending" ? 0 : 1;
  const pendingB = b.review_status === "pending" ? 0 : 1;
  if (pendingA !== pendingB) return pendingA - pendingB;

  const rankA = a.frequency_rank ?? Number.MAX_SAFE_INTEGER;
  const rankB = b.frequency_rank ?? Number.MAX_SAFE_INTEGER;
  if (rankA !== rankB) return rankA - rankB;

  return a.display_text.localeCompare(b.display_text);
}

export default function LexiconJsonlReviewPage() {
  const [artifactPath, setArtifactPath] = useState("");
  const [decisionsPath, setDecisionsPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [session, setSession] = useState<LexiconJsonlReviewSession | null>(null);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [materializeResult, setMaterializeResult] = useState<LexiconJsonlReviewMaterializeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const artifactPathHint = "Use a container-visible repo path like data/lexicon/snapshots/... or /app/data/lexicon/snapshots/....";
  const decisionsPathHint = "Optional. Defaults to review.decisions.jsonl beside the artifact.";
  const outputDirHint = "Optional. Defaults to the artifact directory when materializing outputs.";
  const selectedCount = session?.items.length ?? 0;

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/jsonl-review");
    }
  }, []);

  const filteredItems = useMemo(() => {
    const items = session?.items ?? [];
    const normalizedSearch = search.trim().toLowerCase();
    return items
      .filter((item) => {
      if (statusFilter !== "all" && item.review_status !== statusFilter) return false;
      if (!normalizedSearch) return true;
      return [
        item.entry_id,
        item.display_text,
        item.normalized_form ?? "",
        ...(item.warning_labels ?? []),
        item.review_summary?.primary_definition ?? "",
      ].some((value) => value.toLowerCase().includes(normalizedSearch));
      })
      .sort(compareReviewItems);
  }, [search, session?.items, statusFilter]);

  const selectedItem = useMemo(
    () => filteredItems.find((item) => item.entry_id === selectedItemId) ?? filteredItems[0] ?? null,
    [filteredItems, selectedItemId],
  );

  useEffect(() => {
    setSelectedItemId(selectedItem?.entry_id ?? "");
  }, [selectedItem?.entry_id]);

  useEffect(() => {
    setDecisionReason(selectedItem?.decision_reason ?? "");
  }, [selectedItem?.decision_reason, selectedItem?.entry_id]);

  const loadSession = async (event: FormEvent) => {
    event.preventDefault();
    setLoading(true);
    setMessage(null);
    setMaterializeResult(null);
    try {
      const nextSession = await loadLexiconJsonlReviewSession({
        artifactPath,
        decisionsPath: decisionsPath || undefined,
        outputDir: outputDir || undefined,
      });
      setSession(nextSession);
      setDecisionsPath(nextSession.decisions_path);
      setOutputDir(nextSession.output_dir ?? outputDir);
      setMessage(`Loaded ${nextSession.artifact_filename}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load artifact.");
    } finally {
      setLoading(false);
    }
  };

  const replaceItem = (updated: LexiconJsonlReviewItem) => {
    setSession((current) => {
      if (!current) return current;
      const items = current.items.map((item) => (item.entry_id === updated.entry_id ? updated : item));
      const approvedCount = items.filter((item) => item.review_status === "approved").length;
      const rejectedCount = items.filter((item) => item.review_status === "rejected").length;
      return {
        ...current,
        items,
        approved_count: approvedCount,
        rejected_count: rejectedCount,
        pending_count: items.length - approvedCount - rejectedCount,
      };
    });
  };

  const saveDecision = useCallback(async (reviewStatus: "pending" | "approved" | "rejected") => {
    if (!selectedItem || !session) return;
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateLexiconJsonlReviewItem(selectedItem.entry_id, {
        artifactPath: session.artifact_path,
        decisionsPath: decisionsPath || session.decisions_path,
        reviewStatus,
        decisionReason: decisionReason || null,
      });
      replaceItem(updated);
      setMessage(`Saved ${updated.entry_id} as ${updated.review_status}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save decision.");
    } finally {
      setSaving(false);
    }
  }, [decisionsPath, selectedItem, session, decisionReason]);

  const materialize = async () => {
    if (!session) return;
    setSaving(true);
    setMessage(null);
    try {
      const result = await materializeLexiconJsonlReviewOutputs({
        artifactPath: session.artifact_path,
        decisionsPath: decisionsPath || session.decisions_path,
        outputDir: outputDir || undefined,
      });
      setMaterializeResult(result);
      setMessage("Materialized outputs.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to materialize outputs.");
    } finally {
      setSaving(false);
    }
  };

  useEffect(() => {
    const handleKeydown = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target instanceof HTMLSelectElement ||
        target?.isContentEditable
      ) {
        return;
      }

      if (!filteredItems.length || saving || loading) {
        return;
      }

      const currentIndex = filteredItems.findIndex((item) => item.entry_id === selectedItem?.entry_id);
      if (event.key === "j") {
        event.preventDefault();
        const nextIndex = currentIndex >= 0 ? Math.min(currentIndex + 1, filteredItems.length - 1) : 0;
        setSelectedItemId(filteredItems[nextIndex]?.entry_id ?? "");
        return;
      }

      if (event.key === "k") {
        event.preventDefault();
        const nextIndex = currentIndex >= 0 ? Math.max(currentIndex - 1, 0) : 0;
        setSelectedItemId(filteredItems[nextIndex]?.entry_id ?? "");
        return;
      }

      if (!selectedItem || !session) {
        return;
      }

      if (event.key === "a") {
        event.preventDefault();
        void saveDecision("approved");
      } else if (event.key === "r") {
        event.preventDefault();
        void saveDecision("rejected");
      } else if (event.key === "p") {
        event.preventDefault();
        void saveDecision("pending");
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [filteredItems, loading, saving, selectedItem, session, decisionReason, decisionsPath, saveDecision]);

  return (
    <div className="relative isolate mx-auto w-full max-w-[1900px] space-y-6 px-4 py-6 xl:px-6 2xl:px-8" data-testid="lexicon-jsonl-review-page">
      <div aria-hidden="true" className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-64 bg-[radial-gradient(circle_at_top_right,_rgba(59,130,246,0.18),_transparent_35%),radial-gradient(circle_at_top_left,_rgba(15,23,42,0.08),_transparent_30%)]" />

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white/95 shadow-[0_18px_60px_-36px_rgba(15,23,42,0.35)] backdrop-blur">
        <div className="grid gap-6 p-6 xl:grid-cols-[minmax(0,1.5fr)_minmax(18rem,22rem)] xl:p-8">
          <div className="space-y-5">
            <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
              JSONL Review Mode
            </div>
            <div className="max-w-4xl">
              <h3 className="text-3xl font-semibold tracking-tight text-slate-950" data-testid="lexicon-jsonl-review-title">
                JSONL-Only Lexicon Review
              </h3>
              <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-600">
                Review compiled artifacts directly from JSONL and persist decisions as a sidecar without using review DB tables.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">Artifact path</p>
                <p className="mt-2 break-all font-mono text-sm text-slate-800">{artifactPath || "Not loaded yet"}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">Items</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{selectedCount}</p>
              </div>
              <div className="rounded-xl border border-slate-200 bg-slate-50/70 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">Decision sidecar</p>
                <p className="mt-2 break-all font-mono text-sm text-slate-800">{decisionsPath || "review.decisions.jsonl"}</p>
              </div>
            </div>
          </div>

          <aside className="rounded-xl border border-amber-200 bg-amber-50/80 p-4 text-sm text-amber-950">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">Path format</p>
            <p className="mt-2 leading-6">{artifactPathHint}</p>
            <p className="mt-4 text-xs leading-5 text-amber-800">
              Use the repo-relative `data/...` path in Docker, or the `/app/data/...` form if you prefer to be explicit.
            </p>
          </aside>
        </div>

        <form onSubmit={loadSession} className="grid gap-4 border-t border-slate-200 bg-slate-50/60 p-6 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] xl:items-end xl:p-8">
          <label className="grid gap-1 text-sm text-slate-700">
            <span className="font-medium">Artifact path</span>
            <input
              aria-label="Artifact path"
              value={artifactPath}
              onChange={(event) => setArtifactPath(event.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              placeholder="data/lexicon/snapshots/.../words.enriched.jsonl"
            />
            <span className="text-xs leading-5 text-slate-500">{artifactPathHint}</span>
          </label>
          <label className="grid gap-1 text-sm text-slate-700">
            <span className="font-medium">Decisions path</span>
            <input
              aria-label="Decisions path"
              value={decisionsPath}
              onChange={(event) => setDecisionsPath(event.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              placeholder="review.decisions.jsonl"
            />
            <span className="text-xs leading-5 text-slate-500">{decisionsPathHint}</span>
          </label>
          <label className="grid gap-1 text-sm text-slate-700">
            <span className="font-medium">Output directory</span>
            <input
              aria-label="Output directory"
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              className="rounded-lg border border-slate-300 bg-white px-3 py-2 font-mono text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              placeholder="optional materialize folder"
            />
            <span className="text-xs leading-5 text-slate-500">{outputDirHint}</span>
          </label>
          <div className="flex flex-wrap gap-3 xl:justify-end">
            <button type="submit" disabled={!artifactPath || loading} className="rounded-lg bg-slate-950 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 disabled:opacity-50">
              {loading ? "Loading..." : "Load Artifact"}
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void materialize()} className="rounded-lg border border-sky-300 bg-white px-5 py-2.5 text-sm font-medium text-sky-700 shadow-sm transition hover:bg-sky-50 disabled:opacity-50">
              Materialize Outputs
            </button>
          </div>
        </form>
        {message ? <div className="border-t border-slate-200 px-6 py-4 text-sm text-slate-700 xl:px-8">{message}</div> : null}
      </section>

      {session ? (
        <section className="grid gap-6 2xl:grid-cols-[minmax(22rem,26rem)_minmax(0,1fr)]">
          <div className="sticky top-6 self-start rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.35)] backdrop-blur">
            <div className="mb-4 grid grid-cols-3 gap-3 text-sm">
              <div className="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">Pending</p>
                <p className="mt-1 text-xl font-semibold text-amber-950">{session.pending_count}</p>
              </div>
              <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">Approved</p>
                <p className="mt-1 text-xl font-semibold text-emerald-950">{session.approved_count}</p>
              </div>
              <div className="rounded-xl border border-rose-100 bg-rose-50 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">Rejected</p>
                <p className="mt-1 text-xl font-semibold text-rose-950">{session.rejected_count}</p>
              </div>
            </div>
            <div className="grid gap-2">
              <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
                Risk first
              </div>
              <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                Shortcuts: <span className="font-semibold text-slate-900">j</span>/<span className="font-semibold text-slate-900">k</span> move, <span className="font-semibold text-emerald-700">a</span> approve, <span className="font-semibold text-rose-700">r</span> reject, <span className="font-semibold text-slate-700">p</span> reopen
              </div>
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search entry id or display text"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              />
              <select
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as "all" | "pending" | "approved" | "rejected")}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              >
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
            </div>
            <div className="mt-4 max-h-[72vh] space-y-2 overflow-auto pr-1">
              {filteredItems.map((item) => (
                <button
                  key={item.entry_id}
                  type="button"
                  onClick={() => setSelectedItemId(item.entry_id)}
                  className={`w-full rounded-xl border p-3 text-left transition ${item.entry_id === selectedItem?.entry_id ? "border-sky-400 bg-sky-50 shadow-sm" : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"}`}
                >
                  <p className="font-medium text-gray-900">{item.display_text}</p>
                  <div className="mt-1 flex flex-wrap gap-2 text-[11px] text-slate-500">
                    <span className="rounded-full bg-slate-100 px-2 py-0.5">{item.entry_type}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5">{item.review_status}</span>
                    {item.entity_category ? <span className="rounded-full bg-slate-100 px-2 py-0.5">{item.entity_category}</span> : null}
                    {(item.warning_labels ?? []).map((warning) => (
                      <span key={warning} className="rounded-full bg-amber-100 px-2 py-0.5 text-amber-800">
                        {warning}
                      </span>
                    ))}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className="min-w-0 rounded-2xl border border-slate-200 bg-white/95 p-4 shadow-[0_12px_40px_-28px_rgba(15,23,42,0.35)] backdrop-blur">
            {selectedItem ? (
              <div className="space-y-6">
                <div className="space-y-4">
                <div className="space-y-4">
                  <div>
                    <h4 className="text-2xl font-semibold tracking-tight text-slate-950">{selectedItem.display_text}</h4>
                    <p className="mt-1 text-sm text-slate-500">
                      {selectedItem.entry_id} · {selectedItem.entry_type} · reviewed {formatDateTime(selectedItem.reviewed_at)}
                      </p>
                      <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-500">
                        <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">status: {selectedItem.review_status}</span>
                        {selectedItem.entity_category ? <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">entity: {selectedItem.entity_category}</span> : null}
                        {selectedItem.cefr_level ? <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">CEFR: {selectedItem.cefr_level}</span> : null}
                        {selectedItem.frequency_rank ? <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1">rank: {selectedItem.frequency_rank}</span> : null}
                      </div>
                    </div>
                    <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Reviewer summary</p>
                        {(selectedItem.warning_labels ?? []).map((warning) => (
                          <span key={warning} className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
                            {warning}
                          </span>
                        ))}
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-3">
                        <div className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Senses</p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">{selectedItem.review_summary?.sense_count ?? 0}</p>
                        </div>
                        <div className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Form variants</p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">{selectedItem.review_summary?.form_variant_count ?? 0}</p>
                        </div>
                        <div className="rounded-xl border border-slate-200 bg-white px-3 py-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Confusables</p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">{selectedItem.review_summary?.confusable_count ?? 0}</p>
                        </div>
                      </div>
                      <div className="mt-3 space-y-2 text-sm text-slate-600">
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Primary definition</p>
                          <p className="mt-1 text-slate-900">{selectedItem.review_summary?.primary_definition ?? "—"}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Primary example</p>
                          <p className="mt-1 text-slate-900">{selectedItem.review_summary?.primary_example ?? "—"}</p>
                        </div>
                        <div>
                          <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Provenance</p>
                          <div className="mt-1 flex flex-wrap gap-2">
                            {(selectedItem.review_summary?.provenance_sources?.length ?? 0) > 0 ? (
                              selectedItem.review_summary?.provenance_sources.map((source) => (
                                <span key={source} className="rounded-full border border-slate-200 bg-white px-2.5 py-1 text-xs text-slate-700">
                                  {source}
                                </span>
                              ))
                            ) : (
                              <span className="text-slate-900">—</span>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                    <label className="grid gap-1 text-sm text-gray-700">
                      <span className="font-medium text-slate-700">Decision reason</span>
                      <textarea
                        data-testid="jsonl-review-decision-reason"
                        value={decisionReason}
                        onChange={(event) => setDecisionReason(event.target.value)}
                        className="min-h-32 w-full rounded-xl border border-slate-300 bg-white px-3 py-3 text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
                        placeholder="Optional reason to preserve in the sidecar"
                      />
                    </label>
                    <div className="flex flex-wrap gap-3">
                      <button type="button" data-testid="jsonl-review-approve-button" disabled={saving} onClick={() => void saveDecision("approved")} className="rounded-lg border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-800 shadow-sm transition hover:bg-emerald-100 disabled:opacity-50">
                        Approve
                      </button>
                      <button type="button" data-testid="jsonl-review-reject-button" disabled={saving} onClick={() => void saveDecision("rejected")} className="rounded-lg border border-rose-300 bg-rose-50 px-4 py-2 text-sm font-medium text-rose-800 shadow-sm transition hover:bg-rose-100 disabled:opacity-50">
                        Reject
                      </button>
                      <button type="button" data-testid="jsonl-review-reopen-button" disabled={saving} onClick={() => void saveDecision("pending")} className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:bg-slate-50 disabled:opacity-50">
                        Reopen
                      </button>
                    </div>
                  </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3 rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
                    <div>
                      <h5 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Raw compiled JSON</h5>
                      <p className="mt-1 text-xs text-slate-500">Scrollable snapshot of the compiled record being reviewed.</p>
                    </div>
                    <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">scrolling panel</span>
                  </div>
                  <pre className="max-h-[56vh] overflow-auto rounded-2xl bg-slate-950 p-4 text-xs leading-5 text-slate-100 shadow-inner">
                    {JSON.stringify(selectedItem.compiled_payload, null, 2)}
                  </pre>
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-500">No items match the current filter.</p>
            )}
          </div>
        </section>
      ) : null}

      {materializeResult ? (
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm text-sm text-gray-700">
          <p>{materializeResult.approved_output_path}</p>
          <p>{materializeResult.rejected_output_path}</p>
          <p>{materializeResult.regenerate_output_path}</p>
        </section>
      ) : null}
    </div>
  );
}
