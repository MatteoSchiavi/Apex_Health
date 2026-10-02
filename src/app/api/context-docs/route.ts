import { NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Context docs API (plan §1 column C + plan §8 settings AI memory).
 *   GET /api/context-docs   — all 6 docs for the user (seeded empty if missing)
 *
 * Kinds: profile, goals, injuries, equipment, preferences, season_plan.
 * Cap = 4000 chars per doc.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const KINDS = ["profile", "goals", "injuries", "equipment", "preferences", "season_plan"] as const;
const CHAR_CAP = 4000;

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

export async function GET() {
  try {
    const user = await ensureUser();
    const existing = await db.contextDoc.findMany({ where: { userId: user.id } });
    const have = new Set(existing.map((d) => d.kind));

    // Seed any missing kind so the UI can show "empty".
    const toCreate = KINDS.filter((k) => !have.has(k));
    if (toCreate.length) {
      await db.contextDoc.createMany({
        data: toCreate.map((kind) => ({ userId: user.id, kind, content: "" })),
      });
    }

    const all = await db.contextDoc.findMany({ where: { userId: user.id } });
    const docs = all
      .filter((d) => (KINDS as readonly string[]).includes(d.kind))
      .map((d) => ({
        kind: d.kind,
        content: d.content,
        updated_at: d.updatedAt.toISOString(),
        char_count: d.content.length,
        char_cap: CHAR_CAP,
      }));

    return NextResponse.json({ ok: true, docs });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
