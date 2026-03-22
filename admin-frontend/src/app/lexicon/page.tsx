"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";

export default function LexiconPage() {
  const router = useRouter();

  useEffect(() => {
    if (!readAccessToken()) {
      redirectToLogin("/lexicon/ops");
      return;
    }
    router.replace("/lexicon/ops");
  }, [router]);

  return (
    <div className="space-y-4" data-testid="lexicon-page">
      <section className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700">
        <p className="font-medium text-gray-900">Redirecting to Lexicon Ops</p>
        <p className="mt-1">The staged selection review surface has been removed. Use the compiled-artifact workflow in Lexicon Ops.</p>
      </section>
    </div>
  );
}
