import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { activityDetail } from "@/lib/apex/activityRecord";

export async function GET(_req: NextRequest, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  if (!id || id.length > 200) return NextResponse.json({ ok: false, error: "Invalid activity ID" }, { status: 400 });
  try {
    const user = await db.user.findFirst({ where: { email: process.env.GARMIN_EMAIL || "" } });
    if (!user) return NextResponse.json({ ok: false, error: "Account not found" }, { status: 404 });
    const activity = await db.activity.findFirst({ where: { id, userId: user.id } });
    if (!activity) return NextResponse.json({ ok: false, error: "Activity not found" }, { status: 404 });
    return NextResponse.json({ ok: true, activity: activityDetail(activity) });
  } catch {
    return NextResponse.json({ ok: false, error: "Could not load activity" }, { status: 500 });
  }
}
