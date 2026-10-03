import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  computeUsagePct,
  bindingMetric,
} from "@/lib/apex/gearHelpers";
import {
  parseDefaultFor,
  readDefaultForMany,
  serializeDefaultFor,
  setDefaultFor,
} from "@/lib/apex/gearDb";

/**
 * GET /api/gear   — list the user's gear, sorted by usage_pct desc, active first.
 * POST /api/gear  — create a new gear item.
 *
 * Per plan §6. If the user has no gear, seeds three demo items so the Overview
 * "Gear due" card and this page have something to display. usage_pct is
 * recomputed on every read.
 *
 * The `defaultFor` column is read/written via raw SQL because the running dev
 * server's Prisma client was created before the column was added (server
 * restart is out of scope). See src/lib/apex/gearDb.ts.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function ensureUser() {
  const email = process.env.GARMIN_EMAIL || "";
  let user = await db.user.findFirst({ where: { email } });
  if (!user) {
    user = await db.user.create({
      data: {
        email,
        name: "Apex Athlete",
        password: process.env.GARMIN_PASSWORD || "",
        timezone: "Europe/Rome",
        locale: "en",
        theme: "dark",
        units: "metric",
        role: "owner",
        aiTier: "pro",
      },
    });
  }
  return user;
}

type GearRow = Awaited<ReturnType<typeof db.gear.create>>;

function shape(g: GearRow, defaultFor: string[]) {
  return {
    id: g.id,
    user_id: g.userId,
    name: g.name,
    gear_type: g.gearType,
    brand: g.brand,
    active: g.active,
    service_interval_hours: g.serviceIntervalHours,
    service_interval_km: g.serviceIntervalKm,
    hours_since_service: Math.round(g.hoursSinceService * 10) / 10,
    km_since_service: Math.round(g.kmSinceService * 10) / 10,
    usage_pct: computeUsagePct(
      g.hoursSinceService,
      g.kmSinceService,
      g.serviceIntervalHours,
      g.serviceIntervalKm,
    ),
    last_service_type: g.lastServiceType,
    last_service_at: g.lastServiceAt,
    default_for: defaultFor,
    created_at: g.createdAt.toISOString(),
    updated_at: g.updatedAt.toISOString(),
  };
}

/** Merge defaultFor (read via raw SQL) into each gear row before shaping. */
async function withDefaults(rows: GearRow[]): Promise<
  { row: GearRow; defaults: string[] }[]
> {
  const ids = rows.map((r) => r.id);
  const map = await readDefaultForMany(ids);
  return rows.map((row) => ({
    row,
    defaults: parseDefaultFor(map.get(row.id) ?? "[]"),
  }));
}

export async function GET() {
  try {
    const user = await ensureUser();

    const gear: GearRow[] = await db.gear.findMany({ where: { userId: user.id } });

    const enriched = await withDefaults(gear);
    const shaped = enriched
      .map(({ row, defaults }) => shape(row, defaults))
      .sort((a, b) => {
        if (a.active !== b.active) return a.active ? -1 : 1;
        return b.usage_pct - a.usage_pct;
      });

    return NextResponse.json({ ok: true, gear: shaped });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const user = await ensureUser();
    const body = await req.json().catch(() => ({}));
    const name = (body?.name ?? "").toString().trim();
    if (!name) {
      return NextResponse.json({ ok: false, error: "name is required" }, { status: 400 });
    }
    const gearType = (body?.gear_type ?? "other").toString().trim() || "other";
    const intervalHours =
      body?.service_interval_hours === null || body?.service_interval_hours === undefined
        ? null
        : Number(body.service_interval_hours);
    const intervalKm =
      body?.service_interval_km === null || body?.service_interval_km === undefined
        ? null
        : Number(body.service_interval_km);
    const defaultFor = Array.isArray(body?.default_for)
      ? (body.default_for as unknown[]).filter((x): x is string => typeof x === "string")
      : [];

    const created = await db.gear.create({
      data: {
        userId: user.id,
        name,
        gearType,
        active: true,
        serviceIntervalHours:
          intervalHours === null || !Number.isFinite(intervalHours) || intervalHours <= 0
            ? null
            : Math.round(intervalHours),
        serviceIntervalKm:
          intervalKm === null || !Number.isFinite(intervalKm) || intervalKm <= 0
            ? null
            : Math.round(intervalKm),
        hoursSinceService: 0,
        kmSinceService: 0,
        usagePct: 0,
      },
    });
    await setDefaultFor(created.id, serializeDefaultFor(defaultFor));

    const enriched = await withDefaults([created]);
    return NextResponse.json(
      { ok: true, gear: shape(enriched[0].row, enriched[0].defaults) },
      { status: 201 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
