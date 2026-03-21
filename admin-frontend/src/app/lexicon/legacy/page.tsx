"use client";

import LexiconPage from "@/app/lexicon/page";

export default function LexiconLegacyPage() {
  return (
    <div className="space-y-6" data-testid="lexicon-legacy-page">
      <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-medium">Legacy Selection Review</p>
        <p className="mt-1">
          This surface preserves the older staged `selection_decisions.jsonl` review flow. Use the compiled-review and JSONL-review tools for the current compiled artifact workflow.
        </p>
      </section>
      <LexiconPage />
    </div>
  );
}
