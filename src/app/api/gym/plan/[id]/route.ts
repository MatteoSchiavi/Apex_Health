import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Gym Plan detail API (plan §2)
 *
 * GET    /api/gym/plan/[id]   → plan incl. exercises (parsed) + set logs
 * PATCH  /api/gym/plan/[id]   → body { status?, adjustmentNote? } (confirm a draft)
 * DELETE /api/gym/plan/[id]   → remove the plan (and its set logs by cascade is
 *                               NOT configured in Prisma — explicit delete first)
 */

export async function GET(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const id = parseInt(idStr);
    if (!Number.isFinite(id)) {
      return NextResponse.json({ ok: false, error: "invalid id" }, { status: 400 });
    }

    const plan = await db.gymPlan.findUnique({
      where: { id },
      include: { setLogs: { orderBy: { setIndex: "asc" } } },
    });
    if (!plan) return NextResponse.json({ ok: false, error: "not found" }, { status: 404 });

    return NextResponse.json({
      ok: true,
      plan: {
        id: plan.id,
        date: plan.date,
        title: plan.title,
        status: plan.status,
        adjustmentNote: plan.adjustmentNote,
        exercises: JSON.parse(plan.exercises),
        setLogs: plan.setLogs.map((l) => ({
          id: l.id,
          exerciseId: l.exerciseId,
          exerciseName: l.exerciseName,
          setIndex: l.setIndex,
          weightKg: l.weightKg,
          reps: l.reps,
          rpe: l.rpe,
          loggedAt: l.loggedAt.toISOString(),
        })),
        createdAt: plan.createdAt.toISOString(),
        updatedAt: plan.updatedAt.toISOString(),
      },
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const id = parseInt(idStr);
    if (!Number.isFinite(id)) {
      return NextResponse.json({ ok: false, error: "invalid id" }, { status: 400 });
    }

    const body = await req.json();
    const { status, adjustmentNote } = body || {};

    const data: { status?: string; adjustmentNote?: string | null } = {};
    if (typeof status === "string") data.status = status;
    if (typeof adjustmentNote === "string") data.adjustmentNote = adjustmentNote;
    if (adjustmentNote === null) data.adjustmentNote = null;

    if (Object.keys(data).length === 0) {
      return NextResponse.json({ ok: false, error: "nothing to update" }, { status: 400 });
    }

    const updated = await db.gymPlan.update({
      where: { id },
      data,
    });

    return NextResponse.json({
      ok: true,
      plan: {
        id: updated.id,
        date: updated.date,
        title: updated.title,
        status: updated.status,
        adjustmentNote: updated.adjustmentNote,
        createdAt: updated.createdAt.toISOString(),
        updatedAt: updated.updatedAt.toISOString(),
      },
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const id = parseInt(idStr);
    if (!Number.isFinite(id)) {
      return NextResponse.json({ ok: false, error: "invalid id" }, { status: 400 });
    }

    // Prisma GymSetLog has no onDelete cascade, so wipe logs first
    await db.gymSetLog.deleteMany({ where: { planId: id } });
    await db.gymPlan.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
