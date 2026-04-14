import { redirectToLogin } from "../auth-redirect";

describe("redirectToLogin", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/lexicon?tab=review");
  });

  it("preserves the current path as next by default", () => {
    redirectToLogin();

    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("?next=%2Flexicon%3Ftab%3Dreview");
  });

  it("does not append next when already on the login route", () => {
    window.history.pushState({}, "", "/login");

    redirectToLogin();

    expect(window.location.pathname).toBe("/login");
    expect(window.location.search).toBe("");
  });
});
