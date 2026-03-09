import type { Metadata } from "next";
import { AuthNavigation } from "@/lib/auth-nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Words Admin",
  description: "Admin tools for lexicon review and publishing",
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
          <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
            <h1 className="text-lg font-semibold">Words Admin</h1>
            <AuthNavigation />
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
