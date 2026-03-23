import { render, screen } from "@testing-library/react";
import SettingsPage from "@/app/settings/page";
import { getUserPreferences, updateUserPreferences } from "@/lib/user-preferences-client";

jest.mock("@/lib/user-preferences-client");

describe("SettingsPage", () => {
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockUpdateUserPreferences = updateUserPreferences as jest.MockedFunction<typeof updateUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
    });
    mockUpdateUserPreferences.mockResolvedValue({
      accent_preference: "us",
      translation_locale: "es",
      knowledge_view_preference: "cards",
    });
  });

  it("renders the learner settings sections", async () => {
    render(<SettingsPage />);

    expect(await screen.findByText(/settings/i)).toBeInTheDocument();
    expect(screen.getByText(/learning/i)).toBeInTheDocument();
    expect(screen.getByText(/translation/i)).toBeInTheDocument();
    expect(screen.getAllByText(/review cards/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/data\/storage/i)).toBeInTheDocument();
  });

  it("loads the persisted learner preferences", async () => {
    render(<SettingsPage />);

    expect(await screen.findByDisplayValue("Chinese")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /uk accent/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cards view/i })).toBeInTheDocument();
  });
});
