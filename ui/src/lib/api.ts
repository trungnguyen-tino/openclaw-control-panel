// Same-origin fetch wrapper that auto-attaches the stored Bearer key.
// 401 → wipe token + redirect to /login.

const AUTH_KEY_STORAGE = "openclaw.mgmt.key";

export function getStoredKey(): string | null {
  try {
    return localStorage.getItem(AUTH_KEY_STORAGE);
  } catch {
    return null;
  }
}

export function setStoredKey(key: string): void {
  localStorage.setItem(AUTH_KEY_STORAGE, key);
}

export function clearStoredKey(): void {
  localStorage.removeItem(AUTH_KEY_STORAGE);
}

export async function api<T = unknown>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const key = getStoredKey();
  const headers: Record<string, string> = {
    ...(opts.body && !(opts.body instanceof FormData)
      ? { "Content-Type": "application/json" }
      : {}),
    ...(key ? { Authorization: `Bearer ${key}` } : {}),
    ...((opts.headers as Record<string, string>) ?? {}),
  };
  const res = await fetch(path, { ...opts, headers });
  if (res.status === 401) {
    clearStoredKey();
    if (!path.startsWith("/api/auth/login")) {
      window.location.href = "/login";
    }
    throw new Error("Unauthorized");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.error ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function jsonBody(payload: unknown): RequestInit {
  return { method: "POST", body: JSON.stringify(payload) };
}
