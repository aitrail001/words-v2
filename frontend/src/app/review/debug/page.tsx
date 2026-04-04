"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiClient } from "@/lib/api-client";
import { type StoredReviewCard } from "@/lib/review-session-storage";

function getPromptTypeLabel(promptType: string | undefined): string {
  if (!promptType) {
    return "unknown";
  }
  return promptType.replaceAll("_", " ");
}

export default function ReviewDebugPage() {
  const [cards, setCards] = useState<StoredReviewCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    apiClient
      .get<StoredReviewCard[]>("/reviews/queue/due")
      .then((response) => {
        if (!active) {
          return;
        }
        setCards(response);
        setLoading(false);
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setError("Unable to load the current review queue.");
        setLoading(false);
      });

    return () => {
      active = false;
    };
  }, []);

  return (
    <div className="mx-auto max-w-[46rem] space-y-4 pb-10 text-[#472164]">
      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-[0.75rem] font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
              Review Debug
            </p>
            <h1 className="mt-1 text-[1.4rem] font-semibold text-[#5b2590]">
              Current queue prompt types
            </h1>
          </div>
          <div className="flex items-center gap-2">
            <Link
              href="/"
              className="rounded-full border border-[#d8caec] px-3 py-2 text-sm font-semibold text-[#684f85]"
            >
              Home
            </Link>
            <Link
              href="/review"
              className="rounded-full bg-[#7b32d3] px-4 py-2 text-sm font-semibold text-white"
            >
              Start Review
            </Link>
          </div>
        </div>
        <p className="mt-2 text-sm text-[#7b6795]">
          This reads the live due queue for the signed-in user and shows the prompt family order.
        </p>
      </section>

      <section className="rounded-[0.9rem] bg-white px-4 py-4 shadow-[0_8px_18px_rgba(95,53,177,0.08)]">
        {loading ? <p className="text-sm text-[#7b6795]">Loading queue…</p> : null}
        {error ? <p className="text-sm font-semibold text-[#a5374a]">{error}</p> : null}
        {!loading && !error && cards.length === 0 ? (
          <p className="text-sm text-[#7b6795]">No due review items.</p>
        ) : null}
        {!loading && !error && cards.length > 0 ? (
          <ol className="space-y-3">
            {cards.map((card, index) => (
              <li
                key={card.id}
                className="rounded-[0.8rem] border border-[#ece1f7] bg-[#faf7ff] px-3 py-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-[0.75rem] font-semibold uppercase tracking-[0.12em] text-[#8e38f2]">
                      {index + 1}. {getPromptTypeLabel(card.prompt?.prompt_type)}
                    </p>
                    <p className="mt-1 text-base font-semibold text-[#5a357b]">
                      {card.word ?? card.detail?.display_text ?? "Review item"}
                    </p>
                    <p className="mt-1 text-sm text-[#7b6795]">
                      {card.definition ?? card.detail?.primary_definition ?? card.prompt?.question ?? "No definition"}
                    </p>
                  </div>
                  {card.queue_item_id || card.id ? (
                    <Link
                      href={`/review?queue_item_id=${encodeURIComponent(card.queue_item_id ?? card.id ?? "")}`}
                      className="rounded-full border border-[#d8caec] px-3 py-1.5 text-sm font-semibold text-[#684f85]"
                    >
                      Open
                    </Link>
                  ) : null}
                </div>
              </li>
            ))}
          </ol>
        ) : null}
      </section>
    </div>
  );
}
