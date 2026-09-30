"use client";

/**
 * Apex Health — ThemePreviewCard.
 *
 * A small live preview of how the Apex dashboard will look in the selected
 * theme. Shown next to the theme segmented control on the Settings > Appearance
 * section. Clicking the preview applies that theme immediately (no commit step).
 *
 * Renders a mini "dashboard snapshot" with:
 *  - readiness BigStat (84/100)
 *  - ScoreBar
 *  - HRV sparkline
 *
 * The preview container itself uses a forced `dark:` or `light:` class so the
 * user sees the target theme even before applying.
 */

import { Moon, Sun } from "lucide-react";
import { useT } from "@/lib/apex/i18nContext";
import { Eyebrow } from "@/components/apex/kit";

interface ThemePreviewCardProps {
  /** The theme this preview represents */
  previewTheme: "dark" | "light";
  /** Whether this preview is currently active (matches the applied theme) */
  isActive: boolean;
  /** Apply this theme when clicked */
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
    >
      {/* Forced-theme wrapper: this scopes our `dark:` / `light:` overrides
          to this subtree without affecting the rest of the page. */}
      <div
        className={previewTheme === "dark" ? "dark" : "light"}
        style={{ background: "var(--c-bg-accent)" }}
      >
        <div
          className="p-3"
          style={{ background: "var(--c-bg-accent)", color: "var(--c-text)" }}
        >
          {/* Header row: icon + label + active check */}
          <div className="mb-2 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div
                className="flex h-6 w-6 items-center justify-center rounded-[var(--radius-control)]"
                style={{
                  background: previewTheme === "dark" ? "var(--c-primary-soft)" : "var(--c-primary-soft)",
                  color: "var(--c-primary-text)",
                }}
              >
                <Icon size={11} />
              </div>
              <span
                className="text-[12px] font-semibold"
                style={{ color: "var(--c-text)" }}
              >
                {label}
              </span>
            </div>
            {isActive && (
              <span
                className="num rounded-[var(--radius-control)] px-1.5 py-0.5 text-[9px] font-semibold"
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
              <span
                className="text-[10px] font-medium"
                style={{ color: "var(--c-text-muted)" }}
              >
                /100
              </span>
            </div>
            {/* Score bar */}
            <div
              className="mt-1.5 h-1 w-full overflow-hidden rounded-full"
              style={{ background: "var(--c-surface-3)" }}
            >
              <div
                style={{
                  width: "84%",
                  height: "100%",
                  background: "var(--c-primary)",
                }}
              />
            </div>
            {/* Sub-row: HRV + dot */}
            <div className="mt-2 flex items-center justify-between">
              <span
                className="num text-[9px]"
                style={{ color: "var(--c-text-faint)" }}
              >
                HRV
              </span>
              <div className="flex items-center gap-1">
                <span
                  className="h-1 w-1 rounded-full"
                  style={{ background: "var(--c-positive)" }}
                />
                <span
                  className="num text-[10px] font-semibold"
                  style={{ color: "var(--c-positive-text)" }}
                >
                  64 ms
                </span>
              </div>
            </div>
          </div>

          {/* Bottom hint */}
          <div
            className="num mt-2 text-[10px]"
            style={{ color: "var(--c-text-faint)" }}
          >
            {isActive ? "Currently applied" : "Click to apply"}
          </div>
        </div>
      </div>
    </button>
  );
}
