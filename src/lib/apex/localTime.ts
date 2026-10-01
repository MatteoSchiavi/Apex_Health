/**
 * Local-today helpers (plan finding 3 — UTC "today" bug).
 *
 * The plan day and the event form must use the user's *local* today, not UTC.
 * For Italy (Europe/Rome, UTC+1/+2), 00:00–02:00 UTC = previous calendar day;
 * using `new Date().toISOString().slice(0,10)` therefore returns yesterday during
 * late evening Italian time.
 *
 * `Intl.DateTimeFormat('en-CA', { timeZone })` returns the locale date in the
 * `YYYY-MM-DD` format (Canadian English uses ISO-style dates) — exactly what
 * we want, evaluated in the user's timezone.
 *
 * For SSR safety (running on the server where the timezone is the server's),
 * the consumer passes the user's IANA timezone explicitly via `me.timezone`.
 */

import { me } from "./data";

/** Return today's date in `YYYY-MM-DD` form, evaluated in the given IANA timezone. */
export function localToday(timezone: string = me.timezone): string {
  try {
    const fmt = new Intl.DateTimeFormat("en-CA", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    });
    // en-CA outputs `YYYY-MM-DD`
    return fmt.format(new Date());
  } catch {
    // invalid tz fallback to system local
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return d.toISOString().slice(0, 10);
  }
}

/** Add `days` calendar days to a `YYYY-MM-DD` string, returning a `YYYY-MM-DD`. */
export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** Difference in calendar days between two `YYYY-MM-DD` strings (b - a). */
export function dayDiff(a: string, b: string): number {
  const da = new Date(`${a}T00:00:00Z`).getTime();
  const db = new Date(`${b}T00:00:00Z`).getTime();
  return Math.round((db - da) / 86400000);
}

/** ISO weekday number for a `YYYY-MM-DD` string (1 = Mon … 7 = Sun). */
export function isoWeekday(iso: string): number {
  const d = new Date(`${iso}T00:00:00Z`).getUTCDay(); // 0 = Sun … 6 = Sat
  return d === 0 ? 7 : d;
}
