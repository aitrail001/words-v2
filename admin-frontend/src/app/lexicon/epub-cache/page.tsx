"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LexiconEpubCacheRootPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/lexicon/epub-cache/sources");
  }, [router]);

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-600" data-testid="lexicon-epub-cache-redirect">
      Redirecting to EPUB Cache Sources...
    </div>
  );
}
