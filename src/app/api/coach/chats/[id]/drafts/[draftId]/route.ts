import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/** Legacy drafts can be discarded idempotently. Confirmation is unavailable
 * until the canonical agent can actually apply the payload; never report a
 * changed status as an applied plan or protocol. */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string; draftId: string }> }) {
  try {
    const user = await db.user.findFirst({ where: { email: process.env.GARMIN_EMAIL || "" } });
    if (!user) return NextResponse.json({ ok: false, error: "Account not found" }, { status: 404 });
    const { id: idStr, draftId } = await ctx.params;
    const sessionId = /^\d+$/.test(idStr) ? Number(idStr) : NaN;
    if (!Number.isSafeInteger(sessionId) || sessionId < 1) return NextResponse.json({ ok: false, error: "Bad session id" }, { status: 400 });

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
      const draft = arr.find((d) => d && typeof d === "object" && d.id === draftId);
      if (!draft) continue;
      if (action === "confirm") {
        return NextResponse.json({ ok: false, error: "Draft application is unavailable. No plan or protocol was applied." }, { status: 501 });
      }
      if (draft.status === "discarded") return NextResponse.json({ ok: true, drafts: arr });
      if (draft.status !== "pending") return NextResponse.json({ ok: false, error: "Draft is already finalized" }, { status: 409 });
      const next = arr.map((d) => d?.id === draftId ? { ...d, status: "discarded" } : d);
      // Compare-and-swap prevents one simultaneous draft update overwriting another.
      const result = await db.chatMessage.updateMany({
        where: { id: m.id, drafts: m.drafts }, data: { drafts: JSON.stringify(next) },
      });
      if (result.count !== 1) return NextResponse.json({ ok: false, error: "Draft changed. Reload and retry." }, { status: 409 });
      updated = next;
      break;
    }

    if (!updated) {
      return NextResponse.json({ ok: false, error: "Draft not found in this chat" }, { status: 404 });
    }

    return NextResponse.json({ ok: true, drafts: updated });
  } catch (err) {
    return NextResponse.json({ ok: false, error: "Could not update draft" }, { status: 500 });
  }
}
