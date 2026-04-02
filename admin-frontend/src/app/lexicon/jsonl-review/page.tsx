"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { PathGuidanceCard } from "@/components/lexicon/path-guidance-card";
import { ReviewerSummaryCard } from "@/components/lexicon/reviewer-summary-card";
import { LexiconSectionNav } from "@/components/lexicon/section-nav";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  bulkUpdateLexiconJsonlReviewItems,
  browseLexiconJsonlReviewItems,
  getLexiconJsonlReviewSession,
  type LexiconJsonlReviewMaterializeResult,
  downloadApprovedLexiconJsonlReviewOutput,
  downloadDecisionLexiconJsonlReviewOutput,
  downloadRegenerateLexiconJsonlReviewOutput,
  downloadRejectedLexiconJsonlReviewOutput,
  LexiconJsonlReviewBrowseResponse,
  LexiconJsonlReviewItem,
  LexiconJsonlReviewSessionSummary,
  updateLexiconJsonlReviewItem,
} from "@/lib/lexicon-jsonl-reviews-client";
import {
  createJsonlMaterializeLexiconJob,
  getLexiconJob,
  type LexiconJob,
} from "@/lib/lexicon-jobs-client";
import { derivePhraseDetails, deriveReviewSummary } from "@/lib/lexicon-review-summary";

type ReviewDecisionStatus = "pending" | "approved" | "rejected";
const PAGE_LIMIT = 25;

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
  const [sessionSummary, setSessionSummary] = useState<LexiconJsonlReviewSessionSummary | null>(null);
  const [items, setItems] = useState<LexiconJsonlReviewItem[]>([]);
  const [filteredTotal, setFilteredTotal] = useState(0);
  const [pageOffset, setPageOffset] = useState(0);
  const [selectedItemId, setSelectedItemId] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");
  const [decisionReason, setDecisionReason] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [materializeResult, setMaterializeResult] = useState<LexiconJsonlReviewMaterializeResult | null>(null);
  const [materializeJob, setMaterializeJob] = useState<LexiconJob | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [pendingBulkDecision, setPendingBulkDecision] = useState<ReviewDecisionStatus | null>(null);
  const artifactPathHint = "Use a container-visible repo path like data/lexicon/snapshots/... or /app/data/lexicon/snapshots/....";
  const decisionsPathHint = "File-backed decision ledger path. Optional. Defaults to reviewed/review.decisions.jsonl under the snapshot.";
  const outputDirHint = "Optional. Defaults to the shared reviewed/ directory under the artifact snapshot.";
  const contextArtifactPath = sessionSummary?.artifact_path ?? artifactPath;
  const contextDecisionsPath = sessionSummary?.decisions_path ?? decisionsPath;
  const contextOutputDir = sessionSummary?.output_dir ?? outputDir;
  const materializeResultFromJob = useCallback((job: LexiconJob): LexiconJsonlReviewMaterializeResult | null => {
    if (!job.result_payload) {
      return null;
    }
    return {
      artifact_sha256: typeof job.result_payload.artifact_sha256 === "string" ? job.result_payload.artifact_sha256 : undefined,
      decision_count: typeof job.result_payload.decision_count === "number" ? job.result_payload.decision_count : undefined,
      approved_count: Number(job.result_payload.approved_count ?? 0),
      rejected_count: Number(job.result_payload.rejected_count ?? 0),
      regenerate_count: Number(job.result_payload.regenerate_count ?? 0),
      decisions_output_path: String(job.result_payload.decisions_output_path ?? ""),
      approved_output_path: String(job.result_payload.approved_output_path ?? ""),
      rejected_output_path: String(job.result_payload.rejected_output_path ?? ""),
      regenerate_output_path: String(job.result_payload.regenerate_output_path ?? ""),
    };
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/jsonl-review");
    }
  }, []);

  const applyBrowseResponse = useCallback((response: LexiconJsonlReviewBrowseResponse) => {
    setSessionSummary((current) => {
      const nextSummary = {
        artifact_filename: response.artifact_filename,
        artifact_path: response.artifact_path,
        artifact_sha256: response.artifact_sha256,
        decisions_path: response.decisions_path,
        output_dir: response.output_dir ?? null,
        total_items: response.total_items,
        pending_count: response.pending_count,
        approved_count: response.approved_count,
        rejected_count: response.rejected_count,
      };
      if (
        current &&
        current.artifact_filename === nextSummary.artifact_filename &&
        current.artifact_path === nextSummary.artifact_path &&
        current.artifact_sha256 === nextSummary.artifact_sha256 &&
        current.decisions_path === nextSummary.decisions_path &&
        current.output_dir === nextSummary.output_dir &&
        current.total_items === nextSummary.total_items &&
        current.pending_count === nextSummary.pending_count &&
        current.approved_count === nextSummary.approved_count &&
        current.rejected_count === nextSummary.rejected_count
      ) {
        return current;
      }
      return nextSummary;
    });
    setItems(response.items);
    setFilteredTotal(response.filtered_total);
    setPageOffset(response.offset);
    setSelectedItemId((current) => {
      if (response.items.some((item) => item.entry_id === current)) {
        return current;
      }
      return response.items[0]?.entry_id ?? "";
    });
  }, []);

  const loadBrowsePage = useCallback(async (
    nextArtifactPath: string,
    nextDecisionsPath: string,
    nextOutputDir: string,
    nextOffset: number,
    nextSearch: string,
    nextStatusFilter: "all" | "pending" | "approved" | "rejected",
  ) => {
    const response = await browseLexiconJsonlReviewItems({
      artifactPath: nextArtifactPath,
      decisionsPath: nextDecisionsPath || undefined,
      outputDir: nextOutputDir || undefined,
      offset: nextOffset,
      limit: PAGE_LIMIT,
      search: nextSearch || undefined,
      reviewStatus: nextStatusFilter,
    });
    applyBrowseResponse(response);
  }, [applyBrowseResponse]);

  const loadSessionForPaths = useCallback(async (
    nextArtifactPath: string,
    nextDecisionsPath?: string,
    nextOutputDir?: string,
  ) => {
    setLoading(true);
    setMessage(null);
    setMaterializeResult(null);
    try {
      const nextSession = await getLexiconJsonlReviewSession({
        artifactPath: nextArtifactPath,
        decisionsPath: nextDecisionsPath || undefined,
        outputDir: nextOutputDir || undefined,
      });
      setSessionSummary(nextSession);
      setArtifactPath(nextSession.artifact_path);
      setDecisionsPath(nextSession.decisions_path);
      setOutputDir(nextSession.output_dir ?? nextOutputDir ?? "");
      await loadBrowsePage(
        nextSession.artifact_path,
        nextSession.decisions_path,
        nextSession.output_dir ?? nextOutputDir ?? "",
        0,
        "",
        "all",
      );
      setSearchDraft("");
      setSearch("");
      setStatusFilter("all");
      setMessage(`Loaded ${nextSession.artifact_filename}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to load artifact.");
    } finally {
      setLoading(false);
    }
  }, [loadBrowsePage]);

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

  const selectedItem = useMemo(
    () => items.find((item) => item.entry_id === selectedItemId) ?? items[0] ?? null,
    [items, selectedItemId],
  );
  const selectedPhraseDetails = useMemo(
    () => (selectedItem ? derivePhraseDetails(selectedItem.entry_type, selectedItem.compiled_payload) : null),
    [selectedItem],
  );
  const selectedReviewSummary = useMemo(() => {
    if (!selectedItem) return null;
    const derived = deriveReviewSummary(selectedItem.compiled_payload);
    return {
      ...derived,
      senseCount: selectedItem.review_summary?.sense_count ?? derived.senseCount,
      formVariantCount: selectedItem.review_summary?.form_variant_count ?? derived.formVariantCount,
      confusableCount: selectedItem.review_summary?.confusable_count ?? derived.confusableCount,
      provenanceSources: selectedItem.review_summary?.provenance_sources ?? derived.provenanceSources,
      primaryDefinition: selectedItem.review_summary?.primary_definition ?? derived.primaryDefinition,
      primaryExample: selectedItem.review_summary?.primary_example ?? derived.primaryExample,
    };
  }, [selectedItem]);

  useEffect(() => {
    setSelectedItemId(selectedItem?.entry_id ?? "");
  }, [selectedItem?.entry_id]);

  useEffect(() => {
    setDecisionReason(selectedItem?.decision_reason ?? "");
  }, [selectedItem?.decision_reason, selectedItem?.entry_id]);

  useEffect(() => {
    if (!sessionSummary) {
      return;
    }
    let cancelled = false;
    setLoading(true);
    setMessage(null);
    void loadBrowsePage(
      sessionSummary.artifact_path,
      decisionsPath || sessionSummary.decisions_path,
      outputDir || sessionSummary.output_dir || "",
      pageOffset,
      search,
      statusFilter,
    )
      .catch((error) => {
        if (!cancelled) {
          setMessage(error instanceof Error ? error.message : "Failed to browse review items.");
        }
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [decisionsPath, loadBrowsePage, outputDir, pageOffset, search, sessionSummary, statusFilter]);

  const loadSession = async (event: FormEvent) => {
    event.preventDefault();
    await loadSessionForPaths(artifactPath, decisionsPath, outputDir);
  };

  const confirmDecision = useCallback(async (reviewStatus: ReviewDecisionStatus) => {
    if (!selectedItem || !sessionSummary) return;
    const nextEntryId = nextPendingEntryId(items, selectedItem.entry_id);
    setSaving(true);
    setMessage(null);
    try {
      const updated = await updateLexiconJsonlReviewItem(selectedItem.entry_id, {
        artifactPath: sessionSummary.artifact_path,
        decisionsPath: decisionsPath || sessionSummary.decisions_path,
        reviewStatus,
        decisionReason: decisionReason || null,
      });
      setSessionSummary((current) => current ? {
        ...current,
        total_items: updated.total_items,
        pending_count: updated.pending_count,
        approved_count: updated.approved_count,
        rejected_count: updated.rejected_count,
      } : current);
      await loadBrowsePage(
        sessionSummary.artifact_path,
        decisionsPath || sessionSummary.decisions_path,
        outputDir || sessionSummary.output_dir || "",
        pageOffset,
        search,
        statusFilter,
      );
      setMessage(`Saved ${updated.item.entry_id} as ${updated.item.review_status}.`);
      if (nextEntryId && nextEntryId !== updated.item.entry_id) {
        setSelectedItemId(nextEntryId);
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save decision.");
    } finally {
      setSaving(false);
    }
  }, [decisionsPath, decisionReason, items, loadBrowsePage, outputDir, pageOffset, search, selectedItem, sessionSummary, statusFilter]);

  const confirmBulkDecision = useCallback(async (reviewStatus: ReviewDecisionStatus) => {
    if (!sessionSummary) return;
    setSaving(true);
    setMessage(null);
    try {
      const nextSession = await bulkUpdateLexiconJsonlReviewItems({
        artifactPath: sessionSummary.artifact_path,
        decisionsPath: decisionsPath || sessionSummary.decisions_path,
        reviewStatus,
        decisionReason: decisionReason || null,
      });
      setSessionSummary((current) => current ? { ...current, ...nextSession } : current);
      await loadBrowsePage(
        sessionSummary.artifact_path,
        decisionsPath || sessionSummary.decisions_path,
        outputDir || sessionSummary.output_dir || "",
        0,
        search,
        statusFilter,
      );
      setPendingBulkDecision(null);
      setMessage(`Updated ${nextSession.total_items} rows to ${reviewStatus}.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to save bulk decision.");
    } finally {
      setSaving(false);
    }
  }, [decisionReason, decisionsPath, loadBrowsePage, outputDir, search, sessionSummary, statusFilter]);

  const materialize = async () => {
    if (!sessionSummary) return;
    setMessage(null);
    try {
      const job = await createJsonlMaterializeLexiconJob({
        artifactPath: sessionSummary.artifact_path,
        decisionsPath: decisionsPath || sessionSummary.decisions_path,
        outputDir: outputDir || undefined,
      });
      setMaterializeJob(job);
      setMaterializeResult(materializeResultFromJob(job));
      setMessage(job.status === "completed" ? "Materialized outputs." : "Materialize job started.");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to materialize outputs.");
    }
  };

  useEffect(() => {
    if (!materializeJob || materializeJob.status === "completed" || materializeJob.status === "failed") {
      return;
    }
    const timer = window.setInterval(() => {
      void getLexiconJob(materializeJob.id)
        .then((nextJob) => {
          setMaterializeJob(nextJob);
          if (nextJob.status === "completed") {
            setMaterializeResult(materializeResultFromJob(nextJob));
            setMessage("Materialized outputs.");
          } else if (nextJob.status === "failed") {
            setMessage(nextJob.error_message || "Materialize job failed.");
          }
        })
        .catch((error) => {
          setMessage(error instanceof Error ? error.message : "Failed to refresh materialize job.");
        });
    }, 500);
    return () => window.clearInterval(timer);
  }, [materializeJob, materializeResultFromJob]);

  const downloadOutput = async (kind: "approved" | "decisions" | "rejected" | "regenerate") => {
    if (!sessionSummary) return;
    setSaving(true);
    setMessage(null);
    try {
      const input = {
        artifactPath: sessionSummary.artifact_path,
        decisionsPath: decisionsPath || sessionSummary.decisions_path,
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

      if (!items.length || saving || loading) {
        return;
      }

      const currentIndex = items.findIndex((item) => item.entry_id === selectedItem?.entry_id);
      if (event.key === "j") {
        event.preventDefault();
        const nextIndex = currentIndex >= 0 ? Math.min(currentIndex + 1, items.length - 1) : 0;
        setSelectedItemId(items[nextIndex]?.entry_id ?? "");
        return;
      }

      if (event.key === "k") {
        event.preventDefault();
        const nextIndex = currentIndex >= 0 ? Math.max(currentIndex - 1, 0) : 0;
        setSelectedItemId(items[nextIndex]?.entry_id ?? "");
        return;
      }

      if (!selectedItem || !sessionSummary) {
        return;
      }

      if (event.key === "a") {
        event.preventDefault();
        void confirmDecision("approved");
      } else if (event.key === "r") {
        event.preventDefault();
        void confirmDecision("rejected");
      } else if (event.key === "p") {
        event.preventDefault();
        void confirmDecision("pending");
      }
    };

    window.addEventListener("keydown", handleKeydown);
    return () => window.removeEventListener("keydown", handleKeydown);
  }, [confirmDecision, items, loading, saving, selectedItem, sessionSummary]);

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
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-gray-900" data-testid="lexicon-jsonl-review-title">
              JSONL-Only Lexicon Review
            </h3>
            <p className="mt-1 text-sm text-gray-600">
              Review compiled artifacts directly from JSONL and persist decisions as a sidecar without using review DB tables.
            </p>
          </div>
          <div className="flex gap-2">
            <button type="button" disabled={!sessionSummary || saving} onClick={() => void downloadOutput("approved")} className="rounded-md border border-blue-300 px-3 py-2 text-sm text-blue-700 disabled:opacity-50">
              Download Approved Rows
            </button>
            <button type="button" disabled={!sessionSummary || saving} onClick={() => void downloadOutput("decisions")} className="rounded-md border border-emerald-300 px-3 py-2 text-sm text-emerald-700 disabled:opacity-50">
              Download Decision Ledger
            </button>
            <button type="button" disabled={!sessionSummary || saving} onClick={() => void downloadOutput("rejected")} className="rounded-md border border-amber-300 px-3 py-2 text-sm text-amber-700 disabled:opacity-50">
              Download Rejected Overlay
            </button>
            <button type="button" disabled={!sessionSummary || saving} onClick={() => void downloadOutput("regenerate")} className="rounded-md border border-violet-300 px-3 py-2 text-sm text-violet-700 disabled:opacity-50">
              Download Regeneration Requests
            </button>
            <button type="button" disabled={!sessionSummary || saving} onClick={() => void materialize()} className="rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-700 disabled:opacity-50">
              Materialize Reviewed Outputs
            </button>
          </div>
        </div>
        <div className="mt-4">
          <LexiconSectionNav
            testId="lexicon-enrichment-review-section-nav"
            items={[
              { label: "Compiled Review", href: "/lexicon/compiled-review" },
              { label: "JSONL Review", href: "/lexicon/jsonl-review", active: true },
            ]}
          />
        </div>
        <div className="mt-6 grid gap-3 rounded-lg border border-slate-200 bg-slate-50 p-4 md:grid-cols-3">
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

        <div className="mt-3 grid gap-3 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 md:grid-cols-4">
          <div className="text-sm text-gray-700">
            <p className="font-medium text-gray-900">Approved rows</p>
            <p className="mt-1">Reviewed compiled rows for final Import DB. Equivalent to <span className="font-mono text-xs">reviewed/approved.jsonl</span>.</p>
          </div>
          <div className="text-sm text-gray-700">
            <p className="font-medium text-gray-900">Decision ledger</p>
            <p className="mt-1">Final approve/reject overlay stored in the sidecar ledger file. Materialize or download it as <span className="font-mono text-xs">reviewed/review.decisions.jsonl</span>.</p>
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
          modeNote="JSONL Review is file-backed. This page reads and writes the decision ledger file directly."
        />

        <form onSubmit={loadSession} className="mt-6 grid gap-4 rounded-lg border border-dashed border-gray-300 bg-gray-50 p-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)_minmax(0,1fr)_14rem] xl:items-start">
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
            <span className="font-medium">Decision ledger path</span>
            <input
              aria-label="Decision ledger path"
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
          <div className="grid gap-1 text-sm text-slate-700 xl:self-start">
            <span className="font-medium">Load artifact</span>
            <button type="submit" disabled={!artifactPath || loading} className="rounded-md bg-slate-950 px-3 py-2 text-sm font-medium text-white transition hover:bg-slate-800 disabled:opacity-50">
              {loading ? "Loading..." : "Load Artifact"}
            </button>
            <span className="text-xs leading-5 text-slate-500">Load the compiled artifact and sidecar paths into the review session.</span>
          </div>
        </form>
        {message ? <div className="mt-3 text-sm text-slate-700">{message}</div> : null}
      </section>

      {sessionSummary ? (
        <section className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
            <div className="mb-4 grid grid-cols-3 gap-3 text-sm">
              <div className="rounded-xl border border-amber-100 bg-amber-50 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-amber-700">Pending</p>
                <p className="mt-1 text-xl font-semibold text-amber-950">{sessionSummary.pending_count}</p>
              </div>
              <div className="rounded-xl border border-emerald-100 bg-emerald-50 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-emerald-700">Approved</p>
                <p className="mt-1 text-xl font-semibold text-emerald-950">{sessionSummary.approved_count}</p>
              </div>
              <div className="rounded-xl border border-rose-100 bg-rose-50 px-3 py-2">
                <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-rose-700">Rejected</p>
                <p className="mt-1 text-xl font-semibold text-rose-950">{sessionSummary.rejected_count}</p>
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
                value={searchDraft}
                onChange={(event) => setSearchDraft(event.target.value)}
                placeholder="Search entry id or display text"
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              />
              <select
                value={statusFilter}
                onChange={(event) => {
                  setStatusFilter(event.target.value as "all" | "pending" | "approved" | "rejected");
                  setPageOffset(0);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm shadow-sm outline-none transition focus:border-sky-400 focus:ring-2 focus:ring-sky-100"
              >
                <option value="all">All statuses</option>
                <option value="pending">Pending</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
              </select>
              <button
                type="button"
                onClick={() => {
                  setSearch(searchDraft.trim());
                  setPageOffset(0);
                }}
                className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm font-medium text-slate-700"
              >
                Apply filters
              </button>
            </div>
            <div className="mt-4">
              <div className="space-y-3" data-testid="jsonl-review-items-list">
                <div className="flex items-center justify-between gap-3">
                  <h5 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Entries</h5>
                  <span className="text-xs text-gray-500">
                    {filteredTotal.toLocaleString()} matches · page {Math.floor(pageOffset / PAGE_LIMIT) + 1}
                  </span>
                </div>
                <div className="space-y-2">
                  {items.map((item) => {
                    const selected = item.entry_id === selectedItem?.entry_id;
                    return (
                      <button
                        key={item.entry_id}
                        type="button"
                        onClick={() => setSelectedItemId(item.entry_id)}
                        className={`w-full rounded-lg border p-3 text-left ${selected ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
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
                    );
                  })}
                  {!items.length ? <p className="text-sm text-gray-500">No items match the current filter.</p> : null}
                </div>
                <div className="flex items-center justify-between gap-3">
                  <button
                    type="button"
                    data-testid="jsonl-review-items-list-prev-page"
                    onClick={() => setPageOffset((current) => Math.max(0, current - PAGE_LIMIT))}
                    disabled={pageOffset === 0}
                    className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    data-testid="jsonl-review-items-list-next-page"
                    onClick={() => setPageOffset((current) => current + PAGE_LIMIT)}
                    disabled={!items.length || pageOffset + PAGE_LIMIT >= filteredTotal}
                    className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
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
                    {selectedReviewSummary ? (
                      <ReviewerSummaryCard
                        summary={selectedReviewSummary}
                        warningLabels={selectedItem.warning_labels ?? []}
                      />
                    ) : null}
                    {selectedPhraseDetails ? (
                      <div className="rounded-lg border border-sky-200 bg-sky-50 p-4" data-testid="jsonl-review-phrase-details">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">Phrase details</p>
                        <div className="mt-3 grid gap-3 md:grid-cols-2">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">Kind</p>
                            <p className="mt-1 text-sm text-slate-900">{selectedPhraseDetails.phraseKind ?? "—"}</p>
                          </div>
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">Spanish definition</p>
                            <p className="mt-1 text-sm text-slate-900">{selectedPhraseDetails.spanishDefinition ?? "—"}</p>
                          </div>
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">Definition</p>
                            <p className="mt-1 text-sm text-slate-900">{selectedPhraseDetails.definition ?? "—"}</p>
                          </div>
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-sky-700">Example</p>
                            <p className="mt-1 text-sm text-slate-900">{selectedPhraseDetails.example ?? "—"}</p>
                          </div>
                        </div>
                      </div>
                    ) : null}
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
                        <button type="button" data-testid="jsonl-review-approve-button" disabled={saving} onClick={() => void confirmDecision("approved")} className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                          Approve (A)
                        </button>
                        <button type="button" data-testid="jsonl-review-reject-button" disabled={saving} onClick={() => void confirmDecision("rejected")} className="rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50">
                          Reject (R)
                        </button>
                        <button type="button" data-testid="jsonl-review-reopen-button" disabled={saving} onClick={() => void confirmDecision("pending")} className="rounded-md border border-gray-300 px-4 py-2 text-sm font-medium text-gray-700 disabled:opacity-50">
                          Reopen (P)
                        </button>
                      </div>
                      <div className="mt-3 border-t border-dashed border-slate-300 pt-3">
                        <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Snapshot actions</p>
                        <div className="mt-2 flex flex-wrap gap-2">
                          <button type="button" data-testid="jsonl-review-approve-all-button" disabled={saving} onClick={() => setPendingBulkDecision("approved")} className="rounded-md border border-emerald-300 bg-white px-4 py-2 text-sm font-medium text-emerald-700 disabled:opacity-50">
                            Approve All
                          </button>
                          <button type="button" data-testid="jsonl-review-reject-all-button" disabled={saving} onClick={() => setPendingBulkDecision("rejected")} className="rounded-md border border-rose-300 bg-white px-4 py-2 text-sm font-medium text-rose-700 disabled:opacity-50">
                            Reject All
                          </button>
                          <button type="button" data-testid="jsonl-review-reopen-all-button" disabled={saving} onClick={() => setPendingBulkDecision("pending")} className="rounded-md border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50">
                            Reopen All
                          </button>
                        </div>
                      </div>
                      {pendingBulkDecision ? (
                        <div className="mt-3 flex flex-wrap items-center gap-2 rounded-md border border-sky-200 bg-sky-50 px-3 py-3 text-sm text-sky-900">
                          <span className="font-medium">
                            Confirm {pendingBulkDecision === "approved" ? "approve" : pendingBulkDecision === "rejected" ? "reject" : "reopen"} every row in this snapshot.
                          </span>
                          <button
                            type="button"
                            data-testid={`jsonl-review-confirm-bulk-${pendingBulkDecision}-button`}
                            disabled={saving}
                            onClick={() => void confirmBulkDecision(pendingBulkDecision)}
                            className="rounded-md border border-sky-300 bg-white px-3 py-2 text-sm font-medium text-sky-800 disabled:opacity-50"
                          >
                            Confirm {pendingBulkDecision === "approved" ? "Approve All" : pendingBulkDecision === "rejected" ? "Reject All" : "Reopen All"}
                          </button>
                          <button
                            type="button"
                            disabled={saving}
                            onClick={() => setPendingBulkDecision(null)}
                            className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 disabled:opacity-50"
                          >
                            Cancel
                          </button>
                        </div>
                      ) : (
                        <p className="mt-3 text-xs text-gray-500">Per-row actions save immediately and move to the next pending row. Snapshot actions require confirmation.</p>
                      )}
                    </div>
                </div>
              </div>
            ) : (
              <p className="text-sm text-gray-500">No items match the current filter.</p>
            )}
          </div>
        </section>
      ) : null}

      {sessionSummary && selectedItem ? (
        <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm">
          <div className="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-slate-50 px-4 py-3">
            <div>
              <h5 className="text-sm font-semibold uppercase tracking-[0.18em] text-slate-500">Raw compiled JSON</h5>
              <p className="mt-1 text-xs text-slate-500">Scrollable snapshot of the compiled record being reviewed.</p>
            </div>
            <span className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-500">wide panel</span>
          </div>
          <pre className="mt-3 max-h-[40rem] overflow-auto rounded-lg bg-slate-950 p-4 text-xs leading-5 text-slate-100 shadow-inner">
            {JSON.stringify(selectedItem.compiled_payload, null, 2)}
          </pre>
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
