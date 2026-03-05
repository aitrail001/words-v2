import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Words-Codex",
  description: "Context-aware vocabulary learning",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <h1 className="text-lg font-semibold">Words-Codex</h1>
            <nav className="flex items-center gap-4 text-sm font-medium text-gray-600">
              <Link
                href="/"
                className="hover:text-gray-900"
                data-testid="nav-home-link"
              >
                Home
              </Link>
              <Link
                href="/review"
                className="hover:text-gray-900"
                data-testid="nav-review-link"
              >
                Review
              </Link>
              <Link
                href="/login"
                className="hover:text-gray-900"
                data-testid="nav-login-link"
              >
                Log In
              </Link>
              <Link
                href="/register"
                className="hover:text-gray-900"
                data-testid="nav-register-link"
              >
                Register
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
