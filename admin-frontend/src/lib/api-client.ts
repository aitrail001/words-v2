import { redirectToLogin } from "@/lib/auth-redirect";
import {
  clearAuthTokens,
  persistAuthTokens,
  readAccessToken,
  readRefreshToken,
} from "@/lib/auth-session";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "/api";

const parseJsonBody = async (response: Response): Promise<any> =>
  response.json().catch(() => null);

class ApiClient {
  private baseUrl: string;
  private accessToken: string | null = null;
  private refreshToken: string | null = null;
  private refreshPromise: Promise<boolean> | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.accessToken = readAccessToken();
    this.refreshToken = readRefreshToken();
  }

  setToken(token: string | null) {
    if (token === null) {
      this.setTokens(null, null);
      return;
    }

    this.setTokens(token, this.refreshToken);
  }

  setTokens(accessToken: string | null, refreshToken: string | null) {
    this.accessToken = accessToken;
    this.refreshToken = refreshToken;
    persistAuthTokens(accessToken, refreshToken);
  }

  private shouldHandleAuthFailure(path: string): boolean {
    return !path.startsWith("/auth/");
  }

  private async refreshAccessToken(): Promise<boolean> {
    if (!this.refreshToken) return false;
    if (this.refreshPromise) return this.refreshPromise;

    this.refreshPromise = (async () => {
      try {
        const response = await fetch(`${this.baseUrl}/auth/refresh`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ refresh_token: this.refreshToken }),
          credentials: "include",
        });

        if (!response.ok) {
          return false;
        }

        const body = await parseJsonBody(response);
        const nextAccessToken =
          typeof body?.access_token === "string" ? body.access_token : null;
        const nextRefreshToken =
          typeof body?.refresh_token === "string" ? body.refresh_token : null;
        if (!nextAccessToken || !nextRefreshToken) {
          return false;
        }

        this.setTokens(nextAccessToken, nextRefreshToken);
        return true;
      } catch {
        return false;
      } finally {
        this.refreshPromise = null;
      }
    })();

    return this.refreshPromise;
  }

  private clearSessionAndRedirect(): void {
    this.accessToken = null;
    this.refreshToken = null;
    clearAuthTokens();
    redirectToLogin();
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
    allowRefresh = true,
  ): Promise<T> {
    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };
    const hasContentTypeHeader = Object.keys(headers).some(
      (headerName) => headerName.toLowerCase() === "content-type",
    );
    if (
      options.body !== undefined &&
      options.body !== null &&
      !(options.body instanceof FormData) &&
      !hasContentTypeHeader
    ) {
      headers["Content-Type"] = "application/json";
    }

    if (this.accessToken) {
      headers["Authorization"] = `Bearer ${this.accessToken}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    if (response.status === 401 && this.shouldHandleAuthFailure(path)) {
      if (allowRefresh) {
        const refreshSucceeded = await this.refreshAccessToken();
        if (refreshSucceeded) {
          return this.request<T>(path, options, false);
        }
      }

      this.clearSessionAndRedirect();
      throw new ApiError(401, "Authentication required");
    }

    if (!response.ok) {
      const body = await parseJsonBody(response);
      throw new ApiError(
        response.status,
        body?.detail ?? `Request failed: ${response.status}`,
      );
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return parseJsonBody(response);
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: this.normalizeBody(body),
    });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: this.normalizeBody(body),
    });
  }

  patch<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      body: this.normalizeBody(body),
    });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
  }

  async logout(): Promise<void> {
    try {
      await this.request("/auth/logout", { method: "POST" }, false);
    } catch {
      // Client-side logout should always clear local auth state.
    }

    this.clearSessionAndRedirect();
  }

  private normalizeBody(body: unknown): BodyInit | undefined {
    if (body === undefined || body === null) {
      return undefined;
    }
    if (body instanceof FormData) {
      return body;
    }
    if (typeof body === "string") {
      return body;
    }
    return JSON.stringify(body);
  }
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export const apiClient = new ApiClient(API_BASE_URL);
