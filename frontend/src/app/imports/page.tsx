"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import {
  addWordListItem,
  bulkAddWordListEntries,
  createListFromImport,
  createWordListImport,
  deleteWordList,
  deleteWordListItem,
  getImportEntries,
  getImportJob,
  getImportProgressPercent,
  getWordList,
  type ImportJob,
  type ReviewEntry,
  resolveEntries,
  isImportJobTerminal,
  listWordLists,
  type WordList,
  type WordListDetail,
  updateWordList,
} from "@/lib/imports-client";
import { searchKnowledgeMap, type KnowledgeMapEntrySummary } from "@/lib/knowledge-map-client";

const POLL_INTERVAL_MS = 2000;
const REVIEW_PAGE_SIZE = 100;

type SortMode = "book_frequency" | "general_rank" | "alpha";
type WordListSortMode = "alpha" | "rank" | "rank_desc";
type WordListViewMode = "cards" | "tags" | "list";

export default function ImportsPage() {
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [listName, setListName] = useState("");
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [wordLists, setWordLists] = useState<WordList[]>([]);
  const [activeWordListId, setActiveWordListId] = useState<string | null>(null);
  const [activeWordList, setActiveWordList] = useState<WordListDetail | null>(null);
  const [wordListNameDraft, setWordListNameDraft] = useState("");
  const [wordListDescriptionDraft, setWordListDescriptionDraft] = useState("");
  const [wordListSearchQuery, setWordListSearchQuery] = useState("");
  const [wordListSort, setWordListSort] = useState<WordListSortMode>("alpha");
  const [wordListViewMode, setWordListViewMode] = useState<WordListViewMode>("cards");
  const [manualAddQuery, setManualAddQuery] = useState("");
  const [manualAddResults, setManualAddResults] = useState<KnowledgeMapEntrySummary[]>([]);
  const [manualAddMessage, setManualAddMessage] = useState<string | null>(null);
  const [reviewEntries, setReviewEntries] = useState<ReviewEntry[]>([]);
  const [selectedEntryKeys, setSelectedEntryKeys] = useState<Set<string>>(new Set());
  const [reviewQuery, setReviewQuery] = useState("");
  const [reviewType, setReviewType] = useState<"all" | "word" | "phrase">("all");
  const [reviewSort, setReviewSort] = useState<SortMode>("book_frequency");
  const [listEditorText, setListEditorText] = useState("");
  const [listEditorMessage, setListEditorMessage] = useState<string | null>(null);
  const [activeReviewJobId, setActiveReviewJobId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [creatingList, setCreatingList] = useState(false);
  const [editingList, setEditingList] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const lists = await listWordLists();
        if (active) {
          setWordLists(lists);
        }
      } catch {
        if (active) {
          setError("Failed to load word lists");
        }
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
  }, [activeReviewJobId, reviewQuery, reviewSort, reviewType]);

  useEffect(() => {
    if (!activeWordListId) {
      setActiveWordList(null);
      return;
    }

    let active = true;
    setListEditorMessage(null);
    setManualAddMessage(null);
    getWordList(activeWordListId, {
      q: wordListSearchQuery.trim() || undefined,
      sort: wordListSort,
    })
      .then((detail) => {
        if (active) {
          setActiveWordList(detail);
          setWordListNameDraft(detail.name);
          setWordListDescriptionDraft(detail.description ?? "");
        }
      })
      .catch(() => {
        if (active) {
          setError("Failed to load word list");
        }
      });

    return () => {
      active = false;
    };
  }, [activeWordListId, wordListSearchQuery, wordListSort]);

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
      setActiveReviewJobId(job.status === "completed" ? job.id : null);
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
      setWordLists((prev) => [created, ...prev.filter((item) => item.id !== created.id)]);
      setActiveWordListId(created.id);
      setJobs((prev) =>
        prev.map((job) => (job.id === activeReviewJobId ? { ...job, word_list_id: created.id } : job)),
      );
    } catch {
      setError("Failed to create list");
    } finally {
      setCreatingList(false);
    }
  };

  const handleRemoveListItem = async (itemId: string) => {
    if (!activeWordListId) {
      return;
    }

    setEditingList(true);
    setListEditorMessage(null);
    try {
      await deleteWordListItem(activeWordListId, itemId);
      setActiveWordList((current) =>
        current
          ? { ...current, items: current.items.filter((item) => item.id !== itemId) }
          : current,
      );
    } catch {
      setListEditorMessage("Failed to remove list item");
    } finally {
      setEditingList(false);
    }
  };

  const handleBulkAddToList = async () => {
    if (!activeWordListId || !listEditorText.trim()) {
      setListEditorMessage("Enter at least one term to add");
      return;
    }

    setEditingList(true);
    setListEditorMessage(null);
    try {
      const resolved = await resolveEntries(listEditorText);
      if (resolved.found_entries.length === 0) {
        setListEditorMessage("No entries matched that text");
        return;
      }

      const updated = await bulkAddWordListEntries(activeWordListId, {
        selected_entries: resolved.found_entries.map((entry) => ({
          entry_type: entry.entry_type,
          entry_id: entry.entry_id,
        })),
      });
      setActiveWordList(updated);
      setListEditorText("");
      const notes: string[] = [`Added ${resolved.found_entries.length} entr${resolved.found_entries.length === 1 ? "y" : "ies"}`];
      if (resolved.ambiguous_entries.length > 0) {
        notes.push(`${resolved.ambiguous_entries.length} ambiguous`);
      }
      if (resolved.not_found_count > 0) {
        notes.push(`${resolved.not_found_count} not found`);
      }
      setListEditorMessage(notes.join(" · "));
    } catch {
      setListEditorMessage("Failed to add entries");
    } finally {
      setEditingList(false);
    }
  };

  const handleRenameWordList = async () => {
    if (!activeWordListId) {
      return;
    }

    const trimmedName = wordListNameDraft.trim();
    if (!trimmedName) {
      setListEditorMessage("List name is required");
      return;
    }

    setEditingList(true);
    setListEditorMessage(null);
    try {
      const updated = await updateWordList(activeWordListId, {
        name: trimmedName,
        description: wordListDescriptionDraft.trim() || null,
      });
      setWordLists((prev) =>
        prev.map((item) => (item.id === activeWordListId ? { ...item, ...updated } : item)),
      );
      setActiveWordList((current) =>
        current
          ? { ...current, name: updated.name, description: updated.description }
          : current,
      );
      setListEditorMessage("List updated");
    } catch {
      setListEditorMessage("Failed to update list");
    } finally {
      setEditingList(false);
    }
  };

  const handleDeleteWordList = async () => {
    if (!activeWordListId) {
      return;
    }

    setEditingList(true);
    setListEditorMessage(null);
    try {
      await deleteWordList(activeWordListId);
      setWordLists((prev) => prev.filter((item) => item.id !== activeWordListId));
      setActiveWordListId(null);
      setActiveWordList(null);
      setManualAddResults([]);
      setManualAddQuery("");
    } catch {
      setListEditorMessage("Failed to delete list");
    } finally {
      setEditingList(false);
    }
  };

  const handleManualSearch = async () => {
    const trimmed = manualAddQuery.trim();
    if (!trimmed) {
      setManualAddMessage("Enter a term to search");
      return;
    }

    setEditingList(true);
    setManualAddMessage(null);
    try {
      const response = await searchKnowledgeMap(trimmed);
      setManualAddResults(response.items);
      if (response.items.length === 0) {
        setManualAddMessage("No matching entries found");
      }
    } catch {
      setManualAddMessage("Failed to search catalog");
    } finally {
      setEditingList(false);
    }
  };

  const handleManualAddItem = async (entry: KnowledgeMapEntrySummary) => {
    if (!activeWordListId) {
      return;
    }

    setEditingList(true);
    setManualAddMessage(null);
    try {
      const created = await addWordListItem(activeWordListId, {
        entry_type: entry.entry_type,
        entry_id: entry.entry_id,
        frequency_count: 1,
      });
      setActiveWordList((current) =>
        current
          ? {
              ...current,
              items: [...current.items.filter((item) => item.id !== created.id), created].sort((a, b) =>
                (a.display_text ?? "").localeCompare(b.display_text ?? ""),
              ),
            }
          : current,
      );
      setManualAddMessage(`Added ${entry.display_text}`);
    } catch {
      setManualAddMessage("Failed to add entry");
    } finally {
      setEditingList(false);
    }
  };

  return (
    <div className="space-y-6">
      <h2 className="text-2xl font-bold" data-testid="imports-page-title">
        Import Word Lists
      </h2>

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
                <button
                  type="button"
                  className="w-full text-left"
                  data-testid={`word-list-open-${wordList.id}`}
                  onClick={() => setActiveWordListId(wordList.id)}
                >
                  <p className="font-medium">{wordList.name}</p>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      {activeWordList && (
        <section
          className="space-y-3 rounded-lg border border-gray-200 bg-white p-4"
          data-testid="word-list-detail-panel"
        >
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold" data-testid="word-list-detail-title">
                {activeWordList.name}
              </h3>
              <p className="text-sm text-gray-500" data-testid="word-list-detail-count">
                {activeWordList.items.length} items
              </p>
            </div>
            <button
              type="button"
              data-testid="word-list-delete-button"
              onClick={handleDeleteWordList}
              disabled={editingList}
              className="rounded border border-red-300 px-3 py-1 text-sm text-red-700 disabled:opacity-50"
            >
              Delete list
            </button>
          </div>

          <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto]">
            <input
              data-testid="word-list-rename-input"
              value={wordListNameDraft}
              onChange={(event) => setWordListNameDraft(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2"
              placeholder="List name"
            />
            <input
              data-testid="word-list-description-input"
              value={wordListDescriptionDraft}
              onChange={(event) => setWordListDescriptionDraft(event.target.value)}
              className="rounded-md border border-gray-300 px-3 py-2"
              placeholder="Optional description"
            />
            <button
              type="button"
              data-testid="word-list-rename-button"
              disabled={editingList}
              onClick={handleRenameWordList}
              className="rounded-md border px-4 py-2 text-sm disabled:opacity-50"
            >
              Save list
            </button>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <input
              data-testid="word-list-search-input"
              value={wordListSearchQuery}
              onChange={(event) => setWordListSearchQuery(event.target.value)}
              className="min-w-[14rem] flex-1 rounded-md border border-gray-300 px-3 py-2"
              placeholder="Search within list"
            />
            <select
              data-testid="word-list-sort-select"
              value={wordListSort}
              onChange={(event) => setWordListSort(event.target.value as WordListSortMode)}
              className="rounded-md border border-gray-300 px-3 py-2"
            >
              <option value="alpha">Alphabetic</option>
              <option value="rank">General rank</option>
              <option value="rank_desc">General rank desc</option>
            </select>
            <div className="flex items-center gap-2">
              <button
                type="button"
                data-testid="word-list-view-cards"
                onClick={() => setWordListViewMode("cards")}
                className="rounded border px-3 py-1 text-sm"
              >
                Cards
              </button>
              <button
                type="button"
                data-testid="word-list-view-tags"
                onClick={() => setWordListViewMode("tags")}
                className="rounded border px-3 py-1 text-sm"
              >
                Tags
              </button>
              <button
                type="button"
                data-testid="word-list-view-list"
                onClick={() => setWordListViewMode("list")}
                className="rounded border px-3 py-1 text-sm"
              >
                List
              </button>
            </div>
          </div>

          <div className="space-y-2">
            <label htmlFor="word-list-manual-search-input" className="text-sm font-medium text-gray-700">
              Add one entry from the catalog
            </label>
            <div className="flex flex-wrap items-center gap-3">
              <input
                id="word-list-manual-search-input"
                data-testid="word-list-manual-search-input"
                value={manualAddQuery}
                onChange={(event) => setManualAddQuery(event.target.value)}
                className="min-w-[14rem] flex-1 rounded-md border border-gray-300 px-3 py-2"
                placeholder="Search for a word or phrase"
              />
              <button
                type="button"
                data-testid="word-list-manual-search-button"
                disabled={editingList}
                onClick={handleManualSearch}
                className="rounded-md border px-4 py-2 text-sm disabled:opacity-50"
              >
                Search catalog
              </button>
            </div>
            {manualAddMessage && (
              <p className="text-sm text-gray-600" data-testid="word-list-manual-search-message">
                {manualAddMessage}
              </p>
            )}
            {manualAddResults.length > 0 && (
              <ul className="space-y-2" data-testid="word-list-manual-results">
                {manualAddResults.map((entry) => (
                  <li key={`${entry.entry_type}:${entry.entry_id}`} className="flex items-center justify-between gap-3 rounded border border-gray-200 px-3 py-2">
                    <div className="min-w-0 flex-1">
                      <p className="font-medium">{entry.display_text}</p>
                      <p className="text-xs text-gray-500">
                        {entry.entry_type}
                        {entry.phrase_kind ? ` · ${entry.phrase_kind}` : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      data-testid={`word-list-manual-add-${entry.entry_id}`}
                      disabled={editingList}
                      onClick={() => handleManualAddItem(entry)}
                      className="rounded border px-3 py-1 text-sm disabled:opacity-50"
                    >
                      Add
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="space-y-2">
            <label htmlFor="word-list-editor-text" className="text-sm font-medium text-gray-700">
              Add entries from text
            </label>
            <p className="text-xs text-gray-500" data-testid="word-list-editor-help">
              Enter one word per space, or quote multi-word phrases. You can also put one phrase per
              line.
            </p>
            <textarea
              id="word-list-editor-text"
              data-testid="word-list-editor-text"
              value={listEditorText}
              onChange={(event) => setListEditorText(event.target.value)}
              placeholder='Type words, or quote phrases like "on the other hand"'
              className="min-h-24 w-full rounded-md border border-gray-300 px-3 py-2"
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                data-testid="word-list-add-button"
                disabled={editingList}
                onClick={handleBulkAddToList}
                className="rounded-md bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              >
                {editingList ? "Saving..." : "Add to list"}
              </button>
              {listEditorMessage && (
                <p className="text-sm text-gray-600" data-testid="word-list-editor-message">
                  {listEditorMessage}
                </p>
              )}
            </div>
          </div>

          {activeWordList.items.length === 0 ? (
            <p className="text-sm text-gray-500" data-testid="word-list-detail-empty">
              No items in this list yet.
            </p>
          ) : wordListViewMode === "tags" ? (
            <div className="flex flex-wrap gap-2" data-testid="word-list-tags-view">
              {activeWordList.items.map((item) => (
                <span
                  key={item.id}
                  className="rounded-full border border-gray-300 px-3 py-1 text-sm"
                >
                  {item.display_text ?? item.normalized_form ?? item.entry_id}
                </span>
              ))}
            </div>
          ) : wordListViewMode === "list" ? (
            <table className="min-w-full text-left text-sm" data-testid="word-list-list-view">
              <thead>
                <tr className="border-b">
                  <th className="py-2 pr-3">Entry</th>
                  <th className="py-2 pr-3">Type</th>
                  <th className="py-2 pr-3">Rank</th>
                  <th className="py-2">Freq</th>
                </tr>
              </thead>
              <tbody>
                {activeWordList.items.map((item) => (
                  <tr key={item.id} className="border-b last:border-b-0">
                    <td className="py-2 pr-3">{item.display_text ?? item.normalized_form ?? item.entry_id}</td>
                    <td className="py-2 pr-3">{item.entry_type}</td>
                    <td className="py-2 pr-3">{item.browse_rank ?? "—"}</td>
                    <td className="py-2">{item.frequency_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <ul className="space-y-2" data-testid="word-list-detail-items">
              {activeWordList.items.map((item) => (
                <li
                  key={item.id}
                  className="flex items-center justify-between gap-3 rounded border border-gray-200 px-3 py-2"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">{item.display_text ?? item.normalized_form ?? item.entry_id}</p>
                    <p className="text-xs text-gray-500">
                      {item.entry_type} · freq {item.frequency_count}
                      {item.phrase_kind ? ` · ${item.phrase_kind}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    data-testid={`word-list-remove-${item.id}`}
                    disabled={editingList}
                    onClick={() => handleRemoveListItem(item.id)}
                    className="rounded border px-3 py-1 text-sm"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  );
}
