"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";

export default function AdminHomePage() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean | null>(null);

  useEffect(() => {
    const hasToken = Boolean(readAccessToken());
    setIsAuthenticated(hasToken);
    if (!hasToken) {
      redirectToLogin("/");
    }
  }, []);

  if (!isAuthenticated) {
    return <div data-testid="admin-auth-loading" className="text-sm text-gray-500">Checking authentication…</div>;
  }

  return (
    <div className="space-y-6" data-testid="admin-home-page">
      <div>
        <h2 className="text-2xl font-bold">Admin Dashboard</h2>
        <p className="text-sm text-gray-600">
          Use the admin frontend for lexicon word inspection, snapshot operations, and optional legacy staged review.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="text-lg font-semibold">Lexicon Admin</h3>
        <p className="mt-2 text-sm text-gray-600">
          Open the split lexicon workspace: inspect imported DB words, monitor offline snapshot progress, or use the older staged-review flow when legacy review artifacts exist.
        </p>
        <Link
          href="/lexicon"
          className="mt-4 inline-flex rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          data-testid="admin-home-lexicon-link"
        >
          Open Lexicon Admin
        </Link>
      </div>
    </div>
  );
}
