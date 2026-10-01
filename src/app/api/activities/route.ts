/**
 * GET /api/activities
 *
 * Returns activities from the Prisma database, filtered by date range + discipline
 * + source, with pagination (offset/limit) and a server-side summary block that
 * compares the current window to the previous equal-length window (for DeltaChip).
 *
 * Query params (additive — old callers still work):
 *   days=90              (default 90)
 *   discipline=cycling    repeatable: ?discipline=cycling&discipline=running
 *   source=Garmin         repeatable, matched against the comma-separated sources column
 *   offset=0              default 0
 *   limit=60              default 60, clamped 1..100
 *
 * Response shape (back-compat: keeps `count`; ADDS `total` + `summary`):
 *   { ok, activities: ActivityCard[], count, total, summary: SummaryBlock }
 *
 *   summary = {
 *     sessions, total_time_s, total_distance_m, total_load,            // current window
 *     prev_sessions, prev_total_time_s, prev_total_distance_m, prev_total_load  // previous window
 *   }
 *
 * Notes:
 * - `total` is the count of all activities in the filtered range (used by the
 *   page's "X of Y" counter and "Load more" logic). `count` is kept for any
 *   legacy caller; both equal `activities.length` only when offset=0.
 * - `id` is converted from Prisma's String @id to Number (the JS mock layer uses
 *   numbers; this keeps the frontend store + ActivityDetailPage contract stable).
 * - `startTime` is normalised to ISO "YYYY-MM-DDTHH:MM:SS" so the client's
 *   `new Date(iso)` parses it deterministically across engines.
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

function toISOTime(raw: string): string {
  // SQLite stores as "YYYY-MM-DD HH:MM:SS"; rewrite to ISO for client Date parsing.
  return raw.includes(" ") ? raw.replace(" ", "T") : raw;
}

function toSummaryNum(v: number | null | undefined): number {
  if (v === null || v === undefined || !Number.isFinite(v)) return 0;
  return v;
}

interface SummaryBlock {
  sessions: number;
  total_time_s: number;
  total_distance_m: number;
  total_load: number;
  prev_sessions: number;
  prev_total_time_s: number;
  prev_total_distance_m: number;
  prev_total_load: number;
}

function buildWhere(
  userId: number,
  dateGte: string,
  dateLt: string | null,
  disciplines: string[],
  sources: string[]
) {
  const where: any = { userId, localDate: { gte: dateGte } };
  if (dateLt) where.localDate.lt = dateLt;
  if (disciplines.length) where.discipline = { in: disciplines };
  // sources is stored as a comma-separated string; substring match per source.
  if (sources.length) where.OR = sources.map((s) => ({ sources: { contains: s } }));
  return where;
}

function summarize(rows: { durationS: number; distanceM: number | null; trainingLoad: number | null }[]) {
  let total_time_s = 0;
  let total_distance_m = 0;
  let total_load = 0;
  for (const r of rows) {
    total_time_s += r.durationS || 0;
    total_distance_m += toSummaryNum(r.distanceM);
    total_load += toSummaryNum(r.trainingLoad);
  }
  return { sessions: rows.length, total_time_s, total_distance_m, total_load };
}

export async function GET(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) {
      return NextResponse.json(
        { ok: false, error: "No user. Run POST /api/garmin/sync first." },
        { status: 404 }
      );
    }

    const { searchParams } = new URL(req.url);
    const days = Math.max(1, parseInt(searchParams.get("days") || "90"));
    const disciplines = searchParams.getAll("discipline").filter(Boolean);
    const sources = searchParams.getAll("source").filter(Boolean);
    const offset = Math.max(0, parseInt(searchParams.get("offset") || "0"));
    const limitRaw = parseInt(searchParams.get("limit") || "60");
    const limit = Math.max(1, Math.min(100, limitRaw));

    // Current range window: today - days (inclusive, by localDate string compare).
    const now = new Date();
    const cutoff = new Date(now);
    cutoff.setDate(cutoff.getDate() - days);
    const cutoffStr = cutoff.toISOString().slice(0, 10);

    // Previous equal-length window: starts another `days` earlier. Used for the delta.
    const prevCutoff = new Date(cutoff);
    prevCutoff.setDate(prevCutoff.getDate() - days);
    const prevCutoffStr = prevCutoff.toISOString().slice(0, 10);

    // Pull everything in the current window (for summary + total + paginated slice).
    const whereCurrent = buildWhere(user.id, cutoffStr, null, disciplines, sources);
    const all = await db.activity.findMany({
      where: whereCurrent,
      orderBy: { startTime: "desc" },
    });

    const total = all.length;
    const page = all.slice(offset, offset + limit);

    // Pull everything in the previous window for the delta comparison.
    // Previous window: [prevCutoff, cutoff) — equal length, ending where current begins.
    const wherePrev = buildWhere(user.id, prevCutoffStr, cutoffStr, disciplines, sources);
    const prevAll = await db.activity.findMany({
      where: wherePrev,
      orderBy: { startTime: "desc" },
    });

    const summary: SummaryBlock = {
      ...summarize(all),
      prev_sessions: prevAll.length,
      prev_total_time_s: prevAll.reduce((s, a) => s + (a.durationS || 0), 0),
      prev_total_distance_m: prevAll.reduce((s, a) => s + toSummaryNum(a.distanceM), 0),
      prev_total_load: prevAll.reduce((s, a) => s + toSummaryNum(a.trainingLoad), 0),
    };

    return NextResponse.json({
      ok: true,
      activities: page.map((a) => ({
        id: Number(a.id),
        start_time: toISOTime(a.startTime),
        local_date: a.localDate,
        discipline: a.discipline,
        title: a.title,
        duration_s: a.durationS,
        distance_m: a.distanceM,
        elevation_gain_m: a.elevationGainM,
        avg_hr: a.avgHr,
        max_hr: a.maxHr,
        avg_power: a.avgPower,
        np_power: a.npPower,
        avg_speed_mps: a.avgSpeedMps,
        calories: a.calories,
        training_load: a.trainingLoad,
        data_completeness: a.dataCompleteness,
        sources: a.sources.split(",").map((s) => s.trim()).filter(Boolean),
      })),
      count: page.length, // legacy alias of activities.length
      total, // total in filtered range (for "X of Y" + Load more)
      offset,
      limit,
      summary,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
