"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getKnowledgeMapDashboard,
  type KnowledgeMapDashboard,
} from "@/lib/knowledge-map-client";

function formatCount(value: number): string {
  return value.toLocaleString();
}

export default function HomePage() {
  const [dashboard, setDashboard] = useState<KnowledgeMapDashboard | null>(null);

  useEffect(() => {
    let active = true;

    getKnowledgeMapDashboard()
      .then((response) => {
        if (active) {
          setDashboard(response);
        }
      })
      .catch(() => {
        if (active) {
          setDashboard({
            total_entries: 0,
            counts: { undecided: 0, to_learn: 0, learning: 0, known: 0 },
            discovery_range_start: null,
            discovery_range_end: null,
            discovery_entry: null,
            next_learn_entry: null,
          });
        }
      });

    return () => {
      active = false;
    };
  }, []);

  const totalEntries = dashboard?.total_entries ?? 0;
  const newCount = dashboard?.counts.undecided ?? 0;
  const learningCount = dashboard?.counts.learning ?? 0;
  const toLearnCount = dashboard?.counts.to_learn ?? 0;
  const knownCount = dashboard?.counts.known ?? 0;
  const progressTotal = learningCount + toLearnCount + knownCount;
  const progressSegments = progressTotal > 0
    ? [
        { label: "Known", value: knownCount, color: "bg-[#3dc8df]" },
        { label: "Started", value: learningCount, color: "bg-[#b674ff]" },
        { label: "To Learn", value: toLearnCount, color: "bg-[#dd49ff]" },
      ]
    : [];

  return (
    <div className="mx-auto max-w-[27rem] space-y-5 pb-10 text-[#472164]">
      <section className="overflow-hidden rounded-[2.1rem] bg-[linear-gradient(180deg,#6e22b8_0%,#6a1fb1_35%,#63209d_100%)] px-5 py-6 text-white shadow-[0_20px_44px_rgba(86,30,147,0.28)]">
        <div className="flex items-center justify-between">
          <button
            type="button"
            aria-label="Menu"
            className="rounded-full bg-white/10 px-3 py-2 text-lg font-semibold"
          >
            ≡
          </button>
          <div className="flex items-center gap-3">
            <Link
              href="/knowledge-map"
              aria-label="Search"
              className="rounded-full bg-white/10 px-3 py-2 text-lg font-semibold"
            >
              ⌕
            </Link>
            <Link
              href="/settings"
              aria-label="Settings"
              className="rounded-full border-2 border-[#3dd4e5] bg-white/10 px-3 py-2 text-lg font-semibold text-[#52e4f1]"
            >
              ✓
            </Link>
          </div>
        </div>

        <div className="mt-6 flex items-center gap-4">
          <div className="flex h-20 w-20 items-center justify-center overflow-hidden rounded-full border-4 border-white/30 bg-[linear-gradient(145deg,#e7ebf5,#f8f3ff)] text-center text-[0.62rem] font-semibold uppercase tracking-[0.2em] text-[#7449b1]">
            Lexi
          </div>
          <div className="flex-1">
            <p className="text-[2rem] font-semibold leading-none">Words Uncovered</p>
          </div>
          <Link href="/knowledge-map" className="text-[2.6rem] font-semibold tracking-tight">
            {formatCount(totalEntries)}
          </Link>
        </div>

        <div className="mt-6 overflow-hidden rounded-full bg-white/20">
          <div className="flex h-3 w-full">
            {progressSegments.map((segment) => (
              <div
                key={segment.label}
                className={segment.color}
                style={{ width: `${(segment.value / progressTotal) * 100}%` }}
              />
            ))}
          </div>
        </div>

        <div className="mt-4 grid grid-cols-2 gap-x-6 gap-y-2 text-[1.05rem] font-semibold">
          <Link href="/knowledge-list/known" className="text-[#36d0e6]">
            Knew {formatCount(knownCount)}
          </Link>
          <Link href="/knowledge-list/to-learn" className="text-right text-[#d28fff]">
            To Learn {formatCount(toLearnCount)}
          </Link>
          <Link href="/knowledge-list/learning" className="col-span-2 text-right text-[#e0b6ff]">
            Started {formatCount(learningCount)}
          </Link>
        </div>
      </section>

      <section className="rounded-[2rem] bg-white/90 px-5 py-6 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <h2 className="text-center text-[2rem] font-semibold tracking-tight text-[#5b2590]">
          Knowledge Map
        </h2>
        <p className="mt-2 text-center text-sm leading-6 text-[#7b6795]">
          Discover what you need to learn next.
        </p>

        <div className="mt-5 grid grid-cols-2 gap-4">
          <Link
            href={dashboard?.discovery_range_start ? `/knowledge-map?rangeStart=${dashboard.discovery_range_start}` : "/knowledge-map"}
            className="overflow-hidden rounded-[1.1rem] border border-[#e5ddf4] bg-white shadow-[0_12px_28px_rgba(78,41,126,0.08)]"
          >
            <div className="grid h-36 grid-cols-2 gap-1 bg-[#f3eef9] p-2">
              <div className="rounded-[0.7rem] bg-[linear-gradient(140deg,#756a5c,#d4c49b)]" />
              <div className="rounded-[0.7rem] bg-[linear-gradient(140deg,#6f9dc8,#f2d6d1)]" />
              <div className="rounded-[0.7rem] bg-[linear-gradient(140deg,#f4c672,#f8efe0)]" />
              <div className="rounded-[0.7rem] bg-[linear-gradient(140deg,#45425a,#9691cc)]" />
            </div>
            <div className="space-y-3 px-4 py-4">
              <div className="inline-flex rounded-[1rem] bg-[#c066ff] px-5 py-3 text-lg font-semibold text-white">
                Discover
              </div>
              <p className="text-center text-base font-semibold text-[#9b85b4]">
                Range {dashboard?.discovery_range_start ? Math.floor(dashboard.discovery_range_start / 100) * 100 : 0}
              </p>
            </div>
          </Link>

          <Link
            href={
              dashboard?.next_learn_entry
                ? getKnowledgeEntryHref(
                    dashboard.next_learn_entry.entry_type,
                    dashboard.next_learn_entry.entry_id,
                  )
                : "/knowledge-map"
            }
            className="overflow-hidden rounded-[1.1rem] border border-[#e5ddf4] bg-white shadow-[0_12px_28px_rgba(78,41,126,0.08)]"
          >
            <div className="h-36 bg-[linear-gradient(145deg,#49517d,#4a1d76_42%,#45c1d8)]" />
            <div className="space-y-3 px-4 py-4">
              <div className="inline-flex rounded-[1rem] bg-[#42c2dd] px-7 py-3 text-lg font-semibold text-white">
                Learn
              </div>
              <p className="text-center text-base font-semibold text-[#9b85b4]">
                Next: {dashboard?.next_learn_entry?.display_text ?? "Nothing queued"}
              </p>
            </div>
          </Link>
        </div>
      </section>

      <section className="rounded-[2rem] bg-white/88 px-5 py-6 shadow-[0_18px_42px_rgba(84,46,135,0.12)]">
        <h2 className="text-center text-[2rem] font-semibold tracking-tight text-[#5b2590]">
          Practice with Lexi
        </h2>
        <p className="mt-2 text-center text-sm leading-6 text-[#7b6795]">
          Your AI tutor for reading, writing and speaking.
        </p>

        <div className="mt-5 grid grid-cols-3 gap-3">
          {["Vocabulary", "Writing", "Speaking"].map((label, index) => (
            <div
              key={label}
              className="overflow-hidden rounded-[1rem] border border-[#eadff8] bg-white shadow-[0_10px_24px_rgba(86,54,145,0.08)]"
            >
              <div
                className={`h-24 ${
                  index === 1
                    ? "bg-[linear-gradient(145deg,#74dff1,#2bb7d5)]"
                    : "bg-[linear-gradient(145deg,#cd7cff,#9141df)]"
                }`}
              />
              <p className="px-2 py-3 text-center text-lg font-semibold text-[#5b2a85]">{label}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
