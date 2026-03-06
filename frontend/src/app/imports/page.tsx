"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  createWordListImport,
  getImportJob,
  getImportProgressPercent,
  ImportJob,
  isImportJobTerminal,
  listWordLists,
  WordList,
} from "@/lib/imports-client";

const POLL_INTERVAL_MS = 2000;

export default function ImportsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [listName, setListName] = useState("");
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [wordLists, setWordLists] = useState<WordList[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const lists = await listWordLists();
        if (!active) return;
        setWordLists(lists);
      } catch {
        if (!active) return;
        setError("Failed to load word lists");
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  const activeJobIds = useMemo(
    () => jobs.filter((job) => !isImportJobTerminal(job.status)).map((job) => job.id),
    [jobs],
  );

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
          return Array.from(byId.values()).sort((a, b) =>
            b.created_at.localeCompare(a.created_at),
          );
        });
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
      const job = await createWordListImport(selectedFile, listName);
      setJobs((prev) => [job, ...prev.filter((existing) => existing.id !== job.id)]);
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

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold" data-testid="imports-page-title">
        Import Word Lists
      </h2>

      <form
        className="space-y-4 rounded-lg border border-gray-200 bg-white p-4"
        onSubmit={handleSubmit}
      >
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
            List Name (optional)
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
                  <span className="text-sm text-gray-700">{job.status}</span>
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

      <section className="space-y-2">
        <h3 className="text-lg font-semibold">Your Word Lists</h3>
        {wordLists.length === 0 ? (
          <p className="text-sm text-gray-500" data-testid="word-lists-empty-state">
            No word lists yet.
          </p>
        ) : (
          <ul className="space-y-2" data-testid="word-lists-list">
            {wordLists.map((wordList) => (
              <li key={wordList.id} className="rounded-md border border-gray-200 bg-white p-3">
                <p className="font-medium">{wordList.name}</p>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
