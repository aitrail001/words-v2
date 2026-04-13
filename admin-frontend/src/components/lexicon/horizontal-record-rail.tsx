"use client";

import { ReactNode, useMemo, useState } from "react";

type HorizontalRecordRailProps<T> = {
  items: T[];
  selectedId: string | null;
  getId: (item: T) => string;
  onSelect: (id: string) => void;
  renderItem: (item: T, selected: boolean) => ReactNode;
  title: string;
  testId: string;
  windowSize?: number;
};

export function HorizontalRecordRail<T>({
  items,
  selectedId,
  getId,
  onSelect,
  renderItem,
  title,
  testId,
  windowSize = 3,
}: HorizontalRecordRailProps<T>) {
  const [windowStart, setWindowStart] = useState(0);
  const maxWindowStart = Math.max(0, items.length - windowSize);
  const clampedWindowStart = Math.min(windowStart, maxWindowStart);

  const visibleItems = useMemo(
    () => items.slice(clampedWindowStart, clampedWindowStart + windowSize),
    [clampedWindowStart, items, windowSize],
  );

  return (
    <section className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm" data-testid={testId}>
      <div className="flex items-center justify-between gap-3">
        <h4 className="text-sm font-semibold uppercase tracking-[0.18em] text-gray-500">{title}</h4>
        <div className="flex items-center gap-2">
          <button
            type="button"
            data-testid={`${testId}-prev`}
            onClick={() => setWindowStart((current) => Math.max(0, Math.min(current, maxWindowStart) - 1))}
            disabled={clampedWindowStart === 0}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            Previous
          </button>
          <button
            type="button"
            data-testid={`${testId}-next`}
            onClick={() => setWindowStart((current) => Math.min(maxWindowStart, Math.min(current, maxWindowStart) + 1))}
            disabled={clampedWindowStart + windowSize >= items.length}
            className="rounded-md border border-gray-300 px-3 py-2 text-sm text-gray-700 disabled:opacity-50"
          >
            Next
          </button>
        </div>
      </div>
      <div className="mt-4 grid gap-3 lg:grid-cols-3">
        {visibleItems.map((item) => {
          const id = getId(item);
          const selected = id === selectedId;
          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={`rounded-lg border p-3 text-left ${selected ? "border-blue-400 bg-blue-50" : "border-gray-200 bg-white hover:bg-gray-50"}`}
            >
              {renderItem(item, selected)}
            </button>
          );
        })}
      </div>
    </section>
  );
}
