import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Draft confirm / discard.
 *   POST /api/coach/chats/[id]/drafts/[draftId]   body: { action: "confirm" | "discard" }
 *
 * Updates the draft's `status` field inside the assistant message's `drafts`
 * JSON array. Returns the updated drafts list.
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

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string; draftId: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr, draftId } = await ctx.params;
    const sessionId = parseInt(idStr);
    if (!sessionId) return NextResponse.json({ ok: false, error: "Bad session id" }, { status: 400 });

    const session = await db.chatSession.findFirst({ where: { id: sessionId, userId: user.id } });
    if (!session) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const body = await req.json().catch(() => ({}));
    const action = body?.action;
    if (action !== "confirm" && action !== "discard") {
      return NextResponse.json({ ok: false, error: "action must be confirm|discard" }, { status: 400 });
    }

    // Find the latest assistant message that carries a draft with this id.
    const msgs = await db.chatMessage.findMany({
      where: { sessionId, role: "assistant" },
      orderBy: { createdAt: "desc" },
    });

    let updated: unknown[] | null = null;
    for (const m of msgs) {
      if (!m.drafts) continue;
      let arr: unknown;
      try {
        arr = JSON.parse(m.drafts);
      } catch {
        continue;
      }
      if (!Array.isArray(arr)) continue;
      let touched = false;
      arr = arr.map((d) => {
        if (d && typeof d === "object" && "id" in d && (d as { id: string }).id === draftId) {
          touched = true;
          return { ...(d as Record<string, unknown>), status: action === "confirm" ? "confirmed" : "discarded" };
        }
        return d;
      });
      if (touched) {
        await db.chatMessage.update({
          where: { id: m.id },
          data: { drafts: JSON.stringify(arr) },
        });
        updated = arr as unknown[];
        break;
      }
    }

    if (!updated) {
      return NextResponse.json({ ok: false, error: "Draft not found in this chat" }, { status: 404 });
    }

    return NextResponse.json({ ok: true, drafts: updated });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
