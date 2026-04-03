"use client";

import { LexiconSectionNav } from "@/components/lexicon/section-nav";

type EpubCacheNavProps = {
  active: "sources" | "batches";
};

export function EpubCacheNav({ active }: EpubCacheNavProps) {
  return (
    <LexiconSectionNav
      testId="lexicon-epub-cache-nav"
      items={[
        { label: "Cache Sources", href: "/lexicon/epub-cache/sources", active: active == "sources" },
        { label: "Batch Import", href: "/lexicon/epub-cache/batches", active: active == "batches" },
      ]}
    />
  );
}
