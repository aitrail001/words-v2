"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { LearnerListRows, type LearnerListRowItem } from "@/components/learner-list-rows";
import { ApiError } from "@/lib/api-client";
import {
  addWordListItem,
  bulkAddWordListEntries,
  bulkDeleteWordListItems,
  deleteWordList,
  deleteWordListItem,
  getWordList,
  resolveEntries,
  updateWordList,
  type WordListDetail,
  type WordListItem,
} from "@/lib/imports-client";
import {
  searchKnowledgeMap,
  type KnowledgeMapEntrySummary,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

type WordListSortMode = "alpha" | "rank";
type WordListSortOrder = "asc" | "desc";

type WordListDetailPageProps = {
  wordListId: string;
};

type DetailRow = WordListItem & LearnerListRowItem;

export function WordListDetailPage({ wordListId }: WordListDetailPageProps) {
  const router = useRouter();
  const [detail, setDetail] = useState<WordListDetail | null>(null);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<WordListSortMode>("alpha");
  const [order, setOrder] = useState<WordListSortOrder>("asc");
  const [showTranslations, setShowTranslations] = useState(true);
  const [selectedItemIds, setSelectedItemIds] = useState<Set<string>>(new Set());
  const [manualAddQuery, setManualAddQuery] = useState("");
  const [manualAddResults, setManualAddResults] = useState<KnowledgeMapEntrySummary[]>([]);
  const [bulkText, setBulkText] = useState("");
  const [managerOpen, setManagerOpen] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    getUserPreferences()
      .then((preferences) => {
        if (active) {
          setShowTranslations(preferences.show_translations_by_default);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    getWordList(wordListId, { q: query.trim() || undefined, sort, order })
      .then((response) => {
        if (active) {
          setDetail(response);
          setNameDraft(response.name);
          setDescriptionDraft(response.description ?? "");
          setSelectedItemIds(new Set());
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
  }, [order, query, sort, wordListId]);

  const rows = useMemo(() => (detail?.items ?? []) as DetailRow[], [detail?.items]);

  const cycleSort = () => {
    const options: WordListSortMode[] = ["alpha", "rank"];
    const nextIndex = (options.indexOf(sort) + 1) % options.length;
    setSort(options[nextIndex]);
  };

  const toggleSelected = (itemId: string) => {
    setSelectedItemIds((current) => {
      const next = new Set(current);
      if (next.has(itemId)) {
        next.delete(itemId);
      } else {
        next.add(itemId);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedItemIds(new Set((detail?.items ?? []).map((item) => item.id)));
  };

  const clearSelection = () => {
    setSelectedItemIds(new Set());
  };

  const handleStatusChange = async (item: DetailRow, nextStatus: KnowledgeStatus) => {
    const response = await updateKnowledgeEntryStatus(item.entry_type, item.entry_id, nextStatus);
    setDetail((current) =>
      current
        ? {
            ...current,
            items: current.items.map((entry) =>
              entry.id === item.id ? { ...entry, status: response.status } : entry,
            ),
          }
        : current,
    );
  };

  const handleRemoveSingle = async (itemId: string) => {
    if (!window.confirm("Remove this item from the word list?")) {
      return;
    }
    setBusy(true);
    setMessage(null);
    try {
      await deleteWordListItem(wordListId, itemId);
      setDetail((current) =>
        current
          ? { ...current, items: current.items.filter((item) => item.id !== itemId) }
          : current,
      );
      setSelectedItemIds((current) => {
        const next = new Set(current);
        next.delete(itemId);
        return next;
      });
    } catch {
      setError("Failed to remove item");
    } finally {
      setBusy(false);
    }
  };

  const handleBulkRemove = async () => {
    const ids = Array.from(selectedItemIds);
    if (ids.length === 0) {
      return;
    }
    if (!window.confirm(`Remove ${ids.length} selected item${ids.length === 1 ? "" : "s"}?`)) {
      return;
    }

    setBusy(true);
    setMessage(null);
    try {
      await bulkDeleteWordListItems(wordListId, ids);
      setDetail((current) =>
        current
          ? { ...current, items: current.items.filter((item) => !selectedItemIds.has(item.id)) }
          : current,
      );
      setSelectedItemIds(new Set());
    } catch {
      setError("Failed to remove selected items");
    } finally {
      setBusy(false);
    }
  };

  const handleSaveListMeta = async () => {
    const trimmedName = nameDraft.trim();
    if (!trimmedName) {
      setError("List name is required");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const updated = await updateWordList(wordListId, {
        name: trimmedName,
        description: descriptionDraft.trim() || null,
      });
      setDetail((current) =>
        current ? { ...current, name: updated.name, description: updated.description } : current,
      );
      setManagerOpen(false);
      setMessage("List updated");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError("Choose a unique word list name");
      } else {
        setError("Failed to update list");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteList = async () => {
    if (!window.confirm("Delete this word list?")) {
      return;
    }
    setBusy(true);
    try {
      await deleteWordList(wordListId);
      router.push("/word-lists");
    } catch {
      setError("Failed to delete word list");
      setBusy(false);
    }
  };

  const handleBulkAdd = async () => {
    if (!bulkText.trim()) {
      setError("Enter at least one word or phrase");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const resolved = await resolveEntries(bulkText);
      if (resolved.found_entries.length === 0) {
        setError("No entries matched that text");
        return;
      }
      const updated = await bulkAddWordListEntries(wordListId, {
        selected_entries: resolved.found_entries.map((entry) => ({
          entry_type: entry.entry_type,
          entry_id: entry.entry_id,
        })),
      });
      setDetail(updated);
      setBulkText("");
      setMessage(`Added ${resolved.found_entries.length} entr${resolved.found_entries.length === 1 ? "y" : "ies"}`);
    } catch {
      setError("Failed to add entries");
    } finally {
      setBusy(false);
    }
  };

  const handleManualSearch = async () => {
    const trimmed = manualAddQuery.trim();
    if (!trimmed) {
      setError("Enter a term to search");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const response = await searchKnowledgeMap(trimmed);
      setManualAddResults(response.items);
    } catch {
      setError("Failed to search catalog");
    } finally {
      setBusy(false);
    }
  };

  const handleManualAdd = async (entry: KnowledgeMapEntrySummary) => {
    setBusy(true);
    setError(null);
    try {
      await addWordListItem(wordListId, {
        entry_type: entry.entry_type,
        entry_id: entry.entry_id,
      });
      const refreshed = await getWordList(wordListId, { q: query.trim() || undefined, sort, order });
      setDetail(refreshed);
      setMessage(`Added ${entry.display_text}`);
    } catch {
      setError("Failed to add entry");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#492160]">
      <section className="rounded-[0.8rem] bg-[#f1f2f8] px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <Link href="/word-lists" data-testid="word-list-back-link" className="text-2xl font-semibold text-[#6f42aa]">
            ←
          </Link>
          <h1 className="text-[1.45rem] font-semibold tracking-tight text-[#54267f]" data-testid="word-list-detail-title">
            {detail?.name ?? "Word List"}
          </h1>
          <button
            type="button"
            data-testid="word-list-manage-button"
            onClick={() => setManagerOpen(true)}
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            Manage
          </button>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            onClick={cycleSort}
            data-testid="word-list-sort-button"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            ↕ {sort === "alpha" ? "Alphabetic" : "Difficulty"}
          </button>
          <button
            type="button"
            onClick={() => setOrder((current) => (current === "asc" ? "desc" : "asc"))}
            data-testid="word-list-order-button"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            {order === "asc" ? "↑ Asc" : "↓ Desc"}
          </button>
          <button
            type="button"
            onClick={() => setShowTranslations((current) => !current)}
            data-testid="word-list-translation-toggle"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            {showTranslations ? "Hide Translation" : "Show Translation"}
          </button>
          <button
            type="button"
            onClick={selectAll}
            data-testid="word-list-select-all-button"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            Select All
          </button>
          <button
            type="button"
            onClick={clearSelection}
            data-testid="word-list-clear-selection-button"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            Unselect All
          </button>
          <button
            type="button"
            onClick={handleBulkRemove}
            disabled={selectedItemIds.size === 0 || busy}
            data-testid="word-list-bulk-remove-button"
            className="rounded-[0.45rem] border border-[#f0c1c1] bg-[#fff5f5] px-3 py-2 text-xs font-semibold text-[#b13a3a] disabled:opacity-50"
          >
            Remove Selected
          </button>
        </div>

        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search"
          data-testid="word-list-search-input"
          className="mt-3 w-full rounded-[0.35rem] border border-[#dce0ee] bg-white px-3 py-2.5 text-sm text-[#43235f] outline-none placeholder:text-[#b6a9c8]"
        />
      </section>

      {message ? <p className="text-sm text-emerald-700" data-testid="word-list-message">{message}</p> : null}
      {error ? <p className="text-sm text-red-600" data-testid="word-list-error">{error}</p> : null}

      <div className="max-h-[32rem] overflow-y-auto pr-1" data-testid="word-list-detail-scroll-region">
        <LearnerListRows
          items={rows}
          showTranslations={showTranslations}
          emptyMessage={query.trim() ? "No entries match this word list search." : "This word list is empty."}
          listTestId="word-list-detail-items"
          emptyTestId="word-list-detail-empty"
          onStatusChange={handleStatusChange}
          renderActions={(item) => (
            <div className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={selectedItemIds.has(item.id)}
                onChange={() => toggleSelected(item.id)}
                data-testid={`word-list-select-item-${item.id}`}
              />
              <button
                type="button"
                onClick={() => void handleRemoveSingle(item.id)}
                data-testid={`word-list-remove-${item.id}`}
                className="rounded-[0.35rem] border border-[#f0c1c1] bg-[#fff5f5] px-2 py-1 text-[0.7rem] font-semibold text-[#b13a3a]"
              >
                Remove
              </button>
            </div>
          )}
        />
      </div>

      <section className="space-y-3 rounded-[0.8rem] border border-[#dce0ee] bg-white px-3 py-3">
        <div>
          <h2 className="text-lg font-semibold text-[#54267f]">Add Entries</h2>
          <p className="text-sm text-[#6b5b86]" data-testid="word-list-editor-help">
            Enter one word per space, or quote multi-word phrases. You can also put one phrase per line.
          </p>
        </div>
        <textarea
          value={bulkText}
          onChange={(event) => setBulkText(event.target.value)}
          data-testid="word-list-editor-text"
          className="min-h-28 w-full rounded-[0.45rem] border border-[#d9dcec] px-3 py-2 text-sm"
        />
        <button
          type="button"
          onClick={handleBulkAdd}
          data-testid="word-list-add-button"
          disabled={busy}
          className="rounded-[0.45rem] bg-[#6f42aa] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
        >
          Bulk Add
        </button>

        <div className="border-t border-[#ece7f5] pt-3">
          <div className="flex gap-2">
            <input
              value={manualAddQuery}
              onChange={(event) => setManualAddQuery(event.target.value)}
              data-testid="word-list-manual-search-input"
              placeholder="Search the catalog"
              className="flex-1 rounded-[0.45rem] border border-[#d9dcec] px-3 py-2 text-sm"
            />
            <button
              type="button"
              onClick={handleManualSearch}
              data-testid="word-list-manual-search-button"
              className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-sm font-semibold text-[#5c3d84]"
            >
              Search
            </button>
          </div>
          {manualAddResults.length > 0 ? (
            <ul className="mt-3 space-y-2" data-testid="word-list-manual-results">
              {manualAddResults.map((entry) => (
                <li key={`${entry.entry_type}-${entry.entry_id}`} className="flex items-center justify-between gap-3 rounded-[0.35rem] border border-[#dce0ee] px-3 py-2">
                  <span className="text-sm font-semibold text-[#35204e]">{entry.display_text}</span>
                  <button
                    type="button"
                    onClick={() => void handleManualAdd(entry)}
                    data-testid={`word-list-manual-add-${entry.entry_id}`}
                    className="rounded-[0.45rem] bg-[#42c2dd] px-3 py-2 text-xs font-semibold text-white"
                  >
                    Add
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      </section>

      {managerOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(48,23,77,0.32)] px-4" data-testid="word-list-manage-modal">
          <div className="w-full max-w-md rounded-[0.9rem] bg-white p-4 shadow-[0_14px_28px_rgba(86,30,147,0.22)]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-[#54267f]">Manage Word List</h2>
              <button
                type="button"
                onClick={() => setManagerOpen(false)}
                className="text-sm font-semibold text-[#7b6795]"
              >
                Close
              </button>
            </div>
            <div className="mt-4 space-y-3">
              <input
                value={nameDraft}
                onChange={(event) => setNameDraft(event.target.value)}
                data-testid="word-list-rename-input"
                className="w-full rounded-[0.45rem] border border-[#d9dcec] px-3 py-2 text-sm"
              />
              <textarea
                value={descriptionDraft}
                onChange={(event) => setDescriptionDraft(event.target.value)}
                data-testid="word-list-description-input"
                className="min-h-24 w-full rounded-[0.45rem] border border-[#d9dcec] px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={handleSaveListMeta}
                data-testid="word-list-rename-button"
                disabled={busy}
                className="w-full rounded-[0.45rem] bg-[#6f42aa] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Save Changes
              </button>
              <button
                type="button"
                onClick={handleDeleteList}
                data-testid="word-list-delete-button"
                disabled={busy}
                className="w-full rounded-[0.45rem] border border-[#f0c1c1] bg-[#fff5f5] px-3 py-2 text-sm font-semibold text-[#b13a3a] disabled:opacity-50"
              >
                Delete Word List
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
