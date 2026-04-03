"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { LexiconSectionNav } from "@/components/lexicon/section-nav";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  addLexiconActiveJobId,
  cancelLexiconJob,
  createVoiceImportDbLexiconJob,
  formatLexiconJobDuration,
  getLexiconJob,
  getLexiconJobConflictMessage,
  getLexiconJobProgressTiming,
  isLexiconJobActive,
  listLexiconJobs,
  readLexiconActiveJobIds,
  type LexiconJob,
  removeLexiconActiveJobId,
  upsertLexiconJob,
  writeLexiconActiveJobIds,
} from "@/lib/lexicon-jobs-client";
import { dryRunVoiceImport, type LexiconVoiceImportResult } from "@/lib/lexicon-imports-client";

const ACTIVE_JOB_STORAGE_KEY = "lexicon-voice-import-active-jobs";
const INLINE_RECENT_JOB_LIMIT = 6;
const RECENT_JOB_FETCH_LIMIT = 24;

const sortJobsByCreatedAtDesc = (jobs: LexiconJob[]): LexiconJob[] =>
  [...jobs].sort((leftJob, rightJob) =>
    new Date(rightJob.created_at).getTime() - new Date(leftJob.created_at).getTime(),
  );

function statusBadgeClass(status: LexiconJob["status"]): string {
  if (status === "cancel_requested") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "cancelled") return "border-slate-200 bg-slate-100 text-slate-600";
  if (status === "failed") return "border-rose-200 bg-rose-50 text-rose-700";
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "running") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
}

function currentEntryLabel(targetJob: LexiconJob): string {
  if (targetJob.status === "completed") return "Completed";
  if (targetJob.status === "cancelled") return "Cancelled";
  if (targetJob.status === "cancel_requested") return targetJob.progress_current_label ?? "Cancellation requested...";
  if (targetJob.status === "failed") {
    if (targetJob.progress_current_label) return targetJob.progress_current_label;
    if (targetJob.progress_completed === 0) return "Failed before first row";
    return targetJob.progress_total > 0
      ? `Failed after ${targetJob.progress_completed}/${targetJob.progress_total}`
      : "Failed";
  }
  return targetJob.progress_current_label ?? "Waiting for first row...";
}

const skippedForJob = (targetJob: LexiconJob): number =>
  Number(targetJob.progress_summary?.skipped ?? targetJob.result_payload?.skipped_rows ?? 0);

const failedForJob = (targetJob: LexiconJob): number =>
  Number(targetJob.progress_summary?.failed ?? targetJob.result_payload?.failed_rows ?? 0);

const recentJobCardClass = (targetJob: LexiconJob): string => {
  if (targetJob.status === "failed" || failedForJob(targetJob) > 0) {
    return "border-rose-200 bg-rose-50/40";
  }
  if (targetJob.status === "cancelled") {
    return "border-slate-300 bg-slate-100/60";
  }
  if (skippedForJob(targetJob) > 0) {
    return "border-amber-200 bg-amber-50/40";
  }
  if (targetJob.status === "completed") {
    return "border-emerald-200 bg-emerald-50/40";
  }
  return "border-gray-200 bg-gray-50/50";
};

const modeValueForJob = (
  targetJob: LexiconJob,
  key: "conflict_mode" | "error_mode",
): string => {
  const value = targetJob.request_payload[key];
  if (typeof value !== "string" || value.trim().length === 0) {
    return "—";
  }
  return value.trim();
};

const progressPercentForJob = (targetJob: LexiconJob): number => (
  targetJob.progress_total > 0
    ? Math.round((targetJob.progress_completed / targetJob.progress_total) * 100)
    : 0
);

const jobConfigValue = (targetJob: LexiconJob, key: string): string =>
  String(targetJob.request_payload?.[key] ?? "—");

const timingEntriesForJob = (targetJob: LexiconJob): Array<{ label: string; value: string }> => {
  const timing = getLexiconJobProgressTiming(targetJob);
  if (!timing) {
    return [];
  }
  return [
    { label: "Elapsed", value: formatLexiconJobDuration(timing.elapsed_ms) },
    { label: "Validation", value: formatLexiconJobDuration(timing.validation_elapsed_ms) },
    { label: "Import", value: formatLexiconJobDuration(timing.import_elapsed_ms) },
    { label: "Overhead", value: formatLexiconJobDuration(timing.orchestration_elapsed_ms) },
    { label: "Queue wait", value: formatLexiconJobDuration(timing.queue_wait_ms) },
  ].filter((entry): entry is { label: string; value: string } => Boolean(entry.value));
};

type ProgressEstimate = {
  overallPercent: number;
  validationPercent: number;
  importPercent: number;
  validationEtaMs: number | null;
  importEtaMs: number | null;
  totalEtaMs: number | null;
};

const progressEstimateForJob = (targetJob: LexiconJob): ProgressEstimate => {
  const summary = targetJob.progress_summary ?? null;
  const total = Number(summary?.total ?? targetJob.progress_total ?? 0);
  const validated = Number(summary?.validated ?? targetJob.progress_completed ?? 0);
  const toValidate = Number(summary?.to_validate ?? Math.max(total - validated, 0));
  const imported = Number(summary?.imported ?? 0);
  const skipped = Number(summary?.skipped ?? 0);
  const failed = Number(summary?.failed ?? 0);
  const toImport = Number(summary?.to_import ?? Math.max(total - imported - skipped - failed, 0));
  const processedImportRows = Math.max(total - toImport, 0);
  const validationPercent = total > 0 ? Math.round((validated / total) * 100) : 0;
  const timing = getLexiconJobProgressTiming(targetJob);
  const validationElapsed = Number(timing?.validation_elapsed_ms ?? 0);
  const importElapsed = Number(timing?.import_elapsed_ms ?? 0);
  const groupCursor = Number(targetJob.request_payload.voice_group_cursor ?? 0);
  const totalGroupCount = Number(targetJob.request_payload.voice_total_group_count ?? 0);
  const groupImportPercent = (
    totalGroupCount > 0
      ? Math.round((Math.min(groupCursor, totalGroupCount) / totalGroupCount) * 100)
      : null
  );

  const validationEtaMs = (
    toValidate > 0 && validated > 0 && validationElapsed > 0
      ? Math.round((validationElapsed / validated) * toValidate)
      : null
  );
  const importEtaMs = (
    totalGroupCount > 0 && groupCursor > 0 && importElapsed > 0 && groupCursor < totalGroupCount
      ? Math.round((importElapsed / groupCursor) * (totalGroupCount - groupCursor))
      : (toImport > 0 && processedImportRows > 0 && importElapsed > 0
        ? Math.round((importElapsed / processedImportRows) * toImport)
        : null)
  );
  const overallPercent = (
    groupImportPercent !== null
      ? (validationPercent === 100 ? groupImportPercent : Math.min(progressPercentForJob(targetJob), groupImportPercent))
      : progressPercentForJob(targetJob)
  );
  const importPercent = (
    groupImportPercent !== null
      ? groupImportPercent
      : null
  );
  const totalEtaMs = (
    validationEtaMs !== null || importEtaMs !== null
      ? (validationEtaMs ?? 0) + (importEtaMs ?? 0)
      : null
  );

  return {
    overallPercent,
    validationPercent,
    importPercent: importPercent ?? (total > 0 ? Math.round((processedImportRows / total) * 100) : 0),
    validationEtaMs,
    importEtaMs,
    totalEtaMs,
  };
};

export default function LexiconVoiceImportPage() {
  const [inputPath, setInputPath] = useState("");
  const [language, setLanguage] = useState("en");
  const [voiceGroupChunkSize, setVoiceGroupChunkSize] = useState(100);
  const [conflictMode, setConflictMode] = useState<"fail" | "skip" | "upsert">("fail");
  const [errorMode, setErrorMode] = useState<"fail_fast" | "continue">("continue");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<LexiconVoiceImportResult | null>(null);
  const [activeJobs, setActiveJobs] = useState<LexiconJob[]>([]);
  const [recentJobs, setRecentJobs] = useState<LexiconJob[]>([]);
  const [showAllRecentJobs, setShowAllRecentJobs] = useState(false);
  const [loading, setLoading] = useState(false);
  const [cancelingJobIds, setCancelingJobIds] = useState<string[]>([]);

  const loadRecentJobs = useCallback(async () => {
    try {
      const nextJobs = await listLexiconJobs({ jobType: "voice_import_db", limit: RECENT_JOB_FETCH_LIMIT });
      setRecentJobs(nextJobs);
      setActiveJobs((currentJobs) => {
        const mergedJobs = nextJobs
          .filter((job) => isLexiconJobActive(job))
          .reduce<LexiconJob[]>((acc, job) => upsertLexiconJob(acc, job), currentJobs);
        const nextActiveJobs = sortJobsByCreatedAtDesc(mergedJobs.filter((job) => isLexiconJobActive(job)));
        writeLexiconActiveJobIds(
          ACTIVE_JOB_STORAGE_KEY,
          nextActiveJobs.map((job) => job.id),
        );
        return nextActiveJobs;
      });
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
    if (typeof window === "undefined") {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    setInputPath(params.get("inputPath") ?? "");
    setLanguage(params.get("language") || "en");

    const persistedJobIds = readLexiconActiveJobIds(ACTIVE_JOB_STORAGE_KEY);
    if (!persistedJobIds.length) {
      return;
    }

    void Promise.allSettled(persistedJobIds.map((jobId) => getLexiconJob(jobId)))
      .then((results) => {
        const nextActiveJobs: LexiconJob[] = [];
        let latestFailureMessage: string | null = null;

        results.forEach((resultState) => {
          if (resultState.status !== "fulfilled") {
            return;
          }
          const nextJob = resultState.value;
          if (isLexiconJobActive(nextJob)) {
            nextActiveJobs.push(nextJob);
            return;
          }
          if (nextJob.status === "failed") {
            latestFailureMessage = nextJob.error_message || latestFailureMessage;
          }
        });

        writeLexiconActiveJobIds(
          ACTIVE_JOB_STORAGE_KEY,
          nextActiveJobs.map((job) => job.id),
        );
        setActiveJobs(sortJobsByCreatedAtDesc(nextActiveJobs));
        if (latestFailureMessage) {
          setMessage(latestFailureMessage);
        }
      })
      .catch(() => {
        writeLexiconActiveJobIds(ACTIVE_JOB_STORAGE_KEY, []);
      });
  }, []);

  useEffect(() => {
    void loadRecentJobs();
  }, [loadRecentJobs]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const timer = window.setInterval(() => {
      void loadRecentJobs();
    }, 2000);
    return () => window.clearInterval(timer);
  }, [loadRecentJobs]);

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const trackedJobs = activeJobs.filter((job) => isLexiconJobActive(job));
    if (!trackedJobs.length) {
      return;
    }

    const timer = window.setInterval(() => {
      void Promise.allSettled(trackedJobs.map((job) => getLexiconJob(job.id)))
        .then((results) => {
          const nextActiveJobs: LexiconJob[] = [];
          let latestMessage: string | null = null;
          let shouldReloadRecentJobs = false;

          results.forEach((resultState, index) => {
            const currentJob = trackedJobs[index];
            if (!currentJob) {
              return;
            }
            if (resultState.status !== "fulfilled") {
              nextActiveJobs.push(currentJob);
              latestMessage = resultState.reason instanceof Error
                ? resultState.reason.message
                : "Failed to refresh voice import progress.";
              return;
            }
            const nextJob = resultState.value;
            if (isLexiconJobActive(nextJob)) {
              nextActiveJobs.push(nextJob);
              return;
            }
            shouldReloadRecentJobs = true;
            removeLexiconActiveJobId(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
            latestMessage = nextJob.status === "completed"
              ? "Voice import completed."
              : nextJob.error_message || "Voice import failed.";
          });

          writeLexiconActiveJobIds(
            ACTIVE_JOB_STORAGE_KEY,
            nextActiveJobs.map((job) => job.id),
          );
          setActiveJobs(sortJobsByCreatedAtDesc(nextActiveJobs));
          if (latestMessage) {
            setMessage(latestMessage);
          }
          if (shouldReloadRecentJobs) {
            void loadRecentJobs();
          }
        });
    }, 500);

    return () => window.clearInterval(timer);
  }, [activeJobs, loadRecentJobs]);

  const canRun = inputPath.trim().length > 0;
  const resultSummaryEntries = useMemo(
    () => Object.entries(result?.import_summary ?? {}),
    [result?.import_summary],
  );
  const completedRecentJobs = useMemo(
    () => recentJobs.filter((job) => !isLexiconJobActive(job)),
    [recentJobs],
  );
  const visibleRecentJobs = useMemo(
    () => (showAllRecentJobs ? completedRecentJobs : completedRecentJobs.slice(0, INLINE_RECENT_JOB_LIMIT)),
    [completedRecentJobs, showAllRecentJobs],
  );

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
        return;
      }
      const nextJob = await createVoiceImportDbLexiconJob({
        ...payload,
        voiceGroupChunkSize,
      });
      setActiveJobs((currentJobs) => sortJobsByCreatedAtDesc(upsertLexiconJob(currentJobs, nextJob)));
      setResult(null);
      addLexiconActiveJobId(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
      setMessage("Voice import started. This page will reconnect if you return in the same browser session.");
      void loadRecentJobs();
    } catch (error) {
      setMessage(
        (mode === "run" ? getLexiconJobConflictMessage("voice import", error) : null)
          ?? (error instanceof Error ? error.message : "Voice import request failed."),
      );
    } finally {
      setLoading(false);
    }
  }, [canRun, conflictMode, errorMode, inputPath, language, loadRecentJobs, voiceGroupChunkSize]);

  const cancelJob = useCallback(async (jobId: string) => {
    setCancelingJobIds((current) => (current.includes(jobId) ? current : [...current, jobId]));
    try {
      const nextJob = await cancelLexiconJob(jobId);
      setActiveJobs((currentJobs) => sortJobsByCreatedAtDesc(upsertLexiconJob(currentJobs, nextJob)));
      if (!isLexiconJobActive(nextJob)) {
        removeLexiconActiveJobId(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
      }
      setMessage(nextJob.status === "cancel_requested" ? "Cancellation requested." : "Voice import cancelled.");
      void loadRecentJobs();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to cancel voice import job.");
    } finally {
      setCancelingJobIds((current) => current.filter((existingJobId) => existingJobId !== jobId));
    }
  }, [loadRecentJobs]);

  return (
    <div className="space-y-6" data-testid="lexicon-voice-import-page">
      <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
        <h3 className="text-2xl font-semibold text-gray-900">Lexicon Voice Import</h3>
        <p className="mt-1 max-w-3xl text-sm text-gray-600">
          Dry run validates the voice manifest before any DB writes. Import runs the same validation first, then writes voice assets with the selected conflict and error modes.
        </p>
        <div className="mt-4">
          <LexiconSectionNav
            testId="lexicon-voice-import-section-nav"
            items={[
              { label: "Storage", href: "/lexicon/voice-storage" },
              { label: "Voice Runs", href: "/lexicon/voice-runs" },
              { label: "Voice DB Import", href: "/lexicon/voice-import", active: true },
            ]}
          />
        </div>

        <div className="mt-6 space-y-4" data-testid="lexicon-voice-import-form-grid">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_10rem]">
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
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,14rem)_minmax(0,16rem)_minmax(0,14rem)_auto]">
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
            <label className="grid gap-1 text-sm text-gray-700">
              <span className="font-medium">Chunk size (lexical groups)</span>
              <input
                data-testid="lexicon-voice-import-chunk-size"
                type="number"
                min={1}
                step={1}
                value={voiceGroupChunkSize}
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10);
                  setVoiceGroupChunkSize(Number.isFinite(parsed) && parsed > 0 ? parsed : 100);
                }}
                className="rounded-md border border-gray-300 px-3 py-2 text-sm"
              />
            </label>
            <div className="flex flex-wrap items-end gap-3">
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
        </div>
        {message ? <p className="mt-4 text-sm text-slate-700">{message}</p> : null}
      </section>

      {activeJobs.length > 0 ? (
        <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm" data-testid="lexicon-voice-import-progress">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.16em] text-gray-500">Import progress</p>
              <p className="mt-1 text-sm text-gray-600">
                Showing {activeJobs.length} queued or running voice import job{activeJobs.length === 1 ? "" : "s"}.
              </p>
            </div>
          </div>
          <div className="mt-3 space-y-3">
            {activeJobs.map((job) => {
              const progressSummary = job.progress_summary ?? null;
              const progressEstimate = progressEstimateForJob(job);
              const timingEntries = timingEntriesForJob(job);
              return (
                <div key={job.id} data-testid="lexicon-voice-import-active-job" className="rounded-lg border border-gray-200 bg-white p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <p className="text-base text-gray-700">Current entry: {currentEntryLabel(job)}</p>
                      <p className="text-base text-gray-600">Input: {String(job.request_payload.input_path ?? "—")}</p>
                      {job.error_message ? <p className="mt-1 text-base text-rose-700">{job.error_message}</p> : null}
                    </div>
                    <span className={`rounded-full border px-3 py-1 text-sm font-medium ${statusBadgeClass(job.status)}`}>
                      {job.status} · {progressEstimate.overallPercent}%
                    </span>
                  </div>
                  <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-gray-100">
                    <div className="h-full bg-slate-900 transition-all" style={{ width: `${progressEstimate.overallPercent}%` }} />
                  </div>
                  {job.status === "queued" || job.status === "running" || job.status === "cancel_requested" ? (
                    <div className="mt-3">
                      <button
                        type="button"
                        data-testid="lexicon-voice-import-cancel-job"
                        onClick={() => void cancelJob(job.id)}
                        disabled={job.status === "cancel_requested" || cancelingJobIds.includes(job.id)}
                        className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 disabled:opacity-60"
                      >
                        {job.status === "cancel_requested" || cancelingJobIds.includes(job.id) ? "Cancelling..." : "Cancel"}
                      </button>
                    </div>
                  ) : null}
                  <div className="mt-3 flex flex-wrap gap-2 text-base text-gray-700">
                    <span className="rounded-full border border-gray-200 px-2 py-1">Conflict {modeValueForJob(job, "conflict_mode")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Error {modeValueForJob(job, "error_mode")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Chunk {jobConfigValue(job, "voice_group_chunk_size")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Progress flush {jobConfigValue(job, "progress_commit_callback_interval")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Overall {progressEstimate.overallPercent}%</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Validate {progressEstimate.validationPercent}%</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Import {progressEstimate.importPercent}%</span>
                    {progressEstimate.totalEtaMs !== null ? (
                      <span className="rounded-full border border-gray-200 px-2 py-1">ETA {formatLexiconJobDuration(progressEstimate.totalEtaMs)}</span>
                    ) : null}
                    {progressEstimate.validationEtaMs !== null ? (
                      <span className="rounded-full border border-gray-200 px-2 py-1">Validate ETA {formatLexiconJobDuration(progressEstimate.validationEtaMs)}</span>
                    ) : null}
                    {progressEstimate.importEtaMs !== null ? (
                      <span className="rounded-full border border-gray-200 px-2 py-1">Import ETA {formatLexiconJobDuration(progressEstimate.importEtaMs)}</span>
                    ) : null}
                    <span className="rounded-full border border-gray-200 px-2 py-1">To validate {progressSummary?.to_validate ?? 0}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Validated {progressSummary?.validated ?? 0}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">To import {progressSummary?.to_import ?? 0}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Imported {progressSummary?.imported ?? 0}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Skipped {skippedForJob(job)}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Failed {failedForJob(job)}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Total {progressSummary?.total ?? job.progress_total}</span>
                  </div>
                  {timingEntries.length > 0 ? (
                    <div className="mt-3 flex flex-wrap gap-2 text-base text-gray-700">
                      {timingEntries.map((timingEntry) => (
                        <span key={timingEntry.label} className="rounded-full border border-gray-200 px-2 py-1">
                          {timingEntry.label} {timingEntry.value}
                        </span>
                      ))}
                    </div>
                  ) : null}
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
                </div>
              );
            })}
          </div>
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
              {completedRecentJobs.length > INLINE_RECENT_JOB_LIMIT && !showAllRecentJobs
                ? `Showing the latest ${INLINE_RECENT_JOB_LIMIT} of ${completedRecentJobs.length} jobs.`
                : `Showing ${visibleRecentJobs.length} job${visibleRecentJobs.length === 1 ? "" : "s"}.`}
            </p>
          </div>
          {completedRecentJobs.length > INLINE_RECENT_JOB_LIMIT ? (
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
          {visibleRecentJobs.length ? visibleRecentJobs.map((recentJob) => {
            const timingEntries = timingEntriesForJob(recentJob);
            return (
              <div key={recentJob.id} className={`rounded-md border p-4 ${recentJobCardClass(recentJob)}`}>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-gray-900">{String(recentJob.request_payload.input_path ?? recentJob.target_key)}</p>
                    <p className="mt-1 text-xs text-gray-500">{new Date(recentJob.created_at).toLocaleString()}</p>
                  </div>
                  <span className={`rounded-full border px-3 py-1 text-xs font-medium ${statusBadgeClass(recentJob.status)}`}>
                    {recentJob.status}
                  </span>
                </div>
                <p className="mt-2 text-sm text-gray-600">Current entry: {currentEntryLabel(recentJob)}</p>
                {recentJob.error_message ? <p className="mt-2 text-sm text-rose-700">{recentJob.error_message}</p> : null}
                <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-700">
                  <span className="rounded-full border border-gray-200 px-2 py-1">Conflict {modeValueForJob(recentJob, "conflict_mode")}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Error {modeValueForJob(recentJob, "error_mode")}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Chunk {jobConfigValue(recentJob, "voice_group_chunk_size")}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Progress flush {jobConfigValue(recentJob, "progress_commit_callback_interval")}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Done {recentJob.progress_completed}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Total {recentJob.progress_total}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Skipped {skippedForJob(recentJob)}</span>
                  <span className="rounded-full border border-gray-200 px-2 py-1">Failed {failedForJob(recentJob)}</span>
                </div>
                {timingEntries.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-2 text-xs text-gray-700">
                    {timingEntries.map((timingEntry) => (
                      <span key={timingEntry.label} className="rounded-full border border-gray-200 px-2 py-1">
                        {timingEntry.label} {timingEntry.value}
                      </span>
                    ))}
                  </div>
                ) : null}
              </div>
            );
          }) : <p className="text-sm text-gray-500">No completed voice import jobs yet.</p>}
        </div>
      </section>
    </div>
  );
}
