import { redirectToLogin } from "../auth-redirect";

describe("redirectToLogin", () => {
  const assignMock = jest.fn();

  beforeEach(() => {
    assignMock.mockReset();
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        pathname: "/lexicon",
        search: "?tab=review",
        assign: assignMock,
      },
    });
  });

  it("preserves the current path as next by default", () => {
    redirectToLogin();

    expect(assignMock).toHaveBeenCalledWith("/login?next=%2Flexicon%3Ftab%3Dreview");
  });

  it("does not append next when already on the login route", () => {
    Object.defineProperty(window, "location", {
      configurable: true,
      value: {
        pathname: "/login",
        search: "",
        assign: assignMock,
      },
    });

    redirectToLogin();

    expect(assignMock).toHaveBeenCalledWith("/login");
  });
});
