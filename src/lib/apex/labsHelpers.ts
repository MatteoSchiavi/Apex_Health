/**
 * Apex Health — Labs helpers (plan §7).
 *
 * Shared between the Labs page and the /api/labs routes:
 *  - MARKERS:           the six core markers (Hb, Hct, ferritin, iron, WBC, PLT)
 *                        with default reference ranges + units + labels.
 *  - DEFAULT_RANGES:    reference ranges used to pre-fill the Add panel form
 *                        (mirrors the backend's `reference_ranges` JSON).
 *  - statusForValue:    "normal" | "low" | "high" | "borderline" given a value
 *                        and its reference range (mirrors LabMarker.status).
 *  - markerValueGetter: pull a marker value off a LabPanel row (handles
 *                        both core + extra markers).
 *  - serializeRanges / parseRanges: JSON round-trip for the Prisma
 *                        `referenceRanges` (TEXT) column.
 *  - serializeExtra / parseExtra:  JSON round-trip for `extraMarkers`.
 *
 * Lives outside kit.tsx (which is off-limits). Page-side code uses
 * `rangeTone` + `toneFor` from the kit; this file owns the labs-specific
 * reference-range knowledge so the API routes and the page agree on it.
 */

import type { LabPanel } from "./types";

/** Marker metadata. Order matches the plan's marker selector. */
export interface MarkerMeta {
  key: string;
  label: string;
  unit: string;
  ref_low: number;
  ref_high: number;
}

/** The six core markers. Reference ranges are the standard adult ranges used
 *  by the backend's `medical/labs.py` defaults; the user can override per
 *  panel via the `reference_ranges` JSON column. */
export const CORE_MARKERS: MarkerMeta[] = [
  { key: "hemoglobin",  label: "Haemoglobin",  unit: "g/dL",  ref_low: 13.5, ref_high: 17.5 },
  { key: "hematocrit",  label: "Haematocrit",  unit: "%",     ref_low: 41,   ref_high: 50 },
  { key: "ferritin",    label: "Ferritin",     unit: "ng/mL", ref_low: 30,   ref_high: 400 },
  { key: "iron",        label: "Iron",         unit: "µg/dL", ref_low: 60,   ref_high: 170 },
  { key: "wbc",         label: "WBC",          unit: "10³/µL", ref_low: 4.0,  ref_high: 11.0 },
  { key: "plt",         label: "Platelets",    unit: "10³/µL", ref_low: 150,  ref_high: 400 },
];

/** Quick lookup by key. */
export const MARKER_BY_KEY: Record<string, MarkerMeta> = Object.fromEntries(
  CORE_MARKERS.map((m) => [m.key, m]),
);

/** Reference ranges the Add-panel form opens with — copied from the user's
 *  last panel when present, otherwise these defaults. Keyed by marker key
 *  (matches the shape of the `reference_ranges` JSON column). */
export const DEFAULT_RANGES: Record<string, { low: number; high: number; unit: string }> = Object.fromEntries(
  CORE_MARKERS.map((m) => [m.key, { low: m.ref_low, high: m.ref_high, unit: m.unit }]),
);

/** Compute a LabMarker-style status from a value against its reference range.
 *  Margins mirror the kit's `rangeTone`: 10% of the span on either side is
 *  "borderline" (still in range but worth flagging). */
export function statusForValue(
  value: number | null,
  low: number | null,
  high: number | null,
): "normal" | "low" | "high" | "borderline" | "unknown" {
  if (value === null || value === undefined || !Number.isFinite(value)) return "unknown";
  if (low === null || high === null) return "unknown";
  const margin = (high - low) * 0.1;
  if (value < low - margin) return "low";
  if (value > high + margin) return "high";
  if (value < low || value > high) return "borderline";
  return "normal";
}

/** Pull a marker value off a LabPanel. For core markers this is the typed
 *  column; for extra markers it lives in `extra_markers[]`. Returns null if
 *  not present or not a finite number. */
export function markerValue(panel: LabPanel, key: string): number | null {
  if (key in panel && typeof (panel as unknown as Record<string, unknown>)[key] === "number") {
    const v = (panel as unknown as Record<string, unknown>)[key] as number;
    return Number.isFinite(v) ? v : null;
  }
  const extra = panel.extra_markers?.find((m) => m.key === key);
  if (extra && extra.value !== null && Number.isFinite(extra.value)) return extra.value;
  return null;
}

/** Reference range for a marker on a given panel — falls back to defaults. */
export function markerRange(
  panel: LabPanel,
  key: string,
): { low: number; high: number; unit: string } {
  const fromPanel = panel.reference_ranges?.[key];
  if (fromPanel && typeof fromPanel.low === "number" && typeof fromPanel.high === "number") {
    return { low: fromPanel.low, high: fromPanel.high, unit: fromPanel.unit ?? MARKER_BY_KEY[key]?.unit ?? "" };
  }
  return DEFAULT_RANGES[key] ?? { low: 0, high: 0, unit: "" };
}

/** All marker keys available on a panel: the six core ones + any extra. */
export function panelMarkerKeys(panel: LabPanel): string[] {
  const extras = (panel.extra_markers ?? []).map((m) => m.key);
  return [...CORE_MARKERS.map((m) => m.key), ...extras];
}

/** JSON-serialize the reference-ranges map for the Prisma TEXT column. */
export function serializeRanges(ranges: Record<string, { low: number | null; high: number | null; unit: string }>): string {
  return JSON.stringify(ranges);
}

/** Parse the reference-ranges column. Empty / malformed → {}. */
export function parseRanges(raw: string | null | undefined): Record<string, { low: number | null; high: number | null; unit: string }> {
  if (!raw) return {};
  try {
    const parsed = JSON.parse(raw);
    if (parsed && typeof parsed === "object") return parsed as Record<string, { low: number | null; high: number | null; unit: string }>;
  } catch { /* ignore */ }
  return {};
}

/** JSON-serialize the extra-markers list for the Prisma TEXT column. */
export function serializeExtra(markers: { key: string; label: string; value: number | null; unit: string; ref_low: number | null; ref_high: number | null }[]): string {
  return JSON.stringify(markers);
}

/** Parse the extra-markers column. Empty / malformed → []. */
export function parseExtra(raw: string | null | undefined): { key: string; label: string; value: number | null; unit: string; ref_low: number | null; ref_high: number | null }[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed as { key: string; label: string; value: number | null; unit: string; ref_low: number | null; ref_high: number | null }[];
  } catch { /* ignore */ }
  return [];
}

/** Days until the given date string (YYYY-MM-DD). Negative if past. */
export function daysUntil(dateStr: string | null | undefined): number | null {
  if (!dateStr) return null;
  const d = new Date(`${dateStr}T00:00:00Z`);
  if (isNaN(d.getTime())) return null;
  const diff = d.getTime() - Date.now();
  return Math.ceil(diff / (24 * 3600 * 1000));
}
