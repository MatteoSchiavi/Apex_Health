import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import ZAI from "z-ai-web-dev-sdk";

/** Conversation-only coach. Only completed replies are persisted; actual health
 * queries and action drafts belong to the backend agent and are not simulated here. */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const SYSTEM_PROMPT = `You are Apex Health's AI Coach. Answer the user's questions using only information supplied in this conversation. No health readings, trends, overview, or tool results have been loaded. State this limitation when asked to assess their measured health or readiness. Do not imply access to their dashboard or suggest a specific supplement regimen. You cannot create or apply plans or protocols.

RULES:
1. You are grounded in measured data only. Never invent metrics or fabricate values.
2. Use personal baselines (Δ7d, 28-day baseline) when the user mentions them.
3. Be calm, restrained, precise. No exclamation marks. No emojis. No "AI-powered" buzzwords.
4. Keep responses under 180 words.
5. Always end with one short medical disclaimer sentence: "This is an interpretation of measured data, not medical advice."
6. Treat the user as a serious athlete / health-conscious individual. The tone is editorial, not clinical.
7. Use **bold**, lists (- ), and short tables sparingly to make multi-part answers scannable.

If asked about something you have no data on, say so honestly. Do not speculate.`;

interface ContextDocRow {
  kind: string;
  content: string;
}

interface SimpleMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await db.user.findFirst({ where: { email: process.env.GARMIN_EMAIL || "" } });
    if (!user) return NextResponse.json({ ok: false, error: "Account not found" }, { status: 404 });
    const { id: idStr } = await ctx.params;
    const sessionId = /^\d+$/.test(idStr) ? Number(idStr) : NaN;
    if (!Number.isSafeInteger(sessionId) || sessionId < 1) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const session = await db.chatSession.findFirst({ where: { id: sessionId, userId: user.id } });
    if (!session) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const body = await req.json().catch(() => ({}));
    const content = typeof body?.content === "string" ? body.content.trim() : "";
    if (!content || content.length > 4000) return NextResponse.json({ ok: false, error: "content must contain 1–4000 characters" }, { status: 400 });

    const priorMsgs = await db.chatMessage.findMany({
      where: { sessionId },
      orderBy: [{ createdAt: "desc" }, { id: "desc" }],
      take: 30,
      select: { role: true, content: true },
    });
    const ctxDocs = await db.contextDoc.findMany({
      where: { userId: user.id },
      select: { kind: true, content: true },
    });

    // The pending message is not yet persisted, so it appears exactly once.
    const history: SimpleMessage[] = priorMsgs.reverse()
      .filter((m) => m.content && (m.role === "user" || m.role === "assistant"))
      .map((m) => ({ role: m.role as "user" | "assistant", content: m.content.slice(0, 4000) }));

    const filledDocs = ctxDocs.filter((d) => d.content.trim()).slice(0, 10);
    const docBlock =
      filledDocs.length > 0
        ? `\n\nThe user has provided the following context documents (use them):\n` +
          filledDocs.map((d) => `--- ${d.kind} ---\n${d.content.slice(0, 1200)}`).join("\n\n")
        : "";

    const chatMessages = [
      { role: "system", content: SYSTEM_PROMPT },
      ...history.map((m) => ({ role: m.role, content: m.content })),
      { role: "user", content: `${content}${docBlock}` },
    ];

    // Call the provider before committing either side of the conversation.
    let assistantContent = "";
    const modelTier = "cheap";
    let llmError: string | null = null;
    try {
      const zai = await ZAI.create();
      const completion = await zai.chat.completions.create({
        model: process.env.LLM_PROVIDER_CHEAP || "deepseek-flash",
        messages: chatMessages as SimpleMessage[],
        thinking: { type: "disabled" },
      });
      assistantContent = completion?.choices?.[0]?.message?.content ?? "";
      if (!assistantContent) {
        llmError = "Empty model response";
      }
    } catch (err) {
      llmError = "The coach is unavailable. Please retry.";
    }

    if (llmError) return NextResponse.json({ ok: false, error: llmError }, { status: 502 });

    // Only supplied context documents are cited. No measured-data tool was executed.
    const referenced = { tool_calls: [], context_keys: filledDocs.map((d) => `doc:${d.kind}`) };
    const [userMsg, assistantMsg] = await db.$transaction(async (tx) => {
      const userMsg = await tx.chatMessage.create({ data: { sessionId, role: "user", content, kind: "data" } });
      const assistantMsg = await tx.chatMessage.create({ data: {
        sessionId, role: "assistant", content: assistantContent,
        referencedData: JSON.stringify(referenced), drafts: null, modelTier, kind: "data",
      } });
      await tx.chatSession.update({ where: { id: sessionId }, data: {
        lastActivityAt: new Date(), title: session.title || content.slice(0, 48),
      } });
      return [userMsg, assistantMsg];
    });

    return NextResponse.json({
      ok: true,
      user_message: {
        id: userMsg.id,
        role: "user",
        content: userMsg.content,
        created_at: userMsg.createdAt.toISOString(),
      },
      assistant_message: {
        id: assistantMsg.id,
        role: "assistant",
        content: assistantMsg.content,
        referenced_data: referenced,
        drafts: null,
        model_tier: assistantMsg.modelTier,
        kind: assistantMsg.kind,
        created_at: assistantMsg.createdAt.toISOString(),
      },
    });
  } catch (err) {
    return NextResponse.json({ ok: false, error: "Could not send message" }, { status: 500 });
  }
}
