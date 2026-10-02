import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Coach chat sessions API.
 *   GET  /api/coach/chats            — list sessions for the user
 *   POST /api/coach/chats            — create a new session
 *
 * Mirrors the plan §1 sessions rail. Session rows are slim (id, title,
 * startedAt, lastActivityAt, messageCount, preview) so the rail can render
 * hundreds of rows cheaply.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/** Ensure the GARMIN_EMAIL user exists; seed if missing. */
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
    const sessions = await db.chatSession.findMany({
      where: { userId: user.id },
      orderBy: { lastActivityAt: "desc" },
    });

    // Pull message counts + previews in one pass.
    const sessionIds = sessions.map((s) => s.id);
    const messages = await db.chatMessage.findMany({
      where: { sessionId: { in: sessionIds } },
      orderBy: { createdAt: "asc" },
      select: { id: true, sessionId: true, content: true, role: true },
    });

    const bySession = new Map<number, { count: number; preview: string }>();
    for (const m of messages) {
      const cur = bySession.get(m.sessionId) ?? { count: 0, preview: "" };
      cur.count += 1;
      // preview = first non-empty user message (or last assistant one)
      if (!cur.preview && m.role === "user" && m.content.trim()) {
        cur.preview = m.content.slice(0, 140);
      }
      bySession.set(m.sessionId, cur);
    }

    const out = sessions.map((s) => {
      const meta = bySession.get(s.id) ?? { count: 0, preview: "" };
      return {
        id: s.id,
        title: s.title,
        started_at: s.startedAt.toISOString(),
        last_activity_at: s.lastActivityAt.toISOString(),
        message_count: meta.count,
        preview: meta.preview,
      };
    });

    return NextResponse.json({ ok: true, sessions: out });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const user = await ensureUser();
    const body = await req.json().catch(() => ({}));
    const title = typeof body?.title === "string" && body.title.trim() ? body.title.trim() : null;

    const session = await db.chatSession.create({
      data: {
        userId: user.id,
        title: title ?? null,
        modelTier: "cheap",
      },
    });

    return NextResponse.json({
      ok: true,
      session: {
        id: session.id,
        title: session.title,
        started_at: session.startedAt.toISOString(),
        last_activity_at: session.lastActivityAt.toISOString(),
        message_count: 0,
        preview: "",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
