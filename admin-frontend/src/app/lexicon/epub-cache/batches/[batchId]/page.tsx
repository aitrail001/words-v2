"use client";

import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";

import { EpubCacheNav } from "@/components/lexicon/epub-cache-nav";
import { ApiError } from "@/lib/api-client";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  getAdminImportBatch,
  listAdminImportBatchJobs,
  type AdminImportBatchJob,
  type AdminImportBatchSummary,
} from "@/lib/admin-epub-batches-client";
import { getAdminImportJob, type AdminImportJobDetail } from "@/lib/admin-import-jobs-client";

const POLL_INTERVAL_MS = 2500;

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "-";
  if (seconds < 1) return "<1s";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function resolveUiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

function isBatchTerminal(batch: AdminImportBatchSummary | null): boolean {
  if (!batch) return true;
  return Number(batch.active_jobs ?? 0) === 0;
}

export default function EpubCacheBatchDetailPage() {
  const params = useParams<{ batchId: string }>();
  const batchId = String(params?.batchId || "");

  const [batch, setBatch] = useState<AdminImportBatchSummary | null>(null);
  const [jobs, setJobs] = useState<AdminImportBatchJob[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJobDetail, setSelectedJobDetail] = useState<AdminImportJobDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadBatch = useCallback(async () => {
    if (!batchId) return;
    try {
      const [batchResponse, jobsResponse] = await Promise.all([
        getAdminImportBatch(batchId),
        listAdminImportBatchJobs(batchId, { limit: 500 }),
      ]);
      setBatch(batchResponse);
      setJobs(jobsResponse.items);
      if (!selectedJobId && jobsResponse.items.length > 0) {
        setSelectedJobId(jobsResponse.items[0].id);
      }
    } catch (nextError) {
      setError(resolveUiErrorMessage(nextError, "Failed to load batch"));
    }
  }, [batchId, selectedJobId]);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin(`/lexicon/epub-cache/batches/${batchId}`);
      return;
    }
    void loadBatch();
  }, [batchId, loadBatch]);

  useEffect(() => {
    if (!batchId) return;
    if (isBatchTerminal(batch)) return;
    const intervalId = window.setInterval(() => {
      void loadBatch();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [batch, batchId, loadBatch]);

  useEffect(() => {
    if (!selectedJobId) {
      setSelectedJobDetail(null);
      return;
    }
    getAdminImportJob(selectedJobId)
      .then((detail) => setSelectedJobDetail(detail))
      .catch((nextError) => setError(resolveUiErrorMessage(nextError, "Failed to load import job detail")));
  }, [selectedJobId]);

  const summary = useMemo(() => {
    if (!batch) return "-";
    return `${batch.completed_jobs ?? 0}/${batch.total_jobs ?? 0} completed${(batch.failed_jobs ?? 0) > 0 ? `, ${batch.failed_jobs} failed` : ""}`;
  }, [batch]);

  return (
    <div className="space-y-6" data-testid="lexicon-epub-cache-batch-detail-page">
      <header className="space-y-3">
        <h1 className="text-2xl font-semibold text-slate-900">EPUB Cache Management</h1>
        <EpubCacheNav active="batches" />
      </header>

      {error ? <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Batch Summary</h2>
        <p className="mt-2 text-sm text-slate-700">
          <span className="font-medium">{batch?.name || batchId}</span> · {summary} · created {formatDate(batch?.created_at)}
        </p>
      </section>

      <section className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-lg border border-slate-200 bg-white p-4">
          <h3 className="text-sm font-semibold text-slate-900">Book Imports</h3>
          <ul className="mt-3 space-y-2" data-testid="epub-cache-batch-jobs">
            {jobs.map((job) => (
              <li key={job.id} className="rounded border border-slate-200 bg-slate-50 px-3 py-2">
                <button
                  type="button"
                  onClick={() => setSelectedJobId(job.id)}
                  className="w-full text-left"
                >
                  <p className="text-sm font-medium text-slate-900">{job.source_filename}</p>
                  <p className="text-xs text-slate-600">
                    {job.status}{job.from_cache ? " · cache hit" : " · fresh"} · {formatDate(job.created_at)}
                  </p>
                </button>
              </li>
            ))}
            {jobs.length === 0 ? <li className="text-xs text-slate-500">No jobs in this batch.</li> : null}
          </ul>
        </div>

        <div className="rounded-lg border border-slate-200 bg-white p-4" data-testid="epub-cache-batch-job-detail">
          <h3 className="text-sm font-semibold text-slate-900">Book Import Detail</h3>
          {!selectedJobDetail ? (
            <p className="mt-2 text-xs text-slate-500">Select a book import to inspect details.</p>
          ) : (
            <div className="mt-3 space-y-2 text-sm text-slate-700">
              <p><span className="font-medium">Title:</span> {selectedJobDetail.source_title || selectedJobDetail.list_name || "-"}</p>
              <p><span className="font-medium">Filename:</span> {selectedJobDetail.source_filename}</p>
              <p><span className="font-medium">Author:</span> {selectedJobDetail.source_author || "-"}</p>
              <p><span className="font-medium">Status:</span> {selectedJobDetail.status}</p>
              <p><span className="font-medium">From cache:</span> {selectedJobDetail.from_cache ? "yes" : "no"}</p>
              <p><span className="font-medium">Matched entries:</span> {selectedJobDetail.matched_entry_count}</p>
              <p><span className="font-medium">Words:</span> {selectedJobDetail.word_entry_count}</p>
              <p><span className="font-medium">Phrases:</span> {selectedJobDetail.phrase_entry_count}</p>
              <p><span className="font-medium">Progress:</span> {selectedJobDetail.progress_completed}/{selectedJobDetail.progress_total}</p>
              <p><span className="font-medium">Duration:</span> {formatDuration(selectedJobDetail.processing_duration_seconds)}</p>
              <p><span className="font-medium">Started:</span> {formatDate(selectedJobDetail.started_at)}</p>
              <p><span className="font-medium">Completed:</span> {formatDate(selectedJobDetail.completed_at)}</p>
              {selectedJobDetail.error_message ? <p className="text-rose-700"><span className="font-medium">Error:</span> {selectedJobDetail.error_message}</p> : null}
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
