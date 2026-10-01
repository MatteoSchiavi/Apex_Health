import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Coach session detail / delete.
 *   GET    /api/coach/chats/[id]   — session + messages (referencedData + drafts parsed)
 *   DELETE /api/coach/chats/[id]   — delete session + all its messages
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

function safeParse(raw: string | null): unknown {
  if (!raw) return null;
  try {
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const session = await db.chatSession.findFirst({ where: { id, userId: user.id } });
    if (!session) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const msgs = await db.chatMessage.findMany({
      where: { sessionId: id },
      orderBy: { createdAt: "asc" },
    });

    const messages = msgs.map((m) => ({
      id: m.id,
      role: m.role,
      content: m.content,
      referenced_data: safeParse(m.referencedData) as Record<string, unknown> | null,
      drafts: safeParse(m.drafts) as unknown[] | null,
      model_tier: m.modelTier,
      kind: m.kind,
      created_at: m.createdAt.toISOString(),
    }));

    return NextResponse.json({
      ok: true,
      session: {
        id: session.id,
        title: session.title,
        started_at: session.startedAt.toISOString(),
        last_activity_at: session.lastActivityAt.toISOString(),
        message_count: messages.length,
        preview: messages.find((m) => m.role === "user" && m.content)?.content?.slice(0, 140) ?? "",
      },
      messages,
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    // Make sure session belongs to user before cascade.
    const session = await db.chatSession.findFirst({ where: { id, userId: user.id } });
    if (!session) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    await db.chatMessage.deleteMany({ where: { sessionId: id } });
    await db.chatSession.delete({ where: { id } });

    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
