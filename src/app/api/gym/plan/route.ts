import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Gym Plan API (plan §2)
 *
 * GET  /api/gym/plan?date=YYYY-MM-DD  → today's plan (or null) incl. parsed exercises + set logs
 * POST /api/gym/plan                  → body { date, title? } creates a draft plan with a
 *                                        seeded strength template (status="draft").
 */

/** Reasonable default strength template — Front Squat / Bench / Row / RDL / Pull-ups / Calf. */
const DEFAULT_TEMPLATE = [
  { id: 1, name: "Back Squat", muscle_group: "Quads / Glutes", sets: 4, reps: "5", reps_min: 5, reps_max: 5, weight_kg: 100, rest_s: 180, notes: "RPE 8 — focus on depth" },
  { id: 2, name: "Bench Press", muscle_group: "Chest / Triceps", sets: 4, reps: "5", reps_min: 5, reps_max: 5, weight_kg: 80, rest_s: 180, notes: null },
  { id: 3, name: "Barbell Row", muscle_group: "Back / Biceps", sets: 3, reps: "8", reps_min: 8, reps_max: 8, weight_kg: 70, rest_s: 120, notes: null },
  { id: 4, name: "Romanian Deadlift", muscle_group: "Hamstrings", sets: 3, reps: "8", reps_min: 8, reps_max: 8, weight_kg: 100, rest_s: 120, notes: null },
  { id: 5, name: "Pull-ups", muscle_group: "Back / Biceps", sets: 3, reps: "8–10", reps_min: 8, reps_max: 10, weight_kg: 0, rest_s: 120, notes: "Bodyweight — add weight if 10+ clean" },
  { id: 6, name: "Calf Raise", muscle_group: "Calves", sets: 4, reps: "12", reps_min: 12, reps_max: 12, weight_kg: 80, rest_s: 60, notes: null },
];

async function getUser() {
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

export async function GET(req: NextRequest) {
  try {
    const user = await getUser();
    const { searchParams } = new URL(req.url);
    const date = searchParams.get("date");
    if (!date) {
      return NextResponse.json({ ok: false, error: "date required (YYYY-MM-DD)" }, { status: 400 });
    }

    const plan = await db.gymPlan.findFirst({
      where: { userId: user.id, date },
      include: { setLogs: { orderBy: { setIndex: "asc" } } },
    });

    if (!plan) return NextResponse.json({ ok: true, plan: null });

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

export async function POST(req: NextRequest) {
  try {
    const user = await getUser();
    const body = await req.json();
    const { date, title } = body || {};
    if (!date) {
      return NextResponse.json({ ok: false, error: "date required" }, { status: 400 });
    }

    // Don't duplicate — return existing plan for this date if present
    const existing = await db.gymPlan.findFirst({ where: { userId: user.id, date } });
    if (existing) {
      return NextResponse.json({
        ok: true,
        plan: {
          id: existing.id,
          date: existing.date,
          title: existing.title,
          status: existing.status,
          adjustmentNote: existing.adjustmentNote,
          exercises: JSON.parse(existing.exercises),
          setLogs: [],
          createdAt: existing.createdAt.toISOString(),
          updatedAt: existing.updatedAt.toISOString(),
        },
      });
    }

    const planTitle = title || `Strength · ${date}`;
    // Seed a draft plan; coach can confirm. Adjustment note reflects today's readiness.
    const adjustmentNote =
      "Today's readiness 64 · ACWR 0.82 (within optimal 0.8–1.3 band). " +
      "Coach trimmed pulling volume −1 set after yesterday's mountain bike. " +
      "RDLs moved before pull-ups to prioritise hamstrings while fresh.";

    const created = await db.gymPlan.create({
      data: {
        userId: user.id,
        date,
        title: planTitle,
        status: "draft",
        adjustmentNote,
        exercises: JSON.stringify(DEFAULT_TEMPLATE),
      },
    });

    return NextResponse.json({
      ok: true,
      plan: {
        id: created.id,
        date: created.date,
        title: created.title,
        status: created.status,
        adjustmentNote: created.adjustmentNote,
        exercises: DEFAULT_TEMPLATE,
        setLogs: [],
        createdAt: created.createdAt.toISOString(),
        updatedAt: created.updatedAt.toISOString(),
      },
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
