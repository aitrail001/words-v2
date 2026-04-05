import { render, screen, within } from "@testing-library/react";
import HomePage from "@/app/page";
import { getAuthRedirectPath } from "@/lib/auth-route-guard";
import { getAuthUserProfile, getKnowledgeMapDashboard, getReviewQueueStats } from "@/lib/knowledge-map-client";
import { getUserPreferences } from "@/lib/user-preferences-client";

jest.mock("next/navigation", () => ({
  usePathname: jest.fn(() => "/"),
}));

jest.mock("@/lib/knowledge-map-client");
jest.mock("@/lib/user-preferences-client");
jest.mock("../globals.css", () => ({}));

describe("HomePage (Knowledge Map)", () => {
  const mockGetKnowledgeMapDashboard = getKnowledgeMapDashboard as jest.MockedFunction<typeof getKnowledgeMapDashboard>;
  const mockGetReviewQueueStats = getReviewQueueStats as jest.MockedFunction<typeof getReviewQueueStats>;
  const mockGetAuthUserProfile = getAuthUserProfile as jest.MockedFunction<typeof getAuthUserProfile>;
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetKnowledgeMapDashboard.mockResolvedValue({
      total_entries: 13760,
      counts: {
        undecided: 1,
        to_learn: 4293,
        learning: 7082,
        known: 4,
      },
      discovery_range_start: 7001,
      discovery_range_end: 7100,
      discovery_entry: {
        entry_type: "word",
        entry_id: "word-1",
        display_text: "Resilience",
        browse_rank: 7002,
        status: "undecided",
      },
      next_learn_entry: {
        entry_type: "word",
        entry_id: "word-2",
        display_text: "Drum",
        browse_rank: 2616,
        status: "to_learn",
      },
    });
    mockGetReviewQueueStats.mockResolvedValue({
      total_items: 8,
      due_items: 3,
      review_count: 12,
      correct_count: 10,
      accuracy: 10 / 12,
    });
    mockGetAuthUserProfile.mockResolvedValue({
      id: "user-1",
      email: "user@user.com",
      role: "user",
      tier: "free",
      is_active: true,
    });
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
  });

  it("renders the dashboard summary cards", async () => {
    render(<HomePage />);

    expect(
      (await screen.findAllByText((_, element) => element?.textContent === "WordsUncovered")).length,
    ).toBeGreaterThan(0);
    expect(await screen.findByText("13,760")).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Knew 4" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "Started 7,082" })).toBeInTheDocument();
    expect(await screen.findByRole("link", { name: "To Learn 4,293" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: /review/i })).toBeInTheDocument();
    expect(screen.getByText(/keep your spaced repetition queue moving/i)).toBeInTheDocument();
    expect(screen.getByText("3 due today")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start review/i })).toHaveAttribute("href", "/review");
    expect(screen.getByRole("link", { name: /view review queue/i })).toHaveAttribute("href", "/review/queue");
    expect(screen.queryByRole("link", { name: /admin review queue/i })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /queue debug/i })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /discover/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /learn next: drum/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /import epub/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /manage word lists/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })[0]).toHaveAttribute("href", "/imports");
    expect(screen.getAllByRole("link", { name: "Open" })[1]).toHaveAttribute("href", "/word-lists");
  });

  it("loads dashboard data and shows the current discovery and next learn words", async () => {
    render(<HomePage />);

    expect(await screen.findByText(/range 7000/i)).toBeInTheDocument();
    expect(screen.getByText(/next: drum/i)).toBeInTheDocument();
    expect(mockGetKnowledgeMapDashboard).toHaveBeenCalled();
    expect(mockGetReviewQueueStats).toHaveBeenCalled();
  });

  it("keeps the review card visible when items are scheduled but not yet due", async () => {
    mockGetReviewQueueStats.mockResolvedValueOnce({
      total_items: 8,
      due_items: 0,
      review_count: 12,
      correct_count: 10,
      accuracy: 10 / 12,
    });

    render(<HomePage />);

    expect(await screen.findByText("13,760")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /review/i })).toBeInTheDocument();
    expect(screen.getByText("8 scheduled review items")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /start review/i })).not.toBeInTheDocument();
    expect(screen.getByText("8 items waiting in your queue")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /view review queue/i })).toHaveAttribute("href", "/review/queue");
  });

  it("shows the admin review queue link on the homepage for admin users", async () => {
    mockGetAuthUserProfile.mockResolvedValueOnce({
      id: "admin-1",
      email: "admin@admin.com",
      role: "admin",
      tier: "pro",
      is_active: true,
    });

    render(<HomePage />);

    expect(await screen.findByRole("link", { name: /admin review queue/i })).toHaveAttribute(
      "href",
      "/admin/review-queue",
    );
    expect(screen.getByText(/internal queue inspection and qa tools/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /queue debug/i })).toHaveAttribute("href", "/review/debug");
  });

  it("keeps the main dashboard navigation visible", async () => {
    render(<HomePage />);

    expect(await screen.findByRole("link", { name: "13,760" })).toHaveAttribute("href", "/knowledge-map");
    expect(screen.getByRole("link", { name: "Knew 4" })).toHaveAttribute("href", "/knowledge-list/known");
    expect(screen.getByRole("link", { name: "Started 7,082" })).toHaveAttribute("href", "/knowledge-list/learning");
    expect(screen.getByRole("link", { name: "To Learn 4,293" })).toHaveAttribute("href", "/knowledge-list/to-learn");
    expect(screen.getByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
  });
});

describe("RootLayout learner shell", () => {
  const mockUsePathname = require("next/navigation").usePathname as jest.Mock;

  beforeEach(() => {
    mockUsePathname.mockReturnValue("/");
  });

  it("renders the persistent learner bottom nav links", () => {
    const RootLayout = require("@/app/layout").default as typeof import("@/app/layout").default;
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});

    try {
      render(
        <RootLayout>
          <div>Child content</div>
        </RootLayout>,
      );

      const learnerShellNav = within(screen.getByTestId("learner-shell-nav"));

      expect(learnerShellNav.getByRole("link", { name: /home/i })).toHaveAttribute("href", "/");
      expect(learnerShellNav.getByRole("link", { name: /knowledge/i })).toHaveAttribute("href", "/knowledge-map");
      expect(learnerShellNav.getByRole("link", { name: /view review queue/i })).toHaveAttribute("href", "/review/queue");
      expect(learnerShellNav.getByRole("link", { name: /imports/i })).toHaveAttribute("href", "/imports");
      expect(learnerShellNav.getByRole("link", { name: /imports/i })).toHaveAttribute("href", "/imports");
      expect(learnerShellNav.getByRole("link", { name: /search/i })).toHaveAttribute("href", "/search");
      expect(learnerShellNav.getByRole("link", { name: /settings/i })).toHaveAttribute("href", "/settings");
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });

  it.each(["/knowledge-list/new", "/word/word-1"])(
    "keeps the Knowledge tab active on learner knowledge routes like %s",
    (pathname) => {
    const RootLayout = require("@/app/layout").default as typeof import("@/app/layout").default;
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    mockUsePathname.mockReturnValue(pathname);

    try {
      render(
        <RootLayout>
          <div>Child content</div>
        </RootLayout>,
      );

      const learnerShellNav = within(screen.getByTestId("learner-shell-nav"));
      const knowledgeLink = learnerShellNav.getByRole("link", { name: /knowledge/i });
      const searchLink = learnerShellNav.getByRole("link", { name: /search/i });

      expect(knowledgeLink.className).toContain("text-white");
      expect(searchLink.className).toContain("bg-white");
    } finally {
      consoleErrorSpy.mockRestore();
    }
    },
  );

  it("keeps learner nav visible on /imports so users can return home", () => {
    const RootLayout = require("@/app/layout").default as typeof import("@/app/layout").default;
    const consoleErrorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    mockUsePathname.mockReturnValue("/imports");

    try {
      render(
        <RootLayout>
          <div>Child content</div>
        </RootLayout>,
      );

      const learnerShellNav = within(screen.getByTestId("learner-shell-nav"));
      expect(learnerShellNav.getByRole("link", { name: /home/i })).toHaveAttribute("href", "/");
      expect(learnerShellNav.getByRole("link", { name: /imports/i })).toHaveAttribute("href", "/imports");
    } finally {
      consoleErrorSpy.mockRestore();
    }
  });
});

describe("Auth middleware for /", () => {
  it("redirects unauthenticated requests to /login", () => {
    expect(getAuthRedirectPath("/", false)).toBe("/login?next=%2F");
  });

  it("allows authenticated requests", () => {
    expect(getAuthRedirectPath("/", true)).toBeNull();
  });

  it("redirects unauthenticated /imports requests", () => {
    expect(getAuthRedirectPath("/imports", false)).toBe(
      "/login?next=%2Fimports",
    );
  });

  it("redirects unauthenticated /word-lists requests", () => {
    expect(getAuthRedirectPath("/word-lists", false)).toBe(
      "/login?next=%2Fword-lists",
    );
  });

  it("redirects unauthenticated knowledge-map routes", () => {
    expect(getAuthRedirectPath("/knowledge-map", false)).toBe(
      "/login?next=%2Fknowledge-map",
    );
    expect(getAuthRedirectPath("/knowledge-list/new", false)).toBe(
      "/login?next=%2Fknowledge-list%2Fnew",
    );
    expect(getAuthRedirectPath("/search", false)).toBe(
      "/login?next=%2Fsearch",
    );
    expect(getAuthRedirectPath("/settings", false)).toBe(
      "/login?next=%2Fsettings",
    );
  });

  it("allows authenticated /imports requests", () => {
    expect(getAuthRedirectPath("/imports", true)).toBeNull();
  });

  it("allows authenticated /word-lists requests", () => {
    expect(getAuthRedirectPath("/word-lists", true)).toBeNull();
  });
});
