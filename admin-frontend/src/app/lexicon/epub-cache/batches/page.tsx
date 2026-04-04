"use client";

import Link from "next/link";
import { FormEvent, useCallback, useEffect, useState } from "react";

import { EpubCacheNav } from "@/components/lexicon/epub-cache-nav";
import { ApiError } from "@/lib/api-client";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  addAdminEpubFilesToBatch,
  createAdminImportBatch,
  listAdminImportBatches,
  type AdminImportBatchSummary,
} from "@/lib/admin-epub-batches-client";

const MAX_BATCH_FILES = 10;

function formatDate(value: string | null | undefined): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function resolveUiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

export default function EpubCacheBatchesPage() {
  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [batchName, setBatchName] = useState("");
  const [creatingBatch, setCreatingBatch] = useState(false);
  const [recentBatches, setRecentBatches] = useState<AdminImportBatchSummary[]>([]);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [submissionTotal, setSubmissionTotal] = useState(0);
  const [uploadedCount, setUploadedCount] = useState(0);
  const [queuedJobCount, setQueuedJobCount] = useState(0);
  const [failedUploadCount, setFailedUploadCount] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const loadRecentBatches = useCallback(async () => {
    try {
      const response = await listAdminImportBatches({ limit: 20 });
      setRecentBatches(response.items);
    } catch {
      // keep page usable
    }
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/epub-cache/batches");
      return;
    }
    void loadRecentBatches();
  }, [loadRecentBatches]);

  const handleCreateBatch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (uploadFiles.length === 0) {
      setError("Select one or more EPUB files");
      return;
    }
    if (uploadFiles.length > MAX_BATCH_FILES) {
      setError(`Too many files in batch (max ${MAX_BATCH_FILES})`);
      return;
    }

    setCreatingBatch(true);
    setError(null);
    setMessage(null);
    setSubmissionTotal(uploadFiles.length);
    setUploadedCount(0);
    setQueuedJobCount(0);
    setFailedUploadCount(0);
    setActiveBatchId(null);
    try {
      const batch = await createAdminImportBatch({ batchName: batchName.trim() || undefined });
      setActiveBatchId(batch.id);
      setMessage(`Batch created. Uploading 0/${uploadFiles.length} books...`);
      await loadRecentBatches();

      let totalQueuedJobs = 0;
      let totalFailures = 0;
      const failureMessages: string[] = [];
      for (let index = 0; index < uploadFiles.length; index += 1) {
        const file = uploadFiles[index];
        try {
          const response = await addAdminEpubFilesToBatch(batch.id, { files: [file] });
          totalQueuedJobs += response.jobs.length;
          totalFailures += response.failures?.length || 0;
          if (response.failures?.length) {
            failureMessages.push(...response.failures.map((item) => `${item.source_filename}: ${item.error}`));
          }
        } catch (nextError) {
          totalFailures += 1;
          failureMessages.push(`${file.name}: ${resolveUiErrorMessage(nextError, "Failed to enqueue import")}`);
        }
        setUploadedCount(index + 1);
        setQueuedJobCount(totalQueuedJobs);
        setFailedUploadCount(totalFailures);
        setMessage(`Batch created. Uploading ${index + 1}/${uploadFiles.length} books...`);
        if ((index + 1) % 3 === 0 || index === uploadFiles.length - 1) {
          await loadRecentBatches();
        }
      }

      setUploadFiles([]);
      setBatchName("");
      setMessage(`Batch created with ${totalQueuedJobs} jobs${totalFailures > 0 ? `, ${totalFailures} failed` : ""}`);
      if (totalFailures > 0) {
        setError(failureMessages.join(" | ") || "Some files failed");
      }
    } catch (nextError) {
      setError(resolveUiErrorMessage(nextError, "Failed to start pre-import batch"));
    } finally {
      setCreatingBatch(false);
      setSubmissionTotal(0);
    }
  };

  return (
    <div className="space-y-6" data-testid="lexicon-epub-cache-batches-page">
      <header className="space-y-3">
        <h1 className="text-2xl font-semibold text-slate-900">EPUB Cache Management</h1>
        <EpubCacheNav active="batches" />
      </header>

      {error ? <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
      {message ? <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}
      {creatingBatch && activeBatchId ? (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-800">
          Upload progress: {uploadedCount}/{submissionTotal} books submitted, {queuedJobCount} jobs queued
          {failedUploadCount > 0 ? `, ${failedUploadCount} failed` : ""}.{" "}
          <Link href={`/lexicon/epub-cache/batches/${activeBatchId}`} className="underline">
            Open batch
          </Link>
        </div>
      ) : null}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Batch Import</h2>
        <form className="mt-3 space-y-3" onSubmit={(event) => void handleCreateBatch(event)}>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Batch name (optional)</label>
            <input
              type="text"
              value={batchName}
              onChange={(event) => setBatchName(event.target.value)}
              className="w-full max-w-lg rounded-md border border-slate-300 px-3 py-2 text-sm"
              placeholder="April pre-import wave"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">EPUB files</label>
            <input
              type="file"
              accept=".epub"
              multiple
              onChange={(event) => {
                const nextFiles = Array.from(event.target.files ?? []);
                setUploadFiles(nextFiles);
                if (nextFiles.length > MAX_BATCH_FILES) {
                  setError(`Too many files in batch (max ${MAX_BATCH_FILES})`);
                } else {
                  setError(null);
                }
              }}
              className="block text-sm"
            />
            <p className="mt-1 text-xs text-slate-500">
              {uploadFiles.length} selected. Max {MAX_BATCH_FILES} books per batch.
            </p>
          </div>
          <button
            type="submit"
            disabled={creatingBatch || uploadFiles.length === 0 || uploadFiles.length > MAX_BATCH_FILES}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {creatingBatch ? `Submitting ${uploadedCount}/${submissionTotal} book${submissionTotal === 1 ? "" : "s"}...` : "Start pre-import batch"}
          </button>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-base font-semibold text-slate-900">Recent Batches</h2>
          <button
            type="button"
            onClick={() => void loadRecentBatches()}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-xs"
          >
            Refresh
          </button>
        </div>
        <ul className="mt-3 space-y-2" data-testid="epub-cache-recent-batches">
          {recentBatches.map((batch) => (
            <li key={batch.id} className="rounded border border-slate-200 bg-slate-50 px-3 py-2 text-sm">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="space-y-1">
                  <p className="font-medium text-slate-900">{batch.name || batch.id}</p>
                  <p className="text-xs text-slate-600">{formatDate(batch.created_at)}</p>
                  <p className="text-xs text-slate-600">
                    Launched by: {batch.created_by_email || batch.created_by_user_id}
                    {" · "}
                    Books: {batch.total_jobs ?? 0}
                  </p>
                </div>
                <Link
                  href={`/lexicon/epub-cache/batches/${batch.id}`}
                  className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                >
                  Open batch
                </Link>
              </div>
            </li>
          ))}
          {recentBatches.length === 0 ? <li className="text-xs text-slate-500">No recent batches.</li> : null}
        </ul>
      </section>
    </div>
  );
}
