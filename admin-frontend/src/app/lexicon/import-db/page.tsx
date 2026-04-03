"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { PathGuidanceCard } from "@/components/lexicon/path-guidance-card";
import { LexiconSectionNav } from "@/components/lexicon/section-nav";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";
import {
  addLexiconActiveJobId,
  cancelLexiconJob,
  createImportDbLexiconJob,
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
import {
  dryRunLexiconImport,
  type LexiconImportResult,
} from "@/lib/lexicon-imports-client";

const ACTIVE_JOB_STORAGE_KEY = "lexicon-import-db-active-jobs";
const INLINE_RECENT_JOB_LIMIT = 6;
const RECENT_JOB_FETCH_LIMIT = 24;

type WorkflowContext = {
  hasContext: boolean;
  inputPath: string;
  sourceReference: string;
  language: string;
};

const EMPTY_WORKFLOW_CONTEXT: WorkflowContext = {
  hasContext: false,
  inputPath: "",
  sourceReference: "",
  language: "en",
};

const sortJobsByCreatedAtDesc = (jobs: LexiconJob[]): LexiconJob[] =>
  [...jobs].sort((leftJob, rightJob) =>
    new Date(rightJob.created_at).getTime() - new Date(leftJob.created_at).getTime(),
  );

const statusBadgeClass = (status: LexiconJob["status"]): string => {
  if (status === "cancel_requested") return "border-amber-200 bg-amber-50 text-amber-700";
  if (status === "cancelled") return "border-slate-200 bg-slate-100 text-slate-600";
  if (status === "failed") return "border-rose-200 bg-rose-50 text-rose-700";
  if (status === "completed") return "border-emerald-200 bg-emerald-50 text-emerald-700";
  if (status === "running") return "border-sky-200 bg-sky-50 text-sky-700";
  return "border-slate-200 bg-slate-50 text-slate-600";
};

const currentEntryLabel = (targetJob: LexiconJob): string => {
  const phase = String(targetJob.progress_summary?.phase ?? "").toLowerCase();
  if (targetJob.status === "completed") {
    return "Completed";
  }
  if (targetJob.status === "cancelled") {
    return "Cancelled";
  }
  if (targetJob.status === "cancel_requested") {
    return targetJob.progress_current_label ?? "Cancellation requested...";
  }
  if (targetJob.status === "failed") {
    if (targetJob.progress_current_label) {
      return targetJob.progress_current_label;
    }
    if (targetJob.progress_completed === 0) {
      return "Failed before first row";
    }
    return targetJob.progress_total > 0
      ? `Failed after ${targetJob.progress_completed}/${targetJob.progress_total}`
      : "Failed";
  }
  if (phase === "finalizing") {
    return targetJob.progress_current_label ?? "Finalizing import...";
  }
  if (phase === "completed") {
    return "Completed";
  }
  return targetJob.progress_current_label ?? "Waiting for first row...";
};

const skippedForJob = (targetJob: LexiconJob): number => {
  if (targetJob.progress_summary) {
    return Number(targetJob.progress_summary.skipped ?? 0);
  }
  const payload = (targetJob.result_payload ?? {}) as Record<string, unknown>;
  return Number(payload.skipped_words ?? 0)
    + Number(payload.skipped_phrases ?? 0)
    + Number(payload.skipped_reference_entries ?? 0);
};

const failedForJob = (targetJob: LexiconJob): number => {
  if (targetJob.progress_summary) {
    return Number(targetJob.progress_summary.failed ?? 0);
  }
  const payload = (targetJob.result_payload ?? {}) as Record<string, unknown>;
  return Number(payload.failed_rows ?? 0);
};

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

const progressPercentForJob = (targetJob: LexiconJob): number => (
  targetJob.progress_total > 0
    ? Math.round((targetJob.progress_completed / targetJob.progress_total) * 100)
    : 0
);

const jobConfigValue = (targetJob: LexiconJob, key: string): string =>
  String(targetJob.request_payload?.[key] ?? "—");

const performanceMetricsForJob = (targetJob: LexiconJob): Record<string, unknown> => {
  const metrics = targetJob.request_payload?.performance_metrics;
  if (typeof metrics === "object" && metrics !== null) {
    return metrics as Record<string, unknown>;
  }
  return {};
};

const timingEntriesForJob = (targetJob: LexiconJob): Array<{ label: string; value: string }> => {
  const timing = getLexiconJobProgressTiming(targetJob);
  if (!timing) {
    return [];
  }
  return [
    { label: "Elapsed", value: formatLexiconJobDuration(timing.elapsed_ms) },
    { label: "Validation", value: formatLexiconJobDuration(timing.validation_elapsed_ms) },
    { label: "Import", value: formatLexiconJobDuration(timing.import_elapsed_ms) },
    { label: "Rebuild", value: formatLexiconJobDuration(timing.finalization_elapsed_ms) },
    { label: "Overhead", value: formatLexiconJobDuration(timing.orchestration_elapsed_ms) },
    { label: "Queue wait", value: formatLexiconJobDuration(timing.queue_wait_ms) },
  ].filter((entry): entry is { label: string; value: string } => Boolean(entry.value));
};

type ProgressEstimate = {
  overallPercent: number;
  validationPercent: number;
  importPercent: number;
  finalizePercent: number;
  validationEtaMs: number | null;
  importEtaMs: number | null;
  finalizeEtaMs: number | null;
  totalEtaMs: number | null;
};

const progressEstimateForJob = (targetJob: LexiconJob): ProgressEstimate => {
  const summary = targetJob.progress_summary ?? null;
  const phase = String(summary?.phase ?? "").toLowerCase();
  const phaseStartedAtMs = Number(summary?.phase_started_at_ms ?? 0);
  const total = Number(summary?.total ?? targetJob.progress_total ?? 0);
  const validated = Number(summary?.validated ?? targetJob.progress_completed ?? 0);
  const toValidate = Number(summary?.to_validate ?? Math.max(total - validated, 0));
  const imported = Number(summary?.imported ?? targetJob.progress_completed ?? 0);
  const skipped = Number(summary?.skipped ?? 0);
  const failed = Number(summary?.failed ?? 0);
  const toImport = Number(summary?.to_import ?? Math.max(total - imported - skipped - failed, 0));
  const processedImportRows = Math.max(total - toImport, 0);
  const timing = getLexiconJobProgressTiming(targetJob);
  const validationElapsed = Number(timing?.validation_elapsed_ms ?? 0);
  const importElapsed = Number(timing?.import_elapsed_ms ?? 0);

  const validationEtaMs = (
    toValidate > 0 && validated > 0 && validationElapsed > 0
      ? Math.round((validationElapsed / validated) * toValidate)
      : null
  );
  const importEtaMs = (
    toImport > 0 && processedImportRows > 0 && importElapsed > 0
      ? Math.round((importElapsed / processedImportRows) * toImport)
      : null
  );

  const validationPercent = total > 0 ? Math.round((validated / total) * 100) : 0;
  const importPercent = total > 0 ? Math.round((processedImportRows / total) * 100) : 0;
  const phaseElapsedMs = (
    phaseStartedAtMs > 0
      ? Math.max(Date.now() - phaseStartedAtMs, 0)
      : 0
  );
  const finalizeEstimateMs = Math.max(
    10_000,
    Math.min(
      120_000,
      Math.round(importElapsed * 0.15),
    ),
  );
  const finalizePercent = (
    phase === "completed" || targetJob.status === "completed"
      ? 100
      : phase === "finalizing"
        ? Math.min(Math.round((phaseElapsedMs / finalizeEstimateMs) * 100), 99)
        : 0
  );
  const finalizeEtaMs = (
    phase === "finalizing"
      ? Math.max(finalizeEstimateMs - phaseElapsedMs, 0)
      : null
  );
  const validationWeight = 0.1;
  const importWeight = 0.85;
  const finalizeWeight = 0.05;
  const weightedOverall = (
    (validationPercent / 100) * validationWeight
    + (importPercent / 100) * importWeight
    + (finalizePercent / 100) * finalizeWeight
  ) * 100;
  let overallPercent = Math.round(weightedOverall);
  if (targetJob.status === "completed" || phase === "completed") {
    overallPercent = 100;
  } else if (isLexiconJobActive(targetJob)) {
    overallPercent = Math.min(overallPercent, 99);
  }
  const totalEtaMs = (
    validationEtaMs !== null || importEtaMs !== null || finalizeEtaMs !== null
      ? (validationEtaMs ?? 0) + (importEtaMs ?? 0) + (finalizeEtaMs ?? 0)
      : null
  );

  return {
    overallPercent,
    validationPercent,
    importPercent,
    finalizePercent,
    validationEtaMs,
    importEtaMs,
    finalizeEtaMs,
    totalEtaMs,
  };
};

export default function LexiconImportDbPage() {
  const [inputPath, setInputPath] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [language, setLanguage] = useState("en");
  const [importRowChunkSize, setImportRowChunkSize] = useState(250);
  const [importRowCommitSize, setImportRowCommitSize] = useState(250);
  const [importExecutionMode, setImportExecutionMode] = useState<"continuation" | "single_task">("continuation");
  const [conflictMode, setConflictMode] = useState<"fail" | "skip" | "upsert">("fail");
  const [errorMode, setErrorMode] = useState<"fail_fast" | "continue">("continue");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<LexiconImportResult | null>(null);
  const [activeJobs, setActiveJobs] = useState<LexiconJob[]>([]);
  const [recentJobs, setRecentJobs] = useState<LexiconJob[]>([]);
  const [showAllRecentJobs, setShowAllRecentJobs] = useState(false);
  const [loading, setLoading] = useState(false);
  const [cancelingJobIds, setCancelingJobIds] = useState<string[]>([]);
  const [workflowContext, setWorkflowContext] = useState<WorkflowContext>(EMPTY_WORKFLOW_CONTEXT);

  const loadRecentJobs = useCallback(async () => {
    try {
      const nextJobs = await listLexiconJobs({ jobType: "import_db", limit: RECENT_JOB_FETCH_LIMIT });
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
      // keep the page usable even if the recent-jobs list fails
    }
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

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/import-db");
      return;
    }
    if (typeof window === "undefined") {
      return;
    }

    const params = new URLSearchParams(window.location.search);
    const nextInputPath = params.get("inputPath") ?? "";
    const nextSourceReference = params.get("sourceReference") ?? "";
    const nextLanguage = params.get("language") || "en";

    setInputPath(nextInputPath);
    setSourceReference(nextSourceReference);
    setLanguage(nextLanguage);
    setWorkflowContext({
      hasContext: Boolean(nextInputPath || nextSourceReference || nextLanguage !== "en"),
      inputPath: nextInputPath,
      sourceReference: nextSourceReference,
      language: nextLanguage,
    });

    const persistedJobIds = readLexiconActiveJobIds(ACTIVE_JOB_STORAGE_KEY);
    if (!persistedJobIds.length) {
      return;
    }

    void Promise.allSettled(persistedJobIds.map((jobId) => getLexiconJob(jobId)))
      .then((results) => {
        const nextActiveJobs: LexiconJob[] = [];
        let latestCompletedJob: LexiconJob | null = null;
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
          if (nextJob.status === "completed") {
            latestCompletedJob = nextJob;
            return;
          }
          latestFailureMessage = nextJob.error_message || latestFailureMessage;
        });

        writeLexiconActiveJobIds(
          ACTIVE_JOB_STORAGE_KEY,
          nextActiveJobs.map((job) => job.id),
        );
        setActiveJobs(sortJobsByCreatedAtDesc(nextActiveJobs));
        if (latestCompletedJob) {
          setResult(importResultFromJob(latestCompletedJob));
        }
        if (latestFailureMessage) {
          setMessage(latestFailureMessage);
        }
      })
      .catch(() => {
        writeLexiconActiveJobIds(ACTIVE_JOB_STORAGE_KEY, []);
      });
  }, [importResultFromJob]);

  useEffect(() => {
    void loadRecentJobs();
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
          let latestCompletedJob: LexiconJob | null = null;
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
                : "Failed to refresh import progress.";
              return;
            }
            const nextJob = resultState.value;
            if (isLexiconJobActive(nextJob)) {
              nextActiveJobs.push(nextJob);
              return;
            }
            shouldReloadRecentJobs = true;
            removeLexiconActiveJobId(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
            if (nextJob.status === "completed") {
              latestCompletedJob = nextJob;
            } else {
              latestMessage = nextJob.error_message || "Import failed.";
            }
          });

          writeLexiconActiveJobIds(
            ACTIVE_JOB_STORAGE_KEY,
            nextActiveJobs.map((job) => job.id),
          );
          setActiveJobs(sortJobsByCreatedAtDesc(nextActiveJobs));
          if (latestCompletedJob) {
            setResult(importResultFromJob(latestCompletedJob));
            setMessage("Import completed.");
          } else if (latestMessage) {
            setMessage(latestMessage);
          }
          if (shouldReloadRecentJobs) {
            void loadRecentJobs();
          }
        });
    }, 500);

    return () => window.clearInterval(timer);
  }, [activeJobs, importResultFromJob, loadRecentJobs]);

  const canRun = inputPath.trim().length > 0;
  const importSummaryEntries = useMemo(
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
        importExecutionMode,
        importRowChunkSize,
        importRowCommitSize,
      };
      if (mode === "dry-run") {
        const nextResult = await dryRunLexiconImport(payload);
        setResult(nextResult);
        setMessage("Import dry-run complete.");
        return;
      }
      const nextJob = await createImportDbLexiconJob(payload);
      setActiveJobs((currentJobs) => sortJobsByCreatedAtDesc(upsertLexiconJob(currentJobs, nextJob)));
      setResult(null);
      addLexiconActiveJobId(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
      void loadRecentJobs();
      setMessage("Import started. The queued job keeps running if you browse away from this page.");
    } catch (error) {
      setMessage(
        (mode === "run" ? getLexiconJobConflictMessage("import", error) : null)
          ?? (error instanceof Error ? error.message : "Import request failed."),
      );
    } finally {
      setLoading(false);
    }
  }, [canRun, conflictMode, errorMode, importExecutionMode, importRowChunkSize, importRowCommitSize, inputPath, language, loadRecentJobs, sourceReference]);

  const cancelJob = useCallback(async (jobId: string) => {
    setCancelingJobIds((current) => (current.includes(jobId) ? current : [...current, jobId]));
    try {
      const nextJob = await cancelLexiconJob(jobId);
      setActiveJobs((currentJobs) => sortJobsByCreatedAtDesc(upsertLexiconJob(currentJobs, nextJob)));
      if (!isLexiconJobActive(nextJob)) {
        removeLexiconActiveJobId(ACTIVE_JOB_STORAGE_KEY, nextJob.id);
      }
      setMessage(nextJob.status === "cancel_requested" ? "Cancellation requested." : "Import cancelled.");
      void loadRecentJobs();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Failed to cancel import job.");
    } finally {
      setCancelingJobIds((current) => current.filter((existingJobId) => existingJobId !== jobId));
    }
  }, [loadRecentJobs]);

  return (
    <div className="space-y-6" data-testid="lexicon-import-db-page">
      {workflowContext.hasContext ? (
        <section className="rounded-lg border border-gray-200 bg-slate-50 p-4 text-sm text-slate-800" data-testid="lexicon-import-db-context">
          <p className="font-medium">Workflow context</p>
          <p className="mt-1">Input path: {workflowContext.inputPath || "—"}</p>
          <p>Source reference: {workflowContext.sourceReference || "—"}</p>
          <p>Language: {workflowContext.language || "—"}</p>
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
              Imports run in the backend. If you browse away and come back in the same browser session, this page reconnects to queued and running import jobs.
            </p>
          </div>
        </div>
        <div className="mt-4">
          <LexiconSectionNav
            testId="lexicon-db-section-nav"
            items={[
              { label: "Enrichment Import", href: "/lexicon/import-db", active: true },
              { label: "DB Inspector", href: "/lexicon/db-inspector" },
            ]}
          />
        </div>

        <PathGuidanceCard
          className="mt-4"
          modeNote="Import DB should normally use reviewed/approved.jsonl, not the raw compiled artifact, unless you are intentionally bypassing review."
        />

        <div className="mt-6 space-y-4" data-testid="lexicon-import-db-form-grid">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)_8rem]">
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
                className="w-full max-w-[8rem] rounded-md border border-gray-300 px-2 py-2 text-sm"
              />
            </label>
          </div>
          <div className="grid gap-4 lg:grid-cols-[minmax(0,10rem)_minmax(0,11rem)_minmax(0,11rem)_minmax(0,8rem)_minmax(0,8rem)_auto]">
            <label className="grid gap-1 text-sm text-gray-700">
              <span className="font-medium">Conflict handling</span>
              <select
                value={conflictMode}
                onChange={(event) => setConflictMode(event.target.value as "fail" | "skip" | "upsert")}
                className="w-full max-w-[10rem] rounded-md border border-gray-300 px-2.5 py-2 text-sm"
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
                className="w-full max-w-[11rem] rounded-md border border-gray-300 px-2.5 py-2 text-sm"
                data-testid="lexicon-import-db-error-mode"
              >
                <option value="continue">Continue and report failures</option>
                <option value="fail_fast">Stop on first error</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm text-gray-700">
              <span className="font-medium">Execution mode</span>
              <select
                value={importExecutionMode}
                onChange={(event) => setImportExecutionMode(event.target.value as "continuation" | "single_task")}
                className="w-full max-w-[11rem] rounded-md border border-gray-300 px-2.5 py-2 text-sm"
                data-testid="lexicon-import-db-execution-mode"
              >
                <option value="continuation">Continuation slices</option>
                <option value="single_task">Single task</option>
              </select>
            </label>
            <label className="grid gap-1 text-sm text-gray-700">
              <span className="font-medium">Chunk size (rows)</span>
              <input
                type="number"
                min={1}
                step={1}
                value={importRowChunkSize}
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10);
                  const nextChunk = Number.isFinite(parsed) && parsed > 0 ? parsed : 250;
                  setImportRowChunkSize(nextChunk);
                  setImportRowCommitSize((current) => Math.min(current, Math.max(nextChunk, 1)));
                }}
                className="w-full max-w-[8rem] rounded-md border border-gray-300 px-2 py-2 text-sm"
                data-testid="lexicon-import-db-chunk-size"
              />
            </label>
            <label className="grid gap-1 text-sm text-gray-700">
              <span className="font-medium">Commit size (rows)</span>
              <input
                type="number"
                min={1}
                step={1}
                value={importRowCommitSize}
                onChange={(event) => {
                  const parsed = Number.parseInt(event.target.value, 10);
                  const nextValue = Number.isFinite(parsed) && parsed > 0 ? parsed : 250;
                  setImportRowCommitSize(Math.min(nextValue, Math.max(importRowChunkSize, 1)));
                }}
                className="w-full max-w-[8rem] rounded-md border border-gray-300 px-2 py-2 text-sm"
                data-testid="lexicon-import-db-commit-size"
              />
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
                {loading ? "Working..." : "Import"}
              </button>
            </div>
          </div>
        </div>

        {message ? <p className="mt-4 text-sm text-gray-700">{message}</p> : null}
      </section>

      {activeJobs.length > 0 ? (
        <section className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm" data-testid="lexicon-import-db-progress">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Import progress</h4>
              <p className="mt-1 text-sm text-gray-600">
                Showing {activeJobs.length} queued or running import job{activeJobs.length === 1 ? "" : "s"}.
              </p>
            </div>
          </div>
          <div className="mt-3 space-y-3">
            {activeJobs.map((job) => {
              const progressSummary = job.progress_summary ?? null;
              const progressEstimate = progressEstimateForJob(job);
              const timingEntries = timingEntriesForJob(job);
              const perfMetrics = performanceMetricsForJob(job);
              return (
                <div
                  key={job.id}
                  data-testid="lexicon-import-db-active-job"
                  className={`rounded-lg border bg-white p-4 ${job.status === "failed" ? "border-rose-200" : job.status === "completed" ? "border-emerald-200" : "border-gray-200"}`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-base text-gray-700">
                        Status: <span className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${statusBadgeClass(job.status)}`}>{job.status}</span>
                      </p>
                      <p className="mt-1 text-base text-gray-700">
                        Current entry: <span className="font-medium">{currentEntryLabel(job)}</span>
                      </p>
                      <p className="mt-1 text-base text-gray-600">
                        Input: <span className="font-medium">{String(job.request_payload.input_path ?? "") || "—"}</span>
                      </p>
                      {job.error_message ? (
                        <p className="mt-1 text-base text-rose-700">{job.error_message}</p>
                      ) : null}
                    </div>
                    <span className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1 text-xs text-slate-600">
                      {progressEstimate.overallPercent}%
                    </span>
                  </div>
                  {job.status === "queued" || job.status === "running" || job.status === "cancel_requested" ? (
                    <div className="mt-3">
                      <button
                        type="button"
                        data-testid="lexicon-import-db-cancel-job"
                        onClick={() => void cancelJob(job.id)}
                        disabled={job.status === "cancel_requested" || cancelingJobIds.includes(job.id)}
                        className="rounded-md border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-800 disabled:opacity-60"
                      >
                        {job.status === "cancel_requested" || cancelingJobIds.includes(job.id) ? "Cancelling..." : "Cancel"}
                      </button>
                    </div>
                  ) : null}
                  <div className="mt-3 h-2.5 overflow-hidden rounded-full bg-slate-100">
                    <div
                      className="h-full rounded-full bg-slate-900 transition-[width]"
                      style={{ width: `${progressEstimate.overallPercent}%` }}
                    />
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2 text-base text-gray-700">
                    <span className="rounded-full border border-gray-200 px-2 py-1">Conflict {String(job.request_payload.conflict_mode ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Error {String(job.request_payload.error_mode ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Mode {String(job.request_payload.import_execution_mode ?? "continuation")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Chunk {jobConfigValue(job, "import_row_chunk_size")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Commit {jobConfigValue(job, "import_row_commit_size")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Progress flush {jobConfigValue(job, "progress_commit_callback_interval")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Progress updates {String(perfMetrics.progress_update_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">DB flushes {String(perfMetrics.progress_flush_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Import callbacks {String(perfMetrics.import_callback_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Validate callbacks {String(perfMetrics.preflight_callback_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Cancel checks {String(perfMetrics.cancel_query_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Cancel skipped {String(perfMetrics.cancel_skip_count ?? "—")}</span>
                    {perfMetrics.import_callback_elapsed_ms !== undefined ? (
                      <span className="rounded-full border border-gray-200 px-2 py-1">
                        Import callback CPU {formatLexiconJobDuration(Number(perfMetrics.import_callback_elapsed_ms))}
                      </span>
                    ) : null}
                    {perfMetrics.preflight_callback_elapsed_ms !== undefined ? (
                      <span className="rounded-full border border-gray-200 px-2 py-1">
                        Validate callback CPU {formatLexiconJobDuration(Number(perfMetrics.preflight_callback_elapsed_ms))}
                      </span>
                    ) : null}
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
                    <span className="rounded-full border border-gray-200 px-2 py-1">To validate {progressSummary?.to_validate ?? Math.max(job.progress_total - job.progress_completed, 0)}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Validated {progressSummary?.validated ?? job.progress_completed}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">To import {progressSummary?.to_import ?? Math.max(job.progress_total - job.progress_completed, 0)}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Imported {progressSummary?.imported ?? job.progress_completed}</span>
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

      {!activeJobs.length && currentResultSection ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          {currentResultSection}
        </section>
      ) : null}

      {completedRecentJobs.length > 0 ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" data-testid="lexicon-import-db-recent-jobs">
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Recent jobs</h4>
          <div className="mt-4 grid gap-3">
            {visibleRecentJobs.map((recentJob) => {
              const timingEntries = timingEntriesForJob(recentJob);
              const perfMetrics = performanceMetricsForJob(recentJob);
              return (
                <div
                  key={recentJob.id}
                  className={`rounded-md border p-4 ${recentJobCardClass(recentJob)}`}
                >
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
                    <span className="rounded-full border border-gray-200 px-2 py-1">Conflict {String(recentJob.request_payload.conflict_mode ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Error {String(recentJob.request_payload.error_mode ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Mode {String(recentJob.request_payload.import_execution_mode ?? "continuation")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Chunk {jobConfigValue(recentJob, "import_row_chunk_size")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Commit {jobConfigValue(recentJob, "import_row_commit_size")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Progress flush {jobConfigValue(recentJob, "progress_commit_callback_interval")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Progress updates {String(perfMetrics.progress_update_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">DB flushes {String(perfMetrics.progress_flush_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Import callbacks {String(perfMetrics.import_callback_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Validate callbacks {String(perfMetrics.preflight_callback_count ?? "—")}</span>
                    <span className="rounded-full border border-gray-200 px-2 py-1">Cancel checks {String(perfMetrics.cancel_query_count ?? "—")}</span>
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
            })}
          </div>
          {completedRecentJobs.length > INLINE_RECENT_JOB_LIMIT ? (
            <div className="mt-4">
              <button
                type="button"
                onClick={() => setShowAllRecentJobs((current) => !current)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
              >
                {showAllRecentJobs ? "Show fewer recent jobs" : "Show all recent jobs"}
              </button>
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
