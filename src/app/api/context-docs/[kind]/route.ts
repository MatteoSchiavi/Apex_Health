import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Context docs API — single doc.
 *   GET /api/context-docs/[kind]
 *   PUT /api/context-docs/[kind]   body: { content: string }
 *
 * Kinds: profile, goals, injuries, equipment, preferences, season_plan.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const KINDS = new Set(["profile", "goals", "injuries", "equipment", "preferences", "season_plan"]);
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

function shape(d: { kind: string; content: string; updatedAt: Date }) {
  return {
    kind: d.kind,
    content: d.content,
    updated_at: d.updatedAt.toISOString(),
    char_count: d.content.length,
    char_cap: CHAR_CAP,
  };
}

export async function GET(_req: NextRequest, ctx: { params: Promise<{ kind: string }> }) {
  try {
    const user = await ensureUser();
    const { kind } = await ctx.params;
    if (!KINDS.has(kind)) return NextResponse.json({ ok: false, error: "Bad kind" }, { status: 400 });

    let doc = await db.contextDoc.findFirst({ where: { userId: user.id, kind } });
    if (!doc) {
      doc = await db.contextDoc.create({ data: { userId: user.id, kind, content: "" } });
    }
    return NextResponse.json({ ok: true, doc: shape(doc) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

export async function PUT(req: NextRequest, ctx: { params: Promise<{ kind: string }> }) {
  try {
    const user = await ensureUser();
    const { kind } = await ctx.params;
    if (!KINDS.has(kind)) return NextResponse.json({ ok: false, error: "Bad kind" }, { status: 400 });

    const body = await req.json().catch(() => ({}));
    const content = typeof body?.content === "string" ? body.content : null;
    if (content === null) {
      return NextResponse.json({ ok: false, error: "content required" }, { status: 400 });
    }
    const trimmed = content.slice(0, CHAR_CAP);

    // Upsert by (userId, kind) — unique constraint.
    const existing = await db.contextDoc.findFirst({ where: { userId: user.id, kind } });
    let doc;
    if (existing) {
      doc = await db.contextDoc.update({ where: { id: existing.id }, data: { content: trimmed } });
    } else {
      doc = await db.contextDoc.create({ data: { userId: user.id, kind, content: trimmed } });
    }
    return NextResponse.json({ ok: true, doc: shape(doc) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
