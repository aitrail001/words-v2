"use client";

import { FormEvent, useCallback, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { ApiError } from "@/lib/api-client";
import {
  bulkDeleteAdminImportSources,
  deleteAdminImportSourceCache,
  getAdminImportSource,
  listAdminImportSourceEntries,
  listAdminImportSourceJobs,
  listAdminImportSources,
  type AdminImportSourceJob,
  type AdminImportSourceSummary,
} from "@/lib/admin-epub-cache-client";
import {
  createAdminEpubImportBatch,
  getAdminImportBatch,
  listAdminImportBatchJobs,
  listAdminImportBatches,
  type AdminImportBatchJob,
  type AdminImportBatchSummary,
} from "@/lib/admin-epub-batches-client";

const ACTIVE_BATCH_STORAGE_KEY = "admin-epub-cache-active-batch-id";
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

function isBatchTerminal(batch: AdminImportBatchSummary | null): boolean {
  if (!batch) return true;
  return Number(batch.active_jobs ?? 0) === 0;
}

function resolveUiErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof ApiError && error.message.trim().length > 0) {
    return error.message;
  }
  return fallback;
}

export default function LexiconEpubCachePage() {
  const [sources, setSources] = useState<AdminImportSourceSummary[]>([]);
  const [sourcesTotal, setSourcesTotal] = useState(0);
  const [loadingSources, setLoadingSources] = useState(false);
  const [selectedSourceId, setSelectedSourceId] = useState<string | null>(null);
  const [selectedSource, setSelectedSource] = useState<AdminImportSourceSummary | null>(null);
  const [selectedSourceJobs, setSelectedSourceJobs] = useState<AdminImportSourceJob[]>([]);
  const [selectedSourceEntries, setSelectedSourceEntries] = useState<Array<Record<string, unknown>>>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [batchName, setBatchName] = useState("");
  const [creatingBatch, setCreatingBatch] = useState(false);
  const [activeBatchId, setActiveBatchId] = useState<string | null>(null);
  const [activeBatch, setActiveBatch] = useState<AdminImportBatchSummary | null>(null);
  const [activeBatchJobs, setActiveBatchJobs] = useState<AdminImportBatchJob[]>([]);
  const [recentBatches, setRecentBatches] = useState<AdminImportBatchSummary[]>([]);

  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const selectedSourceIds = useMemo(() => Array.from(selectedIds), [selectedIds]);

  const loadSources = useCallback(async () => {
    setLoadingSources(true);
    try {
      const response = await listAdminImportSources({
        q: q.trim() || undefined,
        status: statusFilter,
        sort: "processed_at",
        order: "desc",
        limit: 50,
      });
      setSources(response.items);
      setSourcesTotal(response.total);
    } catch (error) {
      setError(resolveUiErrorMessage(error, "Failed to load cache sources"));
    } finally {
      setLoadingSources(false);
    }
  }, [q, statusFilter]);

  const loadRecentBatches = useCallback(async () => {
    try {
      const response = await listAdminImportBatches({ limit: 12 });
      setRecentBatches(response.items);
    } catch {
      // keep page usable
    }
  }, []);

  const loadSelectedSource = useCallback(async (sourceId: string) => {
    try {
      const [source, jobs, entries] = await Promise.all([
        getAdminImportSource(sourceId),
        listAdminImportSourceJobs(sourceId, { limit: 20 }),
        listAdminImportSourceEntries(sourceId, { limit: 20, offset: 0, sort: "book_frequency", order: "desc" }),
      ]);
      setSelectedSource(source);
      setSelectedSourceJobs(jobs.items);
      setSelectedSourceEntries(entries.items);
    } catch (error) {
      setError(resolveUiErrorMessage(error, "Failed to load source details"));
    }
  }, []);

  const loadActiveBatch = useCallback(async (batchId: string) => {
    try {
      const [batch, jobs] = await Promise.all([
        getAdminImportBatch(batchId),
        listAdminImportBatchJobs(batchId, { limit: 200 }),
      ]);
      setActiveBatch(batch);
      setActiveBatchJobs(jobs.items);
      if (isBatchTerminal(batch)) {
        window.localStorage.removeItem(ACTIVE_BATCH_STORAGE_KEY);
        setActiveBatchId(null);
      }
    } catch (error) {
      setError(resolveUiErrorMessage(error, "Failed to load active batch"));
    }
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/epub-cache");
      return;
    }
    const stored = window.localStorage.getItem(ACTIVE_BATCH_STORAGE_KEY);
    if (stored) {
      setActiveBatchId(stored);
    }
    void loadSources();
    void loadRecentBatches();
  }, [loadRecentBatches, loadSources]);

  useEffect(() => {
    if (!selectedSourceId) {
      setSelectedSource(null);
      setSelectedSourceJobs([]);
      setSelectedSourceEntries([]);
      return;
    }
    void loadSelectedSource(selectedSourceId);
  }, [loadSelectedSource, selectedSourceId]);

  useEffect(() => {
    if (!activeBatchId) {
      setActiveBatch(null);
      setActiveBatchJobs([]);
      return;
    }
    void loadActiveBatch(activeBatchId);
    const intervalId = window.setInterval(() => {
      void loadActiveBatch(activeBatchId);
      void loadSources();
      void loadRecentBatches();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(intervalId);
  }, [activeBatchId, loadActiveBatch, loadRecentBatches, loadSources]);

  const toggleSelect = (sourceId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(sourceId)) next.delete(sourceId);
      else next.add(sourceId);
      return next;
    });
  };

  const handleDeleteSource = async (sourceId: string) => {
    if (!window.confirm("Delete this EPUB cache extract? Word lists are preserved.")) return;
    try {
      await deleteAdminImportSourceCache(sourceId, { deleteMode: "cache_only" });
      setMessage("Cache deleted");
      await loadSources();
      if (selectedSourceId === sourceId) {
        await loadSelectedSource(sourceId);
      }
    } catch (error) {
      setError(resolveUiErrorMessage(error, "Failed to delete cache source"));
    }
  };

  const handleBulkDelete = async () => {
    if (selectedSourceIds.length === 0) return;
    if (!window.confirm(`Delete ${selectedSourceIds.length} selected cache sources? Word lists are preserved.`)) return;
    try {
      await bulkDeleteAdminImportSources(selectedSourceIds, { deleteMode: "cache_only" });
      setSelectedIds(new Set());
      setMessage("Selected cache sources deleted");
      await loadSources();
    } catch (error) {
      setError(resolveUiErrorMessage(error, "Failed to bulk delete sources"));
    }
  };

  const handleCreateBatch = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (uploadFiles.length === 0) {
      setError("Select one or more EPUB files");
      return;
    }

    setCreatingBatch(true);
    setError(null);
    setMessage(null);
    try {
      const response = await createAdminEpubImportBatch({ files: uploadFiles, batchName: batchName.trim() || undefined });
      const nextBatchId = response.batch.id;
      setActiveBatchId(nextBatchId);
      window.localStorage.setItem(ACTIVE_BATCH_STORAGE_KEY, nextBatchId);
      setUploadFiles([]);
      setBatchName("");
      setMessage(`Batch created with ${response.jobs.length} jobs`);
      await loadSources();
      await loadRecentBatches();
    } catch (error) {
      setError(resolveUiErrorMessage(error, "Failed to start pre-import batch"));
    } finally {
      setCreatingBatch(false);
    }
  };

  return (
    <div className="space-y-6" data-testid="lexicon-epub-cache-page">
      <header className="space-y-3">
        <h1 className="text-2xl font-semibold text-slate-900">EPUB Cache Management</h1>
      </header>

      {error ? <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p> : null}
      {message ? <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</p> : null}

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Cache Sources</h2>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input
            type="search"
            value={q}
            onChange={(event) => setQ(event.target.value)}
            placeholder="Search title/author/publisher/isbn"
            className="w-80 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <select
            value={statusFilter}
            onChange={(event) => setStatusFilter(event.target.value)}
            className="rounded-md border border-slate-300 px-2 py-2 text-sm"
          >
            <option value="all">All status</option>
            <option value="completed">Completed</option>
            <option value="processing">Processing</option>
            <option value="pending">Pending</option>
            <option value="failed">Failed</option>
            <option value="deleted">Deleted</option>
          </select>
          <button
            type="button"
            onClick={() => void loadSources()}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            Refresh
          </button>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set(sources.map((source) => source.id)))}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            Select all visible
          </button>
          <button
            type="button"
            onClick={() => setSelectedIds(new Set())}
            className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          >
            Clear selection
          </button>
          <button
            type="button"
            onClick={() => void handleBulkDelete()}
            disabled={selectedSourceIds.length === 0}
            className="rounded-md border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 disabled:opacity-50"
          >
            Bulk delete selected
          </button>
        </div>
        <p className="mt-2 text-xs text-slate-500">{sourcesTotal.toLocaleString()} sources</p>

        <div className="mt-3 overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200 text-sm" data-testid="epub-cache-sources-table">
            <thead className="bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-600">
              <tr>
                <th className="px-2 py-2">Sel</th>
                <th className="px-2 py-2">Title</th>
                <th className="px-2 py-2">Author</th>
                <th className="px-2 py-2">Publisher</th>
                <th className="px-2 py-2">ISBN</th>
                <th className="px-2 py-2">Status</th>
                <th className="px-2 py-2">Matched</th>
                <th className="px-2 py-2">First imported</th>
                <th className="px-2 py-2">Duration</th>
                <th className="px-2 py-2">Cache hits</th>
                <th className="px-2 py-2">Last reused</th>
                <th className="px-2 py-2">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {loadingSources ? (
                <tr><td className="px-2 py-3 text-slate-500" colSpan={12}>Loading...</td></tr>
              ) : null}
              {!loadingSources && sources.length === 0 ? (
                <tr><td className="px-2 py-3 text-slate-500" colSpan={12}>No cache sources found.</td></tr>
              ) : null}
              {sources.map((source) => (
                <tr key={source.id} className={selectedSourceId === source.id ? "bg-sky-50/40" : ""}>
                  <td className="px-2 py-2 align-top">
                    <input type="checkbox" checked={selectedIds.has(source.id)} onChange={() => toggleSelect(source.id)} />
                  </td>
                  <td className="px-2 py-2 align-top">{source.title || "(untitled)"}</td>
                  <td className="px-2 py-2 align-top">{source.author || "-"}</td>
                  <td className="px-2 py-2 align-top">{source.publisher || "-"}</td>
                  <td className="px-2 py-2 align-top">{source.isbn || "-"}</td>
                  <td className="px-2 py-2 align-top">{source.status}{source.deleted_at ? " (cache deleted)" : ""}</td>
                  <td className="px-2 py-2 align-top">{source.matched_entry_count}</td>
                  <td className="px-2 py-2 align-top">{formatDate(source.first_imported_at)}</td>
                  <td className="px-2 py-2 align-top">{formatDuration(source.processing_duration_seconds)}</td>
                  <td className="px-2 py-2 align-top">{source.cache_hit_count}</td>
                  <td className="px-2 py-2 align-top">{formatDate(source.last_reused_at)}</td>
                  <td className="px-2 py-2 align-top">
                    <div className="flex flex-wrap gap-1">
                      <button
                        type="button"
                        onClick={() => setSelectedSourceId(source.id)}
                        className="rounded border border-slate-300 bg-white px-2 py-1 text-xs"
                      >
                        Open
                      </button>
                      <button
                        type="button"
                        onClick={() => void handleDeleteSource(source.id)}
                        className="rounded border border-rose-300 bg-rose-50 px-2 py-1 text-xs text-rose-700"
                      >
                        Delete
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Source Details</h2>
        {!selectedSource ? (
          <p className="mt-2 text-sm text-slate-600">Select a source to view metadata, jobs, and cached entries.</p>
        ) : (
          <div className="mt-3 space-y-3 text-sm text-slate-700" data-testid="epub-cache-source-details">
            <p><span className="font-medium">Title:</span> {selectedSource.title || "(untitled)"}</p>
            <p><span className="font-medium">Source hash:</span> {selectedSource.source_hash_sha256}</p>
            <p><span className="font-medium">Status:</span> {selectedSource.status}{selectedSource.deleted_at ? " (cache deleted)" : ""}</p>
            {selectedSource.deleted_at ? (
              <p className="rounded border border-amber-300 bg-amber-50 px-2 py-2 text-amber-800">
                Cache deleted at {formatDate(selectedSource.deleted_at)}. Re-upload EPUB to regenerate import cache.
              </p>
            ) : null}

            <div>
              <h3 className="font-medium text-slate-900">Job history</h3>
              <ul className="mt-1 space-y-1">
                {selectedSourceJobs.slice(0, 12).map((job) => (
                  <li key={job.id} className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
                    {formatDate(job.created_at)} · {job.status} · {job.source_filename} · {job.user_email || job.user_id}
                    {job.from_cache ? " · from cache" : " · fresh"}
                  </li>
                ))}
                {selectedSourceJobs.length === 0 ? <li className="text-xs text-slate-500">No jobs yet.</li> : null}
              </ul>
            </div>

            <div>
              <h3 className="font-medium text-slate-900">Cached entries (sample)</h3>
              <ul className="mt-1 space-y-1">
                {selectedSourceEntries.slice(0, 12).map((entry) => (
                  <li key={`${String(entry.entry_type)}:${String(entry.entry_id)}`} className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
                    {String(entry.display_text || entry.normalized_form || entry.entry_id)} · {String(entry.entry_type)} · freq {String(entry.frequency_count || 0)}
                  </li>
                ))}
                {selectedSourceEntries.length === 0 ? <li className="text-xs text-slate-500">No cached entries.</li> : null}
              </ul>
            </div>
          </div>
        )}
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Admin Pre-import Uploader</h2>
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
              onChange={(event) => setUploadFiles(Array.from(event.target.files ?? []))}
              className="block text-sm"
            />
            <p className="mt-1 text-xs text-slate-500">{uploadFiles.length} selected</p>
          </div>
          <button
            type="submit"
            disabled={creatingBatch || uploadFiles.length === 0}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            {creatingBatch ? "Starting..." : "Start pre-import batch"}
          </button>
        </form>
      </section>

      <section className="rounded-lg border border-slate-200 bg-white p-4">
        <h2 className="text-base font-semibold text-slate-900">Batch Monitor</h2>
        {activeBatch ? (
          <div className="mt-3 space-y-2" data-testid="epub-cache-active-batch">
            <p className="text-sm text-slate-700">
              <span className="font-medium">Active batch:</span> {activeBatch.name || activeBatch.id}
              {` · ${activeBatch.completed_jobs ?? 0}/${activeBatch.total_jobs ?? 0} completed`}
              {activeBatch.failed_jobs ? ` · ${activeBatch.failed_jobs} failed` : ""}
            </p>
            <ul className="space-y-1">
              {activeBatchJobs.slice(0, 16).map((job) => (
                <li key={job.id} className="rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
                  {job.source_filename} · {job.status} {job.from_cache ? "· cache hit" : ""} · {formatDate(job.created_at)}
                </li>
              ))}
            </ul>
          </div>
        ) : (
          <p className="mt-2 text-sm text-slate-600">No active batch.</p>
        )}

        <div className="mt-4">
          <h3 className="text-sm font-medium text-slate-900">Recent batches</h3>
          <ul className="mt-2 space-y-1" data-testid="epub-cache-recent-batches">
            {recentBatches.map((batch) => (
              <li key={batch.id} className="flex flex-wrap items-center gap-2 rounded border border-slate-200 bg-slate-50 px-2 py-1 text-xs">
                <span>{batch.name || batch.id}</span>
                <span>· {formatDate(batch.created_at)}</span>
                <button
                  type="button"
                  onClick={() => {
                    setActiveBatchId(batch.id);
                    window.localStorage.setItem(ACTIVE_BATCH_STORAGE_KEY, batch.id);
                  }}
                  className="rounded border border-slate-300 bg-white px-2 py-0.5"
                >
                  Monitor
                </button>
              </li>
            ))}
            {recentBatches.length === 0 ? <li className="text-xs text-slate-500">No recent batches.</li> : null}
          </ul>
        </div>
      </section>
    </div>
  );
}
