import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Exercise history API (plan §2)
 *
 * GET /api/gym/exercises/[id]/history?limit=5
 *
 * Returns the last N set-logs for this exercise across ALL plans, newest first:
 *   [{ date, weightKg, reps, rpe, loggedAt }]
 *
 * Used by the live-session "Last time" line, and to pre-fill the weight stepper
 * with the previous session's load.
 */

export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const exerciseId = parseInt(idStr);
    if (!Number.isFinite(exerciseId)) {
      return NextResponse.json({ ok: false, error: "invalid exercise id" }, { status: 400 });
    }

    const { searchParams } = new URL(req.url);
    const limit = Math.min(parseInt(searchParams.get("limit") || "5"), 50);

    const logs = await db.gymSetLog.findMany({
      where: { exerciseId },
      orderBy: { loggedAt: "desc" },
      take: limit,
      include: { plan: { select: { date: true } } },
    });

    return NextResponse.json({
      ok: true,
      history: logs.map((l) => ({
        date: l.plan.date,
        weightKg: l.weightKg,
        reps: l.reps,
        rpe: l.rpe,
        setIndex: l.setIndex,
        loggedAt: l.loggedAt.toISOString(),
      })),
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
