"use client";

import { ThemeProvider } from "next-themes";
import { useEffect } from "react";
import { useApexUi } from "@/lib/apex/store";

/**
 * ApexThemeProvider — applies the Apex semantic palette via the .light class
 * on <html>. Also applies the user-selected accent color via --c-accent.
 */
export function ApexThemeProvider({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider
      attribute="class"
      defaultTheme="dark"
      enableSystem={false}
      disableTransitionOnChange
      value={{ dark: "dark", light: "light" }}
    >
      <ThemeSync />
      <AccentColorSync />
      {children}
    </ThemeProvider>
  );
}

/** Ensures the html class always reflects next-themes' resolved theme. */
function ThemeSync() {
  useEffect(() => {
    const apply = () => {
      const isLight = document.documentElement.classList.contains("light");
      document.documentElement.style.colorScheme = isLight ? "light" : "dark";
    };
    apply();
    const obs = new MutationObserver(apply);
    obs.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return null;
}

/** Applies the user-selected accent color via --c-accent CSS variable. */
function AccentColorSync() {
  const accentColor = useApexUi((s) => s.accentColor);
  useEffect(() => {
    document.documentElement.style.setProperty("--c-accent", accentColor || "#10b981");
  }, [accentColor]);
  return null;
}
