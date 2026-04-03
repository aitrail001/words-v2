"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { apiClient } from "@/lib/api-client";
import { AUTH_TOKEN_CHANGED_EVENT, readAccessToken } from "@/lib/auth-session";

const hasToken = (): boolean => Boolean(readAccessToken());

export function AuthNavigation() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const syncAuthState = () => setIsAuthenticated(hasToken());
    syncAuthState();

    window.addEventListener(AUTH_TOKEN_CHANGED_EVENT, syncAuthState);
    return () => {
      window.removeEventListener(AUTH_TOKEN_CHANGED_EVENT, syncAuthState);
    };
  }, []);

  const handleLogout = async () => {
    await apiClient.logout();
  };

  return (
    <nav className="flex items-center gap-4 text-sm font-medium text-gray-600">
      <Link href="/" className="hover:text-gray-900" data-testid="nav-home-link">
        Home
      </Link>
      <Link
        href="/lexicon/ops"
        className="hover:text-gray-900"
        data-testid="nav-lexicon-ops-link"
      >
        Lexicon Ops
      </Link>
      <Link
        href="/lexicon/voice-runs"
        className="hover:text-gray-900"
        data-testid="nav-lexicon-voice-link"
      >
        Voice
      </Link>
      <Link
        href="/lexicon/compiled-review"
        className="hover:text-gray-900"
        data-testid="nav-lexicon-compiled-review-link"
      >
        Enrichment Review
      </Link>
      <Link
        href="/lexicon/epub-cache/sources"
        className="hover:text-gray-900"
        data-testid="nav-lexicon-epub-cache-link"
      >
        EPUB Cache
      </Link>
      {isAuthenticated ? (
        <button
          type="button"
          onClick={handleLogout}
          className="hover:text-gray-900"
          data-testid="nav-logout-button"
        >
          Logout
        </button>
      ) : (
        <Link
          href="/login"
          className="hover:text-gray-900"
          data-testid="nav-login-link"
        >
          Log In
        </Link>
      )}
    </nav>
  );
}
