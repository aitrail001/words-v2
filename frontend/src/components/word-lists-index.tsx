"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { ApiError } from "@/lib/api-client";
import {
  bulkDeleteWordLists,
  createEmptyWordList,
  listWordLists,
  type WordList,
} from "@/lib/imports-client";

const PAGE_SIZE = 12;

export function WordListsIndex() {
  const [wordLists, setWordLists] = useState<WordList[]>([]);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [page, setPage] = useState(0);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [nameDraft, setNameDraft] = useState("");
  const [descriptionDraft, setDescriptionDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let active = true;
    listWordLists()
      .then((lists) => {
        if (active) {
          setWordLists(lists);
        }
      })
      .catch(() => {
        if (active) {
          setError("Failed to load word lists");
        }
      });
    return () => {
      active = false;
    };
  }, []);

  const totalPages = Math.max(1, Math.ceil(wordLists.length / PAGE_SIZE));
  const pageStart = page * PAGE_SIZE;
  const visibleWordLists = wordLists.slice(pageStart, pageStart + PAGE_SIZE);

  const toggleSelected = (wordListId: string) => {
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(wordListId)) {
        next.delete(wordListId);
      } else {
        next.add(wordListId);
      }
      return next;
    });
  };

  const selectAll = () => {
    setSelectedIds(new Set(wordLists.map((wordList) => wordList.id)));
  };

  const clearSelection = () => {
    setSelectedIds(new Set());
  };

  const handleCreate = async () => {
    const trimmedName = nameDraft.trim();
    if (!trimmedName) {
      setError("List name is required");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const created = await createEmptyWordList({
        name: trimmedName,
        description: descriptionDraft.trim() || null,
      });
      setWordLists((current) => [created, ...current]);
      setPage(0);
      setShowCreateModal(false);
      setNameDraft("");
      setDescriptionDraft("");
    } catch (error) {
      if (error instanceof ApiError && error.status === 409) {
        setError("Choose a unique word list name");
      } else {
        setError("Failed to create word list");
      }
    } finally {
      setBusy(false);
    }
  };

  const handleBulkDelete = async () => {
    const ids = Array.from(selectedIds);
    if (ids.length === 0) {
      return;
    }
    if (!window.confirm(`Delete ${ids.length} selected word list${ids.length === 1 ? "" : "s"}?`)) {
      return;
    }

    setBusy(true);
    setError(null);
    try {
      await bulkDeleteWordLists(ids);
      setWordLists((current) => {
        const next = current.filter((wordList) => !selectedIds.has(wordList.id));
        const nextMaxPage = Math.max(0, Math.ceil(next.length / PAGE_SIZE) - 1);
        setPage((currentPage) => Math.min(currentPage, nextMaxPage));
        return next;
      });
      setSelectedIds(new Set());
    } catch {
      setError("Failed to delete selected word lists");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#492160]">
      <section className="rounded-[0.8rem] bg-[#f1f2f8] px-3 py-3">
        <div className="flex items-center justify-between gap-3">
          <Link href="/" data-testid="word-lists-home-link" className="text-2xl font-semibold text-[#6f42aa]">
            ←
          </Link>
          <h1 className="text-[1.45rem] font-semibold tracking-tight text-[#54267f]" data-testid="word-lists-page-title">
            Manage Word Lists
          </h1>
          <Link
            href="/imports"
            data-testid="word-lists-import-link"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            Imports
          </Link>
        </div>

        <div className="mt-3 flex flex-wrap gap-2">
          <button
            type="button"
            data-testid="word-lists-new-button"
            onClick={() => {
              setError(null);
              setShowCreateModal(true);
            }}
            className="rounded-[0.45rem] bg-[#6f42aa] px-3 py-2 text-xs font-semibold text-white"
          >
            New Word List
          </button>
          <button
            type="button"
            data-testid="word-lists-select-all-button"
            onClick={selectAll}
            disabled={wordLists.length === 0}
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84] disabled:opacity-50"
          >
            Select All
          </button>
          <button
            type="button"
            data-testid="word-lists-clear-selection-button"
            onClick={clearSelection}
            disabled={selectedIds.size === 0}
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84] disabled:opacity-50"
          >
            Unselect All
          </button>
          <button
            type="button"
            data-testid="word-lists-bulk-delete-button"
            onClick={handleBulkDelete}
            disabled={selectedIds.size === 0 || busy}
            className="rounded-[0.45rem] border border-[#f0c1c1] bg-[#fff5f5] px-3 py-2 text-xs font-semibold text-[#b13a3a] disabled:opacity-50"
          >
            Delete Selected
          </button>
        </div>
      </section>

      {error ? (
        <p className="text-sm text-red-600" data-testid="word-lists-error">
          {error}
        </p>
      ) : null}

      {wordLists.length === 0 ? (
        <p className="rounded-[0.35rem] border border-[#dce0ee] bg-white px-3 py-4 text-sm text-[#6b5b86]" data-testid="word-lists-empty-state">
          No word lists yet.
        </p>
      ) : (
        <section className="space-y-2" data-testid="word-lists-list">
          {visibleWordLists.map((wordList) => (
            <div
              key={wordList.id}
              className="flex items-center justify-between gap-3 rounded-[0.35rem] border border-[#dce0ee] bg-white px-3 py-3"
            >
              <label className="flex items-center gap-3">
                <input
                  type="checkbox"
                  checked={selectedIds.has(wordList.id)}
                  onChange={() => toggleSelected(wordList.id)}
                  data-testid={`word-list-select-${wordList.id}`}
                />
                <span className="text-sm font-semibold text-[#35204e]">{wordList.name}</span>
              </label>
              <Link
                href={`/word-lists/${wordList.id}`}
                data-testid={`word-list-open-${wordList.id}`}
                className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
              >
                Open
              </Link>
            </div>
          ))}
        </section>
      )}

      {wordLists.length > PAGE_SIZE ? (
        <div className="flex items-center justify-between gap-3 rounded-[0.35rem] border border-[#dce0ee] bg-white px-3 py-3" data-testid="word-lists-pagination">
          <p className="text-sm text-[#6b5b86]">
            {pageStart + 1}-{Math.min(pageStart + PAGE_SIZE, wordLists.length)} of {wordLists.length}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setPage((current) => Math.max(0, current - 1))}
              disabled={page === 0}
              data-testid="word-lists-prev-page-button"
              className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84] disabled:opacity-50"
            >
              Previous
            </button>
            <button
              type="button"
              onClick={() => setPage((current) => Math.min(totalPages - 1, current + 1))}
              disabled={page >= totalPages - 1}
              data-testid="word-lists-next-page-button"
              className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84] disabled:opacity-50"
            >
              Next
            </button>
          </div>
        </div>
      ) : null}

      {showCreateModal ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-[rgba(48,23,77,0.32)] px-4" data-testid="word-lists-create-modal">
          <div className="w-full max-w-md rounded-[0.9rem] bg-white p-4 shadow-[0_14px_28px_rgba(86,30,147,0.22)]">
            <div className="flex items-center justify-between gap-3">
              <h2 className="text-lg font-semibold text-[#54267f]">New Word List</h2>
              <button
                type="button"
                onClick={() => setShowCreateModal(false)}
                className="text-sm font-semibold text-[#7b6795]"
              >
                Close
              </button>
            </div>
            <div className="mt-4 space-y-3">
              <input
                value={nameDraft}
                onChange={(event) => setNameDraft(event.target.value)}
                data-testid="word-lists-create-name-input"
                placeholder="List name"
                className="w-full rounded-[0.45rem] border border-[#d9dcec] px-3 py-2 text-sm"
              />
              <textarea
                value={descriptionDraft}
                onChange={(event) => setDescriptionDraft(event.target.value)}
                data-testid="word-lists-create-description-input"
                placeholder="Description"
                className="min-h-24 w-full rounded-[0.45rem] border border-[#d9dcec] px-3 py-2 text-sm"
              />
              <button
                type="button"
                onClick={handleCreate}
                data-testid="word-lists-create-submit-button"
                disabled={busy}
                className="w-full rounded-[0.45rem] bg-[#6f42aa] px-3 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                Create Word List
              </button>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}
