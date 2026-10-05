/**
 * UI store (zustand): theme, locale, session user.
 *
 * Theme + locale live on the ACCOUNT (users.theme / users.locale, migration
 * 0007) so the choice follows the user across devices; localStorage mirrors
 * them for instant first paint (index.html inline script) and offline
 * reconciliation on load. Changing them here updates both instantly and
 * persists via PUT /me.
 */

import { create } from "zustand";
import i18next from "../i18n";
import { api, type Me } from "../api";
import { queryClient } from "../query";

export type Theme = "dark" | "light";
export type Locale = "en" | "it";

export function clearAllAccountStorage() {
  try {
    for (let index = localStorage.length - 1; index >= 0; index--) {
      const key = localStorage.key(index);
      if (key && (/^apex\.chat\.[^.]+\.(draft|active)$/.test(key) || /^apex\.sync\.[^.]+$/.test(key))) localStorage.removeItem(key);
    }
  } catch { /* unavailable */ }
}

export function clearAccountStorage(userId: number | string) {
  try {
    for (const key of [
      `apex.chat.${userId}.draft`,
      `apex.chat.${userId}.active`,
      `apex.sync.${userId}`,
    ]) localStorage.removeItem(key);
  } catch { /* unavailable */ }
}

function clearOtherAccountStorage(userId: number | string) {
  try {
    for (let index = localStorage.length - 1; index >= 0; index--) {
      const key = localStorage.key(index);
      const owner = key?.match(/^apex\.(?:chat|sync)\.([^.]+)(?:\.(?:draft|active))?$/)?.[1];
      if (owner && owner !== String(userId)) localStorage.removeItem(key!);
    }
  } catch { /* unavailable */ }
}

interface UiState {
  theme: Theme;
  locale: Locale;
  me: Me | null;
  preferenceError: boolean;
  preferenceSaving: boolean;
  setTheme: (t: Theme, persist?: boolean) => void;
  setLocale: (l: Locale, persist?: boolean) => void;
  setMe: (me: Me | null) => void;
}

function applyTheme(t: Theme) {
  const root = document.documentElement;
  root.classList.remove("dark", "light");
  root.classList.add(t);
  try {
    localStorage.setItem("apex.theme", t);
  } catch {
    /* private mode */
  }
}

function applyLocale(l: Locale) {
  document.documentElement.lang = l;
  // Runtime switch: components use useTranslation(), which only re-renders
  // when i18next's language actually changes — the html lang attribute
  // alone is just the pre-paint hint from index.html.
  if (i18next.language !== l) void i18next.changeLanguage(l);
  try {
    localStorage.setItem("apex.locale", l);
  } catch {
    /* private mode */
  }
}

function storedTheme(): Theme {
  try {
    const t = localStorage.getItem("apex.theme");
    if (t === "light" || t === "dark") return t;
  } catch {
    /* ignore */
  }
  return window.matchMedia("(prefers-color-scheme: light)").matches
    ? "light"
    : "dark";
}

function storedLocale(): Locale {
  try {
    const l = localStorage.getItem("apex.locale");
    if (l === "it" || l === "en") return l;
  } catch {
    /* ignore */
  }
  return navigator.language.toLowerCase().startsWith("it") ? "it" : "en";
}

export const useUi = create<UiState>((set) => ({
  theme: storedTheme(),
  locale: storedLocale(),
  me: null,
  preferenceError: false,
  preferenceSaving: false,
  setTheme: (t, persist = true) => {
    if (persist && useUi.getState().preferenceSaving) return;
    applyTheme(t);
    set({ theme: t, preferenceError: false });
    if (persist && useUi.getState().me) {
      const previous = useUi.getState().me!.theme;
      const uid = useUi.getState().me!.user_id;
      set({ preferenceSaving: true });
      queryClient.setQueryData<Me>(["me"], (old) =>
        old ? { ...old, theme: t } : old,
      );
      api
        .put<Me>("/me", { theme: t })
        .then((me) => {
          if (useUi.getState().me?.user_id !== uid) return;
          queryClient.setQueryData(["me"], me);
          set({ me });
        })
        .catch(() => {
          if (
            useUi.getState().me?.user_id !== uid ||
            useUi.getState().theme !== t
          )
            return;
          applyTheme(previous);
          set({ theme: previous, preferenceError: true });
          queryClient.invalidateQueries({ queryKey: ["me"] });
        })
        .finally(() => {
          if (useUi.getState().me?.user_id === uid)
            set({ preferenceSaving: false });
        });
    }
  },
  setLocale: (l, persist = true) => {
    if (persist && useUi.getState().preferenceSaving) return;
    applyLocale(l);
    set({ locale: l, preferenceError: false });
    if (persist && useUi.getState().me) {
      const previous = useUi.getState().me!.locale;
      const uid = useUi.getState().me!.user_id;
      set({ preferenceSaving: true });
      queryClient.setQueryData<Me>(["me"], (old) =>
        old ? { ...old, locale: l } : old,
      );
      api
        .put<Me>("/me", { locale: l })
        .then((me) => {
          if (useUi.getState().me?.user_id !== uid) return;
          queryClient.setQueryData(["me"], me);
          set({ me });
        })
        .catch(() => {
          if (
            useUi.getState().me?.user_id !== uid ||
            useUi.getState().locale !== l
          )
            return;
          applyLocale(previous);
          set({ locale: previous, preferenceError: true });
          queryClient.invalidateQueries({ queryKey: ["me"] });
        })
        .finally(() => {
          if (useUi.getState().me?.user_id === uid)
            set({ preferenceSaving: false });
        });
    }
  },
  setMe: (me) => {
    const previousId = useUi.getState().me?.user_id;
    if (previousId != null && previousId !== me?.user_id) clearAccountStorage(previousId);
    if (me) clearOtherAccountStorage(me.user_id);
    set(
      me
        ? { me, theme: me.theme, locale: me.locale }
        : { me, preferenceError: false, preferenceSaving: false },
    );
    if (me) {
      applyTheme(me.theme);
      applyLocale(me.locale);
    }
  },
}));
