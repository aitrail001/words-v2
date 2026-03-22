"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  downloadApprovedLexiconJsonlReviewOutput,
  downloadDecisionLexiconJsonlReviewOutput,
  downloadRegenerateLexiconJsonlReviewOutput,
  downloadRejectedLexiconJsonlReviewOutput,
  LexiconJsonlReviewItem,
  LexiconJsonlReviewMaterializeResult,
  LexiconJsonlReviewSession,
  loadLexiconJsonlReviewSession,
  materializeLexiconJsonlReviewOutputs,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";

type ReviewDecisionStatus = "pending" | "approved" | "rejected";

function downloadTextFile(filename: string, text: string): void {
  const blob = new Blob([text], { type: "application/x-ndjson" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

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

function nextPendingEntryId(items: LexiconJsonlReviewItem[], currentEntryId: string): string | null {
  const pendingItems = items.filter((item) => item.review_status === "pending");
  if (!pendingItems.length) return null;

  const currentIndex = pendingItems.findIndex((item) => item.entry_id === currentEntryId);
  if (currentIndex >= 0 && currentIndex + 1 < pendingItems.length) {
    return pendingItems[currentIndex + 1].entry_id;
  }
  if (currentIndex > 0) {
    return pendingItems[currentIndex - 1].entry_id;
  }
  return pendingItems[0]?.entry_id ?? null;
}

export default function LexiconJsonlReviewPage() {
  const [artifactPath, setArtifactPath] = useState("");
  const [decisionsPath, setDecisionsPath] = useState("");
  const [outputDir, setOutputDir] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [session, setSession] = useState<LexiconJsonlReviewSession | null>(null);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [materializeResult, setMaterializeResult] = useState<LexiconJsonlReviewMaterializeResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingDecision, setPendingDecision] = useState<ReviewDecisionStatus | null>(null);
  const artifactPathHint = "Use a container-visible repo path like data/lexicon/snapshots/... or /app/data/lexicon/snapshots/....";
  const decisionsPathHint = "Optional. Defaults to reviewed/review.decisions.jsonl under the snapshot.";
  const outputDirHint = "Optional. Defaults to the shared reviewed/ directory under the artifact snapshot.";
  const selectedCount = session?.items.length ?? 0;
  const contextArtifactPath = session?.artifact_path ?? artifactPath;
  const contextDecisionsPath = session?.decisions_path ?? decisionsPath;
  const contextOutputDir = session?.output_dir ?? outputDir;

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/jsonl-review");
    }
  }, []);

  const loadSessionForPaths = useCallback(async (
    nextArtifactPath: string,
    nextDecisionsPath?: string,
    nextOutputDir?: string,
  ) => {
    setLoading(true);
    setMessage(null);
    setMaterializeResult(null);
    try {
      const nextSession = await loadLexiconJsonlReviewSession({
        artifactPath: nextArtifactPath,
        decisionsPath: nextDecisionsPath || undefined,
        outputDir: nextOutputDir || undefined,
      });
      setSession(nextSession);
      setArtifactPath(nextSession.artifact_path);
      setDecisionsPath(nextSession.decisions_path);
      setOutputDir(nextSession.output_dir ?? nextOutputDir ?? "");
      setMessage(`Loaded ${nextSession.artifact_filename}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load artifact.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const nextArtifactPath = searchParam("artifactPath");
    const nextDecisionsPath = searchParam("decisionsPath");
    const nextOutputDir = searchParam("outputDir");
    const nextSourceReference = searchParam("sourceReference");
    if (nextArtifactPath) {
      setArtifactPath(nextArtifactPath);
      setDecisionsPath(nextDecisionsPath);
      setOutputDir(nextOutputDir);
      setSourceReference(nextSourceReference);
      void loadSessionForPaths(nextArtifactPath, nextDecisionsPath, nextOutputDir);
    }
  }, [loadSessionForPaths]);

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
    setPendingDecision(null);
  }, [selectedItem?.decision_reason, selectedItem?.entry_id]);

  const loadSession = async (event: FormEvent) => {
    event.preventDefault();
    await loadSessionForPaths(artifactPath, decisionsPath, outputDir);
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

  const confirmDecision = useCallback(async (reviewStatus: ReviewDecisionStatus) => {
    if (!selectedItem || !session) return;
    const nextEntryId = nextPendingEntryId([...(session.items ?? [])].sort(compareReviewItems), selectedItem.entry_id);
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
      if (nextEntryId && nextEntryId !== updated.entry_id) {
        setSelectedItemId(nextEntryId);
      }
      setPendingDecision(null);
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

  const downloadOutput = async (kind: "approved" | "decisions" | "rejected" | "regenerate") => {
    if (!session) return;
    setSaving(true);
    setMessage(null);
    try {
      const input = {
        artifactPath: session.artifact_path,
        decisionsPath: decisionsPath || session.decisions_path,
        outputDir: outputDir || undefined,
      };
      const text =
        kind === "approved"
          ? await downloadApprovedLexiconJsonlReviewOutput(input)
          : kind === "decisions"
            ? await downloadDecisionLexiconJsonlReviewOutput(input)
            : kind === "rejected"
              ? await downloadRejectedLexiconJsonlReviewOutput(input)
              : await downloadRegenerateLexiconJsonlReviewOutput(input);
      downloadTextFile(`jsonl-review.${kind}.jsonl`, text);
      setMessage(`Downloaded ${kind} output.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : `Failed to download ${kind} output.`);
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

      if (pendingDecision) {
        if (event.key === "Enter") {
          event.preventDefault();
          void confirmDecision(pendingDecision);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          setPendingDecision(null);
          return;
        }
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
        setPendingDecision("approved");
      } else if (event.key === "r") {
        event.preventDefault();
        setPendingDecision("rejected");
      } else if (event.key === "p") {
        event.preventDefault();
        setPendingDecision("pending");
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [confirmDecision, filteredItems, loading, pendingDecision, saving, selectedItem, session]);

  return (
    <div className="space-y-6" data-testid="lexicon-jsonl-review-page">
      {(contextArtifactPath || contextDecisionsPath || contextOutputDir || sourceReference) ? (
        <section className="rounded-lg border border-sky-200 bg-sky-50 p-4 text-sm text-sky-900" data-testid="lexicon-jsonl-review-context">
          <p className="font-medium">Workflow context</p>
          {sourceReference ? <p className="mt-1">Source reference: {sourceReference}</p> : null}
          <p>Artifact: {contextArtifactPath || "—"}</p>
          <p>Decisions: {contextDecisionsPath || "—"}</p>
          <p>Output dir: {contextOutputDir || "—"}</p>
          <p className="mt-1">Stage: Alternate review path</p>
          <p>Next step: Materialize approved rows, then open Import DB.</p>
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.5fr)_20rem]">
          <div className="space-y-5">
            <div className="inline-flex items-center gap-2 rounded-full border border-sky-200 bg-sky-50 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">
              JSONL Review Mode
            </div>
            <div className="max-w-4xl">
              <h3 className="text-2xl font-semibold text-gray-900" data-testid="lexicon-jsonl-review-title">
                JSONL-Only Lexicon Review
              </h3>
              <p className="mt-1 text-sm text-gray-600">
                Review compiled artifacts directly from JSONL and persist decisions as a sidecar without using review DB tables.
              </p>
            </div>

            <div className="grid gap-3 sm:grid-cols-3">
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">Artifact path</p>
                <p className="mt-2 break-all font-mono text-sm text-slate-800">{artifactPath || "Not loaded yet"}</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">Items</p>
                <p className="mt-2 text-2xl font-semibold text-slate-950">{selectedCount}</p>
              </div>
              <div className="rounded-lg border border-gray-200 bg-gray-50 p-4">
                <p className="text-xs font-medium uppercase tracking-[0.18em] text-slate-500">Decision sidecar</p>
                <p className="mt-2 break-all font-mono text-sm text-slate-800">{decisionsPath || "reviewed/review.decisions.jsonl"}</p>
              </div>
            </div>

            <div className="grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
              <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-950">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Approve</p>
                <p className="mt-2">Approve keeps the compiled row eligible for reviewed/approved.jsonl, the reviewed file you should import into the final DB.</p>
              </div>
              <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-950">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-700">Reject</p>
                <p className="mt-2">Reject records the row in reviewed/review.decisions.jsonl, writes the rejected overlay, and adds a regeneration request row.</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-900">
                <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Reopen</p>
                <p className="mt-2">Reopen removes the final decision so the row stays pending until you decide again.</p>
              </div>
            </div>
          </div>

          <aside className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-950">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-amber-700">Path format</p>
            <p className="mt-2 leading-6">{artifactPathHint}</p>
            <p className="mt-4 text-xs leading-5 text-amber-800">
              Use the repo-relative `data/...` path in Docker, or the `/app/data/...` form if you prefer to be explicit.
            </p>
          </aside>
        </div>

        <form onSubmit={loadSession} className="mt-6 grid gap-4 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_auto] xl:items-end">
          <label className="grid gap-1 text-sm text-slate-700">
            <span className="font-medium">Artifact path</span>
            <input
              aria-label="Artifact path"
              value={artifactPath}
              onChange={(event) => setArtifactPath(event.target.value)}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm"
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
              className="rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm"
              placeholder="data/lexicon/snapshots/.../reviewed/review.decisions.jsonl"
            />
            <span className="text-xs leading-5 text-slate-500">{decisionsPathHint}</span>
          </label>
          <label className="grid gap-1 text-sm text-slate-700">
            <span className="font-medium">Output directory</span>
            <input
              aria-label="Output directory"
              value={outputDir}
              onChange={(event) => setOutputDir(event.target.value)}
              className="rounded-md border border-gray-300 bg-white px-3 py-2 font-mono text-sm"
              placeholder="data/lexicon/snapshots/.../reviewed"
            />
            <span className="text-xs leading-5 text-slate-500">{outputDirHint}</span>
          </label>
          <div className="flex flex-wrap gap-3 xl:justify-end">
            <button type="submit" disabled={!artifactPath || loading} className="rounded-lg bg-slate-950 px-5 py-2.5 text-sm font-medium text-white shadow-sm transition hover:bg-slate-800 disabled:opacity-50">
              {loading ? "Loading..." : "Load Artifact"}
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void downloadOutput("approved")} className="rounded-lg border border-emerald-300 bg-white px-5 py-2.5 text-sm font-medium text-emerald-700 shadow-sm transition hover:bg-emerald-50 disabled:opacity-50">
              Download Approved Rows
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void downloadOutput("decisions")} className="rounded-lg border border-sky-300 bg-white px-5 py-2.5 text-sm font-medium text-sky-700 shadow-sm transition hover:bg-sky-50 disabled:opacity-50">
              Download Decision Ledger
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void downloadOutput("rejected")} className="rounded-lg border border-amber-300 bg-white px-5 py-2.5 text-sm font-medium text-amber-700 shadow-sm transition hover:bg-amber-50 disabled:opacity-50">
              Download Rejected Overlay
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void downloadOutput("regenerate")} className="rounded-lg border border-violet-300 bg-white px-5 py-2.5 text-sm font-medium text-violet-700 shadow-sm transition hover:bg-violet-50 disabled:opacity-50">
              Download Regeneration Requests
            </button>
            <button type="button" disabled={!session || saving} onClick={() => void materialize()} className="rounded-lg border border-sky-300 bg-white px-5 py-2.5 text-sm font-medium text-sky-700 shadow-sm transition hover:bg-sky-50 disabled:opacity-50">
              Materialize Outputs
            </button>
          </div>
        </form>
        {message ? <div className="mt-3 text-sm text-slate-700">{message}</div> : null}
      </section>

      {session ? (
        <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
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
                Shortcuts: <span className="font-semibold text-slate-900">j</span>/<span className="font-semibold text-slate-900">k</span> move, <span className="font-semibold text-emerald-700">a</span> approve, <span className="font-semibold text-rose-700">r</span> reject, <span className="font-semibold text-slate-700">p</span> reopen, <span className="font-semibold text-slate-900">enter</span> confirm, <span className="font-semibold text-slate-900">esc</span> cancel
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

          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            {selectedItem ? (
              <div className="space-y-6">
                <div className="space-y-4">
                  <div>
                    <h4 className="text-xl font-semibold text-gray-900">{selectedItem.display_text}</h4>
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
                    <div className="rounded-lg border border-slate-200 bg-slate-50 p-4">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Reviewer summary</p>
                        {(selectedItem.warning_labels ?? []).map((warning) => (
                          <span key={warning} className="rounded-full bg-amber-100 px-2.5 py-1 text-[11px] font-medium text-amber-800">
                            {warning}
                          </span>
                        ))}
                      </div>
                      <div className="mt-3 grid gap-3 md:grid-cols-3">
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Senses</p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">{selectedItem.review_summary?.sense_count ?? 0}</p>
                        </div>
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
                          <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Form variants</p>
                          <p className="mt-1 text-lg font-semibold text-slate-900">{selectedItem.review_summary?.form_variant_count ?? 0}</p>
                        </div>
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2">
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
                        className="min-h-24 w-full rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                        placeholder="Optional reason to preserve in the sidecar"
                      />
                    </label>
                    <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4">
                      <div className="flex flex-wrap gap-2">
                        <button type="button" data-testid="jsonl-review-approve-button" disabled={saving} onClick={() => setPendingDecision("approved")} className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                          Approve (A)
                        </button>
                        <button type="button" data-testid="jsonl-review-reject-button" disabled={saving} onClick={() => setPendingDecision("rejected")} className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                          Reject (R)
                        </button>
                        <button type="button" data-testid="jsonl-review-reopen-button" disabled={saving} onClick={() => setPendingDecision("pending")} className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 disabled:opacity-50">
                          Reopen (P)
                        </button>
                      </div>
                      {pendingDecision ? (
                        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-3 text-sm text-sky-900">
                          <span className="font-medium">
                            Confirm {pendingDecision === "approved" ? "approve" : pendingDecision === "rejected" ? "reject" : "reopen"} and move to the next pending row.
                          </span>
                          <button
                            type="button"
                            data-testid={`jsonl-review-confirm-${pendingDecision}-button`}
                            disabled={saving}
                            onClick={() => void confirmDecision(pendingDecision)}
                            className="rounded-md border border-sky-300 bg-white px-3 py-2 text-sm font-medium text-sky-800 disabled:opacity-50"
                          >
                            Confirm {pendingDecision === "approved" ? "Approve" : pendingDecision === "rejected" ? "Reject" : "Reopen"}
                          </button>
                          <button
                            type="button"
                            disabled={saving}
                            onClick={() => setPendingDecision(null)}
                            className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <p className="mt-3 text-xs text-gray-500">Choose an action, then confirm it. The reviewer will move to the next pending row automatically.</p>
                      )}
                    </div>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
                    <div>
                      <h5 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Raw compiled JSON</h5>
                      <p className="mt-1 text-xs text-slate-500">Scrollable snapshot of the compiled record being reviewed.</p>
                    </div>
                    <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">scrolling panel</span>
                  </div>
                  <pre className="max-h-[56vh] overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-5 text-slate-100 shadow-inner">
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
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Reviewed outputs</h4>
          <div className="mt-3 grid gap-3 md:grid-cols-2">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3">
              <p className="font-medium text-emerald-900">approved.jsonl</p>
              <p className="mt-1 break-all font-mono text-xs text-emerald-900">{materializeResult.approved_output_path}</p>
              <p className="mt-2 text-emerald-900">approved.jsonl is the reviewed file for Import DB.</p>
            </div>
            <div className="rounded-lg border border-sky-200 bg-sky-50 p-3">
              <p className="font-medium text-sky-900">review.decisions.jsonl</p>
              <p className="mt-1 break-all font-mono text-xs text-sky-900">{materializeResult.decisions_output_path}</p>
              <p className="mt-2 text-sky-900">Decision ledger for the reviewed artifact.</p>
            </div>
            <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
              <p className="font-medium text-amber-900">rejected.jsonl</p>
              <p className="mt-1 break-all font-mono text-xs text-amber-900">{materializeResult.rejected_output_path}</p>
              <p className="mt-2 text-amber-900">Rejected overlay rows with attached review metadata.</p>
            </div>
            <div className="rounded-lg border border-violet-200 bg-violet-50 p-3">
              <p className="font-medium text-violet-900">regenerate.jsonl</p>
              <p className="mt-1 break-all font-mono text-xs text-violet-900">{materializeResult.regenerate_output_path}</p>
              <p className="mt-2 text-violet-900">Regeneration request rows derived from rejected decisions.</p>
            </div>
          </div>
        </section>
      ) : null}
    </div>
  );
}
