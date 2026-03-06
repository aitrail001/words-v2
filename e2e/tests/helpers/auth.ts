import { expect, APIRequestContext, Page } from "@playwright/test";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000/api";
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const TOKEN_STORAGE_KEY = "words_access_token";
const DEFAULT_PASSWORD = "password123";

export type AuthUser = {
  email: string;
  password: string;
  token: string;
};

const uniqueEmail = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

export const registerViaApi = async (
  request: APIRequestContext,
  prefix = "e2e-user",
): Promise<AuthUser> => {
  const email = uniqueEmail(prefix);
  const password = DEFAULT_PASSWORD;

  const response = await request.post(`${API_URL}/auth/register`, {
    data: { email, password },
  });

  expect(response.ok()).toBeTruthy();
  const body = (await response.json()) as { access_token: string };
  expect(body.access_token).toBeTruthy();

  return {
    email,
    password,
    token: body.access_token,
  };
};

export const injectToken = async (page: Page, token: string): Promise<void> => {
  await page.context().addCookies([
    {
      name: TOKEN_STORAGE_KEY,
      value: token,
      url: BASE_URL,
      sameSite: "Lax",
    },
  ]);

  await page.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, value);
    },
    {
      key: TOKEN_STORAGE_KEY,
      value: token,
    },
  );
};

export const authHeaders = (token: string): Record<string, string> => ({
  Authorization: `Bearer ${token}`,
  "Content-Type": "application/json",
});

export const apiUrl = API_URL;
