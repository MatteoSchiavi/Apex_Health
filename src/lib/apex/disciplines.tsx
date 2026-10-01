/**
 * Apex Health — discipline metadata.
 *
 * Centralizes:
 * - the colour assigned to each discipline (used by weekly-volume stack and row dots)
 * - a human label that's broader than `friendlyDiscipline` (adds sailing / boating / rowing)
 * - the *primary metric* per sport — the one number the compact row should highlight
 *   (distance for endurance sports, pace for running, nothing for strength)
 * - ISO-week helpers shared by the activities list + weekly-volume route
 *
 * Plan §3 calls for discipline-aware primary metrics; the previous Activities list
 * showed the same four stats on every card, which left power empty for most sports.
 */

import type { ActivityCard, Locale } from "./types";

/** Disciplines surfaced in the filter chips / weekly-volume stack. */
export const DISCIPLINES: string[] = [
  "cycling",
  "running",
  "swimming",
  "strength",
  "sailing",
  "boating",
  "rowing",
  "hiking",
  "walking",
];

/** Hex colour per discipline (plan §3 spec). */
export const DISCIPLINE_COLORS: Record<string, string> = {
  cycling: "#10b981", // emerald
  running: "#f97316", // orange
  swimming: "#06b6d4", // cyan
  strength: "#8b5cf6", // violet
  sailing: "#3b82f6", // blue
  boating: "#14b8a6", // teal
  rowing: "#14b8a6", // teal (alias of boating)
  hiking: "#f59e0b", // amber
  walking: "#f43f5e", // rose
};

/** Localised discipline label (extends friendlyDiscipline with sailing/boating/rowing). */
const LABELS: Record<string, [string, string]> = {
  cycling: ["Cycling", "Ciclismo"],
  running: ["Running", "Corsa"],
  swimming: ["Swimming", "Nuoto"],
  strength: ["Strength", "Forza"],
  sailing: ["Sailing", "Vela"],
  boating: ["Boating", "Barca"],
  rowing: ["Rowing", "Canottaggio"],
  hiking: ["Hiking", "Escursionismo"],
  walking: ["Walking", "Camminata"],
};

export function disciplineLabel(d: string | null | undefined, locale: Locale = "en"): string {
  if (!d) return locale === "it" ? "Altro" : "Other";
  const entry = LABELS[d];
  if (!entry) return d;
  return entry[locale === "it" ? 1 : 0];
}

/** A small colour swatch element (used in chips + week headers). */
export function DisciplineDot({
  discipline,
  size = 8,
}: {
  discipline: string;
  size?: number;
}) {
  return (
    <span
      aria-hidden
      className="inline-block rounded-full"
      style={{
        width: size,
        height: size,
        background: DISCIPLINE_COLORS[discipline] ?? "var(--c-hairline2)",
      }}
    />
  );
}

/** What's the primary metric this sport should surface on a compact row? */
export function primaryMetricFor(
  a: ActivityCard,
  locale: Locale = "en",
  units: "metric" | "imperial" = "metric"
): { label: string; value: string } | null {
  // Cast to string — the Discipline union doesn't include "rowing", but the DB
  // stores that. Treating discipline as a string here keeps this helper tolerant.
  const d = a.discipline as string;
  switch (d) {
    case "cycling":
    case "boating":
    case "rowing":
    case "sailing":
    case "swimming":
    case "hiking":
    case "walking": {
      if (a.distance_m === null) return null;
      const km = units === "imperial" ? a.distance_m / 1609.344 : a.distance_m / 1000;
      const v = km.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
      return {
        label: locale === "it" ? "Distanza" : "Distance",
        value: units === "imperial" ? `${v} mi` : `${v} km`,
      };
    }
    case "running": {
      // Pace: sec per km (or per mile). If no distance/speed, fall back to distance.
      if (a.distance_m && a.distance_m > 0 && a.duration_s > 0) {
        const perKm = a.duration_s / (a.distance_m / 1000);
        const perUnit = units === "imperial" ? perKm * 1.609344 : perKm;
        const mm = Math.floor(perUnit / 60);
        const ss = Math.round(perUnit % 60);
        return {
          label: locale === "it" ? "Ritmo" : "Pace",
          value: `${mm}:${String(ss).padStart(2, "0")}${units === "imperial" ? "/mi" : "/km"}`,
        };
      }
      if (a.distance_m !== null) {
        const km = units === "imperial" ? a.distance_m / 1609.344 : a.distance_m / 1000;
        const v = km.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
        return {
          label: locale === "it" ? "Distanza" : "Distance",
          value: units === "imperial" ? `${v} mi` : `${v} km`,
        };
      }
      return null;
    }
    case "strength":
      return null; // no primary metric
    default:
      return null;
  }
}

/* ------------------------------------------------------------- ISO week */

/** Returns the Monday that begins the ISO week containing `date` (local time). */
export function isoWeekStart(date: Date): Date {
  const d = new Date(date.getFullYear(), date.getMonth(), date.getDate());
  const dow = d.getDay(); // 0 = Sun .. 6 = Sat
  // ISO weeks start Monday. Shift Sunday (0) → -6, others → 1 - dow.
  const delta = dow === 0 ? -6 : 1 - dow;
  d.setDate(d.getDate() + delta);
  return d;
}

/** Format a Date as YYYY-MM-DD using local time (not UTC). */
export function toLocalDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${dd}`;
}

/** Returns the YYYY-MM-DD of the Monday that begins the week containing the given date string. */
export function weekKeyForLocalDate(localDate: string): string {
  // localDate is "YYYY-MM-DD"
  const [y, m, d] = localDate.split("-").map(Number);
  if (!y || !m || !d) return localDate;
  const date = new Date(y, m - 1, d);
  return toLocalDateStr(isoWeekStart(date));
}

/** Returns the YYYY-MM-DD of the Monday that begins the week containing the given ISO datetime. */
export function weekKeyForISO(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  return toLocalDateStr(isoWeekStart(d));
}

/** Returns the YYYY-MM-DD of the Monday `weeksAgo` weeks before this week. */
export function weekStartAgo(weeksAgo: number, from: Date = new Date()): Date {
  const start = isoWeekStart(from);
  start.setDate(start.getDate() - weeksAgo * 7);
  return start;
}
