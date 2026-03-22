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
  type LexiconOpsSnapshotSummary,
} from "@/lib/lexicon-ops-client";
import { dryRunLexiconImport, runLexiconImport, type LexiconImportResult } from "@/lib/lexicon-imports-client";

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
    base_artifacts: "Compile exported review artifact",
    compiled_ready_for_review: "Review compiled artifact",
    approved_ready_for_import: "Import approved rows",
  };
  const nextStepByKey: Record<string, string> = {
    run_build_base: "Run build-base and enrich outside the portal.",
    run_compile_export: "Run compile-export outside the portal, then return here.",
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
  if (snapshot.has_selection_decisions) {
    return "review-ready";
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

export default function LexiconOpsPage() {
  const router = useRouter();
  const [snapshots, setSnapshots] = useState<LexiconOpsSnapshotSummary[]>([]);
  const [selectedSnapshotName, setSelectedSnapshotName] = useState<string | null>(null);
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
  const workflow = useMemo(() => workflowStage(selectedSnapshot), [selectedSnapshot]);

  const loadSnapshots = useCallback(async () => {
    setSnapshotsLoading(true);
    setSnapshotsError(null);
    try {
      const nextSnapshots = await listLexiconOpsSnapshots();
      setSnapshots(nextSnapshots);
      setSelectedSnapshotName((existingSelected) => {
        if (!nextSnapshots.length) {
          return null;
        }
        return (
          nextSnapshots.find((snapshot) => snapshot.snapshot === existingSelected)?.snapshot ??
          nextSnapshots[0]?.snapshot ??
          null
        );
      });
    } catch (error) {
      setSnapshotsError(error instanceof Error ? error.message : "Failed to load lexicon snapshots.");
    } finally {
      setSnapshotsLoading(false);
    }
  }, []);

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
    if (!selectedSnapshot) return;
    const approvedArtifact = selectedSnapshot.preferred_import_artifact_path ?? "";
    setImportPath(approvedArtifact);
    setImportSourceReference(selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot);
  }, [detail, selectedSnapshot]);

  const reviewArtifactPath = useMemo(
    () => selectedSnapshot?.preferred_review_artifact_path ?? "",
    [selectedSnapshot],
  );
  const reviewDecisionsPath = useMemo(
    () => (selectedSnapshot ? `${selectedSnapshot.snapshot_path}/review.decisions.jsonl` : ""),
    [selectedSnapshot],
  );

  const openWorkflow = (route: string, params: Record<string, string>) => {
    const searchParams = new URLSearchParams();
    for (const [key, value] of Object.entries(params)) {
      if (value) searchParams.set(key, value);
    }
    router.push(searchParams.size > 0 ? `${route}?${searchParams.toString()}` : route);
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

        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="lexicon-ops-workflow-stage">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Current stage</p>
            <p className="mt-2 text-lg font-semibold text-slate-950">{workflow.stage}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="lexicon-ops-next-step">
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-slate-500">Next step</p>
            <p className="mt-2 text-sm leading-6 text-slate-700">{workflow.nextStep}</p>
          </div>
          <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="lexicon-ops-outside-portal">
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
            {snapshots.length === 0 && !snapshotsLoading ? (
              <p className="text-sm text-gray-500">No snapshots found.</p>
            ) : (
              snapshots.map((snapshot) => (
                <button
                  key={snapshot.snapshot}
                  type="button"
                  onClick={() => setSelectedSnapshotName(snapshot.snapshot)}
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
                    onClick={() => openWorkflow("/lexicon/jsonl-review", {
                      artifactPath: reviewArtifactPath,
                      decisionsPath: reviewDecisionsPath,
                      outputDir: selectedSnapshot.snapshot_path,
                      sourceReference: selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot,
                    })}
                  >
                    Open JSONL Review
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-compiled-review"
                    className="rounded-md border border-violet-300 bg-violet-50 px-3 py-2 text-sm text-violet-800"
                    onClick={() => openWorkflow("/lexicon/compiled-review", {
                      snapshot: selectedSnapshot.snapshot,
                      sourceReference: selectedSnapshot.snapshot_id ?? selectedSnapshot.snapshot,
                      artifactPath: reviewArtifactPath,
                    })}
                  >
                    Open Compiled Review
                  </button>
                  <button
                    type="button"
                    data-testid="lexicon-ops-open-import-db"
                    className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                    onClick={() => openWorkflow("/lexicon/import-db", {
                      inputPath: importPath,
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
                </div>

                <div className="grid gap-3 text-sm md:grid-cols-2 xl:grid-cols-3">
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Lexemes</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.lexemes)}</p>
                  </div>
                  <div className="rounded border border-gray-200 bg-white p-3">
                    <p className="text-gray-500">Senses</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.senses)}</p>
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
                    <p className="text-gray-500">Selection decisions</p>
                    <p className="font-medium">{formatNumber(selectedSnapshot.artifact_counts.selection_decisions)}</p>
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
                        detail.artifacts.map((file) => (
                          <div key={file.file_name} className="rounded border border-gray-100 bg-gray-50 p-3 text-sm">
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
                          No `approved.jsonl` artifact is present in this snapshot yet. Materialize or export approved rows first, or enter the final import path manually.
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
                        placeholder="data/lexicon/snapshots/.../approved.jsonl"
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
