import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * GET /api/gear/[id]/history
 *   Returns: { service_logs, monthly_usage, linked_activities }
 *
 * service_logs: full GearServiceLog list for this gear, newest first.
 * monthly_usage: [{ month: "YYYY-MM", hours: number, km: number }] — empty
 *   for now because there is no activity_gear_links table to aggregate from.
 *   (Plan §6 calls for it; the table needs to be added by a future pass —
 *   tracked in worklog.)
 * linked_activities: last 10 linked activities — empty for the same reason.
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
        name: "Matteo Schiavi",
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

    // No activity_gear_links table → monthly usage + linked activities are
    // empty for now. Plan §6 calls for both; tracked in worklog.
    const monthly_usage: { month: string; hours: number; km: number }[] = [];
    const linked_activities: unknown[] = [];

    return NextResponse.json({
      ok: true,
      service_logs: logs.map(shapeLog),
      monthly_usage,
      linked_activities,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
