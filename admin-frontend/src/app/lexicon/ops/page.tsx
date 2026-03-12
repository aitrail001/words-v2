"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  getLexiconOpsSnapshot,
  listLexiconOpsSnapshots,
  type LexiconOpsSnapshotArtifact,
  type LexiconOpsSnapshotDetail,
  type LexiconOpsSnapshotSummary,
} from "@/lib/lexicon-ops-client";

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
  const [snapshots, setSnapshots] = useState<LexiconOpsSnapshotSummary[]>([]);
  const [selectedSnapshotName, setSelectedSnapshotName] = useState<string | null>(null);
  const [detail, setDetail] = useState<LexiconOpsSnapshotDetail | null>(null);
  const [snapshotsLoading, setSnapshotsLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [snapshotsError, setSnapshotsError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);

  const selectedSnapshot = useMemo(
    () => snapshots.find((snapshot) => snapshot.snapshot === selectedSnapshotName) ?? null,
    [selectedSnapshotName, snapshots],
  );

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

  return (
    <div className="space-y-6" data-testid="lexicon-ops-page">
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
