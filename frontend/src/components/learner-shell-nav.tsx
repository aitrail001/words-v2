"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV_ITEMS = [
  { href: "/", label: "Home", icon: "⌂" },
  { href: "/knowledge-map", label: "Knowledge", icon: "◫" },
  { href: "/search", label: "Search", icon: "⌕" },
  { href: "/settings", label: "Settings", icon: "✓" },
] as const;

function isKnowledgeRoute(pathname: string | null): boolean {
  if (!pathname) {
    return false;
  }

  return (
    pathname === "/knowledge-map" ||
    pathname.startsWith("/knowledge-map/") ||
    pathname.startsWith("/knowledge-list/") ||
    pathname.startsWith("/word/") ||
    pathname.startsWith("/phrase/")
  );
}

function isActiveNavItem(pathname: string | null, href: (typeof NAV_ITEMS)[number]["href"]): boolean {
  if (href === "/") {
    return pathname === "/";
  }

  if (href === "/knowledge-map") {
    return isKnowledgeRoute(pathname);
  }

  return pathname === href || pathname?.startsWith(`${href}/`) || false;
}

function shouldHideNav(pathname: string | null): boolean {
  if (!pathname) {
    return false;
  }

  return (
    pathname === "/login" ||
    pathname === "/register" ||
    pathname.startsWith("/review") ||
    pathname.startsWith("/imports")
  );
}

export function LearnerShellNav() {
  const pathname = usePathname();

  if (shouldHideNav(pathname)) {
    return null;
  }

  return (
    <nav
      aria-label="Learner tabs"
      data-testid="learner-shell-nav"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-[#eadbf7] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(247,242,255,0.98))] px-4 pb-[calc(env(safe-area-inset-bottom,0px)+0.75rem)] pt-3 shadow-[0_-18px_34px_rgba(88,44,145,0.12)] backdrop-blur"
    >
      <div className="mx-auto grid max-w-[27rem] grid-cols-4 gap-2">
        {NAV_ITEMS.map((item) => {
          const active = isActiveNavItem(pathname, item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex min-h-[4.25rem] flex-col items-center justify-center rounded-[1.25rem] px-2 py-2 text-center transition ${
                active
                  ? "bg-[linear-gradient(145deg,#7d2cff,#36c7de)] text-white shadow-[0_12px_24px_rgba(93,43,175,0.24)]"
                  : "bg-white/75 text-[#6e5c86]"
              }`}
            >
              <span aria-hidden="true" className="text-lg font-semibold leading-none">
                {item.icon}
              </span>
              <span className="mt-1 text-[0.78rem] font-semibold">{item.label}</span>
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
