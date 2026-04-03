"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";
import { LearnerListRows } from "@/components/learner-list-rows";
import {
  getKnowledgeMapList,
  type KnowledgeMapEntrySummary,
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

type KnowledgeListSortMode = "alpha" | "rank";
type KnowledgeListSortOrder = "asc" | "desc";

export default function KnowledgeListPage() {
  const params = useParams<{ status: string }>();
  const routeStatus = params?.status ?? "known";
  const config = STATUS_PAGE_META[routeStatus] ?? STATUS_PAGE_META.known;

  const [items, setItems] = useState<KnowledgeMapEntrySummary[]>([]);
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<KnowledgeListSortMode>("alpha");
  const [order, setOrder] = useState<KnowledgeListSortOrder>("asc");
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
      order,
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
  }, [config.listStatus, order, query, sort]);

  const cycleSort = () => {
    const options: KnowledgeListSortMode[] = ["alpha", "rank"];
    const nextIndex = (options.indexOf(sort) + 1) % options.length;
    setSort(options[nextIndex]);
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
    <div className="mx-auto max-w-[46rem] space-y-3 pb-10 text-[#492160]">
      <section className="rounded-[0.8rem] bg-[#f1f2f8] px-2 py-2">
        <div className="flex items-center justify-between">
          <Link href="/" className="text-2xl font-semibold text-[#6f42aa]">
            ←
          </Link>
          <h1 className="text-[1.45rem] font-semibold tracking-tight text-[#54267f]">{config.title}</h1>
          <button
            type="button"
            onClick={cycleSort}
            data-testid="knowledge-list-sort-button"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            ↕ {sort === "alpha" ? "Alphabetic" : "Difficulty"}
          </button>
          <button
            type="button"
            onClick={() => setOrder((current) => (current === "asc" ? "desc" : "asc"))}
            data-testid="knowledge-list-order-button"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            {order === "asc" ? "↑ Asc" : "↓ Desc"}
          </button>
          <button
            type="button"
            onClick={() => setShowTranslations((current) => !current)}
            data-testid="knowledge-list-translation-toggle"
            className="rounded-[0.45rem] border border-[#d9dcec] bg-white px-3 py-2 text-xs font-semibold text-[#5c3d84]"
          >
            {showTranslations ? "Hide Translation" : "Show Translation"}
          </button>
        </div>

        <input
          type="text"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search"
          className="mt-3 w-full rounded-[0.35rem] border border-[#dce0ee] bg-white px-3 py-2.5 text-sm text-[#43235f] outline-none placeholder:text-[#b6a9c8]"
        />
      </section>

      <LearnerListRows
        items={items}
        showTranslations={showTranslations}
        emptyMessage="No entries match this filter yet."
        listTestId="knowledge-list-view"
        emptyTestId="knowledge-list-empty"
        onStatusChange={handleStatusChange}
      />
    </div>
  );
}
