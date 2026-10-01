/**
 * Apex Health — Gear helpers (plan §6)
 *
 * Shared between the Gear page and the API routes:
 *  - computeUsagePct:        the binding % used for the binding interval
 *  - gearStateTone:          state tone (positive / warning / alert) from usage
 *  - bindingMetric:          which interval (hours or km) is binding for a piece
 *  - GEAR_TYPE_ICON:         lucide icon per gear_type (used by the cards)
 *  - GEAR_TYPES / SERVICE_PRESETS: constants matching `gear.type_options` /
 *    `gear.service_presets` i18n keys
 *
 * `parseDefaultFor` / `serializeDefaultFor` live in `src/lib/apex/gearDb.ts`
 * (the API-side companion that also owns the raw-SQL workaround for the
 * `defaultFor` column).
 *
 * Lives outside kit.tsx (which is off-limits) so the page can build gear-type
 * iconography without inventing a new visual vocabulary — it just imports the
 * same lucide icons the kit uses and pairs them with the existing Apex tones.
 */

import {
  Bike,
  Footprints,
  Mountain,
  Sailboat,
  Watch,
  Waves,
  type LucideIcon,
} from "lucide-react";

export type GearTone = "positive" | "warning" | "alert" | "muted";

/** Per spec §6: usage ≥ 100% alert, ≥ 80% warning, else positive. */
export function gearStateTone(pct: number | null | undefined): GearTone {
  if (pct === null || pct === undefined || !Number.isFinite(pct)) return "muted";
  if (pct >= 100) return "alert";
  if (pct >= 80) return "warning";
  return "positive";
}

/**
 * Compute the binding usage percent: the larger of the hours and km
 * percentages against their respective intervals. Guards divide-by-zero.
 * Returns 0 when no interval is set.
 */
export function computeUsagePct(
  hoursSince: number,
  kmSince: number,
  intervalHours: number | null,
  intervalKm: number | null,
): number {
  const hPct =
    intervalHours && intervalHours > 0 ? (hoursSince / intervalHours) * 100 : 0;
  const kPct =
    intervalKm && intervalKm > 0 ? (kmSince / intervalKm) * 100 : 0;
  return Math.round(Math.max(hPct, kPct) * 10) / 10;
}

/**
 * Which interval is binding for this gear (the one driving usage_pct)?
 * Returns 'hours' | 'km' | null. Prefers hours when both are equal contributors.
 */
export function bindingMetric(
  hoursSince: number,
  kmSince: number,
  intervalHours: number | null,
  intervalKm: number | null,
): "hours" | "km" | null {
  if (!intervalHours && !intervalKm) return null;
  if (!intervalKm) return "hours";
  if (!intervalHours) return "km";
  const hPct = (hoursSince / intervalHours) * 100;
  const kPct = (kmSince / intervalKm) * 100;
  if (kPct > hPct) return "km";
  return "hours";
}

/**
 * lucide icon per gear_type. Falls back to Waves for unknown types so gear
 * seeded by other agents (e.g. "road_bike", "running_shoes") still renders.
 */
export const GEAR_TYPE_ICON: Record<string, LucideIcon> = {
  bike: Bike,
  mtb: Mountain,
  emtb: Mountain,
  road_bike: Bike,
  boat: Sailboat,
  sail: Sailboat,
  shoes: Footprints,
  running_shoes: Footprints,
  watch: Watch,
  other: Bike,
};

/** The gear types offered in the Add-gear form (matches i18n `gear.type_options.*`). */
export const GEAR_TYPES = [
  "bike",
  "mtb",
  "emtb",
  "boat",
  "sail",
  "shoes",
  "watch",
  "other",
] as const;
export type GearType = (typeof GEAR_TYPES)[number];

/** Service-type quick presets (matches i18n `gear.service_presets.*`). */
export const SERVICE_PRESETS = ["oil", "chain", "brake", "suspension", "wax"] as const;

