import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Gym Plan set log API (plan §2 + Phase 0 fix #1)
 *
 * POST /api/gym/plan/[id]/log
 *   body: { exerciseId, exerciseName, setIndex, weightKg, reps, rpe? }
 *
 * Records what the athlete ACTUALLY lifted — weight + reps (NOT reps_min). The
 * previous implementation always sent `reps_done: ex.reps_min` and omitted
 * `weight_kg`, so progressive-overload tracking was impossible.
 */

export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const planId = parseInt(idStr);
    if (!Number.isFinite(planId)) {
      return NextResponse.json({ ok: false, error: "invalid plan id" }, { status: 400 });
    }

    const body = await req.json();
    const { exerciseId, exerciseName, setIndex, weightKg, reps, rpe } = body || {};

    if (
      typeof exerciseId !== "number" ||
      typeof exerciseName !== "string" ||
      typeof setIndex !== "number" ||
      typeof weightKg !== "number" ||
      typeof reps !== "number"
    ) {
      return NextResponse.json(
        { ok: false, error: "exerciseId, exerciseName, setIndex, weightKg, reps required" },
        { status: 400 }
      );
    }

    // Verify the plan exists
    const plan = await db.gymPlan.findUnique({ where: { id: planId } });
    if (!plan) return NextResponse.json({ ok: false, error: "plan not found" }, { status: 404 });

    const log = await db.gymSetLog.create({
      data: {
        planId,
        exerciseId,
        exerciseName,
        setIndex,
        weightKg,
        reps,
        rpe: typeof rpe === "number" ? rpe : null,
      },
    });

    return NextResponse.json({
      ok: true,
      log: {
        id: log.id,
        planId: log.planId,
        exerciseId: log.exerciseId,
        exerciseName: log.exerciseName,
        setIndex: log.setIndex,
        weightKg: log.weightKg,
        reps: log.reps,
        rpe: log.rpe,
        loggedAt: log.loggedAt.toISOString(),
      },
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
