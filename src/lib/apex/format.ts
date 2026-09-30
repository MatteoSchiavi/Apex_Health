/**
 * Apex Health — formatting helpers.
 * Numerical display is central to Apex; these formatters preserve tabular
 * alignment (tnum) and respect metric/imperial unit preferences.
 */

import type { Locale, Units } from "./types";

export function fmtNum(v: number | null | undefined, dp = 0): string {
  if (v === null || v === undefined || !Number.isFinite(v as number)) return "—";
  const f = Math.pow(10, dp);
  return (Math.round((v as number) * f) / f).toLocaleString(undefined, {
    minimumFractionDigits: dp,
    maximumFractionDigits: dp,
  });
}

export function fmtInt(v: number | null | undefined): string {
  if (v === null || v === undefined || !Number.isFinite(v as number)) return "—";
  return Math.round(v as number).toLocaleString();
}

/** Format a duration in seconds as "h:mm" or "mm:ss" depending on size. */
export function fmtDuration(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s as number)) return "—";
  const total = Math.round(s as number);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  if (h > 0) return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  return `${m}:${String(sec).padStart(2, "0")}`;
}

/** Format hours-only (e.g. sleep total) as "7h42" or "0h00". */
export function fmtHours(s: number | null | undefined): string {
  if (s === null || s === undefined || !Number.isFinite(s as number)) return "—";
  const total = s as number;
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  return `${h}h${String(m).padStart(2, "0")}`;
}

export function fmtHoursDecimal(h: number | null | undefined, dp = 2): string {
  if (h === null || h === undefined || !Number.isFinite(h as number)) return "—";
  return fmtNum(h, dp);
}

/** Distance in meters → km (or mi for imperial). */
export function fmtDistance(m: number | null | undefined, units: Units = "metric", dp = 1): string {
  if (m === null || m === undefined || !Number.isFinite(m as number)) return "—";
  if (units === "imperial") {
    const mi = (m as number) / 1609.344;
    return fmtNum(mi, dp);
  }
  return fmtNum((m as number) / 1000, dp);
}

export function distanceUnitLabel(units: Units = "metric"): string {
  return units === "imperial" ? "mi" : "km";
}

/** Speed in m/s → km/h (or mph). */
export function fmtSpeed(mps: number | null | undefined, units: Units = "metric", dp = 1): string {
  if (mps === null || mps === undefined || !Number.isFinite(mps as number)) return "—";
  if (units === "imperial") {
    const mph = (mps as number) * 2.2369362921;
    return fmtNum(mph, dp);
  }
  return fmtNum((mps as number) * 3.6, dp);
}

export function speedUnitLabel(units: Units = "metric"): string {
  return units === "imperial" ? "mph" : "km/h";
}

/** Weight in kg → kg (or lb). */
export function fmtWeight(kg: number | null | undefined, units: Units = "metric", dp = 1): string {
  if (kg === null || kg === undefined || !Number.isFinite(kg as number)) return "—";
  if (units === "imperial") {
    const lb = (kg as number) * 2.2046226218;
    return fmtNum(lb, dp);
  }
  return fmtNum(kg, dp);
}

export function weightUnitLabel(units: Units = "metric"): string {
  return units === "imperial" ? "lb" : "kg";
}

export function fmtElevation(m: number | null | undefined, units: Units = "metric"): string {
  if (m === null || m === undefined || !Number.isFinite(m as number)) return "—";
  if (units === "imperial") {
    const ft = (m as number) * 3.28084;
    return fmtNum(ft, 0);
  }
  return fmtNum(m, 0);
}

export function elevationUnitLabel(units: Units = "metric"): string {
  return units === "imperial" ? "ft" : "m";
}

/** Clock from ISO string, e.g. "06:32". */
export function fmtClock(iso: string | null | undefined, locale: Locale = "en"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString(locale === "it" ? "it-IT" : "en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

/** Date label like "12 May" or "12 mag". */
export function fmtDate(iso: string | null | undefined, locale: Locale = "en"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale === "it" ? "it-IT" : "en-GB", {
    day: "2-digit",
    month: "short",
  });
}

/** Full date label "Mon 12 May 2025". */
export function fmtDateLong(iso: string | null | undefined, locale: Locale = "en"): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale === "it" ? "it-IT" : "en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
}

export function fmtDateTime(iso: string | null | undefined, locale: Locale = "en"): string {
  if (!iso) return "—";
  return `${fmtDate(iso, locale)} · ${fmtClock(iso, locale)}`;
}

/** Relative time like "3h ago". */
export function timeAgo(iso: string | null | undefined, locale: Locale = "en"): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (isNaN(then)) return "—";
  const diff = Date.now() - then;
  const sec = Math.round(diff / 1000);
  if (sec < 60) return locale === "it" ? "ora" : "now";
  const min = Math.round(sec / 60);
  if (min < 60) return locale === "it" ? `${min} min fa` : `${min}m ago`;
  const hr = Math.round(min / 60);
  if (hr < 24) return locale === "it" ? `${hr} h fa` : `${hr}h ago`;
  const day = Math.round(hr / 24);
  return locale === "it" ? `${day} g fa` : `${day}d ago`;
}

/** Friendly discipline name. */
export function friendlyDiscipline(d: string | null, locale: Locale = "en"): string {
  if (!d) return locale === "it" ? "Altro" : "Other";
  const map: Record<string, [string, string]> = {
    cycling: ["Cycling", "Ciclismo"],
    running: ["Running", "Corsa"],
    swimming: ["Swimming", "Nuoto"],
    strength: ["Strength", "Forza"],
    rowing: ["Rowing", "Canottaggio"],
    hiking: ["Hiking", "Escursionismo"],
    walking: ["Walking", "Camminata"],
    rest: ["Rest", "Riposo"],
  };
  const entry = map[d];
  if (!entry) return d;
  return entry[locale === "it" ? 1 : 0];
}

/** Delta rendering with sign. */
export function fmtDelta(v: number | null | undefined, unit?: string, dp = 1): string {
  if (v === null || v === undefined || !Number.isFinite(v as number)) return "—";
  const abs = Math.abs(v as number);
  const sign = (v as number) >= 0 ? "+" : "−";
  const num = Number.isInteger(abs) ? abs : abs.toFixed(dp);
  if (unit === "%") return `${sign}${num}%`;
  return unit ? `${sign}${num} ${unit}` : `${sign}${num}`;
}
