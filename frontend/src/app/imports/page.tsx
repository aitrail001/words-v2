"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createListFromImport,
  createWordListImport,
  getImportEntries,
  getImportJob,
  getImportProgressPercent,
  listImportJobs,
  type ImportJob,
  type ReviewEntry,
  isImportJobTerminal,
} from "@/lib/imports-client";

const POLL_INTERVAL_MS = 2000;
const REVIEW_PAGE_SIZE = 100;

type SortMode = "book_frequency" | "general_rank" | "alpha";

export default function ImportsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [listName, setListName] = useState("");
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [reviewEntries, setReviewEntries] = useState<ReviewEntry[]>([]);
  const [selectedEntryKeys, setSelectedEntryKeys] = useState<Set<string>>(new Set());
  const [reviewQuery, setReviewQuery] = useState("");
  const [reviewType, setReviewType] = useState<"all" | "word" | "phrase">("all");
  const [reviewSort, setReviewSort] = useState<SortMode>("book_frequency");
  const [activeReviewJobId, setActiveReviewJobId] = useState<string | null>(null);
  const [recentCreatedList, setRecentCreatedList] = useState<{ id: string; name: string } | null>(null);
  const [loading, setLoading] = useState(false);
  const [creatingList, setCreatingList] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const activeReviewJob = useMemo(
    () => jobs.find((job) => job.id === activeReviewJobId) ?? null,
    [activeReviewJobId, jobs],
  );

  const activeJobIds = useMemo(
    () => jobs.filter((job) => !isImportJobTerminal(job.status)).map((job) => job.id),
    [jobs],
  );

  useEffect(() => {
    let active = true;

    listImportJobs()
      .then((loadedJobs) => {
        if (active) {
          setJobs(loadedJobs);
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
        setJobs((prev) => {
          const byId = new Map(prev.map((job) => [job.id, job]));
          for (const updatedJob of updatedJobs) {
            byId.set(updatedJob.id, updatedJob);
          }
          return Array.from(byId.values()).sort((a, b) => b.created_at.localeCompare(a.created_at));
        });
      } catch {
        setError("Failed to refresh import status");
      }
    }, POLL_INTERVAL_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [activeJobIds]);

  useEffect(() => {
    const candidateJob =
      jobs.find((job) => job.id === activeReviewJobId) ??
      jobs.find((job) => job.status === "completed" && !job.word_list_id) ??
      null;
    if (!candidateJob) {
      return;
    }
    setActiveReviewJobId(candidateJob.id);
  }, [activeReviewJobId, jobs]);

  useEffect(() => {
    if (!activeReviewJobId) {
      setReviewEntries([]);
      return;
    }
    if (activeReviewJob && activeReviewJob.status !== "completed") {
      setReviewEntries([]);
      return;
    }

    let active = true;
    setError(null);
    getImportEntries(activeReviewJobId, {
      q: reviewQuery.trim() || undefined,
      entry_type: reviewType === "all" ? undefined : reviewType,
      sort: reviewSort,
      order: reviewSort === "alpha" ? "asc" : "desc",
      limit: REVIEW_PAGE_SIZE,
      offset: 0,
    })
      .then((response) => {
        if (active) {
          setReviewEntries(response.items);
          setSelectedEntryKeys(
            new Set(response.items.map((entry) => `${entry.entry_type}:${entry.entry_id}`)),
          );
        }
      })
      .catch(() => {
        if (active) {
          setError("Failed to load review entries");
        }
      });

    return () => {
      active = false;
    };
  }, [activeReviewJob, activeReviewJobId, reviewQuery, reviewSort, reviewType]);

  const selectedEntries = useMemo(
    () =>
      reviewEntries.filter((entry) => selectedEntryKeys.has(`${entry.entry_type}:${entry.entry_id}`)),
    [reviewEntries, selectedEntryKeys],
  );

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!selectedFile) {
      setError("Please select an .epub file to import");
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const job = await createWordListImport(selectedFile, listName);
      setJobs((prev) => [job, ...prev.filter((existing) => existing.id !== job.id)]);
      setActiveReviewJobId(job.id);
      setSelectedFile(null);
      setListName("");
      const input = document.getElementById("imports-upload-input") as HTMLInputElement | null;
      if (input) {
        input.value = "";
      }
    } catch {
      setError("Import failed. Please try again.");
    } finally {
      setLoading(false);
    }
  };

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

  const selectAllFiltered = () => {
    setSelectedEntryKeys(new Set(reviewEntries.map((entry) => `${entry.entry_type}:${entry.entry_id}`)));
  };

  const deselectAllFiltered = () => {
    setSelectedEntryKeys(new Set());
  };

  const handleCreateList = async () => {
    if (!activeReviewJobId || selectedEntries.length === 0) {
      setError("Select at least one entry");
      return;
    }

    const activeJob = jobs.find((job) => job.id === activeReviewJobId) ?? null;

    setCreatingList(true);
    setError(null);
    try {
      const created = await createListFromImport(activeReviewJobId, {
        name: listName.trim() || activeJob?.list_name?.trim() || "Imported list",
        selected_entries: selectedEntries.map((entry) => ({
          entry_type: entry.entry_type,
          entry_id: entry.entry_id,
        })),
      });
      setRecentCreatedList({ id: created.id, name: created.name });
      setJobs((prev) =>
        prev.map((job) => (job.id === activeReviewJobId ? { ...job, word_list_id: created.id } : job)),
      );
    } catch {
      setError("Failed to create list");
    } finally {
      setCreatingList(false);
    }
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
            Word List Manager
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

        <div className="space-y-2">
          <label htmlFor="imports-list-name" className="text-sm font-medium text-gray-700">
            List Name
          </label>
          <input
            id="imports-list-name"
            value={listName}
            onChange={(event) => setListName(event.target.value)}
            className="w-full rounded-md border border-gray-300 px-3 py-2"
            placeholder="Imported from book"
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

      {recentCreatedList && (
        <section className="rounded-lg border border-emerald-200 bg-emerald-50 p-4" data-testid="imports-created-list-panel">
          <p className="text-sm font-medium text-emerald-800">
            Created <span className="font-semibold">{recentCreatedList.name}</span>.
          </p>
          <div className="mt-3 flex flex-wrap gap-3">
            <Link
              href={`/word-lists?list=${recentCreatedList.id}`}
              data-testid="imports-open-created-list-link"
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white"
            >
              Open In Word List Manager
            </Link>
            <Link
              href="/word-lists"
              className="rounded-md border border-emerald-300 px-4 py-2 text-sm font-medium text-emerald-800"
            >
              View All Word Lists
            </Link>
          </div>
        </section>
      )}

      {error && (
        <p className="text-sm text-red-600" data-testid="imports-error">
          {error}
        </p>
      )}

      <section className="space-y-2">
        <h3 className="text-lg font-semibold">Import Jobs</h3>
        {jobs.length === 0 ? (
          <p className="text-sm text-gray-500" data-testid="imports-empty-state">
            No import jobs yet.
          </p>
        ) : (
          <ul className="space-y-2" data-testid="imports-jobs-list">
            {jobs.map((job) => (
              <li
                key={job.id}
                data-testid={`imports-row-${job.id}`}
                className="rounded-md border border-gray-200 bg-white p-3"
              >
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <p className="font-medium">{job.list_name}</p>
                    <p className="text-xs text-gray-500">{job.source_filename}</p>
                  </div>
                  <button
                    type="button"
                    className="text-sm text-gray-700"
                    onClick={() => setActiveReviewJobId(job.id)}
                  >
                    {job.status}
                  </button>
                </div>
                <div className="mt-2">
                  <div className="h-2 w-full overflow-hidden rounded bg-gray-200">
                    <div
                      data-testid={`imports-progress-${job.id}`}
                      className="h-full bg-blue-600"
                      style={{ width: `${getImportProgressPercent(job)}%` }}
                    />
                  </div>
                  <p className="mt-1 text-xs text-gray-500">
                    {job.processed_items}/{job.total_items || 0} processed
                  </p>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>

      {activeReviewJobId && (
        <section className="space-y-3 rounded-lg border border-gray-200 bg-white p-4" data-testid="imports-review-panel">
          <div className="flex flex-wrap items-center gap-3">
            <input
              value={reviewQuery}
              onChange={(event) => setReviewQuery(event.target.value)}
              placeholder="Search matched entries"
              className="min-w-[14rem] flex-1 rounded-md border border-gray-300 px-3 py-2"
            />
            <select
              value={reviewType}
              onChange={(event) => setReviewType(event.target.value as "all" | "word" | "phrase")}
              className="rounded-md border border-gray-300 px-3 py-2"
            >
              <option value="all">All</option>
              <option value="word">Words</option>
              <option value="phrase">Phrases</option>
            </select>
            <select
              value={reviewSort}
              onChange={(event) => setReviewSort(event.target.value as SortMode)}
              className="rounded-md border border-gray-300 px-3 py-2"
            >
              <option value="book_frequency">Book frequency</option>
              <option value="general_rank">General rank</option>
              <option value="alpha">Alphabetic</option>
            </select>
          </div>

          <div className="flex items-center gap-3 text-sm">
            <button type="button" onClick={selectAllFiltered} className="rounded border px-3 py-1">
              Select all filtered
            </button>
            <button type="button" onClick={deselectAllFiltered} className="rounded border px-3 py-1">
              Deselect all filtered
            </button>
            <span data-testid="imports-selected-count">{selectedEntries.length} selected</span>
          </div>

          {reviewEntries.length === 0 ? (
            <p className="text-sm text-gray-500" data-testid="imports-review-empty">
              No matched entries for this filter.
            </p>
          ) : (
            <ul className="space-y-2" data-testid="imports-review-list">
              {reviewEntries.map((entry) => {
                const key = `${entry.entry_type}:${entry.entry_id}`;
                const checked = selectedEntryKeys.has(key);
                return (
                  <li key={key} className="flex items-center gap-3 rounded border border-gray-200 px-3 py-2">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleEntry(entry)}
                      aria-label={`select-${key}`}
                    />
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{entry.display_text}</p>
                      <p className="text-xs text-gray-500">
                        {entry.entry_type} · freq {entry.frequency_count}
                        {entry.phrase_kind ? ` · ${entry.phrase_kind}` : ""}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}

          <div className="flex items-center gap-3">
            <button
              type="button"
              disabled={creatingList}
              onClick={handleCreateList}
              className="rounded-md bg-emerald-600 px-4 py-2 text-white disabled:opacity-50"
              data-testid="imports-create-list-button"
            >
              {creatingList ? "Creating..." : "Create list from selection"}
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
