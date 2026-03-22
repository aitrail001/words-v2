"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PathGuidanceCard } from "@/components/lexicon/path-guidance-card";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  LexiconCompiledReviewBatch,
  LexiconCompiledReviewItem,
  LexiconCompiledReviewMaterializeResult,
  deleteLexiconCompiledReviewBatch,
  downloadCompiledReviewDecisionsExport,
  downloadApprovedCompiledReviewExport,
  downloadRegenerateCompiledReviewExport,
  downloadRejectedCompiledReviewExport,
  importLexiconCompiledReviewBatch,
  importLexiconCompiledReviewBatchByPath,
  listLexiconCompiledReviewBatches,
  listLexiconCompiledReviewItems,
  materializeLexiconCompiledReviewOutputs,
  updateLexiconCompiledReviewItem,
} from "@/lib/lexicon-compiled-reviews-client";

type ReviewDecisionStatus = "pending" | "approved" | "rejected";

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

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

function slugifySegment(value: string): string {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function buildExportFilename(batch: LexiconCompiledReviewBatch, kind: "approved" | "rejected" | "regenerate" | "decisions"): string {
  const context =
    slugifySegment(batch.source_reference ?? "") ||
    slugifySegment(batch.snapshot_id ?? "") ||
    slugifySegment(batch.artifact_filename.replace(/\.jsonl$/i, "")) ||
    slugifySegment(batch.artifact_family) ||
    "compiled-review";
  return `${context}.${kind}.jsonl`;
}

function nextPendingItemId(items: LexiconCompiledReviewItem[], currentItemId: string): string | null {
  const pendingItems = items.filter((item) => item.review_status === "pending");
  if (!pendingItems.length) return null;

  const currentIndex = pendingItems.findIndex((item) => item.id === currentItemId);
  if (currentIndex >= 0 && currentIndex + 1 < pendingItems.length) {
    return pendingItems[currentIndex + 1].id;
  }
  if (currentIndex > 0) {
    return pendingItems[currentIndex - 1].id;
  }
  return pendingItems[0]?.id ?? null;
}

export default function LexiconCompiledReviewPage() {
  const [itemSearch, setItemSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [batches, setBatches] = useState<LexiconCompiledReviewBatch[]>([]);
  const [selectedBatchId, setSelectedBatchId] = useState("");
  const [items, setItems] = useState<LexiconCompiledReviewItem[]>([]);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [loading, setLoading] = useState(true);
  const [itemsLoading, setItemsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [importError, setImportError] = useState<string | null>(null);
  const [importLoading, setImportLoading] = useState(false);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importSourceReference, setImportSourceReference] = useState("");
  const [importArtifactPath, setImportArtifactPath] = useState("");
  const [materializeOutputDir, setMaterializeOutputDir] = useState("");
  const [materializeResult, setMaterializeResult] = useState<LexiconCompiledReviewMaterializeResult | null>(null);
  const [decisionReason, setDecisionReason] = useState("");
  const [pendingDecision, setPendingDecision] = useState<ReviewDecisionStatus | null>(null);
  const [confirmDeleteBatch, setConfirmDeleteBatch] = useState(false);
  const [saveLoading, setSaveLoading] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const autoImportKeyRef = useRef<string>("");
  const snapshotContext = searchParam("snapshot");
  const sourceReferenceContext = searchParam("sourceReference");
  const artifactPathContext = searchParam("artifactPath");
  const autoStart = searchParam("autostart") === "1";

  const selectedBatch = useMemo(
    () => batches.find((batch) => batch.id === selectedBatchId) ?? null,
    [batches, selectedBatchId],
  );
  const selectedItem = useMemo(
    () => items.find((item) => item.id === selectedItemId) ?? null,
    [items, selectedItemId],
  );
  const filteredItems = useMemo(() => {
    const search = itemSearch.trim().toLowerCase();
    return items.filter((item) => {
      if (statusFilter !== "all" && item.review_status !== statusFilter) return false;
      if (!search) return true;
      return [item.entry_id, item.display_text, item.normalized_form ?? ""].some((value) =>
        value.toLowerCase().includes(search),
      );
    });
  }, [itemSearch, items, statusFilter]);

  const loadBatches = async (preferredBatchId?: string) => {
    setLoading(true);
    setError(null);
    try {
      const nextBatches = await listLexiconCompiledReviewBatches();
      setBatches(nextBatches);
      const nextSelected =
        nextBatches.find((batch) => batch.id === preferredBatchId)?.id ??
        nextBatches[0]?.id ??
        "";
      setSelectedBatchId(nextSelected);
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load compiled review batches.");
    } finally {
      setLoading(false);
    }
  };

  const loadItems = async (batchId: string) => {
    setItemsLoading(true);
    setError(null);
    try {
      const nextItems = await listLexiconCompiledReviewItems(batchId);
      setItems(nextItems);
      setSelectedItemId(nextItems[0]?.id ?? "");
    } catch (nextError) {
      setError(nextError instanceof Error ? nextError.message : "Failed to load compiled review items.");
    } finally {
      setItemsLoading(false);
    }
  };

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/compiled-review");
      return;
    }
    setImportSourceReference(searchParam("sourceReference"));
    setImportArtifactPath(searchParam("artifactPath"));
    void loadBatches();
  }, []);

  useEffect(() => {
    if (!snapshotContext) return;
    setMaterializeOutputDir(`/app/data/lexicon/snapshots/${snapshotContext}/reviewed`);
  }, [snapshotContext]);

  useEffect(() => {
    if (!autoStart || !artifactPathContext.trim()) return;
    const importKey = `${artifactPathContext}::${sourceReferenceContext}`;
    if (autoImportKeyRef.current === importKey) return;
    autoImportKeyRef.current = importKey;
    setImportArtifactPath(artifactPathContext);
    setImportSourceReference(sourceReferenceContext);
    setImportLoading(true);
    setImportError(null);
    void importLexiconCompiledReviewBatchByPath({
      artifactPath: artifactPathContext,
      sourceReference: sourceReferenceContext || undefined,
    })
      .then(async (created) => {
        await loadBatches(created.id);
        setMessage(`Imported ${created.artifact_filename} from ${sourceReferenceContext || "path"}.`);
      })
      .catch((nextError) => {
        setImportError(nextError instanceof Error ? nextError.message : "Import by path failed.");
      })
      .finally(() => {
        setImportLoading(false);
      });
  }, [artifactPathContext, autoStart, sourceReferenceContext]);

  useEffect(() => {
    if (!selectedBatchId) {
      setItems([]);
      setSelectedItemId("");
      return;
    }
    void loadItems(selectedBatchId);
  }, [selectedBatchId]);

  useEffect(() => {
    setDecisionReason(selectedItem?.decision_reason ?? "");
    setPendingDecision(null);
  }, [selectedItem?.decision_reason, selectedItem?.id]);

  useEffect(() => {
    if (!filteredItems.length) {
      setSelectedItemId("");
      return;
    }
    if (!filteredItems.some((item) => item.id === selectedItemId)) {
      setSelectedItemId(filteredItems[0]?.id ?? "");
    }
  }, [filteredItems, selectedItemId]);

  const handleImport = async (event: FormEvent) => {
    event.preventDefault();
    if (!importFile) return;
    setImportLoading(true);
    setImportError(null);
    try {
      const created = await importLexiconCompiledReviewBatch({
        file: importFile,
        sourceReference: importSourceReference || undefined,
      });
      setImportFile(null);
      setImportSourceReference("");
      await loadBatches(created.id);
      setMessage(`Imported ${created.artifact_filename}`);
    } catch (nextError) {
      setImportError(nextError instanceof Error ? nextError.message : "Import failed.");
    } finally {
      setImportLoading(false);
    }
  };

  const handleImportByPath = async () => {
    if (!importArtifactPath.trim()) return;
    setImportLoading(true);
    setImportError(null);
    try {
      const created = await importLexiconCompiledReviewBatchByPath({
        artifactPath: importArtifactPath,
        sourceReference: importSourceReference || undefined,
      });
      await loadBatches(created.id);
      setMessage(`Imported ${created.artifact_filename} from path.`);
    } catch (nextError) {
      setImportError(nextError instanceof Error ? nextError.message : "Import by path failed.");
    } finally {
      setImportLoading(false);
    }
  };

  const handleDecision = useCallback(async (reviewStatus: ReviewDecisionStatus) => {
    if (!selectedItem) return;
    const nextItemId = nextPendingItemId(items, selectedItem.id);
    setSaveLoading(true);
    setMessage(null);
    try {
      const updated = await updateLexiconCompiledReviewItem(selectedItem.id, {
        review_status: reviewStatus,
        decision_reason: decisionReason || null,
      });
      setItems((current) => current.map((item) => (item.id === updated.id ? updated : item)));
      await loadBatches(selectedBatchId || undefined);
      if (nextItemId && nextItemId !== updated.id) {
        setSelectedItemId(nextItemId);
      }
      setPendingDecision(null);
      setMessage(`Updated ${updated.entry_id} to ${updated.review_status}.`);
    } catch (nextError) {
      setMessage(nextError instanceof Error ? nextError.message : "Failed to update review item.");
    } finally {
      setSaveLoading(false);
    }
  }, [items, selectedBatchId, selectedItem, decisionReason]);

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

      if (!filteredItems.length || saveLoading || loading || itemsLoading) return;

      if (pendingDecision) {
        if (event.key === "Enter") {
          event.preventDefault();
          void handleDecision(pendingDecision);
          return;
        }
        if (event.key === "Escape") {
          event.preventDefault();
          setPendingDecision(null);
          return;
        }
      }

      const currentIndex = filteredItems.findIndex((item) => item.id === selectedItem?.id);
      if (event.key === "j") {
        event.preventDefault();
        const nextIndex = currentIndex >= 0 ? Math.min(currentIndex + 1, filteredItems.length - 1) : 0;
        setSelectedItemId(filteredItems[nextIndex]?.id ?? "");
        return;
      }
      if (event.key === "k") {
        event.preventDefault();
        const nextIndex = currentIndex >= 0 ? Math.max(currentIndex - 1, 0) : 0;
        setSelectedItemId(filteredItems[nextIndex]?.id ?? "");
        return;
      }
      if (!selectedItem) return;
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
  }, [filteredItems, handleDecision, itemsLoading, loading, pendingDecision, saveLoading, selectedItem]);

  const handleExport = async (kind: "approved" | "rejected" | "regenerate" | "decisions") => {
    if (!selectedBatch) return;
    try {
      const text =
        kind === "approved"
          ? await downloadApprovedCompiledReviewExport(selectedBatch.id)
          : kind === "rejected"
            ? await downloadRejectedCompiledReviewExport(selectedBatch.id)
            : kind === "decisions"
              ? await downloadCompiledReviewDecisionsExport(selectedBatch.id)
            : await downloadRegenerateCompiledReviewExport(selectedBatch.id);
      downloadTextFile(buildExportFilename(selectedBatch, kind), text);
      setMessage(`Downloaded ${kind} export.`);
    } catch (nextError) {
      setMessage(nextError instanceof Error ? nextError.message : `Failed to export ${kind}.`);
    }
  };

  const handleMaterialize = async () => {
    if (!selectedBatch) return;
    try {
      const result = await materializeLexiconCompiledReviewOutputs(selectedBatch.id, {
        outputDir: materializeOutputDir || undefined,
      });
      setMaterializeResult(result);
      setMessage("Materialized reviewed outputs.");
    } catch (nextError) {
      setMessage(nextError instanceof Error ? nextError.message : "Failed to materialize reviewed outputs.");
    }
  };

  const handleDeleteBatch = async () => {
    if (!selectedBatch) return;
    setSaveLoading(true);
    setMessage(null);
    try {
      await deleteLexiconCompiledReviewBatch(selectedBatch.id);
      setConfirmDeleteBatch(false);
      await loadBatches();
      setItems([]);
      setSelectedItemId("");
      setMessage(`Deleted ${selectedBatch.artifact_filename}.`);
    } catch (nextError) {
      setMessage(nextError instanceof Error ? nextError.message : "Failed to delete review batch.");
    } finally {
      setSaveLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="lexicon-compiled-review-page">
      {(snapshotContext || sourceReferenceContext || artifactPathContext) ? (
        <section className="rounded-lg border border-violet-200 bg-violet-50 p-4 text-sm text-violet-900" data-testid="lexicon-compiled-review-context">
          <p className="font-medium">Workflow context</p>
          {snapshotContext ? <p className="mt-1">Snapshot: {snapshotContext}</p> : null}
          {sourceReferenceContext ? <p>Source reference: {sourceReferenceContext}</p> : null}
          {artifactPathContext ? <p>Artifact: {artifactPathContext}</p> : null}
          <p className="mt-1">Stage: Review compiled artifact</p>
          <p>Next step: Export approved rows, then open Import DB.</p>
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-gray-900" data-testid="lexicon-compiled-review-title">
              Compiled Lexicon Review
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Review compiled learner-facing JSONL before import. Generated artifacts stay immutable; decisions are the overlay.
            </p>
          </div>
          <div className="flex gap-2">
            <button type="button" onClick={() => void loadBatches(selectedBatchId || undefined)} className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 hover:bg-gray-50">
              Refresh
            </button>
            <button type="button" onClick={() => void handleExport("approved")} disabled={!selectedBatch} className="rounded-md border border-blue-300 px-3 py-2 text-sm text-blue-700 disabled:opacity-50" data-testid="compiled-review-export-approved">
              Download Approved Rows
            </button>
            <button type="button" onClick={() => void handleExport("decisions")} disabled={!selectedBatch} className="rounded-md border border-emerald-300 px-3 py-2 text-sm text-emerald-700 disabled:opacity-50">
              Download Decision Ledger
            </button>
            <button type="button" onClick={() => void handleExport("rejected")} disabled={!selectedBatch} className="rounded-md border border-amber-300 px-3 py-2 text-sm text-amber-700 disabled:opacity-50">
              Download Rejected Overlay
            </button>
            <button type="button" onClick={() => void handleExport("regenerate")} disabled={!selectedBatch} className="rounded-md border border-violet-300 px-3 py-2 text-sm text-violet-700 disabled:opacity-50">
              Download Regeneration Requests
            </button>
            <button type="button" onClick={() => void handleMaterialize()} disabled={!selectedBatch} className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-50">
              Materialize Reviewed Outputs
            </button>
          </div>
        </div>

        <div className="mt-6 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
          <div className="rounded-lg border border-emerald-200 bg-emerald-50 p-3 text-sm text-emerald-950">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-emerald-700">Approve</p>
            <p className="mt-2">Approve keeps the compiled row eligible for final import as reviewed/approved.jsonl.</p>
          </div>
          <div className="rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-950">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-rose-700">Reject</p>
            <p className="mt-2">Reject removes the row from reviewed/approved.jsonl, records the review decision ledger, and includes it in regeneration requests.</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-3 text-sm text-slate-900">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Reopen</p>
            <p className="mt-2">Reopen clears the final decision so the row stays pending and is excluded from reviewed exports.</p>
          </div>
        </div>

        <div className="mt-3 grid gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 md:grid-cols-4">
          <div className="text-sm text-gray-700">
            <p className="font-medium text-gray-900">Approved rows</p>
            <p className="mt-1">Reviewed compiled rows for final Import DB. Equivalent to <span className="font-mono text-xs">reviewed/approved.jsonl</span>.</p>
          </div>
          <div className="text-sm text-gray-700">
            <p className="font-medium text-gray-900">Decision ledger</p>
            <p className="mt-1">Final approve/reject overlay with review metadata stored in the review DB. Export or materialize it as <span className="font-mono text-xs">reviewed/review.decisions.jsonl</span>.</p>
          </div>
          <div className="text-sm text-gray-700">
            <p className="font-medium text-gray-900">Rejected overlay</p>
            <p className="mt-1">Rejected rows plus the decision metadata preserved for audit and analysis.</p>
          </div>
          <div className="text-sm text-gray-700">
            <p className="font-medium text-gray-900">Regeneration requests</p>
            <p className="mt-1">Subset of rejected rows exported as requests for a new generation pass. There is no separate regenerate status.</p>
          </div>
        </div>

        <PathGuidanceCard
          className="mt-3"
          modeNote="Compiled Review keeps the decision ledger in review DB tables until you export or materialize it."
        />

        <form onSubmit={handleImport} className="mt-6 grid gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 md:grid-cols-[1fr_1fr_auto]">
          <input type="file" accept=".jsonl,.ndjson" onChange={(event) => setImportFile(event.target.files?.[0] ?? null)} data-testid="compiled-review-import-file" />
          <input value={importSourceReference} onChange={(event) => setImportSourceReference(event.target.value)} placeholder="optional source reference" className="rounded-md border border-gray-300 px-3 py-2 text-sm" />
          <button type="submit" disabled={!importFile || importLoading} className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
            {importLoading ? "Importing..." : "Import Batch"}
          </button>
        </form>
        <div className="mt-3 grid gap-3 rounded-lg border border-dashed border-violet-300 bg-violet-50 p-4 md:grid-cols-[1fr_1fr_auto]">
          <input
            value={importArtifactPath}
            onChange={(event) => setImportArtifactPath(event.target.value)}
            placeholder="compiled artifact path"
            className="rounded-md border border-violet-200 px-3 py-2 font-mono text-sm"
            data-testid="compiled-review-import-artifact-path"
          />
          <div className="self-center text-xs text-violet-800">
            Import an existing compiled artifact directly from the selected snapshot path.
          </div>
          <button
            type="button"
            disabled={!importArtifactPath.trim() || importLoading}
            onClick={() => void handleImportByPath()}
            className="rounded-md border border-violet-300 bg-white px-4 py-2 text-sm font-medium text-violet-700 disabled:opacity-50"
            data-testid="compiled-review-import-by-path-button"
          >
            {importLoading ? "Importing..." : "Import by Path"}
          </button>
        </div>
        <div className="mt-3 grid gap-3 rounded-lg border border-dashed border-emerald-300 bg-emerald-50 p-4 md:grid-cols-[1fr_auto]">
          <input
            value={materializeOutputDir}
            onChange={(event) => setMaterializeOutputDir(event.target.value)}
            placeholder="data/lexicon/snapshots/.../reviewed"
            className="rounded-md border border-emerald-200 px-3 py-2 font-mono text-sm"
            data-testid="compiled-review-materialize-output-dir"
          />
          <div className="self-center text-xs text-emerald-800">
            Write approved, decisions, rejected, and regenerate outputs into the shared reviewed/ directory.
          </div>
        </div>
        {importError ? <p className="mt-2 text-sm text-red-600">{importError}</p> : null}
        {message ? <p className="mt-2 text-sm text-green-700">{message}</p> : null}
        {error ? <p className="mt-2 text-sm text-red-600">{error}</p> : null}
        {materializeResult ? (
          <div className="mt-3 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-700 md:grid-cols-2">
            <div>
              <p className="font-medium text-slate-900">Approved</p>
              <p className="mt-1 break-all font-mono text-xs">{materializeResult.approved_output_path}</p>
            </div>
            <div>
              <p className="font-medium text-slate-900">Decision ledger</p>
              <p className="mt-1 break-all font-mono text-xs">{materializeResult.decisions_output_path}</p>
            </div>
            <div>
              <p className="font-medium text-slate-900">Rejected</p>
              <p className="mt-1 break-all font-mono text-xs">{materializeResult.rejected_output_path}</p>
            </div>
            <div>
              <p className="font-medium text-slate-900">Regenerate</p>
              <p className="mt-1 break-all font-mono text-xs">{materializeResult.regenerate_output_path}</p>
            </div>
          </div>
        ) : null}
      </section>

      <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" data-testid="compiled-review-batches-list">
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Batches</h4>
          <div className="mt-4 space-y-2">
            {!loading && batches.length === 0 ? <p className="text-sm text-gray-500">No compiled review batches yet.</p> : null}
            {batches.map((batch) => (
              <button
                key={batch.id}
                type="button"
                onClick={() => setSelectedBatchId(batch.id)}
                className={`w-full rounded-lg border p-3 text-left ${batch.id === selectedBatchId ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
              >
                <p className="font-medium text-gray-900">{batch.artifact_filename}</p>
                <p className="text-xs text-gray-500">
                  {batch.source_reference ?? batch.snapshot_id ?? "unknown snapshot"} · {batch.artifact_family}
                </p>
                <p className="text-xs text-gray-500">{formatDateTime(batch.created_at)}</p>
                <p className="mt-1 text-xs text-gray-500">
                  pending {batch.pending_count} · approved {batch.approved_count} · rejected {batch.rejected_count}
                </p>
              </button>
            ))}
          </div>
        </section>

        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" data-testid="compiled-review-detail-panel">
          {selectedBatch ? (
            <div className="space-y-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h4 className="text-xl font-semibold text-gray-900">{selectedBatch.artifact_filename}</h4>
                  <p className="text-sm text-gray-500">
                    {selectedBatch.artifact_family} · {selectedBatch.total_items} items · updated {formatDateTime(selectedBatch.updated_at)}
                  </p>
                </div>
              <div className="text-right text-xs text-gray-500">
                <p>schema {selectedBatch.compiled_schema_version}</p>
                <p>{selectedBatch.snapshot_id ?? "no snapshot id"}</p>
              </div>
              <div className="flex flex-wrap gap-2">
                {!confirmDeleteBatch ? (
                  <button
                    type="button"
                    onClick={() => setConfirmDeleteBatch(true)}
                    className="rounded-md border border-rose-300 px-3 py-2 text-sm text-rose-700 disabled:opacity-50"
                    disabled={saveLoading}
                  >
                    Delete Batch
                  </button>
                ) : (
                  <>
                    <span className="self-center text-sm text-rose-700">Delete the selected review batch from review DB staging?</span>
                    <button
                      type="button"
                      onClick={() => void handleDeleteBatch()}
                      className="rounded-md bg-rose-600 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                      disabled={saveLoading}
                    >
                      Confirm Delete Batch
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmDeleteBatch(false)}
                      className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700"
                      disabled={saveLoading}
                    >
                      Cancel
                    </button>
                  </>
                )}
              </div>
            </div>

              <div className="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
                <div className="space-y-3" data-testid="compiled-review-items-list">
                  <div className="grid gap-2">
                    <input
                      value={itemSearch}
                      onChange={(event) => setItemSearch(event.target.value)}
                      placeholder="Search entry id or display text"
                      className="rounded-md border border-gray-300 px-3 py-2 text-sm"
                    />
                    <select
                      value={statusFilter}
                      onChange={(event) => setStatusFilter(event.target.value as "all" | "pending" | "approved" | "rejected")}
                      className="rounded-md border border-gray-300 px-3 py-2 text-sm"
                    >
                      <option value="all">All statuses</option>
                      <option value="pending">Pending</option>
                      <option value="approved">Approved</option>
                      <option value="rejected">Rejected</option>
                    </select>
                  </div>
                  {itemsLoading ? <p className="text-sm text-gray-500">Loading items...</p> : null}
                  {!itemsLoading && filteredItems.length === 0 ? <p className="text-sm text-gray-500">No items match the current filter.</p> : null}
                  {filteredItems.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => setSelectedItemId(item.id)}
                      className={`w-full rounded-lg border p-3 text-left ${item.id === selectedItemId ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
                    >
                      <p className="font-medium text-gray-900">{item.display_text}</p>
                      <p className="text-xs text-gray-500">{item.entry_type} · {item.review_status}</p>
                      <p className="mt-1 text-xs text-gray-500">validator {item.validator_status ?? "—"} · qc {item.qc_status ?? "—"}</p>
                    </button>
                  ))}
                </div>

                <div>
                  {selectedItem ? (
                    <div className="space-y-4">
                      <div>
                        <h5 className="text-lg font-semibold text-gray-900" data-testid="compiled-review-item-title">{selectedItem.display_text}</h5>
                        <p className="text-sm text-gray-500">
                          {selectedItem.entry_id} · {selectedItem.entry_type} · CEFR {selectedItem.cefr_level ?? "—"} · rank {selectedItem.frequency_rank ?? "—"}
                        </p>
                      </div>

                      <div className="grid gap-3 md:grid-cols-2">
                        <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm">
                          <p className="font-medium text-amber-900">Validator</p>
                          <p className="mt-1 text-amber-800">{selectedItem.validator_status ?? "none"}</p>
                          <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-amber-900">{JSON.stringify(selectedItem.validator_issues ?? [], null, 2)}</pre>
                        </div>
                        <div className="rounded-lg border border-violet-200 bg-violet-50 p-3 text-sm">
                          <p className="font-medium text-violet-900">QC</p>
                          <p className="mt-1 text-violet-800">{selectedItem.qc_status ?? "none"} {selectedItem.qc_score !== null ? `(${selectedItem.qc_score})` : ""}</p>
                          <pre className="mt-2 whitespace-pre-wrap break-words text-xs text-violet-900">{JSON.stringify(selectedItem.qc_issues ?? [], null, 2)}</pre>
                        </div>
                      </div>

                      <label className="block text-sm font-medium text-gray-700">
                        Decision reason
                        <textarea value={decisionReason} onChange={(event) => setDecisionReason(event.target.value)} className="mt-1 min-h-24 w-full rounded-md border border-gray-300 px-3 py-2 text-sm" data-testid="compiled-review-decision-reason" />
                      </label>

                      <div className="rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4">
                        <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs text-slate-600">
                          Shortcuts: <span className="font-semibold text-slate-900">j</span>/<span className="font-semibold text-slate-900">k</span> move, <span className="font-semibold text-emerald-700">a</span> approve, <span className="font-semibold text-rose-700">r</span> reject, <span className="font-semibold text-slate-700">p</span> reopen, <span className="font-semibold text-slate-900">enter</span> confirm, <span className="font-semibold text-slate-900">esc</span> cancel
                        </div>
                        <div className="mt-3 flex flex-wrap gap-2">
                          <button type="button" onClick={() => setPendingDecision("approved")} disabled={saveLoading} className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" data-testid="compiled-review-approve-button">
                            Approve (A)
                          </button>
                          <button type="button" onClick={() => setPendingDecision("rejected")} disabled={saveLoading} className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50" data-testid="compiled-review-reject-button">
                            Reject (R)
                          </button>
                          <button type="button" onClick={() => setPendingDecision("pending")} disabled={saveLoading} className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 disabled:opacity-50" data-testid="compiled-review-reopen-button">
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
                              data-testid={`compiled-review-confirm-${pendingDecision}-button`}
                              disabled={saveLoading}
                              onClick={() => void handleDecision(pendingDecision)}
                              className="rounded-md border border-sky-300 bg-white px-3 py-2 text-sm font-medium text-sky-800 disabled:opacity-50"
                            >
                              Confirm {pendingDecision === "approved" ? "Approve" : pendingDecision === "rejected" ? "Reject" : "Reopen"}
                            </button>
                            <button
                              type="button"
                              disabled={saveLoading}
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

                      <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
                        <p className="text-sm font-medium text-gray-900">Compiled payload</p>
                        <pre className="mt-2 max-h-[28rem] overflow-auto whitespace-pre-wrap break-words text-xs text-gray-700">{JSON.stringify(selectedItem.compiled_payload, null, 2)}</pre>
                      </div>
                    </div>
                  ) : (
                    <p className="text-sm text-gray-500">Select an item to review.</p>
                  )}
                </div>
              </div>
            </div>
          ) : (
            <p className="text-sm text-gray-500">Select a compiled review batch.</p>
          )}
        </section>
      </div>
    </div>
  );
}
