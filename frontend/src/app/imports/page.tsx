"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  bulkDeleteImportJobs,
  createWordListImport,
  deleteImportJob,
  getImportElapsedSeconds,
  getImportJob,
  getImportProgressPercent,
  listImportJobs,
  type ImportJob,
  isImportJobTerminal,
} from "@/lib/imports-client";
import { getImportDisplayTitle } from "@/lib/import-display";

const POLL_INTERVAL_MS = 2000;

function formatImportDuration(seconds: number | null): string {
  if (seconds == null) {
    return "In progress";
  }
  if (seconds < 1) {
    return "<1s";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  return `${minutes}m ${remainingSeconds}s`;
}

function formatProgressSummary(job: ImportJob): string {
  const total = job.progress_total > 0 ? job.progress_total : job.total_items;
  const completed = job.progress_total > 0 ? job.progress_completed : job.processed_items;
  if (total > 0) {
    return `${completed}/${total}`;
  }
  return "Pending";
}

function getAuthorLabel(job: ImportJob): string {
  return job.source_author?.trim() || "Unknown";
}

function getPublisherLabel(job: ImportJob): string {
  return job.source_publisher?.trim() || "Unknown";
}

function getPublishedLabel(job: ImportJob): string {
  return job.source_published_year != null ? String(job.source_published_year) : "Unknown";
}

function getIsbnLabel(job: ImportJob): string {
  return job.source_isbn?.trim() || "Unknown";
}

function compactMetricPairs(job: ImportJob): Array<[string, string]> {
  return [
    ["File", job.source_filename],
    ["Status", job.status],
    ["Source", job.from_cache ? "Cached" : "Fresh import"],
    ["Duration", formatImportDuration(getImportElapsedSeconds(job))],
    ["Extracted", String(job.total_entries_extracted)],
    ["Words", String(job.word_entry_count)],
    ["Phrases", String(job.phrase_entry_count)],
    ["Matched", String(job.matched_entry_count)],
  ];
}

export default function ImportsPage() {
  const router = useRouter();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [activeJobs, setActiveJobs] = useState<ImportJob[]>([]);
  const [historyJobs, setHistoryJobs] = useState<ImportJob[]>([]);
  const [selectedHistoryJobIds, setSelectedHistoryJobIds] = useState<Set<string>>(new Set());
  const [showHistory, setShowHistory] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeJobIds = useMemo(
    () => activeJobs.filter((job) => !isImportJobTerminal(job.status)).map((job) => job.id),
    [activeJobs],
  );
  const primaryActiveJob = activeJobs[0] ?? null;

  useEffect(() => {
    let active = true;

    Promise.all([listImportJobs(20, "active"), listImportJobs(20, "history")])
      .then(([loadedActiveJobs, loadedHistoryJobs]) => {
        if (active) {
          setActiveJobs(loadedActiveJobs);
          setHistoryJobs(loadedHistoryJobs);
        }
      })
      .catch(() => {
        if (active) {
          setError("Failed to load import jobs");
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (activeJobIds.length === 0) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      try {
        const updatedJobs = await Promise.all(activeJobIds.map((id) => getImportJob(id)));
        const finishedJobs = updatedJobs.filter((job) => isImportJobTerminal(job.status));
        setActiveJobs((current) =>
          current
            .map((job) => updatedJobs.find((updatedJob) => updatedJob.id === job.id) ?? job)
            .filter((job) => !isImportJobTerminal(job.status))
            .sort((a, b) => b.created_at.localeCompare(a.created_at)),
        );
        if (finishedJobs.length > 0) {
          setHistoryJobs((current) =>
            [...finishedJobs, ...current.filter((job) => !finishedJobs.some((finished) => finished.id === job.id))]
              .sort((a, b) => b.created_at.localeCompare(a.created_at)),
          );
        }
      } catch {
        setError("Failed to refresh import status");
      }
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeJobIds]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedFile) {
      setError("Please select an .epub file to import");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const job = await createWordListImport(selectedFile);
      if (isImportJobTerminal(job.status)) {
        setHistoryJobs((current) => [job, ...current.filter((existing) => existing.id !== job.id)]);
      } else {
        setActiveJobs((current) => [job, ...current.filter((existing) => existing.id !== job.id)]);
      }
      setSelectedFile(null);
      const input = document.getElementById("imports-upload-input") as HTMLInputElement | null;
      if (input) {
        input.value = "";
      }
      router.push(`/imports/${job.id}`);
    } catch {
      setError("Import failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const toggleHistorySelection = (jobId: string) => {
    setSelectedHistoryJobIds((current) => {
      const next = new Set(current);
      if (next.has(jobId)) {
        next.delete(jobId);
      } else {
        next.add(jobId);
      }
      return next;
    });
  };

  const selectAllHistory = () => {
    setSelectedHistoryJobIds(new Set(historyJobs.map((job) => job.id)));
  };

  const clearHistorySelection = () => {
    setSelectedHistoryJobIds(new Set());
  };

  const handleDeleteHistoryJob = async (jobId: string) => {
    if (!window.confirm("Delete this import job from your history?")) {
      return;
    }
    try {
      await deleteImportJob(jobId);
      setHistoryJobs((current) => current.filter((job) => job.id !== jobId));
      setSelectedHistoryJobIds((current) => {
        const next = new Set(current);
        next.delete(jobId);
        return next;
      });
    } catch {
      setError("Failed to delete import history");
    }
  };

  const handleBulkDeleteHistory = async () => {
    const ids = Array.from(selectedHistoryJobIds);
    if (ids.length === 0) {
      return;
    }
    if (!window.confirm(`Delete ${ids.length} import histor${ids.length === 1 ? "y entry" : "y entries"}?`)) {
      return;
    }
    try {
      await bulkDeleteImportJobs(ids);
      setHistoryJobs((current) => current.filter((job) => !selectedHistoryJobIds.has(job.id)));
      setSelectedHistoryJobIds(new Set());
    } catch {
      setError("Failed to delete import history");
    }
  };

  const renderJobList = (
    jobsToRender: ImportJob[],
    testId: string,
    options?: { selectable?: boolean },
  ) => {
    if (jobsToRender.length === 0) {
      return (
        <p className="text-sm text-gray-500" data-testid={`${testId}-empty`}>
          No jobs in this section.
        </p>
      );
    }

    return (
      <ul className="space-y-2" data-testid={testId}>
        {jobsToRender.map((job) => (
          <li
            key={job.id}
            data-testid={`imports-row-${job.id}`}
            className="rounded-md border border-gray-200 bg-white p-3"
          >
            <div className="flex items-center justify-between gap-4">
              <div className="flex items-start gap-3">
                {options?.selectable ? (
                  <input
                    type="checkbox"
                    checked={selectedHistoryJobIds.has(job.id)}
                    onChange={() => toggleHistorySelection(job.id)}
                    data-testid={`imports-select-${job.id}`}
                    className="mt-1"
                  />
                ) : null}
                <div className="space-y-2 text-sm text-gray-700">
                <p className="break-words font-medium" data-testid={`imports-title-${job.id}`}>
                  <span className="font-semibold">Title:</span> {getImportDisplayTitle(job)}
                </p>
                <p className="text-xs text-gray-600">
                  <span className="font-semibold">Author:</span> {getAuthorLabel(job)}
                  {" · "}
                  <span className="font-semibold">Publisher:</span> {getPublisherLabel(job)}
                  {" · "}
                  <span className="font-semibold">Published:</span> {getPublishedLabel(job)}
                  {" · "}
                  <span className="font-semibold">ISBN:</span> {getIsbnLabel(job)}
                </p>
                <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-gray-500">
                  {compactMetricPairs(job).map(([label, value]) => (
                    <p key={`${job.id}-${label}`}>
                      <span className="font-semibold text-gray-600">{label}:</span> {value}
                    </p>
                  ))}
                </div>
                </div>
              </div>
              <div className="flex flex-col items-end gap-2">
                <Link
                  href={`/imports/${job.id}`}
                  data-testid={`imports-open-${job.id}`}
                  className="inline-flex min-w-24 items-center justify-center rounded-md border border-gray-300 bg-white px-3 py-2 text-sm text-gray-700"
                >
                  Open
                </Link>
                {options?.selectable ? (
                  <button
                    type="button"
                    onClick={() => void handleDeleteHistoryJob(job.id)}
                    data-testid={`imports-delete-${job.id}`}
                    className="inline-flex min-w-24 items-center justify-center rounded-md border border-[#f0c1c1] bg-[#fff5f5] px-3 py-2 text-sm text-[#b13a3a]"
                  >
                    Delete
                  </button>
                ) : null}
              </div>
            </div>
            <div className="mt-2">
              <div className="h-2 w-full overflow-hidden rounded bg-gray-200">
                <div
                  data-testid={`imports-progress-${job.id}`}
                  className="h-full bg-blue-600"
                  style={{ width: `${getImportProgressPercent(job)}%` }}
                />
              </div>
              <div className="mt-1 flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
                <p data-testid={`imports-progress-label-${job.id}`}>
                  {job.progress_current_label?.trim() || "Queued"}
                </p>
                <p data-testid={`imports-progress-counts-${job.id}`}>{formatProgressSummary(job)}</p>
              </div>
            </div>
          </li>
        ))}
      </ul>
    );
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.14em] text-[#7b6795]">
            Learner tools
          </p>
          <h2 className="text-2xl font-bold" data-testid="imports-page-title">
            Import Word Lists
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/word-lists"
            data-testid="imports-word-lists-link"
            className="rounded-full border border-[#d7c8ec] bg-[#f5efff] px-4 py-2 text-sm font-medium text-[#5b2590]"
          >
            Word Lists
          </Link>
          <Link
            href="/"
            data-testid="imports-home-link"
            className="rounded-full border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700"
          >
            Back to Home
          </Link>
        </div>
      </div>

      <form className="space-y-4 rounded-lg border border-gray-200 bg-white p-4" onSubmit={handleSubmit}>
        <div className="space-y-2">
          <label htmlFor="imports-upload-input" className="text-sm font-medium text-gray-700">
            EPUB File
          </label>
          <input
            id="imports-upload-input"
            data-testid="imports-upload-input"
            type="file"
            accept=".epub,application/epub+zip"
            onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            className="w-full rounded-md border border-gray-300 px-3 py-2"
          />
        </div>

        <button
          data-testid="imports-submit-button"
          type="submit"
          disabled={loading}
          className="rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {loading ? "Importing..." : "Start Import"}
        </button>
      </form>

      {error ? (
        <p className="text-sm text-red-600" data-testid="imports-error">
          {error}
        </p>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-lg font-semibold">Active Import</h3>
          <button
            type="button"
            data-testid="imports-history-toggle"
            onClick={() => setShowHistory((current) => !current)}
            className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700"
          >
            {showHistory ? "Hide History" : "Show History"}
          </button>
        </div>
        {primaryActiveJob ? renderJobList([primaryActiveJob], "imports-active-jobs-list") : (
          <p className="text-sm text-gray-500" data-testid="imports-active-jobs-list-empty">
            No active import right now.
          </p>
        )}
        {activeJobs.length > 1 ? (
          <p className="text-xs text-gray-500" data-testid="imports-active-jobs-extra">
            {activeJobs.length - 1} additional active import{activeJobs.length - 1 === 1 ? "" : "s"} running.
          </p>
        ) : null}
      </section>

      {showHistory ? (
        <section className="space-y-3">
          <h3 className="text-lg font-semibold">Import History</h3>
          <div className="flex flex-wrap items-center gap-2">
            <button
              type="button"
              onClick={selectAllHistory}
              data-testid="imports-history-select-all"
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700"
            >
              Select All
            </button>
            <button
              type="button"
              onClick={clearHistorySelection}
              data-testid="imports-history-clear-selection"
              className="rounded-md border border-gray-300 bg-white px-3 py-2 text-sm font-medium text-gray-700"
            >
              Unselect All
            </button>
            <button
              type="button"
              onClick={() => void handleBulkDeleteHistory()}
              disabled={selectedHistoryJobIds.size === 0}
              data-testid="imports-history-delete-selected"
              className="rounded-md border border-[#f0c1c1] bg-[#fff5f5] px-3 py-2 text-sm font-medium text-[#b13a3a] disabled:opacity-50"
            >
              Delete Selected
            </button>
          </div>
          {renderJobList(historyJobs, "imports-history-jobs-list", { selectable: true })}
        </section>
      ) : null}
    </div>
  );
}
