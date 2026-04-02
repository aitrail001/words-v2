"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  getLexiconOpsSnapshot,
  listLexiconOpsSnapshots,
  type LexiconOpsSnapshotArtifact,
  type LexiconOpsSnapshotDetail,
  type LexiconOpsSnapshotListResponse,
  type LexiconOpsSnapshotSummary,
} from "@/lib/lexicon-ops-client";
import { dryRunLexiconImport, runLexiconImport, type LexiconImportResult } from "@/lib/lexicon-imports-client";

const SNAPSHOTS_PAGE_SIZE = 10;

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
}

function formatNumber(value: number | null | undefined): string {
  return typeof value === "number" ? value.toLocaleString() : "—";
}

function formatBytes(value: number | null | undefined): string {
  if (typeof value !== "number") {
    return "—";
  }
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

type WorkflowShellData = {
  stage: string;
  nextStep: string;
  outsidePortal: string[];
};

type WorkflowActionState = {
  enabled: boolean;
  reason: string | null;
};

function workflowStage(snapshot: LexiconOpsSnapshotSummary | null | undefined): WorkflowShellData {
  if (!snapshot) {
    return {
      stage: "Select a snapshot",
      nextStep: "Pick a snapshot to see the handoff path.",
      outsidePortal: ["Outside portal guidance appears after a snapshot is selected."],
    };
  }
  const stageLabelByKey: Record<string, string> = {
    snapshot_missing_artifacts: "Build snapshot",
    base_artifacts: "Enrich snapshot",
    compiled_ready_for_review: "Review compiled artifact",
    approved_ready_for_import: "Import approved rows",
  };
  const nextStepByKey: Record<string, string> = {
    run_build_base: "Run build-base and enrich outside the portal.",
    run_enrich: "Run enrich outside the portal, then return here.",
    open_compiled_review: "Open Compiled Review as the default review path.",
    open_import_db: "Open Import DB to dry-run or execute the final write.",
  };
  return {
    stage: stageLabelByKey[snapshot.workflow_stage] ?? snapshot.workflow_stage,
    nextStep: nextStepByKey[snapshot.recommended_action] ?? snapshot.recommended_action,
    outsidePortal: snapshot.outside_portal_steps?.length
      ? snapshot.outside_portal_steps
      : [`Work directly from snapshot_path ${snapshot.snapshot_path} when you leave the portal.`],
  };
}

function deriveSnapshotStatus(snapshot: LexiconOpsSnapshotSummary | null | undefined): string {
  if (!snapshot) {
    return "unknown";
  }
  if (snapshot.has_compiled_export) {
    return "compiled";
  }
  if (snapshot.has_enrichments) {
    return "enriched";
  }
  if ((snapshot.artifact_counts.form_adjudications ?? 0) > 0) {
    return "adjudicated";
  }
  if ((snapshot.artifact_counts.ambiguous_forms ?? 0) > 0) {
    return "base+ambiguous";
  }
  if ((snapshot.artifact_counts.lexemes ?? 0) > 0) {
    return "base";
  }
  return "unknown";
}

function fileBadgeText(file: LexiconOpsSnapshotArtifact): string {
  if (file.read_error) {
    return `read error: ${file.read_error}`;
  }
  if (!file.exists) {
    return "missing";
  }
  return "ok";
}

type ArtifactGroup = {
  stage: string;
  purpose: string;
  files: LexiconOpsSnapshotArtifact[];
};

function artifactStage(fileName: string): string {
  if (fileName.startsWith("reviewed/")) return "Reviewed outputs";
  if (fileName.includes("enriched")) return "Compiled review inputs";
  if (fileName.includes("enrich")) return "Enrichment";
  if (fileName.includes("adjudication") || fileName.includes("ambiguous")) return "Adjudication";
  return "Base inventory";
}

function artifactPurpose(fileName: string): string {
  if (fileName.includes("phrase")) return "Phrase";
  if (fileName.includes("reference")) return "Reference";
  if (fileName.includes("word") || fileName.includes("lexeme")) return "Word";
  return "Shared";
}

function groupArtifacts(artifacts: LexiconOpsSnapshotArtifact[]): ArtifactGroup[] {
  const groups = new Map<string, ArtifactGroup>();
  for (const file of artifacts) {
    const stage = artifactStage(file.file_name);
    const purpose = artifactPurpose(file.file_name);
    const key = `${stage}::${purpose}`;
    const existing = groups.get(key);
    if (existing) {
      existing.files.push(file);
      continue;
    }
    groups.set(key, { stage, purpose, files: [file] });
  }
  return Array.from(groups.values());
}

function artifactPathFromDetail(
  detail: LexiconOpsSnapshotDetail | null,
  fileNames: string[],
): string {
  if (!detail) return "";
  const match = detail.artifacts.find(
    (artifact) => artifact.exists && fileNames.includes(artifact.file_name),
  );
  return match ? `${detail.snapshot_path}/${match.file_name}` : "";
}

function inferArtifactPathFromSummary(
  snapshot: LexiconOpsSnapshotSummary | null,
  kind: "review" | "import",
): string {
  if (!snapshot) return "";
  if (kind === "review" && snapshot.has_compiled_export) {
    if ((snapshot.artifact_counts.compiled_words ?? 0) > 0) {
      return `${snapshot.snapshot_path}/words.enriched.jsonl`;
    }
  }
  if (kind === "import" && snapshot.workflow_stage === "approved_ready_for_import") {
    return `${snapshot.snapshot_path}/reviewed/approved.jsonl`;
  }
  return "";
}

function actionStateForReview(reviewArtifactPath: string): WorkflowActionState {
  if (reviewArtifactPath) {
    return { enabled: true, reason: null };
  }
  return {
    enabled: false,
    reason: "Run enrich first. No compiled artifact is present for this snapshot yet.",
  };
}

function actionStateForImport(importArtifactPath: string): WorkflowActionState {
  if (importArtifactPath) {
    return { enabled: true, reason: null };
  }
  return {
    enabled: false,
    reason: "No reviewed/approved.jsonl is present yet. Finish review/export or materialize approved rows first.",
  };
}

export default function LexiconOpsPage() {
  const router = useRouter();
  const [snapshots, setSnapshots] = useState<LexiconOpsSnapshotSummary[]>([]);
  const [snapshotTotal, setSnapshotTotal] = useState(0);
  const [selectedSnapshotName, setSelectedSnapshotName] = useState<string | null>(null);
  const [snapshotSearchDraft, setSnapshotSearchDraft] = useState("");
  const [snapshotSearch, setSnapshotSearch] = useState("");
  const [snapshotsPage, setSnapshotsPage] = useState(1);
  const [urlStateReady, setUrlStateReady] = useState(false);
  const [detail, setDetail] = useState<LexiconOpsSnapshotDetail | null>(null);
  const [snapshotsLoading, setSnapshotsLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [snapshotsError, setSnapshotsError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [importPath, setImportPath] = useState("");
  const [importSourceReference, setImportSourceReference] = useState("");
  const [importLoading, setImportLoading] = useState(false);
  const [importMessage, setImportMessage] = useState<string | null>(null);
  const [importResult, setImportResult] = useState<LexiconImportResult | null>(null);

  const selectedSnapshot = useMemo(
    () => snapshots.find((snapshot) => snapshot.snapshot === selectedSnapshotName) ?? null,
    [selectedSnapshotName, snapshots],
  );
  const totalSnapshotPages = Math.max(1, Math.ceil(snapshotTotal / SNAPSHOTS_PAGE_SIZE));
  const workflow = useMemo(() => workflowStage(selectedSnapshot), [selectedSnapshot]);
  const handleSnapshotSearchChange = useCallback((value: string) => {
    setSnapshotSearchDraft(value);
  }, []);
  const handleSnapshotSelect = useCallback((snapshotName: string) => {
    setSelectedSnapshotName(snapshotName);
  }, []);

  const loadSnapshots = useCallback(async () => {
    setSnapshotsLoading(true);
    setSnapshotsError(null);
    try {
      const response = await listLexiconOpsSnapshots({
        q: snapshotSearch || undefined,
        limit: SNAPSHOTS_PAGE_SIZE,
        offset: (snapshotsPage - 1) * SNAPSHOTS_PAGE_SIZE,
      });
      const nextSnapshots: LexiconOpsSnapshotListResponse = Array.isArray(response)
        ? {
            items: response,
            total: response.length,
            limit: SNAPSHOTS_PAGE_SIZE,
            offset: (snapshotsPage - 1) * SNAPSHOTS_PAGE_SIZE,
            has_more: false,
            q: snapshotSearch || null,
          }
        : response;
      setSnapshots(nextSnapshots.items);
      setSnapshotTotal(nextSnapshots.total);
      setSelectedSnapshotName((existingSelected) => {
        if (!nextSnapshots.items.length) {
          return null;
        }
        return (
          nextSnapshots.items.find((snapshot) => snapshot.snapshot === existingSelected)?.snapshot ??
          nextSnapshots.items[0]?.snapshot ??
          null
        );
      });
    } catch (error) {
      setSnapshotsError(error instanceof Error ? error.message : "Failed to load lexicon snapshots.");
    } finally {
      setSnapshotsLoading(false);
    }
  }, [snapshotSearch, snapshotsPage]);

  const loadDetail = useCallback(async (snapshotName: string) => {
    setDetail(null);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const nextDetail = await getLexiconOpsSnapshot(snapshotName);
      setDetail(nextDetail);
    } catch (error) {
      setDetail(null);
      setDetailError(error instanceof Error ? error.message : "Failed to load snapshot detail.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialSearch = searchParam("q");
    setSnapshotSearch(initialSearch);
    setSnapshotSearchDraft(initialSearch);
    const rawPage = Number.parseInt(searchParam("page"), 10);
    setSnapshotsPage(Number.isFinite(rawPage) && rawPage > 0 ? rawPage : 1);
    setUrlStateReady(true);
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/ops");
      return;
    }
    void loadSnapshots();
  }, [loadSnapshots]);

  useEffect(() => {
    if (!selectedSnapshotName) {
      setDetail(null);
      return;
    }
    void loadDetail(selectedSnapshotName);
  }, [loadDetail, selectedSnapshotName]);

  useEffect(() => {
    if (!urlStateReady || typeof window === "undefined") {
      return;
    }
    const params = new URLSearchParams(window.location.search);
    if (snapshotSearch.trim()) {
      params.set("q", snapshotSearch);
    } else {
      params.delete("q");
    }
    if (snapshotsPage > 1) {
      params.set("page", String(snapshotsPage));
    } else {
      params.delete("page");
    }
    const query = params.toString();
    const nextUrl = query ? `${window.location.pathname}?${query}` : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
  }, [snapshotSearch, snapshotsPage, urlStateReady]);

  useEffect(() => {
    if (!selectedSnapshot) return;
    const approvedArtifact = selectedSnapshot.preferred_import_artifact_path ?? "";
    setImportPath(approvedArtifact);
    setImportSourceReference(selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot);
  }, [detail, selectedSnapshot]);

  const reviewArtifactPath = useMemo(() => {
    const preferred = selectedSnapshot?.preferred_review_artifact_path ?? "";
    if (preferred) return preferred;
    const fromDetail = artifactPathFromDetail(detail, [
      "words.enriched.jsonl",
      "phrases.enriched.jsonl",
      "references.enriched.jsonl",
    ]);
    if (fromDetail) return fromDetail;
    return inferArtifactPathFromSummary(selectedSnapshot, "review");
  }, [detail, selectedSnapshot]);
  const importArtifactPath = useMemo(() => {
    const preferred = selectedSnapshot?.preferred_import_artifact_path ?? "";
    if (preferred) return preferred;
    const fromDetail = artifactPathFromDetail(detail, ["reviewed/approved.jsonl"]);
    if (fromDetail) return fromDetail;
    return inferArtifactPathFromSummary(selectedSnapshot, "import");
  }, [detail, selectedSnapshot]);
  const reviewDecisionsPath = useMemo(
    () => (selectedSnapshot ? `${selectedSnapshot.snapshot_path}/reviewed/review.decisions.jsonl` : ""),
    [selectedSnapshot],
  );
  const reviewOutputDir = useMemo(
    () => (selectedSnapshot ? `${selectedSnapshot.snapshot_path}/reviewed` : ""),
    [selectedSnapshot],
  );
  const compiledReviewAction = useMemo(
    () => actionStateForReview(reviewArtifactPath),
    [reviewArtifactPath],
  );
  const jsonlReviewAction = useMemo(
    () => actionStateForReview(reviewArtifactPath),
    [reviewArtifactPath],
  );
  const importDbAction = useMemo(
    () => actionStateForImport(importArtifactPath || importPath),
    [importArtifactPath, importPath],
  );

  useEffect(() => {
    if (!selectedSnapshot) return;
    if (selectedSnapshot.preferred_import_artifact_path) return;
    if (!importPath) {
      const fallbackImportPath = artifactPathFromDetail(detail, ["reviewed/approved.jsonl"]);
      if (fallbackImportPath) {
        setImportPath(fallbackImportPath);
      }
    }
  }, [detail, importPath, selectedSnapshot]);

  const openWorkflow = (route: string, params: Record<string, string>) => {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value) searchParams.set(key, value);
    }
    const query = searchParams.toString();
    router.push(query ? `${route}?${query}` : route);
  };

  const runImport = async (mode: "dry-run" | "run") => {
    if (!importPath) return;
    setImportLoading(true);
    setImportMessage(null);
    try {
      const payload = {
        inputPath: importPath,
        sourceType: "lexicon_snapshot",
        sourceReference: importSourceReference || undefined,
        language: "en",
      };
      const result = mode === "dry-run"
        ? await dryRunLexiconImport(payload)
        : await runLexiconImport(payload);
      setImportResult(result);
      setImportMessage(mode === "dry-run" ? "Import dry-run complete." : "Import completed.");
    } catch (error) {
      setImportMessage(error instanceof Error ? error.message : "Import request failed.");
    } finally {
      setImportLoading(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="lexicon-ops-page">
      <section className="rounded-lg border border-slate-200 bg-slate-50 p-5 shadow-sm" data-testid="lexicon-ops-workflow-shell">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Workflow shell</p>
            <h3 className="mt-1 text-2xl font-semibold text-slate-950">Lexicon Ops</h3>
            <p className="mt-1 text-sm text-slate-600">
              Stage guidance stays here. Use the selected snapshot to jump into review, import, or DB inspection.
            </p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 text-sm text-slate-600">
            <p className="font-medium text-slate-900">Selected snapshot</p>
            <p className="mt-1 break-all">{selectedSnapshot?.snapshot_path ?? "Select a snapshot to continue."}</p>
          </div>
        </div>

        <div className="mt-5 grid gap-4 lg:grid-cols-2">
          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="lexicon-ops-workflow-stage">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Current stage</p>
            <p className="mt-2 text-lg font-semibold text-slate-950">{workflow.stage}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="lexicon-ops-next-step">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Next step</p>
            <p className="mt-2 text-sm leading-6 text-slate-700">{workflow.nextStep}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4 lg:col-span-2" data-testid="lexicon-ops-outside-portal">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Outside portal</p>
            <ul className="mt-2 space-y-2 text-sm leading-6 text-slate-700">
              {workflow.outsidePortal.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-gray-900">Lexicon Operations</h3>
            <p className="mt-1 text-sm text-gray-600">
              Inspect lexicon snapshot folders, stage artifacts, and rollout progress.
            </p>
          </div>
          <button
            type="button"
            className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60"
            onClick={() => void loadSnapshots()}
            data-testid="lexicon-ops-refresh-button"
            disabled={snapshotsLoading}
          >
            {snapshotsLoading ? "Refreshing..." : "Refresh"}
          </button>
        </div>

        {snapshotsError ? <p className="mt-3 text-sm text-red-600">{snapshotsError}</p> : null}

        <div className="mt-6 grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
          <div className="space-y-2" data-testid="lexicon-ops-snapshots-list">
            <label className="grid gap-1 rounded-md border border-gray-200 bg-gray-50 p-3 text-sm text-gray-700">
              <span className="font-medium">Search snapshots</span>
              <div className="flex gap-2">
                <input
                  data-testid="lexicon-ops-snapshots-search"
                  value={snapshotSearchDraft}
                  onChange={(event) => handleSnapshotSearchChange(event.target.value)}
                  placeholder="Filter by snapshot, id, or path"
                  className="min-w-0 flex-1 rounded-md border border-gray-300 bg-white px-3 py-2 text-sm"
                />
                <button
                  type="button"
                  onClick={() => {
                    setSnapshotSearch(snapshotSearchDraft.trim());
                    setSnapshotsPage(1);
                  }}
                  className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                >
                  Apply
                </button>
              </div>
            </label>
            {snapshotTotal > SNAPSHOTS_PAGE_SIZE ? (
              <div className="flex items-center justify-between rounded-md border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-600">
                <span>
                  Page {snapshotsPage} of {totalSnapshotPages}
                </span>
                <div className="flex gap-2">
                  <button
                    type="button"
                    data-testid="lexicon-ops-snapshots-prev-page"
                    onClick={() => setSnapshotsPage((current) => Math.max(1, current - 1))}
                    disabled={snapshotsPage === 1}
                    className="rounded border border-gray-300 bg-white px-2 py-1 disabled:opacity-50"
                  >
                    Previous
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-snapshots-next-page"
                    onClick={() => setSnapshotsPage((current) => Math.min(totalSnapshotPages, current + 1))}
                    disabled={snapshotsPage >= totalSnapshotPages}
                    className="rounded border border-gray-300 bg-white px-2 py-1 disabled:opacity-50"
                  >
                    Next
                  </button>
                </div>
              </div>
            ) : null}
            {snapshotTotal > SNAPSHOTS_PAGE_SIZE ? (
              <div className="flex flex-wrap gap-2 rounded-md border border-gray-200 bg-white px-3 py-2">
                {Array.from({ length: totalSnapshotPages }, (_, index) => index + 1).map((pageNumber) => (
                  <button
                    key={pageNumber}
                    type="button"
                    data-testid={`lexicon-ops-snapshots-page-${pageNumber}`}
                    onClick={() => setSnapshotsPage(pageNumber)}
                    className={`rounded border px-2 py-1 text-sm ${
                      pageNumber === snapshotsPage
                        ? "border-blue-500 bg-blue-50 text-blue-700"
                        : "border-gray-300 bg-white text-gray-700"
                    }`}
                  >
                    {pageNumber}
                  </button>
                ))}
              </div>
            ) : null}
            {snapshots.length === 0 && !snapshotsLoading ? (
              <p className="text-sm text-gray-500">No snapshots found.</p>
            ) : (
              snapshots.map((snapshot) => (
                <button
                  key={snapshot.snapshot}
                  type="button"
                  onClick={() => handleSnapshotSelect(snapshot.snapshot)}
                  className={`w-full rounded-md border p-3 text-left ${
                    selectedSnapshotName === snapshot.snapshot
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 bg-white hover:bg-gray-50"
                  }`}
                  data-testid={`lexicon-ops-snapshot-${snapshot.snapshot}`}
                >
                  <p className="font-medium">{snapshot.snapshot}</p>
                  <p className="text-xs text-gray-500">snapshot_id: {snapshot.snapshot_id ?? "—"}</p>
                  <p className="text-xs text-gray-500">status: {deriveSnapshotStatus(snapshot)}</p>
                  <p className="text-xs text-gray-500">updated: {formatDateTime(snapshot.updated_at)}</p>
                </button>
              ))
            )}
          </div>

          <div className="rounded-lg border border-gray-200 bg-gray-50 p-4" data-testid="lexicon-ops-detail-panel">
            {selectedSnapshot ? (
              <div className="space-y-4">
                <div>
                  <h4 className="text-xl font-semibold">{selectedSnapshot.snapshot}</h4>
                  <p className="text-sm text-gray-500">
                    snapshot_id: {selectedSnapshot.snapshot_id ?? "—"} · status: {deriveSnapshotStatus(selectedSnapshot)}
                  </p>
                  <p className="text-sm text-gray-500">updated: {formatDateTime(selectedSnapshot.updated_at)}</p>
                  <p className="text-xs text-gray-500 break-all">{selectedSnapshot.snapshot_path}</p>
                </div>

                <div className="flex flex-wrap gap-2" data-testid="lexicon-ops-workflow-actions">
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-jsonl-review"
                    className="rounded-md border border-sky-300 bg-sky-50 px-3 py-2 text-sm text-sky-800"
                    disabled={!jsonlReviewAction.enabled}
                    onClick={() => openWorkflow("/lexicon/jsonl-review", {
                      artifactPath: reviewArtifactPath,
                      decisionsPath: reviewDecisionsPath,
                      outputDir: reviewOutputDir,
                      sourceReference: selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot,
                      autostart: "1",
                    })}
                  >
                    Open JSONL Review
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-compiled-review"
                    className="rounded-md border border-violet-300 bg-violet-50 px-3 py-2 text-sm text-violet-800"
                    disabled={!compiledReviewAction.enabled}
                    onClick={() => openWorkflow("/lexicon/compiled-review", {
                      snapshot: selectedSnapshot.snapshot,
                      sourceReference: selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot,
                      artifactPath: reviewArtifactPath,
                      autostart: "1",
                    })}
                  >
                    Open Compiled Review
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-import-db"
                    className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                    disabled={!importDbAction.enabled}
                    onClick={() => openWorkflow("/lexicon/import-db", {
                      inputPath: importArtifactPath || importPath,
                      sourceReference: selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot,
                    })}
                  >
                    Open Import DB
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-db-inspector"
                    className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                    onClick={() => openWorkflow("/lexicon/db-inspector", {
                      snapshot: selectedSnapshot.snapshot,
                    })}
                  >
                    Open DB Inspector
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-voice-admin"
                    className="rounded-md border border-emerald-300 bg-emerald-50 px-3 py-2 text-sm text-emerald-800"
                    onClick={() => openWorkflow("/lexicon/voice-import", {
                      sourceReference: selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot,
                    })}
                  >
                    Open Voice Admin
                  </button>
                </div>
                <div className="space-y-1 text-xs text-gray-500" data-testid="lexicon-ops-action-reasons">
                  {!jsonlReviewAction.enabled ? <p>JSONL Review: {jsonlReviewAction.reason}</p> : null}
                  {!compiledReviewAction.enabled ? <p>Compiled Review: {compiledReviewAction.reason}</p> : null}
                  {!importDbAction.enabled ? <p>Import DB: {importDbAction.reason}</p> : null}
                </div>

                <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Lexemes</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.lexemes)}</p>
                  </div>
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Approved rows</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.approved_rows)}</p>
                  </div>
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Enrichments</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.enrichments)}</p>
                  </div>
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Compiled words</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.compiled_words)}</p>
                  </div>
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Review decisions</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.review_decisions)}</p>
                  </div>
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Ambiguous forms</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.ambiguous_forms)}</p>
                  </div>
                </div>

                {detailLoading ? <p className="text-sm text-gray-500">Loading snapshot detail...</p> : null}
                {detailError ? <p className="text-sm text-red-600">{detailError}</p> : null}

                {detail ? (
                  <section className="rounded border border-gray-200 bg-white p-4">
                    <h5 className="text-base font-semibold text-gray-900">Tracked artifacts</h5>
                    <div className="mt-3 space-y-2" data-testid="lexicon-ops-files-list">
                      {detail.artifacts.length === 0 ? (
                        <p className="text-sm text-gray-500">No tracked files available.</p>
                      ) : (
                        groupArtifacts(detail.artifacts).map((group) => (
                          <div key={`${group.stage}-${group.purpose}`} className="rounded border border-gray-100 bg-gray-50 p-3 text-sm">
                            <div className="flex items-center justify-between gap-3">
                              <p className="font-semibold text-gray-900">{group.stage}</p>
                              <span className="rounded bg-white px-2 py-0.5 text-xs text-gray-700">{group.purpose}</span>
                            </div>
                            <div className="mt-3 space-y-2">
                              {group.files.map((file) => (
                                <div key={file.file_name} className="rounded border border-gray-200 bg-white p-3">
                                  <div className="flex items-start justify-between gap-3">
                                    <p className="font-medium break-all">{file.file_name}</p>
                                    <span className="rounded bg-gray-200 px-2 py-0.5 text-xs text-gray-700">
                                      {fileBadgeText(file)}
                                    </span>
                                  </div>
                                  <p className="mt-1 text-xs text-gray-500">exists: {String(file.exists)}</p>
                                  <p className="text-xs text-gray-500">
                                    rows: {formatNumber(file.row_count)} · size: {formatBytes(file.size_bytes)} · updated: {formatDateTime(file.modified_at)}
                                  </p>
                                </div>
                              ))}
                            </div>
                          </div>
                        ))
                      )}
                    </div>
                  </section>
                ) : null}

                <section className="rounded border border-gray-200 bg-white p-4" data-testid="lexicon-ops-import-panel">
                  <div className="flex items-start justify-between gap-4">
                    <div>
                      <h5 className="text-base font-semibold text-gray-900">Import to Final DB</h5>
                      <p className="text-sm text-gray-500">Dry-run or execute the final import using an approved artifact for this snapshot.</p>
                      {!importPath ? (
                        <p className="mt-2 text-xs text-amber-700">
                          No `reviewed/approved.jsonl` artifact is present in this snapshot yet. Materialize or export approved rows first, or enter the final import path manually.
                        </p>
                      ) : null}
                    </div>
                  </div>
                  <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_auto]">
                    <label className="grid gap-1 text-sm text-gray-700">
                      <span className="font-medium">Input path</span>
                      <input
                        data-testid="lexicon-ops-import-input-path"
                        value={importPath}
                        onChange={(event) => setImportPath(event.target.value)}
                        className="rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
                        placeholder="data/lexicon/snapshots/.../reviewed/approved.jsonl"
                      />
                    </label>
                    <label className="grid gap-1 text-sm text-gray-700">
                      <span className="font-medium">Source reference</span>
                      <input
                        value={importSourceReference}
                        onChange={(event) => setImportSourceReference(event.target.value)}
                        className="rounded-md border border-gray-300 px-3 py-2 text-sm"
                        placeholder="optional source reference"
                      />
                    </label>
                    <div className="flex flex-wrap items-end gap-3">
                      <button
                        type="button"
                        data-testid="lexicon-ops-import-dry-run-button"
                        disabled={!importPath || importLoading}
                        onClick={() => void runImport("dry-run")}
                        className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
                      >
                        {importLoading ? "Working..." : "Dry Run"}
                      </button>
                      <button
                        type="button"
                        data-testid="lexicon-ops-import-run-button"
                        disabled={!importPath || importLoading}
                        onClick={() => void runImport("run")}
                        className="rounded-md bg-gray-900 px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
                      >
                        Import
                      </button>
                    </div>
                  </div>
                  {importMessage ? <p className="mt-3 text-sm text-gray-700">{importMessage}</p> : null}
                  {importResult ? (
                    <div className="mt-4 grid gap-3 text-sm md:grid-cols-4">
                      <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Rows</p><p className="font-medium">{importResult.row_summary.row_count}</p></div>
                      <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Words</p><p className="font-medium">{importResult.row_summary.word_count}</p></div>
                      <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">Phrases</p><p className="font-medium">{importResult.row_summary.phrase_count}</p></div>
                      <div className="rounded border border-gray-200 p-3"><p className="text-gray-500">References</p><p className="font-medium">{importResult.row_summary.reference_count}</p></div>
                    </div>
                  ) : null}
                </section>

                <section className="rounded border border-gray-200 bg-emerald-50 p-4" data-testid="lexicon-ops-voice-admin-panel">
                  <h5 className="text-base font-semibold text-emerald-950">Voice admin</h5>
                  <p className="mt-1 text-sm text-emerald-900">
                    Voice storage rewrites and future voice-run controls live on the dedicated Lexicon Voice page.
                  </p>
                  <p className="mt-2 text-xs text-emerald-800">
                    Use the selected snapshot source reference to jump there with the form prefilled.
                  </p>
                </section>
              </div>
            ) : (
              <p className="text-sm text-gray-500">Select a snapshot to inspect operational detail.</p>
            )}
          </div>
        </div>
      </section>
    </div>
  );
}
