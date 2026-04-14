import { redirectToLogin } from "../auth-redirect";
import * as browserLocation from "@/lib/browser-location";

describe("redirectToLogin", () => {
  beforeEach(() => {
    jest.spyOn(browserLocation, "assignLocation");
    window.history.pushState({}, "", "/lexicon?tab=review");
  });

  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("preserves the current path as next by default", () => {
    redirectToLogin();

    expect(browserLocation.assignLocation).toHaveBeenCalledWith("/login?next=%2Flexicon%3Ftab%3Dreview");
  });

  it("does not append next when already on the login route", () => {
    window.history.pushState({}, "", "/login");

    redirectToLogin();

    expect(browserLocation.assignLocation).toHaveBeenCalledWith("/login");
  });
});
