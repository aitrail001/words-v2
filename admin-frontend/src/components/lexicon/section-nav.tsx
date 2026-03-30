"use client";

import Link from "next/link";

type SectionNavItem = {
  label: string;
  href: string;
  active?: boolean;
};

type SectionNavProps = {
  items: SectionNavItem[];
  testId: string;
};

export function LexiconSectionNav({ items, testId }: SectionNavProps) {
  return (
    <nav
      className="flex flex-wrap gap-2 rounded-lg border border-slate-200 bg-slate-50 p-2"
      data-testid={testId}
      aria-label="Lexicon section navigation"
    >
      {items.map((item) => (
        <Link
          key={`${item.label}:${item.href}`}
          href={item.href}
          aria-current={item.active ? "page" : undefined}
          className={`rounded-md px-3 py-2 text-sm font-medium transition-colors ${
            item.active
              ? "bg-slate-900 text-white"
              : "text-slate-700 hover:bg-white hover:text-slate-950"
          }`}
        >
          {item.label}
        </Link>
      ))}
    </nav>
  );
}
