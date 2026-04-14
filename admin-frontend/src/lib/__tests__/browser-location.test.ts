import { assignLocation } from "../browser-location";

describe("assignLocation", () => {
  it("delegates to the provided location object", () => {
    const assign = jest.fn();

    assignLocation("/login", { assign });

    expect(assign).toHaveBeenCalledWith("/login");
  });
});
