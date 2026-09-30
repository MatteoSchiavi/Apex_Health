"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";
import type { Locale, Theme, Units, ViewKey } from "./types";

/**
 * Apex UI store — owns ONLY client UI state (theme, locale, current view,
 * selection ids). Per the design law, Zustand never holds server data.
 */

interface ApexUiState {
  // session
  authed: boolean;
  signIn: () => void;
  signOut: () => void;

  // theme
  theme: Theme;
  setTheme: (t: Theme) => void;
  toggleTheme: () => void;

  // locale
  locale: Locale;
  setLocale: (l: Locale) => void;

  // units (mirrors Me.units; persisted as a client UI preference)
  units: Units;
  setUnits: (u: Units) => void;

  // navigation
  view: ViewKey;
  setView: (v: ViewKey) => void;

  // selections
  selectedActivityId: number | null;
  selectActivity: (id: number | null) => void;
  selectedSleepDate: string | null;
  selectSleepDate: (d: string | null) => void;
  selectedMetricKey: string | null;
  selectMetric: (k: string | null) => void;
  selectedChatId: number | null;
  selectChat: (id: number | null) => void;
  activeGymSessionId: number | null;
  setActiveGymSession: (id: number | null) => void;
}

export const useApexUi = create<ApexUiState>()(
  persist(
    (set, get) => ({
      authed: false,
      signIn: () => set({ authed: true, view: "overview" }),
      signOut: () => set({ authed: false, view: "welcome" }),

      theme: "dark",
      setTheme: (t) => set({ theme: t }),
      toggleTheme: () => set({ theme: get().theme === "dark" ? "light" : "dark" }),

      locale: "en",
      setLocale: (l) => set({ locale: l }),

      units: "metric",
      setUnits: (u) => set({ units: u }),

      view: "welcome",
      setView: (v) => set({ view: v }),

      selectedActivityId: null,
      selectActivity: (id) => set({ selectedActivityId: id }),
      selectedSleepDate: null,
      selectSleepDate: (d) => set({ selectedSleepDate: d }),
      selectedMetricKey: null,
      selectMetric: (k) => set({ selectedMetricKey: k }),
      selectedChatId: null,
      selectChat: (id) => set({ selectedChatId: id }),
      activeGymSessionId: null,
      setActiveGymSession: (id) => set({ activeGymSessionId: id }),
    }),
    {
      name: "apex-ui",
      storage: createJSONStorage(() => (typeof window === "undefined" ? undefined : (window.localStorage as Storage))),
      partialize: (s) => ({
        authed: s.authed,
        theme: s.theme,
        locale: s.locale,
        units: s.units,
      }),
    }
  )
);
