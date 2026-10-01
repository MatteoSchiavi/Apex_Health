import { NextRequest, NextResponse } from "next/server";

/**
 * Gym Feedback API (plan §2 + Phase 0 fix #2)
 *
 * GET  /api/gym/feedback
 *   → seeded demo entries (no Feedback model in the schema).
 *
 * POST /api/gym/feedback
 *   body: { rpe?, soreness?, injuryFlag?, bodyArea?, notes? }
 *   → returns 200 ok and stores NOTHING persistently.
 *
 * HONEST NOTE (plan finding): the Prisma schema has no Feedback table. The plan
 * suggested adding a JSON column or seeding it on the user; neither exists yet,
 * and adding a model + migration is outside this task's scope (schema changes
 * are owned by the main agent). The UI therefore persists feedback locally in
 * `localStorage` (per-user, via `src/lib/apex/storage.ts`) and uses this
 * endpoint only for the seeded history line + an honest 200 acknowledgement.
 * The form DOES send the full structured payload (`rpe`, `soreness`,
 * `injuryFlag`, `bodyArea`, `notes`) — not just `notes` — so once a Feedback
 * table exists this route can wire up to it with no UI change.
 */

const SEED_HISTORY = [
  {
    id: 1,
    date: "2026-09-29",
    rpe: 8,
    soreness: 2,
    injuryFlag: false,
    bodyArea: null,
    notes: "Strong session. Quads tight from yesterday's MTB.",
  },
  {
    id: 2,
    date: "2026-09-26",
    rpe: 7,
    soreness: 3,
    injuryFlag: false,
    bodyArea: null,
    notes: "Heavy deadlifts — left hamstring a bit grumpy.",
  },
  {
    id: 3,
    date: "2026-09-22",
    rpe: 6,
    soreness: 1,
    injuryFlag: false,
    bodyArea: null,
    notes: "Easy day, mobility + technique focus.",
  },
];

export async function GET() {
  return NextResponse.json({ ok: true, feedback: SEED_HISTORY });
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { rpe, soreness, injuryFlag, bodyArea, notes } = body || {};

    // Validate the structured payload (Phase 0 fix #2: form sends rpe + soreness + injuryFlag + bodyArea + notes).
    if (rpe != null && (typeof rpe !== "number" || rpe < 1 || rpe > 10)) {
      return NextResponse.json({ ok: false, error: "rpe must be 1–10" }, { status: 400 });
    }
    if (soreness != null && (typeof soreness !== "number" || soreness < 1 || soreness > 5)) {
      return NextResponse.json({ ok: false, error: "soreness must be 1–5" }, { status: 400 });
    }

    // Honest acknowledgement: stored client-side only. See file header.
    return NextResponse.json({
      ok: true,
      persisted: false,
      reason: "No Feedback model in schema — stored locally in localStorage. See route.ts header.",
      received: { rpe, soreness, injuryFlag, bodyArea, notes },
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
