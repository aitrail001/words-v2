"use client";

import { useEffect } from "react";

import LexiconPage from "@/app/lexicon/page";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";

export default function LexiconLegacyPage() {
  const hasToken = Boolean(readAccessToken());

  useEffect(() => {
    if (!hasToken) {
      redirectToLogin("/lexicon/legacy");
    }
  }, [hasToken]);

  return (
    <div className="space-y-6" data-testid="lexicon-legacy-page">
      <section className="rounded-lg border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
        <p className="font-medium">Legacy Selection Review</p>
        <p className="mt-1">
          This surface preserves the older staged `selection_decisions.jsonl` review flow. Use the compiled-review and JSONL-review tools for the current compiled artifact workflow.
        </p>
      </section>
      {hasToken ? <LexiconPage /> : null}
    </div>
  );
}
