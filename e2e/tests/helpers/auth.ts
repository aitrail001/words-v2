import { expect, APIRequestContext, Page } from "@playwright/test";
import { Client } from "pg";

const API_URL = process.env.E2E_API_URL ?? "http://localhost:8000/api";
const BASE_URL = process.env.E2E_BASE_URL ?? "http://localhost:3000";
const TOKEN_STORAGE_KEY = "words_access_token";
const ADMIN_TOKEN_STORAGE_KEY = "words_admin_access_token";
const DEFAULT_PASSWORD = "password123";

type AuthTokens = {
  access_token: string;
  refresh_token: string;
};

type InjectTokenOptions = {
  baseUrl?: string;
  storageKey?: string;
  cookieKey?: string;
};

export type AuthUser = {
  id: string;
  email: string;
  password: string;
  token: string;
  refreshToken?: string;
  role?: string;
};

const uniqueEmail = (prefix: string): string =>
  `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;

const inferDbHost = (): string => {
  const apiUrl = process.env.E2E_API_URL ?? "";
  return apiUrl.includes("://backend:") ? "postgres" : "localhost";
};

const getDbConfig = () => {
  const connectionString = process.env.E2E_DB_URL;
  if (connectionString) {
    return { connectionString };
  }

  return {
    host: process.env.E2E_DB_HOST ?? inferDbHost(),
    port: Number(process.env.E2E_DB_PORT ?? 5432),
    user: process.env.E2E_DB_USER ?? "vocabapp",
    password: process.env.E2E_DB_PASSWORD ?? "devpassword",
    database: process.env.E2E_DB_NAME ?? "vocabapp_dev",
  };
};

const loginViaApi = async (
  request: APIRequestContext,
  email: string,
  password: string,
): Promise<AuthTokens> => {
  const response = await request.post(`${API_URL}/auth/login`, {
    data: { email, password },
  });

  expect(response.ok()).toBeTruthy();
  return (await response.json()) as AuthTokens;
};

const promoteUserRole = async (email: string, role: "admin" | "user"): Promise<void> => {
  const client = new Client(getDbConfig());
  await client.connect();

  try {
    const result = await client.query<{ id: string }>(
      `
      UPDATE users
      SET role = $2,
          updated_at = now()
      WHERE email = $1
      RETURNING id::text AS id
      `,
      [email, role],
    );

    expect(result.rowCount).toBe(1);
  } finally {
    await client.end();
  }
};

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
  const body = (await response.json()) as AuthTokens;
  expect(body.access_token).toBeTruthy();
  expect(body.refresh_token).toBeTruthy();

  const meResponse = await request.get(`${API_URL}/auth/me`, {
    headers: {
      Authorization: `Bearer ${body.access_token}`,
    },
  });

  expect(meResponse.ok()).toBeTruthy();
  const me = (await meResponse.json()) as { id: string };
  expect(me.id).toBeTruthy();

  return {
    id: me.id,
    email,
    password,
    token: body.access_token,
    refreshToken: body.refresh_token,
    role: "user",
  };
};

export const registerAdminViaApi = async (
  request: APIRequestContext,
  prefix = "e2e-admin",
): Promise<AuthUser> => {
  const user = await registerViaApi(request, prefix);
  await promoteUserRole(user.email, "admin");

  const tokens = await loginViaApi(request, user.email, user.password);
  const meResponse = await request.get(`${API_URL}/auth/me`, {
    headers: authHeaders(tokens.access_token),
  });

  expect(meResponse.ok()).toBeTruthy();
  const me = (await meResponse.json()) as { role: string };
  expect(me.role).toBe("admin");

  return {
    ...user,
    token: tokens.access_token,
    refreshToken: tokens.refresh_token,
    role: "admin",
  };
};

export const injectToken = async (
  page: Page,
  token: string,
  options: InjectTokenOptions = {},
): Promise<void> => {
  const baseUrl = options.baseUrl ?? BASE_URL;
  const storageKey = options.storageKey ?? TOKEN_STORAGE_KEY;
  const cookieKey = options.cookieKey ?? storageKey;

  await page.context().addCookies([
    {
      name: cookieKey,
      value: token,
      url: baseUrl,
      sameSite: "Lax",
    },
  ]);

  await page.addInitScript(
    ({ key, value }) => {
      window.localStorage.setItem(key, value);
    },
    {
      key: storageKey,
      value: token,
    },
  );
};

export const injectAdminToken = async (
  page: Page,
  token: string,
  baseUrl = process.env.E2E_ADMIN_URL ?? "http://localhost:3001",
): Promise<void> => {
  await injectToken(page, token, {
    baseUrl,
    storageKey: ADMIN_TOKEN_STORAGE_KEY,
    cookieKey: ADMIN_TOKEN_STORAGE_KEY,
  });
};

export const waitForAppReady = async (
  request: APIRequestContext,
  baseUrl: string,
  path = "/login",
): Promise<void> => {
  await expect
    .poll(
      async () => {
        try {
          const response = await request.get(`${baseUrl}${path}`);
          return response.status();
        } catch {
          return 0;
        }
      },
      {
        timeout: 30_000,
        intervals: [500, 1_000, 2_000],
      },
    )
    .toBeGreaterThanOrEqual(200);
};

export const authHeaders = (token: string): Record<string, string> => ({
  Authorization: `Bearer ${token}`,
  "Content-Type": "application/json",
});

export const apiUrl = API_URL;
