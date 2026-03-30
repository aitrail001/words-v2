"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import { PathGuidanceCard } from "@/components/lexicon/path-guidance-card";
import {
  LexiconImportResult,
  dryRunLexiconImport,
} from "@/lib/lexicon-imports-client";
import {
  createImportDbLexiconJob,
  getLexiconJob,
  listLexiconJobs,
  type LexiconJob,
} from "@/lib/lexicon-jobs-client";

const ACTIVE_JOB_STORAGE_KEY = "lexicon-import-db-active-job";
const LAST_JOB_STORAGE_KEY = "lexicon-import-db-last-job";

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

export default function LexiconImportDbPage() {
  const [inputPath, setInputPath] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [language, setLanguage] = useState("en");
  const [conflictMode, setConflictMode] = useState<"fail" | "skip" | "upsert">("upsert");
  const [errorMode, setErrorMode] = useState<"fail_fast" | "continue">("continue");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<LexiconImportResult | null>(null);
  const [job, setJob] = useState<LexiconJob | null>(null);
  const [recentJobs, setRecentJobs] = useState<LexiconJob[]>([]);
  const [loading, setLoading] = useState(false);

  const loadRecentJobs = useCallback(async () => {
    try {
      setRecentJobs(await listLexiconJobs({ jobType: "import_db", limit: 6 }));
    } catch {
      // keep the page usable even if the recent-jobs list fails
    }
  }, []);

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/import-db");
      return;
    }
    setInputPath(searchParam("inputPath"));
    setSourceReference(searchParam("sourceReference"));
    setLanguage(searchParam("language") || "en");
  }, []);

  const importResultFromJob = useCallback((nextJob: LexiconJob): LexiconImportResult => {
    const requestPayload = nextJob.request_payload ?? {};
    const resultPayload = nextJob.result_payload ?? {};
    const inputPathValue = typeof requestPayload.input_path === "string" ? requestPayload.input_path : "";
    return {
      artifact_filename: inputPathValue.split("/").pop() || inputPathValue,
      input_path: inputPathValue,
      row_summary: {
        row_count: Number((requestPayload.row_summary as Record<string, unknown> | undefined)?.row_count ?? 0),
        word_count: Number((requestPayload.row_summary as Record<string, unknown> | undefined)?.word_count ?? 0),
        phrase_count: Number((requestPayload.row_summary as Record<string, unknown> | undefined)?.phrase_count ?? 0),
        reference_count: Number((requestPayload.row_summary as Record<string, unknown> | undefined)?.reference_count ?? 0),
      },
      import_summary: Object.keys(resultPayload).length > 0
        ? Object.fromEntries(
            Object.entries(resultPayload).map(([key, value]) => [key, Number(value ?? 0)]),
          )
        : null,
    };
  }, []);

  const canRun = inputPath.trim().length > 0;
  const importSummaryEntries = useMemo(
    () => Object.entries(result?.import_summary ?? {}),
    [result?.import_summary],
  );
  const skippedCount = useMemo(() => {
    const payload = job?.result_payload ?? result?.import_summary ?? {};
    return Number((payload as Record<string, unknown>).skipped_words ?? 0)
      + Number((payload as Record<string, unknown>).skipped_phrases ?? 0)
      + Number((payload as Record<string, unknown>).skipped_reference_entries ?? 0);
  }, [job?.result_payload, result?.import_summary]);
  const failedCount = useMemo(() => {
    const payload = job?.result_payload ?? result?.import_summary ?? {};
    return Number((payload as Record<string, unknown>).failed_rows ?? 0);
  }, [job?.result_payload, result?.import_summary]);
  const skippedForJob = (targetJob: LexiconJob | null): number => {
    const payload = (targetJob?.result_payload ?? {}) as Record<string, unknown>;
    return Number(payload.skipped_words ?? 0)
      + Number(payload.skipped_phrases ?? 0)
      + Number(payload.skipped_reference_entries ?? 0);
  };
  const failedForJob = (targetJob: LexiconJob | null): number => {
    const payload = (targetJob?.result_payload ?? {}) as Record<string, unknown>;
    return Number(payload.failed_rows ?? 0);
  };
  const progressPercent = job && job.progress_total > 0
    ? Math.round((job.progress_completed / job.progress_total) * 100)
    : 0;
  const hasContext =
    Boolean(searchParam("inputPath") || searchParam("sourceReference") || searchParam("language")) ||
    inputPath.trim().length > 0 ||
    sourceReference.trim().length > 0 ||
    language.trim() !== "en";
  const currentResultSection = result ? (
    <div className="mt-4 border-t border-gray-200 pt-4">
      <h5 className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Current result</h5>
      <div className="mt-3 flex flex-wrap gap-2 text-sm">
        <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1" data-testid="lexicon-import-db-summary-rows">
          <span className="text-gray-500">Rows </span>
          <span className="font-medium">{result.row_summary.row_count}</span>
        </div>
        <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1" data-testid="lexicon-import-db-summary-words">
          <span className="text-gray-500">Words </span>
          <span className="font-medium">{result.row_summary.word_count}</span>
        </div>
        <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1" data-testid="lexicon-import-db-summary-phrases">
          <span className="text-gray-500">Phrases </span>
          <span className="font-medium">{result.row_summary.phrase_count}</span>
        </div>
        <div className="rounded-full border border-gray-200 bg-gray-50 px-3 py-1" data-testid="lexicon-import-db-summary-references">
          <span className="text-gray-500">References </span>
          <span className="font-medium">{result.row_summary.reference_count}</span>
        </div>
      </div>
      {importSummaryEntries.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {importSummaryEntries.map(([key, value]) => (
            <div key={key} className="rounded-full border border-gray-200 px-3 py-1 text-sm">
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
    </div>
  ) : null;

  const execute = useCallback(async (mode: "dry-run" | "run") => {
    if (!canRun) return;
    setLoading(true);
    setMessage(null);
    try {
      const payload = {
        inputPath,
        sourceType: "lexicon_snapshot",
        sourceReference: sourceReference || undefined,
        language,
        conflictMode,
        errorMode,
      };
      const nextResult = mode === "dry-run"
        ? await dryRunLexiconImport(payload)
        : await createImportDbLexiconJob(payload);
      if (mode === "dry-run") {
        setResult(nextResult as LexiconImportResult);
        setMessage("Import dry-run complete.");
      } else {
        const nextJob = nextResult as LexiconJob;
        setJob(nextJob);
        setResult(null);
        if (typeof window !== "undefined") {
          window.localStorage.setItem(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
          window.localStorage.setItem(LAST_JOB_STORAGE_KEY, nextJob.id);
        }
        void loadRecentJobs();
        setMessage("Import started. The queued job keeps running if you browse away from this page.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Import request failed.");
    } finally {
      setLoading(false);
    }
  }, [canRun, conflictMode, errorMode, inputPath, language, loadRecentJobs, sourceReference]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const persistedJobId = window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
    if (!persistedJobId) return;
    void getLexiconJob(persistedJobId)
      .then((nextJob) => {
        setJob(nextJob);
        if (nextJob.status === "completed") {
          setResult(importResultFromJob(nextJob));
          window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
        }
      })
      .catch(() => {
        window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
        window.localStorage.removeItem(LAST_JOB_STORAGE_KEY);
      });
  }, [importResultFromJob]);

  useEffect(() => {
    void loadRecentJobs();
  }, [loadRecentJobs]);

  useEffect(() => {
    if (!job || job.status === "completed" || job.status === "failed") {
      return;
    }
    const timer = window.setInterval(() => {
      void getLexiconJob(job.id)
        .then((nextJob) => {
          setJob(nextJob);
          if (nextJob.status === "completed") {
            setResult(importResultFromJob(nextJob));
            setMessage("Import completed.");
            window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
            window.localStorage.setItem(LAST_JOB_STORAGE_KEY, nextJob.id);
            void loadRecentJobs();
          } else if (nextJob.status === "failed") {
            setMessage(nextJob.error_message || "Import failed.");
            window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
            window.localStorage.setItem(LAST_JOB_STORAGE_KEY, nextJob.id);
            void loadRecentJobs();
          }
        })
        .catch((error) => {
          setMessage(error instanceof Error ? error.message : "Failed to refresh import progress.");
        });
    }, 500);
    return () => window.clearInterval(timer);
  }, [importResultFromJob, job, loadRecentJobs]);

  const statusBadgeClass = (status: LexiconJob["status"]): string => {
    if (status === "failed") return "border-rose-200 bg-rose-50 text-rose-700";
    if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
    if (status === "running") return "border-sky-200 bg-sky-50 text-sky-700";
    return "border-slate-200 bg-slate-50 text-slate-600";
  };

  const currentEntryLabel = (targetJob: LexiconJob): string => {
    if (targetJob.status === "completed") {
      return "Completed";
    }
    if (targetJob.status === "failed") {
      if (targetJob.progress_completed === 0) {
        return "Failed before first row";
      }
      return targetJob.progress_total > 0
        ? `Failed after ${targetJob.progress_completed}/${targetJob.progress_total}`
        : "Failed";
    }
    return targetJob.progress_current_label ?? "Waiting for first row...";
  };

  return (
    <div className="space-y-6" data-testid="lexicon-import-db-page">
      {hasContext ? (
        <section className="rounded-lg border border-gray-200 bg-slate-50 p-4 text-sm text-slate-800" data-testid="lexicon-import-db-context">
          <p className="font-medium">Workflow context</p>
          <p className="mt-1">Input path: {inputPath || "—"}</p>
          <p>Source reference: {sourceReference || "—"}</p>
          <p>Language: {language || "—"}</p>
          <p className="mt-1">Stage: Final DB write</p>
          <p>Next step: Open DB Inspector after import to verify the final state.</p>
        </section>
      ) : null}

      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h3 className="text-2xl font-semibold text-gray-900">Lexicon Import to Final DB</h3>
            <p className="mt-1 max-w-3xl text-sm text-gray-600">
              Run a manual dry run to validate importability, then execute the final `import-db` write step when ready.
            </p>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Use reviewed/approved.jsonl from Compiled Review export or JSONL Review materialize, not the raw words.enriched.jsonl artifact unless you are intentionally bypassing review.
            </p>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Dry run checks import-blocking validation and importability issues before any write path starts. Import runs the same preflight again before SQL writes.
            </p>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Imports run in the backend. If you browse away and come back in the same browser session, this page reconnects to the active import job.
            </p>
          </div>
        </div>

        <PathGuidanceCard
          className="mt-4"
          modeNote="Import DB should normally use reviewed/approved.jsonl, not the raw compiled artifact, unless you are intentionally bypassing review."
        />

        <div className="mt-6 grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_10rem_auto]">
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Input path</span>
            <input
              data-testid="lexicon-import-db-input-path"
              value={inputPath}
              onChange={(event) => setInputPath(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 font-mono text-sm"
              placeholder="data/lexicon/snapshots/.../reviewed/approved.jsonl"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Source reference</span>
            <input
              value={sourceReference}
              onChange={(event) => setSourceReference(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              placeholder="optional source reference"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Language</span>
            <input
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
            />
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Conflict handling</span>
            <select
              value={conflictMode}
              onChange={(event) => setConflictMode(event.target.value as "fail" | "skip" | "upsert")}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              data-testid="lexicon-import-db-conflict-mode"
            >
              <option value="fail">Fail if exists</option>
              <option value="skip">Skip existing</option>
              <option value="upsert">Upsert existing</option>
            </select>
          </label>
          <label className="grid gap-1 text-sm text-gray-700">
            <span className="font-medium">Error handling</span>
            <select
              value={errorMode}
              onChange={(event) => setErrorMode(event.target.value as "fail_fast" | "continue")}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              data-testid="lexicon-import-db-error-mode"
            >
              <option value="continue">Continue and report failures</option>
              <option value="fail_fast">Stop on first error</option>
            </select>
          </label>
          <div className="flex flex-wrap items-end gap-3">
            <button
              type="button"
              data-testid="lexicon-import-db-dry-run-button"
              onClick={() => void execute("dry-run")}
              disabled={!canRun || loading}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-700 disabled:opacity-50"
            >
              {loading ? "Working..." : "Dry Run"}
            </button>
            <button
              type="button"
              data-testid="lexicon-import-db-run-button"
              onClick={() => void execute("run")}
              disabled={!canRun || loading}
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Import
            </button>
          </div>
        </div>

        {message ? <p className="mt-4 text-sm text-gray-700">{message}</p> : null}
      </section>

      {job ? (
        <section className={`rounded-lg border bg-white p-6 shadow-sm ${job.status === "failed" ? "border-rose-200" : job.status === "completed" ? "border-emerald-200" : "border-gray-200"}`} data-testid="lexicon-import-db-progress">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Import progress</h4>
              <p className="mt-1 text-sm text-gray-700">
                Status: <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${statusBadgeClass(job.status)}`}>{job.status}</span>
              </p>
              <p className="mt-1 text-sm text-gray-700">
                Current entry: <span className="font-medium">{currentEntryLabel(job)}</span>
              </p>
              <p className="mt-1 text-sm text-gray-700">
                Input: <span className="font-medium">{String(job.request_payload.input_path ?? "") || "—"}</span>
              </p>
              {job.error_message ? (
                <p className="mt-1 text-sm text-rose-700">{job.error_message}</p>
              ) : null}
            </div>
            <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">
              {progressPercent}%
            </span>
          </div>
          <div className="mt-4 h-3 overflow-hidden rounded-full bg-slate-100">
            <div
              className="h-full rounded-full bg-slate-900 transition-[width]"
              style={{ width: `${progressPercent}%` }}
            />
          </div>
          <div className="mt-4 grid gap-3 md:grid-cols-5">
            <div className="rounded border border-gray-200 p-3">
              <p className="text-gray-500">Done</p>
              <p className="font-medium">{job.progress_completed}</p>
            </div>
            <div className="rounded border border-gray-200 p-3">
              <p className="text-gray-500">To do</p>
              <p className="font-medium">{Math.max(job.progress_total - job.progress_completed, 0)}</p>
            </div>
            <div className="rounded border border-gray-200 p-3">
              <p className="text-gray-500">Total</p>
              <p className="font-medium">{job.progress_total}</p>
            </div>
            <div className="rounded border border-gray-200 p-3">
              <p className="text-gray-500">Skipped</p>
              <p className="font-medium">{skippedCount}</p>
            </div>
            <div className="rounded border border-gray-200 p-3">
              <p className="text-gray-500">Failed</p>
              <p className="font-medium">{failedCount}</p>
            </div>
          </div>

          {currentResultSection}
        </section>
      ) : null}

      {!job && currentResultSection ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          {currentResultSection}
        </section>
      ) : null}

      {recentJobs.length > 0 ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" data-testid="lexicon-import-db-recent-jobs">
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Recent jobs</h4>
          <div className="mt-4 grid gap-3">
            {recentJobs.map((recentJob) => (
              <div
                key={recentJob.id}
                className={`rounded border p-3 text-sm ${recentJob.status === "failed" ? "border-rose-200 bg-rose-50" : recentJob.status === "completed" ? "border-emerald-200 bg-emerald-50" : "border-gray-200 bg-white"}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate font-medium" title={String(recentJob.request_payload.input_path ?? "")}>
                      {String(recentJob.request_payload.input_path ?? "") || "—"}
                    </p>
                    <p className="mt-1 text-xs text-gray-600">
                      Current entry: {currentEntryLabel(recentJob)}
                    </p>
                    <p className="mt-1 text-xs text-gray-500">
                      {new Date(recentJob.created_at).toLocaleString()}
                    </p>
                  </div>
                  <span className={`inline-flex shrink-0 rounded-full border px-2 py-0.5 text-xs font-medium ${statusBadgeClass(recentJob.status)}`}>
                    {recentJob.status}
                  </span>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-gray-700 md:grid-cols-4">
                  <p>Done: <span className="font-medium">{recentJob.progress_completed}</span></p>
                  <p>Total: <span className="font-medium">{recentJob.progress_total}</span></p>
                  <p>Skipped: <span className="font-medium">{skippedForJob(recentJob)}</span></p>
                  <p>Failed: <span className="font-medium">{failedForJob(recentJob)}</span></p>
                </div>
                <div className="mt-2 grid gap-2 text-xs text-gray-700 md:grid-cols-2">
                  <p>Conflict: <span className="font-medium">{String(recentJob.request_payload.conflict_mode ?? "—")}</span></p>
                  <p>Error mode: <span className="font-medium">{String(recentJob.request_payload.error_mode ?? "—")}</span></p>
                </div>
                {recentJob.error_message ? (
                  <p className="mt-2 text-xs text-rose-700">{recentJob.error_message}</p>
                ) : null}
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}
