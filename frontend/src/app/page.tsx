"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { getKnowledgeEntryHref } from "@/components/knowledge-entry-detail-page";
import {
  getAuthUserProfile,
  getKnowledgeMapDashboard,
  getReviewQueueStats,
  type AuthUserProfile,
  type KnowledgeMapDashboard,
  type ReviewQueueStats,
} from "@/lib/knowledge-map-client";

function formatCount(value: number): string {
  return value.toLocaleString();
}

export default function HomePage() {
  const [dashboard, setDashboard] = useState<KnowledgeMapDashboard | null>(null);
  const [reviewQueueStats, setReviewQueueStats] = useState<ReviewQueueStats | null>(null);
  const [currentUser, setCurrentUser] = useState<AuthUserProfile | null>(null);

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

  useEffect(() => {
    let active = true;

    getAuthUserProfile()
      .then((response) => {
        if (active) {
          setCurrentUser(response);
        }
      })
      .catch(() => {
        if (active) {
          setCurrentUser(null);
        }
      });

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;

    getReviewQueueStats()
      .then((response) => {
        if (active) {
          setReviewQueueStats(response);
        }
      })
      .catch(() => {
        if (active) {
          setReviewQueueStats({
            total_items: 0,
            due_items: 0,
            review_count: 0,
            correct_count: 0,
            accuracy: 0,
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
  const dueReviewCount = reviewQueueStats?.due_items ?? 0;
  const isAdminUser = currentUser?.role === "admin";

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

      {(reviewQueueStats?.total_items ?? 0) > 0 ? (
        <section className="rounded-[0.85rem] bg-[#eef0f7] px-2 py-2">
          <h2 className="text-center text-[1.5rem] font-semibold tracking-tight text-[#5b2590]">
            Review
          </h2>
          <p className="mt-1 text-center text-[0.86rem] leading-5 text-[#7b6795]">
            Keep your spaced repetition queue moving.
          </p>

          <div className={`mt-3 grid gap-2 ${isAdminUser ? "grid-cols-3" : "grid-cols-2"}`}>
            {dueReviewCount > 0 ? (
              <Link
                href="/review"
                aria-label="Start Review"
                className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white shadow-[0_6px_14px_rgba(78,41,126,0.06)]"
              >
                <div className="flex h-36 items-center justify-center bg-[linear-gradient(145deg,#4d2283,#7b32d3_58%,#4dc8de)] px-4">
                  <div className="text-center text-white">
                    <p className="text-[0.74rem] font-semibold uppercase tracking-[0.16em] text-white/75">
                      Due Today
                    </p>
                    <p className="mt-2 text-[2.8rem] font-semibold leading-none">
                      {formatCount(dueReviewCount)}
                    </p>
                  </div>
                </div>
                <div className="space-y-2 px-3 py-3">
                  <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#7b32d3] px-4 py-2.5 text-base font-semibold text-white">
                    Start Review
                  </div>
                  <p className="text-center text-sm font-semibold text-[#9b85b4]">
                    {`${dueReviewCount} due today`}
                  </p>
                </div>
              </Link>
            ) : (
              <div className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white shadow-[0_6px_14px_rgba(78,41,126,0.06)]">
                <div className="flex h-36 items-center justify-center bg-[linear-gradient(145deg,#4d2283,#7b32d3_58%,#4dc8de)] px-4">
                  <div className="text-center text-white">
                    <p className="text-[0.74rem] font-semibold uppercase tracking-[0.16em] text-white/75">
                      Due Today
                    </p>
                    <p className="mt-2 text-[2.8rem] font-semibold leading-none">
                      {formatCount(dueReviewCount)}
                    </p>
                  </div>
                </div>
                <div className="space-y-2 px-3 py-3">
                  <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#7b32d3] px-4 py-2.5 text-base font-semibold text-white">
                    No Reviews Due
                  </div>
                  <p className="text-center text-sm font-semibold text-[#9b85b4]">
                    {`${reviewQueueStats?.total_items ?? 0} items waiting in your queue`}
                  </p>
                </div>
              </div>
            )}

            <Link
              href="/review/queue"
              className="overflow-hidden rounded-[0.35rem] border border-[#dadceb] bg-white shadow-[0_6px_14px_rgba(78,41,126,0.06)]"
            >
              <div className="flex h-36 items-center justify-center bg-[linear-gradient(145deg,#e8ecf6,#f7f3ff)] px-4">
                <div className="text-center text-[#5b2590]">
                  <p className="text-[0.74rem] font-semibold uppercase tracking-[0.16em] text-[#9b85b4]">
                    Review Queue
                  </p>
                  <p className="mt-2 text-[2.4rem] font-semibold leading-none">
                    {formatCount(reviewQueueStats?.total_items ?? 0)}
                  </p>
                </div>
              </div>
              <div className="space-y-2 px-3 py-3">
                <div className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#eef1f8] px-4 py-2.5 text-base font-semibold text-[#684f85]">
                  View Review Queue
                </div>
                <p className="text-center text-sm font-semibold text-[#9b85b4]">
                  {`${reviewQueueStats?.total_items ?? 0} scheduled review ${(reviewQueueStats?.total_items ?? 0) === 1 ? "item" : "items"}`}
                </p>
              </div>
            </Link>

            {isAdminUser ? (
              <div className="overflow-hidden rounded-[0.35rem] border border-[#d5e7ec] bg-white shadow-[0_6px_14px_rgba(45,111,131,0.08)]">
                <div className="flex h-36 items-center justify-center bg-[linear-gradient(145deg,#dff4f7,#f4fcfd)] px-4">
                  <div className="text-center text-[#2d6f83]">
                    <p className="text-[0.74rem] font-semibold uppercase tracking-[0.16em] text-[#78a4b1]">
                      Admin Tools
                    </p>
                    <p className="mt-3 text-lg font-semibold leading-tight">
                      Internal queue inspection and QA tools
                    </p>
                  </div>
                </div>
                <div className="space-y-2 px-3 py-3">
                  <Link
                    href="/admin/review-queue"
                    className="flex w-full items-center justify-center rounded-[0.35rem] bg-[#dff4f7] px-4 py-2.5 text-base font-semibold text-[#2d6f83]"
                  >
                    Admin Review Queue
                  </Link>
                  <Link
                    href="/review/debug"
                    className="flex w-full items-center justify-center rounded-[0.35rem] border border-[#d5e7ec] bg-white px-4 py-2.5 text-base font-semibold text-[#2d6f83]"
                  >
                    Queue Debug
                  </Link>
                </div>
              </div>
            ) : null}
          </div>
        </section>
      ) : null}

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
