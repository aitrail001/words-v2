"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  getKnowledgeMapOverview,
  type KnowledgeMapOverview,
  type KnowledgeStatus,
} from "@/lib/knowledge-map-client";

const STATUS_COLORS: Record<KnowledgeStatus, string> = {
  undecided: "#d8dced",
  to_learn: "#a62cff",
  learning: "#c563ff",
  known: "#36c3de",
};

function buildTileGradient(counts: Record<KnowledgeStatus, number>): string {
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  if (total <= 0) {
    return STATUS_COLORS.undecided;
  }

  const orderedStatuses: KnowledgeStatus[] = ["known", "learning", "to_learn", "undecided"];
  let offset = 0;
  const stops = orderedStatuses.map((status) => {
    const start = offset;
    offset += (counts[status] / total) * 100;
    return `${STATUS_COLORS[status]} ${start}% ${offset}%`;
  });
  return `linear-gradient(90deg, ${stops.join(", ")})`;
}

export default function KnowledgeMapPage() {
  const [overview, setOverview] = useState<KnowledgeMapOverview | null>(null);

  useEffect(() => {
    let active = true;

    getKnowledgeMapOverview()
      .then((payload) => {
        if (!active) {
          return;
        }
        setOverview(payload);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setOverview({ bucket_size: 100, total_entries: 0, ranges: [] });
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div
      data-testid="knowledge-map-mobile-shell"
      className="mx-auto max-w-[46rem] space-y-3 pb-10 text-[#43235f]"
    >
      <section className="rounded-[0.8rem] bg-[#f1f2f8] px-2 py-2">
        <div className="flex items-center justify-between">
          <span className="w-8 text-xl text-[#7d52c7]">{""}</span>
          <h2 className="text-center text-[1.8rem] font-semibold tracking-tight text-[#502a7d]">
            Full Knowledge Map
          </h2>
          <span className="w-8 text-right text-sm font-semibold text-[#7d52c7]">
            {overview?.total_entries ?? "..."}
          </span>
        </div>
        <p className="mt-3 text-sm leading-6 text-[#6b5d86]">
          This is a map of your English knowledge. Each box shows 100 words and phrases.
          They are sorted by relevance to your life. Discover them all, starting from the top.
        </p>

        <div data-testid="knowledge-map-tile-grid" className="mt-3 grid grid-cols-5 gap-1">
          {overview?.ranges.map((range) => (
            <Link
              key={range.range_start}
              href={`/knowledge-map/range/${range.range_start}`}
              aria-label={`${range.range_start}-${range.range_end}`}
              className="rounded-[0.18rem] border border-white/70 px-1 py-1.5 text-center text-[0.68rem] font-semibold shadow-sm transition"
              style={{ backgroundImage: buildTileGradient(range.counts) }}
            >
              {range.range_start}-{range.range_end}
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
