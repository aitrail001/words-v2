import type { Metadata } from "next";
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
      <body className="min-h-screen bg-[#eef0f7] text-gray-900 antialiased">
        <main className="mx-auto w-full max-w-[46rem] px-2 py-2 pb-28">{children}</main>
        <LearnerShellNav />
      </body>
    </html>
  );
}
