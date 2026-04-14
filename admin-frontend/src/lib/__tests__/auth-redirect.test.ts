import { redirectToLogin } from "../auth-redirect";
import { locationAssignCalls } from "@/test/location-spies";

describe("redirectToLogin", () => {
  beforeEach(() => {
    window.history.pushState({}, "", "/lexicon?tab=review");
  });

  it("preserves the current path as next by default", () => {
    redirectToLogin();

    expect(locationAssignCalls).toEqual(["/login?next=%2Flexicon%3Ftab%3Dreview"]);
  });

  it("does not append next when already on the login route", () => {
    window.history.pushState({}, "", "/login");

    redirectToLogin();

    expect(locationAssignCalls).toEqual(["/login"]);
  });
});
