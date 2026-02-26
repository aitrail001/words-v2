import { ApiError } from "./api-client";

describe("ApiError", () => {
  it("captures status code and message", () => {
    const error = new ApiError(404, "Not found");
    expect(error.status).toBe(404);
    expect(error.message).toBe("Not found");
    expect(error.name).toBe("ApiError");
  });
});
