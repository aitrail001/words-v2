import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsPage from "@/app/settings/page";
import { getUserPreferences, updateUserPreferences } from "@/lib/user-preferences-client";

jest.mock("@/lib/user-preferences-client", () => {
  const actual = jest.requireActual("@/lib/user-preferences-client");
  return {
    ...actual,
    getUserPreferences: jest.fn(),
    updateUserPreferences: jest.fn(),
  };
});

describe("SettingsPage", () => {
  const mockGetUserPreferences = getUserPreferences as jest.MockedFunction<typeof getUserPreferences>;
  const mockUpdateUserPreferences = updateUserPreferences as jest.MockedFunction<typeof updateUserPreferences>;

  beforeEach(() => {
    jest.clearAllMocks();
    mockGetUserPreferences.mockResolvedValue({
      accent_preference: "uk",
      translation_locale: "zh-Hans",
      knowledge_view_preference: "cards",
      show_translations_by_default: true,
    });
    mockUpdateUserPreferences.mockResolvedValue({
      accent_preference: "us",
      translation_locale: "es",
      knowledge_view_preference: "cards",
      show_translations_by_default: false,
    });
  });

  it("renders the learner settings sections", async () => {
    render(<SettingsPage />);

    expect(await screen.findByText(/settings/i)).toBeInTheDocument();
    expect(screen.getByText(/learning/i)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Translation" })).toBeInTheDocument();
    expect(screen.getAllByText(/review cards/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/data\/storage/i)).toBeInTheDocument();
  });

  it("loads the persisted learner preferences", async () => {
    render(<SettingsPage />);

    expect(await screen.findByDisplayValue("Chinese (Simplified)")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /uk accent/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /cards view/i })).toBeInTheDocument();
  });

  it("shows the full supported translation language names", async () => {
    render(<SettingsPage />);

    const languageSelect = await screen.findByLabelText(/language/i);
    const labels = Array.from(languageSelect.querySelectorAll("option")).map((option) => option.textContent);
    expect(labels).toEqual([
      "Arabic",
      "Spanish",
      "Japanese",
      "Portuguese (Brazil)",
      "Chinese (Simplified)",
    ]);
  });

  it("persists the global translation visibility toggle", async () => {
    const user = userEvent.setup();

    render(<SettingsPage />);

    const toggle = await screen.findByRole("button", { name: /show translations by default/i });
    await user.click(toggle);

    await waitFor(() => {
      expect(mockUpdateUserPreferences).toHaveBeenCalledWith({
        accent_preference: "uk",
        translation_locale: "zh-Hans",
        knowledge_view_preference: "cards",
        show_translations_by_default: false,
      });
    });
  });
});
