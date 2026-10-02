import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { computeUsagePct } from "@/lib/apex/gearHelpers";
import { parseDefaultFor, readDefaultForMany } from "@/lib/apex/gearDb";

/**
 * POST /api/gear/[id]/service
 *   body: { service_type: string, performed_at?: ISO string, notes?: string }
 *
 * Creates a GearServiceLog row and resets the gear's hoursSinceService /
 * kmSinceService to 0. Sets lastServiceType + lastServiceAt. Returns the
 * updated gear (with default_for read via raw SQL) and the new log entry.
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

interface GearRow {
  id: number;
  userId: number;
  name: string;
  gearType: string;
  brand: string | null;
  active: boolean;
  serviceIntervalHours: number | null;
  serviceIntervalKm: number | null;
  hoursSinceService: number;
  kmSinceService: number;
  usagePct: number;
  lastServiceType: string | null;
  lastServiceAt: string | null;
  createdAt: Date;
  updatedAt: Date;
}

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

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const gear = await db.gear.findFirst({ where: { id, userId: user.id } });
    if (!gear) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const body = await req.json().catch(() => ({}));
    const serviceType = (body?.service_type ?? "").toString().trim();
    if (!serviceType) {
      return NextResponse.json(
        { ok: false, error: "service_type is required" },
        { status: 400 },
      );
    }
    const performedAt =
      typeof body?.performed_at === "string" && body.performed_at.trim()
        ? body.performed_at.trim()
        : new Date().toISOString();
    const notes =
      typeof body?.notes === "string" && body.notes.trim() ? body.notes.trim() : null;

    const log = await db.gearServiceLog.create({
      data: {
        gearId: id,
        serviceType,
        performedAt,
        notes,
      },
    });

    const updated = await db.gear.update({
      where: { id },
      data: {
        hoursSinceService: 0,
        kmSinceService: 0,
        usagePct: 0,
        lastServiceType: serviceType,
        lastServiceAt: performedAt,
      },
    });

    const map = await readDefaultForMany([id]);
    const defaults = parseDefaultFor(map.get(id) ?? "[]");
    return NextResponse.json(
      { ok: true, gear: shape(updated, defaults), log: shapeLog(log) },
      { status: 201 },
    );
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
