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
  type LexiconJob,
} from "@/lib/lexicon-jobs-client";

const ACTIVE_JOB_STORAGE_KEY = "lexicon-import-db-active-job";

function searchParam(name: string): string {
  if (typeof window === "undefined") return "";
  return new URLSearchParams(window.location.search).get(name) ?? "";
}

export default function LexiconImportDbPage() {
  const [inputPath, setInputPath] = useState("");
  const [sourceReference, setSourceReference] = useState("");
  const [language, setLanguage] = useState("en");
  const [message, setMessage] = useState<string | null>(null);
  const [result, setResult] = useState<LexiconImportResult | null>(null);
  const [job, setJob] = useState<LexiconJob | null>(null);
  const [loading, setLoading] = useState(false);
  const autoStart = searchParam("autostart") === "1";

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
  const progressPercent = job && job.progress_total > 0
    ? Math.round((job.progress_completed / job.progress_total) * 100)
    : 0;
  const hasContext =
    Boolean(searchParam("inputPath") || searchParam("sourceReference") || searchParam("language")) ||
    inputPath.trim().length > 0 ||
    sourceReference.trim().length > 0 ||
    language.trim() !== "en";

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
        }
        setMessage("Import started. The queued job keeps running if you browse away from this page.");
      }
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Import request failed.");
    } finally {
      setLoading(false);
    }
  }, [canRun, inputPath, language, sourceReference]);

  useEffect(() => {
    if (!autoStart || !inputPath.trim() || loading || result) {
      return;
    }
    void execute("dry-run");
  }, [autoStart, execute, inputPath, loading, result]);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const activeJobId = window.localStorage.getItem(ACTIVE_JOB_STORAGE_KEY);
    if (!activeJobId) return;
    void getLexiconJob(activeJobId)
      .then((nextJob) => {
        setJob(nextJob);
        if (nextJob.status === "completed") {
          setResult(importResultFromJob(nextJob));
        }
      })
      .catch(() => {
        window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
      });
  }, [importResultFromJob]);

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
          } else if (nextJob.status === "failed") {
            setMessage(nextJob.error_message || "Import failed.");
            window.localStorage.removeItem(ACTIVE_JOB_STORAGE_KEY);
          }
        })
        .catch((error) => {
          setMessage(error instanceof Error ? error.message : "Failed to refresh import progress.");
        });
    }, 500);
    return () => window.clearInterval(timer);
  }, [importResultFromJob, job]);

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
              Dry-run or execute the final `import-db` write step using an approved compiled artifact.
            </p>
            <p className="mt-2 max-w-3xl text-sm text-gray-600">
              Use reviewed/approved.jsonl from Compiled Review export or JSONL Review materialize, not the raw words.enriched.jsonl artifact unless you are intentionally bypassing review.
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
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm" data-testid="lexicon-import-db-progress">
          <div className="flex items-start justify-between gap-4">
            <div>
              <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Import progress</h4>
              <p className="mt-1 text-sm text-gray-700">
                Status: <span className="font-medium">{job.status}</span>
              </p>
              <p className="mt-1 text-sm text-gray-700">
                Current entry: <span className="font-medium">{job.progress_current_label ?? "Waiting for first row..."}</span>
              </p>
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
          <div className="mt-4 grid gap-3 md:grid-cols-4">
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
              <p className="text-gray-500">Input</p>
              <p className="truncate font-medium" title={String(job.request_payload.input_path ?? "")}>
                {String(job.request_payload.input_path ?? "").split("/").pop() || "—"}
              </p>
            </div>
          </div>
        </section>
      ) : null}

      {result ? (
        <section className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm">
          <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">Result</h4>
          <div className="mt-4 grid gap-3 md:grid-cols-4">
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-rows">
              <p className="text-gray-500">Rows</p>
              <p className="font-medium">{result.row_summary.row_count}</p>
            </div>
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-words">
              <p className="text-gray-500">Words</p>
              <p className="font-medium">{result.row_summary.word_count}</p>
            </div>
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-phrases">
              <p className="text-gray-500">Phrases</p>
              <p className="font-medium">{result.row_summary.phrase_count}</p>
            </div>
            <div className="rounded border border-gray-200 p-3" data-testid="lexicon-import-db-summary-references">
              <p className="text-gray-500">References</p>
              <p className="font-medium">{result.row_summary.reference_count}</p>
            </div>
          </div>
          {importSummaryEntries.length > 0 ? (
            <div className="mt-4 grid gap-3 md:grid-cols-3">
              {importSummaryEntries.map(([key, value]) => (
                <div key={key} className="rounded border border-gray-200 p-3 text-sm">
                  <p className="text-gray-500">{key}</p>
                  <p className="font-medium">{value}</p>
                </div>
              ))}
            </div>
          ) : null}
        </section>
      ) : null}
    </div>
  );
}
