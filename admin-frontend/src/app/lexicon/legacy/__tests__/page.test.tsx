import { render, waitFor } from "@testing-library/react";
import LexiconLegacyPage from "@/app/lexicon/legacy/page";
import { useRouter } from "next/navigation";
import { redirectToLogin } from "@/lib/auth-redirect";
import { readAccessToken } from "@/lib/auth-session";

jest.mock("next/navigation", () => ({ useRouter: jest.fn() }));
jest.mock("@/lib/auth-session", () => ({ readAccessToken: jest.fn() }));
jest.mock("@/lib/auth-redirect", () => ({ redirectToLogin: jest.fn() }));

describe("LexiconLegacyPage", () => {
  const mockUseRouter = useRouter as jest.Mock;
  const mockReadAccessToken = readAccessToken as jest.Mock;
  const replace = jest.fn();

  beforeEach(() => {
    jest.clearAllMocks();
    mockUseRouter.mockReturnValue({ replace });
  });

  it("redirects authenticated users to lexicon ops", async () => {
    mockReadAccessToken.mockReturnValue("active-token");
    render(<LexiconLegacyPage />);
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/lexicon/ops"));
  });

  it("redirects unauthenticated users to login", async () => {
    mockReadAccessToken.mockReturnValue(null);
    render(<LexiconLegacyPage />);
    await waitFor(() => expect(redirectToLogin).toHaveBeenCalledWith("/lexicon/legacy"));
  });
});
