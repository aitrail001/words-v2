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
  const dashboardReady = dashboard !== null;
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
  const discoverHref = dashboard?.discovery_range_start ? `/knowledge-map?rangeStart=${dashboard.discovery_range_start}` : "/knowledge-map";
  const learnHref = dashboard?.next_learn_entry
    ? getKnowledgeEntryHref(
        dashboard.next_learn_entry.entry_type,
        dashboard.next_learn_entry.entry_id,
      )
    : "/knowledge-map";

  return (
    <div className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#472164]">
      <section className="overflow-hidden rounded-[1.2rem] bg-[linear-gradient(180deg,#6b17ab_0%,#64159e_55%,#621598_100%)] px-3 py-3 text-white shadow-[0_14px_28px_rgba(86,30,147,0.22)]">
        <div className="flex items-center justify-between">
          <button
            type="button"
            aria-label="Menu"
            className="rounded-full bg-white/8 px-2.5 py-1.5 text-base font-semibold"
          >
            ≡
          </button>
          <div className="flex items-center gap-3">
            <Link
              href="/search"
              aria-label="Search"
              className="rounded-full bg-white/8 px-2.5 py-1.5 text-base font-semibold"
            >
              ⌕
            </Link>
            <Link
              href="/settings"
              aria-label="Settings"
              className="flex h-8 w-8 items-center justify-center overflow-hidden rounded-full border border-white/40 bg-white/15 text-sm font-semibold text-[#52e4f1]"
            >
              ○
            </Link>
          </div>
        </div>

        <div className="mt-4 flex items-center gap-3">
          <div className="flex h-14 w-14 items-center justify-center overflow-hidden rounded-full border-2 border-white/30 bg-[linear-gradient(145deg,#e7ebf5,#f8f3ff)] text-center text-[0.55rem] font-semibold uppercase tracking-[0.18em] text-[#7449b1]">
            Lexi
          </div>
          <div className="flex-1">
            <span className="sr-only">Words Uncovered</span>
            <p className="text-[1.15rem] font-semibold leading-tight">
              <span className="block">Words</span>
              <span className="block">Uncovered</span>
            </p>
          </div>
          <Link href="/knowledge-map" className="text-[2.15rem] font-semibold tracking-tight">
            {formatCount(totalEntries)}
          </Link>
        </div>

        <div className="mt-4 overflow-hidden rounded-full bg-white/16">
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

        <div className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-[0.88rem] font-semibold">
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

      <section className="rounded-[0.85rem] bg-[#eef0f7] px-2 py-2">
        <h2 className="text-center text-[1.5rem] font-semibold tracking-tight text-[#5b2590]">
          Knowledge Map
        </h2>
        <p className="mt-1 text-center text-[0.86rem] leading-5 text-[#7b6795]">
          Discover what you need to learn next.
        </p>

        <div className="mt-3 grid grid-cols-2 gap-2">
          {dashboardReady ? (
            <Link
              href={discoverHref}
              className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white shadow-[0_6px_14px_rgba(78,41,126,0.06)]"
            >
              <div className="grid h-36 grid-cols-2 gap-1 bg-[#f3eef9] p-1.5">
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#756a5c,#d4c49b)]" />
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#6f9dc8,#f2d6d1)]" />
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#45425a,#9691cc)]" />
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#8b7a5d,#d9cdaa)]" />
              </div>
              <div className="space-y-2 px-3 py-3">
                <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#c066ff] px-4 py-2.5 text-base font-semibold text-white">
                  Discover
                </div>
                <p className="text-center text-sm font-semibold text-[#9b85b4]">
                  Range {dashboard?.discovery_range_start ? Math.floor(dashboard.discovery_range_start / 100) * 100 : 0}
                </p>
              </div>
            </Link>
          ) : (
            <div
              aria-label="Discover loading"
              className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white opacity-70 shadow-[0_6px_14px_rgba(78,41,126,0.06)]"
            >
              <div className="grid h-36 grid-cols-2 gap-1 bg-[#f3eef9] p-1.5">
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#756a5c,#d4c49b)]" />
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#6f9dc8,#f2d6d1)]" />
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#45425a,#9691cc)]" />
                <div className="rounded-[0.15rem] bg-[linear-gradient(140deg,#8b7a5d,#d9cdaa)]" />
              </div>
              <div className="space-y-2 px-3 py-3">
                <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#c066ff] px-4 py-2.5 text-base font-semibold text-white">
                  Discover
                </div>
                <p className="text-center text-sm font-semibold text-[#9b85b4]">
                  Loading...
                </p>
              </div>
            </div>
          )}
          {dashboardReady ? (
            <Link
              href={learnHref}
              aria-label={`Learn next: ${dashboard?.next_learn_entry?.display_text ?? "Nothing queued"}`}
              className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white shadow-[0_6px_14px_rgba(78,41,126,0.06)]"
            >
              <div className="h-36 bg-[linear-gradient(145deg,#49517d,#4a1d76_42%,#45c1d8)]" />
              <div className="space-y-2 px-3 py-3">
                <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#42c2dd] px-4 py-2.5 text-base font-semibold text-white">
                  Learn
                </div>
                <p className="text-center text-sm font-semibold text-[#9b85b4]">
                  Next: {dashboard?.next_learn_entry?.display_text ?? "Nothing queued"}
                </p>
              </div>
            </Link>
          ) : (
            <div
              aria-label="Learn loading"
              className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white opacity-70 shadow-[0_6px_14px_rgba(78,41,126,0.06)]"
            >
              <div className="h-36 bg-[linear-gradient(145deg,#49517d,#4a1d76_42%,#45c1d8)]" />
              <div className="space-y-2 px-3 py-3">
                <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#42c2dd] px-4 py-2.5 text-base font-semibold text-white">
                  Learn
                </div>
                <p className="text-center text-sm font-semibold text-[#9b85b4]">
                  Loading...
                </p>
              </div>
            </div>
          )}
        </div>
      </section>

      <div className="grid gap-3 md:grid-cols-2">
        <section className="rounded-[0.85rem] bg-white px-3 py-3 shadow-[0_8px_18px_rgba(190,112,44,0.08)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-tight text-[#9a4f12]">
                Import EPUB
              </h2>
              <p className="mt-1 text-[0.86rem] leading-5 text-[#8d6d58]">
                Upload a book, extract matched entries, and review them before creating a list.
              </p>
            </div>
            <Link
              href="/imports"
              className="rounded-full bg-[#c76827] px-4 py-2 text-sm font-semibold text-white"
            >
              Open
            </Link>
          </div>
        </section>

        <section className="rounded-[0.85rem] bg-white px-3 py-3 shadow-[0_8px_18px_rgba(52,118,191,0.08)]">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-[1.25rem] font-semibold tracking-tight text-[#235b92]">
                Manage Word Lists
              </h2>
              <p className="mt-1 text-[0.86rem] leading-5 text-[#61768f]">
                Rename, search, sort, and edit the entries already saved in your lists.
              </p>
            </div>
            <Link
              href="/word-lists"
              className="rounded-full bg-[#2f73b3] px-4 py-2 text-sm font-semibold text-white"
            >
              Open
            </Link>
          </div>
        </section>
      </div>
    </div>
  );
}
