export const ACCESS_TOKEN_STORAGE_KEY = "words_admin_access_token";
export const ACCESS_TOKEN_COOKIE_KEY = "words_admin_access_token";
export const REFRESH_TOKEN_STORAGE_KEY = "words_admin_refresh_token";
export const AUTH_TOKEN_CHANGED_EVENT = "words-admin:auth-token-changed";

const canUseLocalStorage = (): boolean =>
  typeof window !== "undefined" && typeof window.localStorage !== "undefined";

const writeAccessTokenCookie = (token: string | null): void => {
  if (typeof document === "undefined") return;

  if (token) {
    document.cookie = `${ACCESS_TOKEN_COOKIE_KEY}=${encodeURIComponent(token)}; Path=/; SameSite=Lax`;
    return;
  }

  document.cookie = `${ACCESS_TOKEN_COOKIE_KEY}=; Path=/; Max-Age=0; SameSite=Lax`;
};

const emitTokenChanged = (): void => {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new Event(AUTH_TOKEN_CHANGED_EVENT));
};

const readStorageValue = (key: string): string | null => {
  if (!canUseLocalStorage()) return null;

  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
};

const writeStorageValue = (key: string, value: string | null): void => {
  if (!canUseLocalStorage()) return;

  try {
    if (value) {
      window.localStorage.setItem(key, value);
    } else {
      window.localStorage.removeItem(key);
    }
  } catch {
  }
};

export const readAccessToken = (): string | null =>
  readStorageValue(ACCESS_TOKEN_STORAGE_KEY);

export const readRefreshToken = (): string | null =>
  readStorageValue(REFRESH_TOKEN_STORAGE_KEY);

export const persistAuthTokens = (
  accessToken: string | null,
  refreshToken: string | null,
): void => {
  writeStorageValue(ACCESS_TOKEN_STORAGE_KEY, accessToken);
  writeStorageValue(REFRESH_TOKEN_STORAGE_KEY, refreshToken);
  writeAccessTokenCookie(accessToken);
  emitTokenChanged();
};

export const clearAuthTokens = (): void => {
  persistAuthTokens(null, null);
};

export const persistAccessToken = (token: string | null): void => {
  persistAuthTokens(token, readRefreshToken());
};
