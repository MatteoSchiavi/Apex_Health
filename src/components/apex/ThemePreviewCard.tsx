"use client";

/**
 * Apex Health — ThemePreviewCard.
 *
 * A small live preview of how the Apex dashboard will look in the selected
 * theme. Shown next to the theme segmented control on the Settings > Appearance
 * section. Clicking the preview applies that theme immediately (no commit step).
 *
 * IMPORTANT: the preview container LOCALLY re-declares all theme CSS variables
 * for the target theme, so it always renders in the correct theme regardless
 * of which theme is currently applied to <html>. (Previously it relied on a
 * `.dark`/`.light` class which only affects Tailwind `dark:` variants, not the
 * raw `var(--c-*)` custom properties — so both previews rendered in the active
 * theme. Fixed.)
 */

import { Moon, Sun } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { Eyebrow } from "@/components/apex/kit";
import type { CSSProperties } from "react";

/** The full set of theme CSS vars, for one theme. Kept in sync with globals.css. */
const THEME_VARS: Record<"dark" | "light", Record<string, string>> = {
  dark: {
    "--c-bg": "#000000",
    "--c-bg-accent": "#08080a",
    "--c-surface": "#0e0e10",
    "--c-surface-2": "#161618",
    "--c-surface-3": "#1e1e22",
    "--c-hairline": "rgba(255, 255, 255, 0.08)",
    "--c-hairline-strong": "rgba(255, 255, 255, 0.14)",
    "--c-text": "#f0f0f2",
    "--c-text-2": "#c0c0c4",
    "--c-text-muted": "#80808a",
    "--c-text-faint": "#50505a",
    "--c-primary": "#10b981",
    "--c-primary-soft": "rgba(16, 185, 129, 0.12)",
    "--c-primary-text": "#34d399",
    "--c-positive": "#10b981",
    "--c-positive-soft": "rgba(16, 185, 129, 0.10)",
    "--c-positive-text": "#34d399",
  },
  light: {
    "--c-bg": "#f5f5f5",
    "--c-bg-accent": "#fafafa",
    "--c-surface": "#ffffff",
    "--c-surface-2": "#f8f8f8",
    "--c-surface-3": "#eaeaec",
    "--c-hairline": "rgba(0, 0, 0, 0.08)",
    "--c-hairline-strong": "rgba(0, 0, 0, 0.14)",
    "--c-text": "#0a0a0a",
    "--c-text-2": "#3a3a3c",
    "--c-text-muted": "#6a6a70",
    "--c-text-faint": "#9a9aa0",
    "--c-primary": "#059669",
    "--c-primary-soft": "rgba(5, 150, 105, 0.10)",
    "--c-primary-text": "#047857",
    "--c-positive": "#059669",
    "--c-positive-soft": "rgba(5, 150, 105, 0.08)",
    "--c-positive-text": "#047857",
  },
};

interface ThemePreviewCardProps {
  previewTheme: "dark" | "light";
  isActive: boolean;
  onApply: () => void;
}

export function ThemePreviewCard({
  previewTheme,
  isActive,
  onApply,
}: ThemePreviewCardProps) {
  const t = useT();
  const Icon = previewTheme === "dark" ? Moon : Sun;
  const label = previewTheme === "dark" ? t("theme.dark") : t("theme.light");

  // Locally force the theme's CSS variables so the preview is always honest.
  const themeStyle = THEME_VARS[previewTheme] as CSSProperties;

  return (
    <button
      type="button"
      onClick={onApply}
      className={`group relative overflow-hidden rounded-[var(--radius-card)] border text-left transition-all ${
        isActive
          ? "border-primary ring-2 ring-primary/30"
          : "border-hairline hover:border-hairline2"
      }`}
      aria-pressed={isActive}
      aria-label={`Use ${label} theme`}
      style={themeStyle}
    >
      <div className="p-3" style={{ background: "var(--c-bg-accent)", color: "var(--c-text)" }}>
        {/* Header row: icon + label + active check */}
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div
              className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)]"
              style={{
                background: "var(--c-primary-soft)",
                color: "var(--c-primary-text)",
              }}
            >
              <Icon size={11} />
            </div>
            <span className="text-[12px] font-semibold" style={{ color: "var(--c-text)" }}>
              {label}
            </span>
          </div>
          {isActive && (
            <span
              className="num rounded-[var(--radius-control)] px-1.5 py-0.5 text-[12px] font-semibold"
              style={{
                background: "var(--c-primary-soft)",
                color: "var(--c-primary-text)",
              }}
            >
              ACTIVE
            </span>
          )}
        </div>

        {/* Mini dashboard preview */}
        <div
          className="rounded-[var(--radius-card)] border p-2"
          style={{
            borderColor: "var(--c-hairline)",
            background: "var(--c-surface)",
          }}
        >
          <Eyebrow>
            <span style={{ color: "var(--c-text-muted)" }}>READINESS</span>
          </Eyebrow>
          <div
            className="num mt-1 flex items-baseline gap-1 text-[20px] font-bold"
            style={{ color: "var(--c-text)" }}
          >
            84
            <span className="text-[12px] font-medium" style={{ color: "var(--c-text-muted)" }}>
              /100
            </span>
          </div>
          {/* Score bar — STATE color (positive = in good range), not accent */}
          <div
            className="mt-1.5 h-1 w-full overflow-hidden rounded-full"
            style={{ background: "var(--c-surface-3)" }}
          >
            <div
              style={{
                width: "84%",
                height: "100%",
                background: "var(--c-positive)",
              }}
            />
          </div>
          {/* Sub-row: HRV + dot */}
          <div className="mt-2 flex items-center justify-between">
            <span className="num text-[12px]" style={{ color: "var(--c-text-faint)" }}>
              HRV
            </span>
            <div className="flex items-center gap-1">
              <span className="h-1 w-1 rounded-full" style={{ background: "var(--c-positive)" }} />
              <span
                className="num text-[12px] font-semibold"
                style={{ color: "var(--c-positive-text)" }}
              >
                64 ms
              </span>
            </div>
          </div>
        </div>

        {/* Bottom hint */}
        <div className="num mt-2 text-[12px]" style={{ color: "var(--c-text-faint)" }}>
          {isActive ? "Currently applied" : "Click to apply"}
        </div>
      </div>
    </button>
  );
}
