import { expect, test } from "@playwright/test";
import { apiUrl, authHeaders, registerViaApi } from "../helpers/auth";

type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

type MeResponse = {
  id: string;
  email: string;
  role: string;
  tier: string;
  is_active: boolean;
};

test("@smoke auth contract login/refresh issues rotating token pairs", async ({ request }) => {
  const user = await registerViaApi(request, "auth-contract");

  const loginResponse = await request.post(`${apiUrl}/auth/login`, {
    data: {
      email: user.email,
      password: user.password,
    },
  });

  expect(loginResponse.status()).toBe(200);
  const loginBody = (await loginResponse.json()) as TokenPair;
  expect(loginBody.token_type).toBe("bearer");
  expect(loginBody.access_token).toBeTruthy();
  expect(loginBody.refresh_token).toBeTruthy();

  const meWithAccess = await request.get(`${apiUrl}/auth/me`, {
    headers: authHeaders(loginBody.access_token),
  });
  expect(meWithAccess.status()).toBe(200);

  const meBody = (await meWithAccess.json()) as MeResponse;
  expect(meBody.email).toBe(user.email);

  const meWithRefresh = await request.get(`${apiUrl}/auth/me`, {
    headers: authHeaders(loginBody.refresh_token),
  });
  expect(meWithRefresh.status()).toBe(401);

  const refreshResponse = await request.post(`${apiUrl}/auth/refresh`, {
    data: {
      refresh_token: loginBody.refresh_token,
    },
  });

  expect(refreshResponse.status()).toBe(200);
  const refreshedBody = (await refreshResponse.json()) as TokenPair;
  expect(refreshedBody.token_type).toBe("bearer");
  expect(refreshedBody.access_token).toBeTruthy();
  expect(refreshedBody.refresh_token).toBeTruthy();
  expect(refreshedBody.access_token).not.toBe(loginBody.access_token);
  expect(refreshedBody.refresh_token).not.toBe(loginBody.refresh_token);

  const reusedRefreshResponse = await request.post(`${apiUrl}/auth/refresh`, {
    data: {
      refresh_token: loginBody.refresh_token,
    },
  });
  expect(reusedRefreshResponse.status()).toBe(401);
});
