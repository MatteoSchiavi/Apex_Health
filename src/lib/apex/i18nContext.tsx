"use client";

import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { translations, type Locale } from "./i18n";

type Dict = typeof translations.en;

interface I18nCtx {
  locale: Locale;
  t: (path: string, vars?: Record<string, string | number>) => string;
  setLocale: (l: Locale) => void;
}

const Ctx = createContext<I18nCtx | null>(null);

/** Resolve a dotted path against the dictionary. */
function resolve(obj: unknown, path: string): string {
  const parts = path.split(".");
  let cur: unknown = obj;
  for (const p of parts) {
    if (cur && typeof cur === "object" && p in (cur as Record<string, unknown>)) {
      cur = (cur as Record<string, unknown>)[p];
    } else {
      return path;
    }
  }
  return typeof cur === "string" ? cur : path;
}

/** Replace {{name}} placeholders with values from `vars`. */
function interpolate(str: string, vars?: Record<string, string | number>): string {
  if (!vars) return str;
  return str.replace(/\{\{(\w+)\}\}/g, (_, k) =>
    vars[k] !== undefined ? String(vars[k]) : `{{${k}}}`
  );
}

export function I18nProvider({
  locale,
  setLocale,
  children,
}: {
  locale: Locale;
  setLocale: (l: Locale) => void;
  children: ReactNode;
}) {
  const t = useCallback(
    (path: string, vars?: Record<string, string | number>) => {
      const dict = (translations[locale] ?? translations.en) as Dict;
      const raw = resolve(dict, path);
      return interpolate(raw, vars);
    },
    [locale]
  );
  const value = useMemo(() => ({ locale, t, setLocale }), [locale, t, setLocale]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useI18n(): I18nCtx {
  const ctx = useContext(Ctx);
  if (!ctx) {
    // Fallback during SSR / before provider mounts
    return {
      locale: "en",
      t: (p: string) => p,
      setLocale: () => {},
    };
  }
  return ctx;
}

export function useT() {
  return useI18n().t;
}
