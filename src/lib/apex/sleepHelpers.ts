/**
 * Apex Health — Sleep math helpers (shared by list + night pages + the
 * /api/sleep/summary route).
 *
 * Plan §4 introduces two derived metrics that don't exist as columns:
 *  - **Regularity**: circular standard deviation of bedtime + wake time
 *    in minutes. Bedtime can cross midnight (23:30 vs 01:00 are close in
 *    sleep-land but 1410 vs 60 minutes-of-day are far apart on a linear
 *    scale), so we compute the SD on the 24-hour circle.
 *  - **Sleep debt**: cumulative shortfall vs target over the last 7 nights.
 *
 * The plan also fixes the long-standing unit bug in the stage bar:
 * denominator = time asleep (deep + light + REM, AWAKE EXCLUDED), and the
 * % labels read "of time asleep". Helpers below compute the bar fractions
 * and the "of sleep" percentages from a SleepSession.
 */

export interface SleepSessionLike {
  local_date: string;
  start_time: string;
  end_time: string;
  total_sleep_s: number | null;
  deep_s: number | null;
  light_s: number | null;
  rem_s: number | null;
  awake_s: number | null;
  sleep_score: number | null;
}

/** Minutes-of-day from an ISO timestamp using UTC components (so the same
 *  calculation gives the same answer on the server and the client, regardless
 *  of system timezone). The stored start_time/end_time are already in UTC
 *  ("…Z"), so this matches what fmtClock renders on the server. */
export function minutesOfDayUTC(iso: string): number {
  const d = new Date(iso);
  if (isNaN(d.getTime())) return NaN;
  return d.getUTCHours() * 60 + d.getUTCMinutes();
}

/** Format minutes-of-day (0–1440, may exceed 1440 for wake after midnight
 *  when paired with bedtime that wraps) as "HH:MM". */
export function fmtMinutes(min: number): string {
  if (!Number.isFinite(min)) return "—";
  const m = ((Math.round(min) % 1440) + 1440) % 1440;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  return `${String(h).padStart(2, "0")}:${String(mm).padStart(2, "0")}`;
}

/** Circular mean of minutes-of-day. Returns minutes-of-day in [0, 1440).
 *  Uses the standard trick: convert to angles on the 24h circle, average
 *  the unit vectors, atan2 back. Robust to bedtimes that cross midnight. */
export function circularMean(minutes: number[]): number | null {
  const valid = minutes.filter((m) => Number.isFinite(m));
  if (valid.length === 0) return null;
  let x = 0, y = 0;
  for (const m of valid) {
    const a = (m / 1440) * 2 * Math.PI;
    x += Math.cos(a);
    y += Math.sin(a);
  }
  x /= valid.length;
  y /= valid.length;
  const r = Math.hypot(x, y);
  if (r < 1e-9) return null; // uniformly distributed — no meaningful mean
  const ang = Math.atan2(y, x);
  const min = ((ang / (2 * Math.PI)) * 1440 + 1440) % 1440;
  return min;
}

/** Circular standard deviation in minutes. Uses the mean resultant length R:
 *  SD = sqrt(-2 · ln(R)) · (1440 / 2π). Returns minutes (0–~1030 for a
 *  maximally-spread distribution). null when input is empty or uniform. */
export function circularSD(minutes: number[]): number | null {
  const valid = minutes.filter((m) => Number.isFinite(m));
  if (valid.length < 2) return null;
  let x = 0, y = 0;
  for (const m of valid) {
    const a = (m / 1440) * 2 * Math.PI;
    x += Math.cos(a);
    y += Math.sin(a);
  }
  x /= valid.length;
  y /= valid.length;
  const r = Math.hypot(x, y);
  if (r >= 1) return 0; // all the same time → zero spread
  if (r < 1e-9) return null;
  const sdRad = Math.sqrt(-2 * Math.log(r));
  return sdRad * (1440 / (2 * Math.PI));
}

/** Linear median (no circular wrap) — used for "median bedtime / wake"
 *  display. Plan §4 calls for median; for sleep schedules this is fine
 *  because wake rarely crosses midnight and the linear median of bedtimes
 *  that cross midnight is still a reasonable single representative. */
export function median(values: number[]): number | null {
  const valid = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (valid.length === 0) return null;
  const mid = Math.floor(valid.length / 2);
  return valid.length % 2 ? valid[mid] : (valid[mid - 1] + valid[mid]) / 2;
}

/** Standard deviation (linear, sample, n-1). */
export function stdev(values: number[]): number | null {
  const valid = values.filter((v) => Number.isFinite(v));
  if (valid.length < 2) return null;
  const mean = valid.reduce((s, v) => s + v, 0) / valid.length;
  const variance = valid.reduce((s, v) => s + (v - mean) ** 2, 0) / (valid.length - 1);
  return Math.sqrt(variance);
}

/** Mean (linear). null when input is empty. */
export function mean(values: number[]): number | null {
  const valid = values.filter((v) => Number.isFinite(v));
  if (valid.length === 0) return null;
  return valid.reduce((s, v) => s + v, 0) / valid.length;
}

/** Quantile (0–1) by linear interpolation. null when empty. */
export function quantile(values: number[], q: number): number | null {
  const valid = values.filter((v) => Number.isFinite(v)).sort((a, b) => a - b);
  if (valid.length === 0) return null;
  if (valid.length === 1) return valid[0];
  const pos = (valid.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  if (lo === hi) return valid[lo];
  return valid[lo] + (valid[hi] - valid[lo]) * (pos - lo);
}

/** "Time asleep" — the single denominator the plan §4 mandates for every
 *  stage percentage. = deep + light + REM (awake EXCLUDED). */
export function timeAsleepS(s: {
  deep_s: number | null;
  light_s: number | null;
  rem_s: number | null;
}): number {
  return (s.deep_s ?? 0) + (s.light_s ?? 0) + (s.rem_s ?? 0);
}

/** Sleep window in seconds = end − start (the same value the old code
 *  called "time in bed" — the plan §4 notes this is derived, not measured,
 *  and renames it "sleep window"). */
export function sleepWindowS(s: { start_time: string; end_time: string }): number {
  const ms = new Date(s.end_time).getTime() - new Date(s.start_time).getTime();
  return ms > 0 ? ms / 1000 : 0;
}

/** Sleep efficiency (%) = time asleep / sleep window × 100. The plan §4
 *  efficiency tooltip reads "Asleep ÷ sleep window". */
export function sleepEfficiencyPct(s: SleepSessionLike): number {
  const win = sleepWindowS(s);
  if (!win) return 0;
  const asleep = s.total_sleep_s ?? timeAsleepS(s);
  return (asleep / win) * 100;
}

/** Default sleep target (plan §4): 8h unless me.sleepTargetH is exposed
 *  later. Centralised so the list and the night page agree. */
export const DEFAULT_SLEEP_TARGET_S = 8 * 3600;

/** Stage CSS variables (deep / rem / light / awake) — the same palette the
 *  legacy SleepPage used. Defining it once here keeps the list and night
 *  pages in sync and avoids re-declaring the map. */
export const STAGE_VARS = {
  deep: "var(--c-stage-deep)",
  rem: "var(--c-stage-rem)",
  light: "var(--c-stage-core)",
  awake: "var(--c-stage-awake)",
} as const;

export type StageKey = "deep" | "rem" | "light" | "awake";

/** Stage row definition in the order the composition bar renders them.
 *  The bar uses ONLY the three asleep stages (deep / light / REM), in that
 *  order so deep is leftmost and REM is rightmost — matches the canonical
 *  hypnogram visual without inventing a timeline. */
export const ASLEEP_STAGES: StageKey[] = ["deep", "light", "rem"];

/** All four stages for the table view (deep, light, REM, awake). */
export const ALL_STAGES: StageKey[] = ["deep", "light", "rem", "awake"];

/** Typical-range reference values (plan §4 "typical range" column).
 *  These are adult-population norms in % of time asleep — they are
 *  constants, NOT user baselines (the user's 30-day average is a separate
 *  column). Sourced from the AASM / widely-cited adult stage proportions:
 *  deep ~13-23%, light ~45-65%, REM ~20-25%. Awake is shown as 0-15% of
 *  total sleep window but for "% of time asleep" it's 0. */
export const TYPICAL_STAGE_RANGE: Record<StageKey, { low: number; high: number }> = {
  deep: { low: 13, high: 23 },
  light: { low: 45, high: 65 },
  rem: { low: 20, high: 25 },
  awake: { low: 0, high: 0 },
};

/** Stage label keys (en). The i18n catalogue has sleep.deep / light / rem /
 *  awake — these keys match the existing t("sleep.*") translations. */
export const STAGE_LABEL_KEY: Record<StageKey, "deep" | "light" | "rem" | "awake"> = {
  deep: "deep",
  light: "light",
  rem: "rem",
  awake: "awake",
};
