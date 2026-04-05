"use client";

import type { ReactNode } from "react";
import Link from "next/link";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import type { KnowledgeEntryType, KnowledgeStatus } from "@/lib/knowledge-map-client";
import { getKnowledgeStatusSelectOptions } from "@/lib/knowledge-status-policy";

const ROW_STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "New",
  to_learn: "To Learn",
  learning: "Learning",
  known: "Already knew",
};

function normalizeRowTranslation(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  if (!trimmed || trimmed === "Translation unavailable") {
    return null;
  }
  return trimmed;
}

function normalizePrimaryDefinition(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}

function normalizePrimaryExample(value: string | null | undefined): string | null {
  if (!value) {
    return null;
  }
  const trimmed = value.trim();
  return trimmed || null;
}

function rowImageStyle(seed: string): string {
  const styles = [
    "bg-[linear-gradient(145deg,#3f3b4e,#809fcc)]",
    "bg-[linear-gradient(145deg,#85745d,#f0dcc4)]",
    "bg-[linear-gradient(145deg,#405767,#59c8de)]",
    "bg-[linear-gradient(145deg,#5e3654,#d58bc8)]",
  ];
  const hash = Array.from(seed).reduce((sum, char) => sum + char.charCodeAt(0), 0);
  return styles[hash % styles.length];
}

export type LearnerListRowItem = {
  entry_type: KnowledgeEntryType;
  entry_id: string;
  display_text: string;
  browse_rank?: number | null;
  status: KnowledgeStatus;
  translation?: string | null;
  primary_definition?: string | null;
  primary_example?: string | null;
  primary_example_translation?: string | null;
};

type LearnerListRowsProps<TItem extends LearnerListRowItem> = {
  items: TItem[];
  showTranslations: boolean;
  emptyMessage: string;
  listTestId: string;
  emptyTestId: string;
  onStatusChange?: (item: TItem, nextStatus: KnowledgeStatus) => void | Promise<void>;
  renderActions?: (item: TItem) => ReactNode;
};

export function LearnerListRows<TItem extends LearnerListRowItem>({
  items,
  showTranslations,
  emptyMessage,
  listTestId,
  emptyTestId,
  onStatusChange,
  renderActions,
}: LearnerListRowsProps<TItem>) {
  if (items.length === 0) {
    return (
      <p className="rounded-[0.35rem] border border-[#dce0ee] bg-white px-3 py-4 text-sm text-[#6b5b86]" data-testid={emptyTestId}>
        {emptyMessage}
      </p>
    );
  }

  return (
    <section className="max-h-[34rem] space-y-1.5 overflow-y-auto pr-1" data-testid={listTestId}>
      {items.map((item) => (
        <div
          key={`${item.entry_type}-${item.entry_id}`}
          className="grid grid-cols-[4.5rem_1fr] gap-2 overflow-hidden rounded-[0.25rem] border border-[#dce0ee] bg-white px-2 py-2"
        >
          <Link
            href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
            className={`min-h-[4.75rem] rounded-[0.15rem] ${rowImageStyle(item.display_text)}`}
          />
          <div className="space-y-1 py-0.5">
            <Link href={getKnowledgeEntryHref(item.entry_type, item.entry_id)} className="block">
              <div className="flex items-start justify-between gap-3">
                <div className="space-y-1">
                  <p className="text-[1.1rem] font-semibold leading-none text-[#35204e]">{item.display_text}</p>
                  {typeof item.browse_rank === "number" ? (
                    <p className="text-[0.68rem] font-semibold uppercase tracking-[0.12em] text-[#8f82a1]">
                      #{item.browse_rank}
                    </p>
                  ) : null}
                </div>
              </div>
              {normalizePrimaryDefinition(item.primary_definition) ? (
                <p className="mt-1 text-[0.82rem] font-semibold leading-5 text-[#6b5b86]">
                  {normalizePrimaryDefinition(item.primary_definition)}
                </p>
              ) : null}
              {showTranslations && normalizeRowTranslation(item.translation) ? (
                <p className="mt-0.5 text-[0.78rem] leading-5 text-[#8b78a5]">
                  {normalizeRowTranslation(item.translation)}
                </p>
              ) : null}
              {normalizePrimaryExample(item.primary_example) ? (
                <p className="mt-1 text-[0.78rem] italic leading-5 text-[#5f5674]">
                  {normalizePrimaryExample(item.primary_example)}
                </p>
              ) : null}
              {showTranslations && normalizeRowTranslation(item.primary_example_translation) ? (
                <p className="mt-0.5 text-[0.76rem] leading-5 text-[#9b8cb2]">
                  {normalizeRowTranslation(item.primary_example_translation)}
                </p>
              ) : null}
            </Link>

            <div className="flex items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-2">
                <p className="text-[0.72rem] font-semibold text-[#48bfd7]">
                  {ROW_STATUS_LABELS[item.status]} ▼
                </p>
                {renderActions ? renderActions(item) : null}
              </div>
              {onStatusChange ? (
                <>
                  <label className="sr-only" htmlFor={`status-${item.entry_type}-${item.entry_id}`}>
                    Update status
                  </label>
                  <select
                    id={`status-${item.entry_type}-${item.entry_id}`}
                    value={item.status}
                    onChange={(event) => void onStatusChange(item, event.target.value as KnowledgeStatus)}
                    className="max-w-[8.2rem] rounded-[0.35rem] border border-[#dce0ee] bg-[#f8fbff] px-2 py-1.5 text-[0.72rem] font-semibold text-[#4bc5db] outline-none"
                  >
                    {getKnowledgeStatusSelectOptions(item.status).map((option) => (
                      <option key={option.status} value={option.status}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </>
              ) : null}
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
