"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getKnowledgeMapList,
  type KnowledgeMapEntrySummary,
  type KnowledgeMapListSort,
  type KnowledgeMapListStatus,
  type KnowledgeStatus,
  updateKnowledgeEntryStatus,
} from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

const STATUS_PAGE_META: Record<string, { title: string; listStatus: KnowledgeMapListStatus }> = {
  known: { title: "Knew Words", listStatus: "known" },
  new: { title: "New Words", listStatus: "new" },
  learning: { title: "Learning Words", listStatus: "learning" },
  "to-learn": { title: "To Learn", listStatus: "to_learn" },
};

const ROW_STATUS_LABELS: Record<KnowledgeStatus, string> = {
  undecided: "New",
  to_learn: "To Learn",
  learning: "Learning",
  known: "Already knew",
};

const SORT_OPTIONS: Array<{ value: KnowledgeMapListSort; label: string }> = [
  { value: "alpha", label: "Alphabetic" },
  { value: "rank_desc", label: "Hardest First" },
  { value: "rank", label: "Easiest First" },
];

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

export default function KnowledgeListPage() {
  const params = useParams<{ status: string }>();
  const routeStatus = params?.status ?? "known";
  const config = STATUS_PAGE_META[routeStatus] ?? STATUS_PAGE_META.known;

  const [items, setItems] = useState<KnowledgeMapEntrySummary[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<KnowledgeMapListSort>("alpha");
  const [showTranslations, setShowTranslations] = useState(true);

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

    getKnowledgeMapList({
      status: config.listStatus,
      q: query.trim() || undefined,
      sort,
      limit: 100,
    })
      .then((response) => {
        if (active) {
          setItems(response.items);
        }
      })
      .catch(() => {
        if (active) {
          setItems([]);
        }
      });

    return () => {
      active = false;
    };
  }, [config.listStatus, query, sort]);

  const cycleSort = () => {
    const currentIndex = SORT_OPTIONS.findIndex((option) => option.value === sort);
    const nextOption = SORT_OPTIONS[(currentIndex + 1) % SORT_OPTIONS.length];
    setSort(nextOption.value);
  };

  const handleStatusChange = async (
    item: KnowledgeMapEntrySummary,
    nextStatus: KnowledgeStatus,
  ) => {
    const response = await updateKnowledgeEntryStatus(item.entry_type, item.entry_id, nextStatus);
    setItems((current) =>
      current.map((entry) =>
        entry.entry_id === item.entry_id && entry.entry_type === item.entry_type
          ? { ...entry, status: response.status }
          : entry,
      ),
    );
  };

  return (
    <div className="mx-auto max-w-[27rem] space-y-4 pb-10 text-[#492160]">
      <section className="rounded-[2rem] bg-white/92 px-4 py-4 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <div className="flex items-center justify-between">
          <Link href="/" className="text-2xl font-semibold text-[#6f42aa]">
            ←
          </Link>
          <h1 className="text-[1.8rem] font-semibold tracking-tight text-[#54267f]">{config.title}</h1>
          <button
            type="button"
            onClick={cycleSort}
            className="rounded-full border border-[#ebdffc] bg-[#faf7ff] px-3 py-2 text-xs font-semibold uppercase tracking-[0.12em] text-[#5c3d84]"
          >
            {SORT_OPTIONS.find((option) => option.value === sort)?.label}
          </button>
        </div>

        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search"
          className="mt-4 w-full rounded-[0.8rem] border border-[#e2daef] bg-white px-4 py-3 text-sm text-[#43235f] outline-none placeholder:text-[#b6a9c8]"
        />
      </section>

      <section className="space-y-2.5">
        {items.map((item) => (
          <div
            key={`${item.entry_type}-${item.entry_id}`}
            className="grid grid-cols-[4.9rem_1fr] gap-3 overflow-hidden rounded-[1.2rem] bg-white/94 px-3 py-3 shadow-[0_12px_28px_rgba(78,41,126,0.08)]"
          >
            <Link
              href={getKnowledgeEntryHref(item.entry_type, item.entry_id)}
              className={`min-h-[5.25rem] rounded-[0.95rem] ${rowImageStyle(item.display_text)}`}
            />
            <div className="space-y-1.5 py-0.5">
              <Link href={getKnowledgeEntryHref(item.entry_type, item.entry_id)} className="block">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[1.45rem] font-semibold leading-none text-[#4e216f]">{item.display_text}</p>
                  <p className="text-[0.72rem] font-semibold uppercase tracking-[0.12em] text-[#a68ebb]">
                    {ROW_STATUS_LABELS[item.status]}
                  </p>
                </div>
                {showTranslations && (
                  <p className="mt-1.5 text-[0.95rem] font-semibold leading-6 text-[#6b5b86]">
                    {item.translation ?? item.primary_definition ?? "No translation yet"}
                  </p>
                )}
              </Link>

              <div className="pt-1">
                <label className="sr-only" htmlFor={`status-${item.entry_id}`}>
                  Update status
                </label>
                <select
                  id={`status-${item.entry_id}`}
                  value={item.status}
                  onChange={(event) => void handleStatusChange(item, event.target.value as KnowledgeStatus)}
                  className="rounded-full border border-[#e2ddf0] bg-[#f4f6fb] px-3 py-2 text-sm font-semibold text-[#4bc5db] outline-none"
                >
                  <option value="undecided">New</option>
                  <option value="to_learn">To Learn</option>
                  <option value="learning">Learning</option>
                  <option value="known">Already knew</option>
                </select>
              </div>
            </div>
          </div>
        ))}
      </section>
    </div>
  );
}
