"use client";

import { ReactNode, useMemo, useState } from "react";

type PagedRecordListProps<T> = {
  items: T[];
  selectedId: string | null;
  getId: (item: T) => string;
  onSelect: (id: string) => void;
  renderItem: (item: T, selected: boolean) => ReactNode;
  title: string;
  testId: string;
  pageSize?: number;
  emptyState: ReactNode;
};

export function PagedRecordList<T>({
  items,
  selectedId,
  getId,
  onSelect,
  renderItem,
  title,
  testId,
  pageSize = 10,
  emptyState,
}: PagedRecordListProps<T>) {
  const [page, setPage] = useState(0);
  const pageCount = Math.max(1, Math.ceil(items.length / pageSize));
  const clampedPage = Math.min(page, pageCount - 1);

  const pagedItems = useMemo(
    () => items.slice(clampedPage * pageSize, clampedPage * pageSize + pageSize),
    [clampedPage, items, pageSize],
  );

  return (
    <div className="space-y-3" data-testid={testId}>
      <div className="flex items-center justify-between gap-3">
        <h5 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">{title}</h5>
        <span className="text-xs text-gray-500">
          page {clampedPage + 1} / {pageCount}
        </span>
      </div>
      <div className="space-y-2">
        {pagedItems.map((item) => {
          const id = getId(item);
          const selected = id === selectedId;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={`w-full rounded-lg border p-3 text-left ${selected ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
            >
              {renderItem(item, selected)}
            </button>
          );
        })}
        {items.length === 0 ? emptyState : null}
      </div>
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          data-testid={`${testId}-prev-page`}
          onClick={() => setPage((current) => Math.max(0, Math.min(current, pageCount - 1) - 1))}
          disabled={clampedPage === 0}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
        >
          Previous
        </button>
        <button
          type="button"
          data-testid={`${testId}-next-page`}
          onClick={() => setPage((current) => Math.min(pageCount - 1, Math.min(current, pageCount - 1) + 1))}
          disabled={clampedPage >= pageCount - 1}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
        >
          Next
        </button>
      </div>
    </div>
  );
}
