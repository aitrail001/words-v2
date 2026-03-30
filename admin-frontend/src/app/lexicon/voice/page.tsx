"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function LexiconVoiceLegacyPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/lexicon/voice-runs");
  }, [router]);

  return null;
}
