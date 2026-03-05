const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000/api";
const TOKEN_STORAGE_KEY = "words_access_token";

const canUseLocalStorage = (): boolean =>
  typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const readPersistedToken = (): string | null => {
  if (!canUseLocalStorage()) return null;

  try {
    return window.localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
};

const persistToken = (token: string | null): void => {
  if (!canUseLocalStorage()) return;

  try {
    if (token) {
      window.localStorage.setItem(TOKEN_STORAGE_KEY, token);
      return;
    }

    window.localStorage.removeItem(TOKEN_STORAGE_KEY);
  } catch {
    // Ignore storage write errors and keep in-memory token as fallback.
  }
};

class ApiClient {
  private baseUrl: string;
  private token: string | null = null;

  constructor(baseUrl: string) {
    this.baseUrl = baseUrl;
    this.token = readPersistedToken();
  }

  setToken(token: string | null) {
    this.token = token;
    persistToken(token);
  }

  private async request<T>(
    path: string,
    options: RequestInit = {},
  ): Promise<T> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...(options.headers as Record<string, string>),
    };

    if (this.token) {
      headers["Authorization"] = `Bearer ${this.token}`;
    }

    const response = await fetch(`${this.baseUrl}${path}`, {
      ...options,
      headers,
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new ApiError(
        response.status,
        body?.detail ?? `Request failed: ${response.status}`,
      );
    }

    return response.json();
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  post<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  put<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      body: body ? JSON.stringify(body) : undefined,
    });
  }

  delete<T>(path: string): Promise<T> {
    return this.request<T>(path, { method: "DELETE" });
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
