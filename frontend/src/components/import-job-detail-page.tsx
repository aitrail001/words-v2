"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ApiError } from "@/lib/api-client";
import { getImportDisplayTitle } from "@/lib/import-display";
import {
  createListFromImport,
  getImportElapsedSeconds,
  getImportEntries,
  getImportJob,
  getImportProgressPercent,
  isImportJobTerminal,
  type ImportJob,
  type ReviewEntry,
} from "@/lib/imports-client";

const REVIEW_PAGE_SIZE = 100;
const JOB_POLL_INTERVAL_MS = 2000;

type SortMode = "book_frequency" | "general_rank" | "alpha";
type SortOrder = "asc" | "desc";

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

function defaultListNameForImportJob(job: ImportJob): string {
  return (
    job.source_title?.trim()
    || job.list_name?.trim()
    || job.source_filename.replace(/\.[^.]+$/, "").trim()
    || "Imported list"
  );
}

function defaultListDescriptionForImportJob(job: ImportJob): string {
  const bookName = defaultListNameForImportJob(job);
  const filename = job.source_filename?.trim() || "Unknown";
  const author = job.source_author?.trim() || "Unknown";
  return `bookname: ${bookName}\nfilename: ${filename}\nauthor: ${author}`;
}

function compactSummaryPairs(job: ImportJob): Array<[string, string]> {
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

export function ImportJobDetailPage({ jobId }: { jobId: string }) {
  const [job, setJob] = useState<ImportJob | null>(null);
  const [reviewEntries, setReviewEntries] = useState<ReviewEntry[]>([]);
  const [reviewTotal, setReviewTotal] = useState(0);
  const [reviewOffset, setReviewOffset] = useState(0);
  const [selectedEntryKeys, setSelectedEntryKeys] = useState<Set<string>>(new Set());
  const [reviewQuery, setReviewQuery] = useState("");
  const [reviewType, setReviewType] = useState<"all" | "word" | "phrase">("all");
  const [reviewSort, setReviewSort] = useState<SortMode>("book_frequency");
  const [reviewOrder, setReviewOrder] = useState<SortOrder>("desc");
  const [createListName, setCreateListName] = useState("");
  const [createListDescription, setCreateListDescription] = useState("");
  const [creatingList, setCreatingList] = useState(false);
  const [createdList, setCreatedList] = useState<{ id: string; name: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    const loadJob = async () => {
      const response = await getImportJob(jobId);
      if (!active) {
        return;
      }
      setJob(response);
      setCreateListName((current) => current || defaultListNameForImportJob(response));
      setCreateListDescription((current) => current || defaultListDescriptionForImportJob(response));
    };
    loadJob()
      .catch(() => {
        if (active) {
          setError("Failed to load import job");
        }
      });
    return () => {
      active = false;
    };
  }, [jobId]);

  useEffect(() => {
    if (!job || isImportJobTerminal(job.status)) {
      return;
    }

    const intervalId = window.setInterval(async () => {
      try {
        const nextJob = await getImportJob(jobId);
        setJob(nextJob);
      } catch {
        setError("Failed to refresh import job");
      }
    }, JOB_POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [job, jobId]);

  useEffect(() => {
    let active = true;
    if (!job || job.status !== "completed") {
      setReviewEntries([]);
      setReviewTotal(0);
      return;
    }

    setError(null);
    getImportEntries(jobId, {
      q: reviewQuery.trim() || undefined,
      entry_type: reviewType === "all" ? undefined : reviewType,
      sort: reviewSort,
      order: reviewOrder,
      limit: REVIEW_PAGE_SIZE,
      offset: reviewOffset,
    })
      .then((response) => {
        if (!active) {
          return;
        }
        setReviewEntries(response.items);
        setReviewTotal(response.total);
        setSelectedEntryKeys(new Set(response.items.map((entry) => `${entry.entry_type}:${entry.entry_id}`)));
      })
      .catch(() => {
        if (active) {
          setError("Failed to load review entries");
        }
      });

    return () => {
      active = false;
    };
  }, [job, jobId, reviewOffset, reviewOrder, reviewQuery, reviewSort, reviewType]);

  useEffect(() => {
    setReviewOffset(0);
  }, [reviewOrder, reviewQuery, reviewSort, reviewType]);

  const selectedEntries = useMemo(
    () => reviewEntries.filter((entry) => selectedEntryKeys.has(`${entry.entry_type}:${entry.entry_id}`)),
    [reviewEntries, selectedEntryKeys],
  );

  const toggleEntry = (entry: ReviewEntry) => {
    const key = `${entry.entry_type}:${entry.entry_id}`;
    setSelectedEntryKeys((current) => {
      const next = new Set(current);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  };

  const handleCreateList = async () => {
    if (selectedEntries.length === 0) {
      setError("Select at least one entry");
      return;
    }
    setCreatingList(true);
    setError(null);
    try {
      const created = await createListFromImport(jobId, {
        name: createListName.trim() || undefined,
        description: createListDescription.trim() || undefined,
        selected_entries: selectedEntries.map((entry) => ({
          entry_type: entry.entry_type,
          entry_id: entry.entry_id,
        })),
      });
      setCreatedList({ id: created.id, name: created.name });
      setJob((current) => (current ? { ...current, word_list_id: created.id } : current));
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError("Choose a unique word list name");
      } else {
        setError("Failed to create list");
      }
    } finally {
      setCreatingList(false);
    }
  };

  const pageStart = reviewEntries.length === 0 ? 0 : reviewOffset + 1;
  const pageEnd = reviewOffset + reviewEntries.length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.14em] text-[#7b6795]">
            Import Review
          </p>
          <h2 className="text-2xl font-bold" data-testid="import-job-detail-title">
            {job ? getImportDisplayTitle(job) : "Import"}
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/imports"
            data-testid="import-job-back-link"
            className="rounded-full border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700"
          >
            Back to Imports
          </Link>
          <Link
            href="/word-lists"
            data-testid="import-job-word-lists-link"
            className="rounded-full border border-[#d7c8ec] bg-[#f5efff] px-4 py-2 text-sm font-medium text-[#5b2590]"
          >
            Word Lists
          </Link>
        </div>
      </div>

      {job ? (
        <section className="rounded-lg border border-gray-200 bg-white p-4" data-testid="import-job-summary">
          <div className="space-y-2 text-sm text-gray-700">
            <p className="break-words" data-testid="import-job-summary-title">
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
              {compactSummaryPairs(job).map(([label, value]) => (
                <p key={`${job.id}-${label}`}>
                  <span className="font-semibold text-gray-600">{label}:</span> {value}
                </p>
              ))}
            </div>
            {!isImportJobTerminal(job.status) ? (
              <div className="space-y-2 pt-2">
                <div className="h-2 w-full overflow-hidden rounded bg-gray-200">
                  <div
                    data-testid="import-job-progress-bar"
                    className="h-full bg-blue-600"
                    style={{ width: `${getImportProgressPercent(job)}%` }}
                  />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-gray-500">
                  <p data-testid="import-job-progress-label">
                    {job.progress_current_label?.trim() || "Queued"}
                  </p>
                  <p data-testid="import-job-progress-counts">{formatProgressSummary(job)}</p>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

      {createdList ? (
        <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-4" data-testid="imports-created-list-panel">
          <p className="text-sm font-medium text-emerald-800">
            Created <span className="font-semibold">{createdList.name}</span>.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Link
              href={`/word-lists/${createdList.id}`}
              data-testid="imports-open-created-list-link"
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white"
            >
              Open Word List
            </Link>
          </div>
        </section>
      ) : null}

      {error ? <p className="text-sm text-red-600" data-testid="imports-error">{error}</p> : null}

      {job?.status === "completed" ? (
        <section className="space-y-4 rounded-lg border border-gray-200 bg-white p-4" data-testid="imports-review-panel">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm font-medium text-gray-600">
              {pageStart}-{pageEnd} of {reviewTotal}
            </p>
            <p className="text-sm text-gray-600" data-testid="imports-selected-count">
              {selectedEntries.length} selected
            </p>
          </div>

          <div className="grid gap-3 md:grid-cols-3">
            <input
              data-testid="imports-review-search-input"
              value={reviewQuery}
              onChange={(event) => setReviewQuery(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2"
              placeholder="Search extracted words"
            />
            <select
              data-testid="imports-review-type-select"
              value={reviewType}
              onChange={(event) => setReviewType(event.target.value as "all" | "word" | "phrase")}
              className="rounded-md border border-gray-300 px-3 py-2"
            >
              <option value="all">All entries</option>
              <option value="word">Words</option>
              <option value="phrase">Phrases</option>
            </select>
            <select
              data-testid="imports-review-sort-select"
              value={reviewSort}
              onChange={(event) => setReviewSort(event.target.value as SortMode)}
              className="rounded-md border border-gray-300 px-3 py-2"
            >
              <option value="book_frequency">Book Frequency</option>
              <option value="general_rank">General Rank</option>
              <option value="alpha">Alphabetic</option>
            </select>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              data-testid="imports-review-order-button"
              onClick={() => setReviewOrder((current) => (current === "asc" ? "desc" : "asc"))}
              className="rounded-md border border-gray-300 px-3 py-1 text-sm"
            >
              {reviewOrder === "asc" ? "↑ Asc" : "↓ Desc"}
            </button>
          </div>

          <ul className="space-y-2" data-testid="imports-review-list">
            {reviewEntries.map((entry) => {
              const key = `${entry.entry_type}:${entry.entry_id}`;
              return (
                <li
                  key={key}
                  className="flex items-center justify-between gap-3 rounded-md border border-gray-200 px-3 py-2"
                >
                  <label className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      checked={selectedEntryKeys.has(key)}
                      onChange={() => toggleEntry(entry)}
                    />
                    <span>
                      <span className="block font-medium">{entry.display_text}</span>
                      <span className="text-xs text-gray-500">
                        {entry.entry_type} · freq {entry.frequency_count}
                      </span>
                    </span>
                  </label>
                </li>
              );
            })}
          </ul>

          <div className="flex items-center justify-between gap-3">
            <button
              type="button"
              data-testid="imports-prev-page-button"
              disabled={reviewOffset === 0}
              onClick={() => setReviewOffset((current) => Math.max(0, current - REVIEW_PAGE_SIZE))}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              data-testid="imports-next-page-button"
              disabled={reviewOffset + REVIEW_PAGE_SIZE >= reviewTotal}
              onClick={() => setReviewOffset((current) => current + REVIEW_PAGE_SIZE)}
              className="rounded-md border border-gray-300 px-3 py-2 text-sm disabled:opacity-50"
            >
              Next
            </button>
          </div>

          <div className="space-y-3 rounded-md border border-[#d7c8ec] bg-[#faf6ff] p-4">
            <h4 className="text-base font-semibold text-[#5b2590]">Create List From Selection</h4>
            <input
              data-testid="imports-create-list-name-input"
              value={createListName}
              onChange={(event) => setCreateListName(event.target.value)}
              className="w-full rounded-md border border-gray-300 px-3 py-2"
              placeholder="Word list name"
            />
            <textarea
              data-testid="imports-create-list-description-input"
              value={createListDescription}
              onChange={(event) => setCreateListDescription(event.target.value)}
              className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2"
              placeholder="Description"
            />
            <button
              type="button"
              data-testid="imports-create-list-button"
              disabled={creatingList}
              onClick={handleCreateList}
              className="rounded-md bg-[#6f42aa] px-4 py-2 text-white disabled:opacity-50"
            >
              {creatingList ? "Creating..." : "Create List From Selection"}
            </button>
          </div>
        </section>
      ) : (
        <p className="text-sm text-gray-500">
          {job ? "This import is still processing." : "Loading import..."}
        </p>
      )}
    </div>
  );
}
