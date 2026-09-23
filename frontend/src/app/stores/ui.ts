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
import type { Me } from "../api";

export type Theme = "dark" | "light";
export type Locale = "en" | "it";

interface UiState {
  theme: Theme;
  locale: Locale;
  me: Me | null;
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
  } catch { /* private mode */ }
}

function applyLocale(l: Locale) {
  document.documentElement.lang = l;
  // Runtime switch: components use useTranslation(), which only re-renders
  // when i18next's language actually changes — the html lang attribute
  // alone is just the pre-paint hint from index.html.
  if (i18next.language !== l) void i18next.changeLanguage(l);
  try {
    localStorage.setItem("apex.locale", l);
  } catch { /* private mode */ }
}

function storedTheme(): Theme {
  try {
    const t = localStorage.getItem("apex.theme");
    if (t === "light" || t === "dark") return t;
  } catch { /* ignore */ }
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

function storedLocale(): Locale {
  try {
    const l = localStorage.getItem("apex.locale");
    if (l === "it" || l === "en") return l;
  } catch { /* ignore */ }
  return navigator.language.toLowerCase().startsWith("it") ? "it" : "en";
}

export const useUi = create<UiState>((set) => ({
  theme: storedTheme(),
  locale: storedLocale(),
  me: null,
  setTheme: (t, persist = true) => {
    applyTheme(t);
    set({ theme: t });
    if (persist) {
      import("../api").then(({ api }) => api.put("/me", { theme: t }).catch(() => undefined));
    }
  },
  setLocale: (l, persist = true) => {
    applyLocale(l);
    set({ locale: l });
    if (persist) {
      import("../api").then(({ api }) => api.put("/me", { locale: l }).catch(() => undefined));
    }
  },
  setMe: (me) => {
    set({ me });
    if (me) {
      applyTheme(me.theme);
      applyLocale(me.locale);
    }
  },
}));
