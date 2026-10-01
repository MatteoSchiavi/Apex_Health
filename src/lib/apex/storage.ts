/**
 * Per-user browser storage helpers (plan finding 4).
 *
 * Browser storage is scoped to the USER, not the browser. A second account on
 * the same browser must NOT inherit the first one's drafts, chat ids, or
 * compare selections. Keys are namespaced by user id; `clearUserStorage` wipes
 * everything for a user on sign-out.
 */

const PREFIX = "apex";

/** Build a per-user storage key. */
export function userKey(userId: number | null, key: string): string {
  const uid = userId ?? 0; // 0 = anonymous / pre-auth
  return `${PREFIX}.u${uid}.${key}`;
}

/** Read a per-user value, falling back to the legacy un-scoped key on first access. */
export function getUserItem<T>(userId: number | null, key: string, fallback: T): T {
  if (typeof window === "undefined") return fallback;
  const scoped = userKey(userId, key);
  const legacy = `${PREFIX}.${key}`;
  try {
    const raw = window.localStorage.getItem(scoped);
    if (raw !== null) return JSON.parse(raw) as T;
    // migrate from legacy key once, then move it under the scoped key
    const legacyRaw = window.localStorage.getItem(legacy);
    if (legacyRaw !== null) {
      window.localStorage.setItem(scoped, legacyRaw);
      window.localStorage.removeItem(legacy);
      return JSON.parse(legacyRaw) as T;
    }
  } catch {
    /* ignore parse errors */
  }
  return fallback;
}

/** Write a per-user value. */
export function setUserItem<T>(userId: number | null, key: string, value: T): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(userKey(userId, key), JSON.stringify(value));
  } catch {
    /* quota / private mode — ignore */
  }
}

/** Remove a per-user value. */
export function removeUserItem(userId: number | null, key: string): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(userKey(userId, key));
  } catch {
    /* ignore */
  }
}

/** Wipe ALL per-user keys for a user (call on sign-out). */
export function clearUserStorage(userId: number | null): void {
  if (typeof window === "undefined") return;
  const uid = userId ?? 0;
  const prefix = `${PREFIX}.u${uid}.`;
  const legacyPrefix = `${PREFIX}.`;
  try {
    const toRemove: string[] = [];
    for (let i = 0; i < window.localStorage.length; i++) {
      const k = window.localStorage.key(i);
      if (k && (k.startsWith(prefix) || k.startsWith(legacyPrefix))) {
        // only clear legacy keys that are NOT scoped (avoid clearing other users)
        if (k.startsWith(prefix)) toRemove.push(k);
      }
    }
    toRemove.forEach((k) => window.localStorage.removeItem(k));
  } catch {
    /* ignore */
  }
}
