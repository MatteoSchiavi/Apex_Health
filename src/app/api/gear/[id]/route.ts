import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { computeUsagePct } from "@/lib/apex/gearHelpers";
import {
  parseDefaultFor,
  readDefaultForMany,
  serializeDefaultFor,
  setDefaultFor,
} from "@/lib/apex/gearDb";

/**
 * GET    /api/gear/[id]  — gear detail + service logs + last 10 linked
 *                          activities (linked-activity table doesn't exist
 *                          yet — returns [] for now).
 * PATCH  /api/gear/[id]  — partial update (name / type / intervals /
 *                          active / default_for).
 * DELETE /api/gear/[id]  — cascade delete gear + its service logs.
 *
 * The `defaultFor` column is read/written via raw SQL — see
 * src/lib/apex/gearDb.ts.
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

type GearRow = Awaited<ReturnType<typeof db.gear.findFirst>> extends infer T
  ? Exclude<T, null>
  : never;

function shape(g: GearRow, defaults: string[]) {
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
    default_for: defaults,
    created_at: g.createdAt.toISOString(),
    updated_at: g.updatedAt.toISOString(),
  };
}

function shapeLog(l: {
  id: number;
  gearId: number;
  serviceType: string;
  performedAt: string;
  notes: string | null;
  createdAt: Date;
}) {
  return {
    id: l.id,
    gear_id: l.gearId,
    service_type: l.serviceType,
    performed_at: l.performedAt,
    notes: l.notes,
    created_at: l.createdAt.toISOString(),
  };
}

async function withDefaults(g: GearRow): Promise<string[]> {
  const map = await readDefaultForMany([g.id]);
  return parseDefaultFor(map.get(g.id) ?? "[]");
}

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const gear = await db.gear.findFirst({ where: { id, userId: user.id } });
    if (!gear) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const logs = await db.gearServiceLog.findMany({
      where: { gearId: id },
      orderBy: { performedAt: "desc" },
    });

    // No activity_gear_links table exists yet — return an empty list for now.
    const linked_activities: unknown[] = [];

    const defaults = await withDefaults(gear);
    return NextResponse.json({
      ok: true,
      gear: shape(gear, defaults),
      service_logs: logs.map(shapeLog),
      linked_activities,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const existing = await db.gear.findFirst({ where: { id, userId: user.id } });
    if (!existing) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const body = await req.json().catch(() => ({}));
    const data: Record<string, unknown> = {};

    if (typeof body?.name === "string" && body.name.trim()) {
      data.name = body.name.trim();
    }
    if (typeof body?.gear_type === "string" && body.gear_type.trim()) {
      data.gearType = body.gear_type.trim();
    }
    if (typeof body?.active === "boolean") {
      data.active = body.active;
    }
    if (body?.service_interval_hours !== undefined) {
      const v = body.service_interval_hours;
      data.serviceIntervalHours =
        v === null || !Number.isFinite(Number(v)) || Number(v) <= 0
          ? null
          : Math.round(Number(v));
    }
    if (body?.service_interval_km !== undefined) {
      const v = body.service_interval_km;
      data.serviceIntervalKm =
        v === null || !Number.isFinite(Number(v)) || Number(v) <= 0
          ? null
          : Math.round(Number(v));
    }

    // defaultFor is set via raw SQL (the typed Prisma client doesn't know
    // about the column yet — see gearDb.ts).
    let nextDefaults: string[] | null = null;
    if (Array.isArray(body?.default_for)) {
      nextDefaults = (body.default_for as unknown[]).filter(
        (x): x is string => typeof x === "string",
      );
    }

    if (Object.keys(data).length > 0) {
      await db.gear.update({ where: { id }, data });
    }
    if (nextDefaults !== null) {
      await setDefaultFor(id, serializeDefaultFor(nextDefaults));
    }

    const updated = await db.gear.findFirst({ where: { id, userId: user.id } });
    if (!updated) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });
    const defaults = await withDefaults(updated);
    return NextResponse.json({ ok: true, gear: shape(updated, defaults) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const existing = await db.gear.findFirst({ where: { id, userId: user.id } });
    if (!existing) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    await db.gearServiceLog.deleteMany({ where: { gearId: id } });
    await db.gear.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
