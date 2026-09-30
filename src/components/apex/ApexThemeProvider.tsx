"use client";

import { ThemeProvider } from "next-themes";
import { useEffect } from "react";

/**
 * ApexThemeProvider — applies the Apex semantic palette via the .light class
 * on <html>. next-themes drives the dark/light toggle; we map dark→:root,
 * light→.light (see globals.css).
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
