"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  addWordListItem,
  bulkAddWordListEntries,
  deleteWordList,
  deleteWordListItem,
  getWordList,
  listWordLists,
  resolveEntries,
  type WordList,
  type WordListDetail,
  updateWordList,
} from "@/lib/imports-client";
import { searchKnowledgeMap, type KnowledgeMapEntrySummary } from "@/lib/knowledge-map-client";

type WordListSortMode = "alpha" | "rank" | "rank_desc";
type WordListViewMode = "cards" | "tags" | "list";

type WordListsManagerProps = {
  initialWordListId?: string | null;
};

export function WordListsManager({ initialWordListId = null }: WordListsManagerProps) {
  const requestedWordListId = initialWordListId;

  const [wordLists, setWordLists] = useState<WordList[]>([]);
  const [activeWordListId, setActiveWordListId] = useState<string | null>(requestedWordListId);
  const [activeWordList, setActiveWordList] = useState<WordListDetail | null>(null);
  const [wordListNameDraft, setWordListNameDraft] = useState("");
  const [wordListDescriptionDraft, setWordListDescriptionDraft] = useState("");
  const [wordListSearchQuery, setWordListSearchQuery] = useState("");
  const [wordListSort, setWordListSort] = useState<WordListSortMode>("alpha");
  const [wordListViewMode, setWordListViewMode] = useState<WordListViewMode>("cards");
  const [manualAddQuery, setManualAddQuery] = useState("");
  const [manualAddResults, setManualAddResults] = useState<KnowledgeMapEntrySummary[]>([]);
  const [manualAddMessage, setManualAddMessage] = useState<string | null>(null);
  const [listEditorText, setListEditorText] = useState("");
  const [listEditorMessage, setListEditorMessage] = useState<string | null>(null);
  const [editingList, setEditingList] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    (async () => {
      try {
        const lists = await listWordLists();
        if (!active) {
          return;
        }

        setWordLists(lists);
        setActiveWordListId((current) => {
          if (requestedWordListId && lists.some((item) => item.id === requestedWordListId)) {
            return requestedWordListId;
          }
          if (current && lists.some((item) => item.id === current)) {
            return current;
          }
          return lists[0]?.id ?? null;
        });
      } catch {
        if (active) {
          setError("Failed to load word lists");
        }
      }
    })();

    return () => {
      active = false;
    };
  }, [requestedWordListId]);

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
      const notes: string[] = [
        `Added ${resolved.found_entries.length} entr${resolved.found_entries.length === 1 ? "y" : "ies"}`,
      ];
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
      setWordLists((prev) => {
        const next = prev.filter((item) => item.id !== activeWordListId);
        setActiveWordListId(next[0]?.id ?? null);
        return next;
      });
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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm font-medium uppercase tracking-[0.14em] text-[#7b6795]">
            Learner tools
          </p>
          <h2 className="text-2xl font-bold" data-testid="word-lists-page-title">
            Manage Word Lists
          </h2>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/imports"
            data-testid="word-lists-import-link"
            className="rounded-full border border-[#d7c8ec] bg-[#f5efff] px-4 py-2 text-sm font-medium text-[#5b2590]"
          >
            Go To Imports
          </Link>
          <Link
            href="/"
            data-testid="word-lists-home-link"
            className="rounded-full border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700"
          >
            Back to Home
          </Link>
        </div>
      </div>

      <section className="space-y-2" id="your-word-lists">
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

      {error && (
        <p className="text-sm text-red-600" data-testid="word-lists-error">
          {error}
        </p>
      )}

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
              <button type="button" data-testid="word-list-view-cards" onClick={() => setWordListViewMode("cards")} className="rounded border px-3 py-1 text-sm">
                Cards
              </button>
              <button type="button" data-testid="word-list-view-tags" onClick={() => setWordListViewMode("tags")} className="rounded border px-3 py-1 text-sm">
                Tags
              </button>
              <button type="button" data-testid="word-list-view-list" onClick={() => setWordListViewMode("list")} className="rounded border px-3 py-1 text-sm">
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
              <p className="text-sm text-gray-600" data-testid="word-list-manual-message">
                {manualAddMessage}
              </p>
            )}
            {manualAddResults.length > 0 && (
              <ul className="space-y-2" data-testid="word-list-manual-results">
                {manualAddResults.map((entry) => (
                  <li key={`${entry.entry_type}:${entry.entry_id}`} className="flex items-center justify-between gap-3 rounded border border-gray-200 px-3 py-2">
                    <div>
                      <p className="font-medium">{entry.display_text}</p>
                      <p className="text-xs text-gray-500">
                        {entry.entry_type}
                        {entry.browse_rank ? ` · rank ${entry.browse_rank}` : ""}
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
              Add many entries at once
            </label>
            <textarea
              id="word-list-editor-text"
              data-testid="word-list-editor-text"
              value={listEditorText}
              onChange={(event) => setListEditorText(event.target.value)}
              rows={4}
              className="w-full rounded-md border border-gray-300 px-3 py-2"
              placeholder='run "make up for"&#10;on the other hand'
            />
            <p className="text-xs text-gray-500" data-testid="word-list-editor-help">
              Enter one word per space, or quote multi-word phrases. You can also put one phrase per line.
            </p>
            <div className="flex items-center gap-3">
              <button
                type="button"
                data-testid="word-list-add-button"
                disabled={editingList}
                onClick={handleBulkAddToList}
                className="rounded-md bg-blue-600 px-4 py-2 text-white disabled:opacity-50"
              >
                Add resolved entries
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
              This word list is empty.
            </p>
          ) : wordListViewMode === "tags" ? (
            <div className="flex flex-wrap gap-2" data-testid="word-list-detail-items">
              {activeWordList.items.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  data-testid={`word-list-remove-${item.id}`}
                  onClick={() => handleRemoveListItem(item.id)}
                  className="rounded-full border border-gray-300 bg-gray-50 px-3 py-1 text-sm"
                >
                  {item.display_text}
                </button>
              ))}
            </div>
          ) : wordListViewMode === "list" ? (
            <ul className="divide-y divide-gray-200" data-testid="word-list-detail-items">
              {activeWordList.items.map((item) => (
                <li key={item.id} className="flex items-center justify-between gap-3 py-3">
                  <div>
                    <p className="font-medium">{item.display_text}</p>
                    <p className="text-xs text-gray-500">
                      {item.entry_type}
                      {item.browse_rank ? ` · rank ${item.browse_rank}` : ""}
                    </p>
                  </div>
                  <button
                    type="button"
                    data-testid={`word-list-remove-${item.id}`}
                    onClick={() => handleRemoveListItem(item.id)}
                    className="rounded border px-3 py-1 text-sm"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <div className="grid gap-3 md:grid-cols-2" data-testid="word-list-detail-items">
              {activeWordList.items.map((item) => (
                <div key={item.id} className="rounded-lg border border-gray-200 p-3">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium">{item.display_text}</p>
                      <p className="text-xs text-gray-500">
                        {item.entry_type}
                        {item.phrase_kind ? ` · ${item.phrase_kind}` : ""}
                      </p>
                    </div>
                    <button
                      type="button"
                      data-testid={`word-list-remove-${item.id}`}
                      onClick={() => handleRemoveListItem(item.id)}
                      className="rounded border px-2 py-1 text-xs"
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  );
}
