"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { dryRunVoiceImport, type LexiconVoiceImportResult } from "@/lib/lexicon-imports-client";
import {
  createVoiceImportDbLexiconJob,
  getLexiconJob,
  listLexiconJobs,
  type LexiconJob,
} from "@/lib/lexicon-jobs-client";

const ACTIVE_JOB_STORAGE_KEY = "lexicon-voice-import-active-job";
const INLINE_RECENT_JOB_LIMIT = 6;
const RECENT_JOB_FETCH_LIMIT = 24;

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

function statusBadgeClass(status: LexiconJob["status"]): string {
  if (status === "failed") return "border-rose-200 bg-rose-50 text-rose-700";
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "running") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function currentEntryLabel(targetJob: LexiconJob): string {
  if (targetJob.status === "completed") return "Completed";
  if (targetJob.status === "failed") {
    if (targetJob.progress_current_label) return targetJob.progress_current_label;
    if (targetJob.progress_completed === 0) return "Failed before first row";
    return targetJob.progress_total > 0
      ? `Failed after ${targetJob.progress_completed}/${targetJob.progress_total}`
      : "Failed";
  }
  return targetJob.progress_current_label ?? "Waiting for first row...";
}

export default function LexiconVoiceImportPage() {
  const [inputPath, setInputPath] = useState("");
  const [language, setLanguage] = useState("en");
  const [conflictMode, setConflictMode] = useState<"fail" | "skip" | "upsert">("upsert");
  const [errorMode, setErrorMode] = useState<"fail_fast" | "continue">("continue");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<LexiconVoiceImportResult | null>(null);
  const [job, setJob] = useState<LexiconJob | null>(null);
  const [recentJobs, setRecentJobs] = useState<LexiconJob[]>([]);
  const [showAllRecentJobs, setShowAllRecentJobs] = useState(false);
  const [loading, setLoading] = useState(false);

  const loadRecentJobs = useCallback(async () => {
    try {
      const nextJobs = await listLexiconJobs({ jobType: "voice_import_db", limit: RECENT_JOB_FETCH_LIMIT });
      setRecentJobs(nextJobs);
      if (nextJobs.length <= INLINE_RECENT_JOB_LIMIT) {
        setShowAllRecentJobs(false);
      }
    } catch {
      // keep page usable if recent jobs fail
    }
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/voice-import");
      return;
    }
    setInputPath(searchParam("inputPath"));
    setLanguage(searchParam("language") || "en");
  }, []);

  useEffect(() => {
    void loadRecentJobs();
  }, [loadRecentJobs]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const persistedJobId = window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
    if (!persistedJobId) return;
    void getLexiconJob(persistedJobId)
      .then((nextJob) => {
        setJob(nextJob);
        if (nextJob.status === "completed") {
          window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
        }
      })
      .catch(() => {
        window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
      });
  }, []);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") return;
    const timer = window.setInterval(() => {
      void getLexiconJob(job.id)
        .then((nextJob) => {
          setJob(nextJob);
          if (nextJob.status === "completed") {
            setMessage("Voice import completed.");
            window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
            void loadRecentJobs();
          } else if (nextJob.status === "failed") {
            setMessage(nextJob.error_message || "Voice import failed.");
            window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
            void loadRecentJobs();
          }
        })
        .catch((error) => {
          setMessage(error instanceof Error ? error.message : "Failed to refresh voice import progress.");
        });
    }, 500);
    return () => window.clearInterval(timer);
  }, [job, loadRecentJobs]);

  const canRun = inputPath.trim().length > 0;
  const progressPercent = job && job.progress_total > 0
    ? Math.round((job.progress_completed / job.progress_total) * 100)
    : 0;
  const progressSummary = job?.progress_summary ?? null;
  const resultSummaryEntries = useMemo(
    () => Object.entries(result?.import_summary ?? {}),
    [result?.import_summary],
  );
  const visibleRecentJobs = useMemo(
    () => (showAllRecentJobs ? recentJobs : recentJobs.slice(0, INLINE_RECENT_JOB_LIMIT)),
    [recentJobs, showAllRecentJobs],
  );
  const skippedCount = Number(progressSummary?.skipped ?? (job?.result_payload?.skipped_rows ?? result?.import_summary?.skipped_rows ?? 0));
  const failedCount = Number(progressSummary?.failed ?? (job?.result_payload?.failed_rows ?? result?.import_summary?.failed_rows ?? 0));

  const execute = useCallback(async (mode: "dry-run" | "run") => {
    if (!canRun) return;
    setLoading(true);
    setMessage(null);
    try {
      const payload = {
        inputPath,
        sourceType: "voice_manifest",
        language,
        conflictMode,
        errorMode,
      };
      if (mode === "dry-run") {
        const nextResult = await dryRunVoiceImport(payload);
        setResult(nextResult);
        setMessage("Voice import dry-run complete.");
      } else {
        const nextJob = await createVoiceImportDbLexiconJob(payload);
        setJob(nextJob);
        setResult(null);
        if (typeof window !== "undefined") {
          window.localStorage.setItem(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
        }
        setMessage("Voice import started. This page will reconnect if you return in the same browser session.");
        void loadRecentJobs();
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Voice import request failed.");
    } finally {
      setLoading(false);
    }
  }, [canRun, conflictMode, errorMode, inputPath, language, loadRecentJobs]);

  return (
    <div className="space-y-6" data-testid="lexicon-voice-import-page">
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="text-2xl font-semibold text-gray-900">Lexicon Voice Import</h3>
        <p className="mt-1 max-w-3xl text-sm text-gray-600">
          Dry run validates the voice manifest before any DB writes. Import runs the same validation first, then writes voice assets with the selected conflict and error modes.
        </p>

        <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.5fr)_9rem_12rem_12rem_auto]">
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Manifest path</span>
            <input
              data-testid="lexicon-voice-import-input-path"
              value={inputPath}
              onChange={(event) => setInputPath(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
              placeholder="data/lexicon/voice/<run>/voice_manifest.jsonl"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Language</span>
            <input
              data-testid="lexicon-voice-import-language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Conflict handling</span>
            <select
              data-testid="lexicon-voice-import-conflict-mode"
              value={conflictMode}
              onChange={(event) => setConflictMode(event.target.value as "fail" | "skip" | "upsert")}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="fail">Fail if exists</option>
              <option value="skip">Skip existing</option>
              <option value="upsert">Upsert existing</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Error handling</span>
            <select
              data-testid="lexicon-voice-import-error-mode"
              value={errorMode}
              onChange={(event) => setErrorMode(event.target.value as "fail_fast" | "continue")}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            >
              <option value="continue">Continue and report failures</option>
              <option value="fail_fast">Stop on first error</option>
            </select>
          </label>
          <div className="flex items-end gap-3">
            <button
              type="button"
              data-testid="lexicon-voice-import-dry-run"
              disabled={!canRun || loading}
              onClick={() => void execute("dry-run")}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              {loading ? "Working..." : "Dry Run"}
            </button>
            <button
              type="button"
              data-testid="lexicon-voice-import-run"
              disabled={!canRun || loading}
              onClick={() => void execute("run")}
              className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {loading ? "Working..." : "Import"}
            </button>
          </div>
        </div>
        {message ? <p className="mt-4 text-sm text-slate-700">{message}</p> : null}
      </section>

      {job ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" data-testid="lexicon-voice-import-progress">
          <div className="flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Import progress</p>
              <p className="mt-1 text-sm text-gray-600">Current entry: {currentEntryLabel(job)}</p>
              <p className="text-sm text-gray-600">Input: {String(job.request_payload.input_path ?? "—")}</p>
            </div>
            <span className={`rounded-full border px-3 py-1 text-sm font-medium ${statusBadgeClass(job.status)}`}>
              {job.status}
            </span>
          </div>
          <div className="mt-4 h-3 overflow-hidden rounded-full bg-gray-100">
            <div className="h-full bg-slate-900 transition-all" style={{ width: `${progressPercent}%` }} />
          </div>
          <div className="mt-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-7">
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">To validate </span><span className="font-medium">{progressSummary?.to_validate ?? 0}</span></div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">Validated </span><span className="font-medium">{progressSummary?.validated ?? 0}</span></div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">To import </span><span className="font-medium">{progressSummary?.to_import ?? 0}</span></div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">Imported </span><span className="font-medium">{progressSummary?.imported ?? 0}</span></div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">Skipped </span><span className="font-medium">{skippedCount}</span></div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">Failed </span><span className="font-medium">{failedCount}</span></div>
            <div className="rounded-md border border-gray-200 bg-gray-50 p-3 text-sm"><span className="text-gray-500">Total </span><span className="font-medium">{progressSummary?.total ?? job.progress_total}</span></div>
          </div>
          {job.result_payload ? (
            <div className="mt-4 border-t border-gray-200 pt-4">
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Current result</p>
              <div className="mt-3 flex flex-wrap gap-2 text-sm">
                {Object.entries(job.result_payload).map(([key, value]) => (
                  <div key={key} className="rounded-full border border-gray-200 px-3 py-1">
                    <span className="text-gray-500">{key} </span>
                    <span className="font-medium">{Number(value ?? 0)}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
      ) : null}

      {result ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" data-testid="lexicon-voice-import-result">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Dry run result</p>
          <p className="mt-1 text-sm text-gray-600">Input: {result.input_path}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-sm">
            <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1">Rows <span className="font-medium">{result.row_summary.row_count}</span></div>
            <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1">Generated <span className="font-medium">{result.row_summary.generated_count}</span></div>
            <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1">Existing <span className="font-medium">{result.row_summary.existing_count}</span></div>
            <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1">Failed ledger rows <span className="font-medium">{result.row_summary.failed_count}</span></div>
          </div>
          {resultSummaryEntries.length ? (
            <div className="mt-3 flex flex-wrap gap-2 text-sm">
              {resultSummaryEntries.map(([key, value]) => (
                <div key={key} className="rounded-full border border-gray-200 px-3 py-1">
                  <span className="text-gray-500">{key} </span>
                  <span className="font-medium">{value}</span>
                </div>
              ))}
            </div>
          ) : null}
          {result.error_samples?.length ? (
            <div className="mt-4 rounded border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
              <p className="font-medium">Detected issues</p>
              <ul className="mt-2 space-y-1">
                {result.error_samples.map((sample, index) => (
                  <li key={`${sample.entry}-${index}`}>
                    <span className="font-medium">{sample.entry}:</span> {sample.error}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" data-testid="lexicon-voice-import-recent-jobs">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Recent jobs</p>
            <p className="mt-1 text-sm text-gray-600">
              {recentJobs.length > INLINE_RECENT_JOB_LIMIT && !showAllRecentJobs
                ? `Showing the latest ${INLINE_RECENT_JOB_LIMIT} of ${recentJobs.length} jobs.`
                : `Showing ${visibleRecentJobs.length} job${visibleRecentJobs.length === 1 ? "" : "s"}.`}
            </p>
          </div>
          {recentJobs.length > INLINE_RECENT_JOB_LIMIT ? (
            <button
              type="button"
              onClick={() => setShowAllRecentJobs((current) => !current)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm font-medium text-gray-700"
            >
              {showAllRecentJobs ? "Show fewer jobs" : "Show more jobs"}
            </button>
          ) : null}
        </div>
        <div className="mt-4 space-y-3">
          {visibleRecentJobs.length ? visibleRecentJobs.map((recentJob) => (
            <div key={recentJob.id} className={`rounded-md border p-4 ${recentJob.status === "failed" ? "border-rose-200 bg-rose-50/40" : "border-gray-200 bg-gray-50/50"}`}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-medium text-gray-900">{String(recentJob.request_payload.input_path ?? recentJob.target_key)}</p>
                  <p className="mt-1 text-xs text-gray-500">{recentJob.created_at}</p>
                </div>
                <span className={`rounded-full border px-3 py-1 text-xs font-medium ${statusBadgeClass(recentJob.status)}`}>
                  {recentJob.status}
                </span>
              </div>
              <p className="mt-2 text-sm text-gray-600">Current entry: {currentEntryLabel(recentJob)}</p>
              {recentJob.error_message ? <p className="mt-2 text-sm text-rose-700">{recentJob.error_message}</p> : null}
              <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-700">
                <span className="rounded-full border border-gray-200 px-2 py-1">Done {recentJob.progress_completed}</span>
                <span className="rounded-full border border-gray-200 px-2 py-1">Total {recentJob.progress_total}</span>
                <span className="rounded-full border border-gray-200 px-2 py-1">Skipped {Number(recentJob.result_payload?.skipped_rows ?? recentJob.progress_summary?.skipped ?? 0)}</span>
                <span className="rounded-full border border-gray-200 px-2 py-1">Failed {Number(recentJob.result_payload?.failed_rows ?? recentJob.progress_summary?.failed ?? 0)}</span>
              </div>
            </div>
          )) : <p className="text-sm text-gray-500">No voice import jobs yet.</p>}
        </div>
      </section>
    </div>
  );
}
