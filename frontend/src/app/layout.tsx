import type { Metadata } from "next";
import { AuthNavigation } from "@/lib/auth-nav";
import { LearnerShellNav } from "@/components/learner-shell-nav";
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
      <body className="min-h-screen bg-[#f3f0f7] text-gray-900 antialiased">
        <header className="border-b border-gray-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <h1 className="text-lg font-semibold">Words-Codex</h1>
            <AuthNavigation />
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6 pb-28">{children}</main>
        <LearnerShellNav />
      </body>
    </html>
  );
}
