"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";

export default function AdminHomePage() {
  const [isAuthenticated] = useState(() => Boolean(readAccessToken()));

  useEffect(() => {
    if (!isAuthenticated) {
      redirectToLogin("/");
    }
  }, [isAuthenticated]);

  if (!isAuthenticated) {
    return <div data-testid="admin-auth-loading" className="text-sm text-gray-500">Checking authentication…</div>;
  }

  return (
    <div className="space-y-6" data-testid="admin-home-page">
      <div>
        <h2 className="text-2xl font-bold">Admin Dashboard</h2>
        <p className="text-sm text-gray-600">
          Use the admin frontend for staged lexicon review, publishing, and local DB inspection.
        </p>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white p-6">
        <h3 className="text-lg font-semibold">Lexicon Review</h3>
        <p className="mt-2 text-sm text-gray-600">
          Start in Lexicon Ops, use Compiled Review as the default review path, then import approved rows and verify the final DB state.
        </p>
        <Link
          href="/lexicon/ops"
          className="mt-4 inline-flex rounded-md bg-blue-600 px-4 py-2 text-white hover:bg-blue-700"
          data-testid="admin-home-lexicon-link"
        >
          Open Lexicon Ops
        </Link>
      </div>
    </div>
  );
}
