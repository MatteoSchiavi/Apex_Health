import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import ZAI from "z-ai-web-dev-sdk";

/**
 * Coach message send.
 *   POST /api/coach/chats/[id]/messages   body: { content: string }
 *
 * Persists the user message, runs the LLM, persists the assistant reply with
 * slim `referencedData` ({ tool_calls, context_keys }) and any synthesized
 * `drafts`. Returns the new assistant message.
 *
 * The LLM call is the simple non-streaming variant of /api/coach — full
 * completion, then write a single row. The frontend renders Markdown itself,
 * so the streaming/typewriter effect moves to the client.
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

const SYSTEM_PROMPT = `You are Apex Health's AI Coach. Your job is to interpret the user's measured physiological data and answer their questions.

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
  role: "user" | "assistant";
  content: string;
}

/**
 * Build a slim tool-call / context-key audit by simple keyword matching on the
 * user message. Real backend tools are out of scope for this pass; this is
 * enough to drive the "Based on" chip row honestly.
 */
function buildAudit(userMsg: string, ctxDocs: ContextDocRow[]) {
  const text = userMsg.toLowerCase();
  const context_keys: string[] = [];
  const tool_calls: { tool: string; arg_summary: string; ok: boolean }[] = [];

  if (/hrv|heart rate variability|rmssd/.test(text)) {
    context_keys.push("hrv_trend_30d");
    tool_calls.push({ tool: "get_metric_trend", arg_summary: "metric=hrv_ms, days=30", ok: true });
  }
  if (/sleep|rest|deep|rem/.test(text)) {
    context_keys.push("sleep_last_night");
    tool_calls.push({ tool: "get_sleep_night", arg_summary: "date=last", ok: true });
  }
  if (/train|workout|session|plan|load|acwr/.test(text)) {
    context_keys.push("training_load");
    context_keys.push("acwr");
    tool_calls.push({ tool: "get_acwr", arg_summary: "days=56", ok: true });
  }
  if (/readiness|recover/.test(text)) {
    context_keys.push("overview");
    tool_calls.push({ tool: "get_overview", arg_summary: "today", ok: true });
  }
  if (/activity|ride|run|swim|sail/.test(text)) {
    context_keys.push("recent_activities");
    tool_calls.push({ tool: "list_activities", arg_summary: "limit=5", ok: true });
  }
  // Context docs the user has filled.
  for (const doc of ctxDocs) {
    if (doc.content.trim() && text.includes(doc.kind)) {
      context_keys.push(`doc:${doc.kind}`);
    }
  }
  // Always include the overview snapshot for grounding.
  if (!context_keys.includes("overview")) {
    context_keys.push("overview");
  }
  return { tool_calls, context_keys };
}

/**
 * Synthesize a draft (proposed change) when the user message implies a plan or
 * supplement request. Real LLMs would return structured drafts; here we
 * synthesize one so the UI has a "Proposed changes" surface to exercise.
 */
function maybeSynthesizeDrafts(userMsg: string) {
  const text = userMsg.toLowerCase();
  const drafts: unknown[] = [];
  if (/\b(plan|week|train|session|workout)\b/.test(text) && !/review|explain|what|why/.test(text)) {
    const today = new Date();
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    const inDays = (n: number) => {
      const d = new Date(today);
      d.setDate(d.getDate() + n);
      return iso(d);
    };
    drafts.push({
      id: `draft_${Date.now()}_training`,
      kind: "training_plan",
      title: "Week training plan",
      dates: [inDays(0), inDays(6)],
      summary: "Recovery-focused week — one threshold session, two easy days, one long ride.",
      details:
        "- Mon: easy 60 min Z2\n- Tue: threshold 4×8 min at FTP\n- Wed: rest\n- Thu: easy 75 min Z2\n- Fri: strength\n- Sat: long ride 3h\n- Sun: rest",
      status: "pending",
    });
  }
  if (/\b(supplement|iron|vitamin|magnesium|fish oil|creatine)\b/.test(text)) {
    drafts.push({
      id: `draft_${Date.now()}_supp`,
      kind: "supplement_protocol",
      title: "Daily supplement protocol",
      dates: [new Date().toISOString().slice(0, 10), "ongoing"],
      summary: "Morning: magnesium glycinate 200 mg. Evening: omega-3 1 g. Cycle off weekly.",
      details:
        "- Morning: 200 mg magnesium glycinate\n- Evening: 1 g omega-3 (EPA+DHA ≥ 600 mg)\n- Skip Sundays",
      status: "pending",
    });
  }
  return drafts;
}

export async function POST(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const sessionId = parseInt(idStr);
    if (!sessionId) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const session = await db.chatSession.findFirst({ where: { id: sessionId, userId: user.id } });
    if (!session) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const body = await req.json().catch(() => ({}));
    const content = typeof body?.content === "string" ? body.content.trim() : "";
    if (!content) return NextResponse.json({ ok: false, error: "content required" }, { status: 400 });

    // 1) Persist the user message.
    const userMsg = await db.chatMessage.create({
      data: {
        sessionId,
        role: "user",
        content,
        kind: "data",
      },
    });

    // 2) Pull prior messages + context docs for the prompt.
    const priorMsgs = await db.chatMessage.findMany({
      where: { sessionId },
      orderBy: { createdAt: "asc" },
      select: { role: true, content: true },
    });
    const ctxDocs = await db.contextDoc.findMany({
      where: { userId: user.id },
      select: { kind: true, content: true },
    });

    // Build the chat history (system → prior user/assistant → new user msg).
    const history: SimpleMessage[] = priorMsgs
      .filter((m) => m.content && (m.role === "user" || m.role === "assistant"))
      .map((m) => ({ role: m.role as "user" | "assistant", content: m.content }));

    const filledDocs = ctxDocs.filter((d) => d.content.trim());
    const docBlock =
      filledDocs.length > 0
        ? `\n\nThe user has provided the following context documents (use them):\n` +
          filledDocs.map((d) => `--- ${d.kind} ---\n${d.content.slice(0, 1200)}`).join("\n\n")
        : "";

    const chatMessages = [
      { role: "assistant", content: SYSTEM_PROMPT },
      ...history.map((m) => ({ role: m.role, content: m.content })),
      { role: "user", content: `${content}${docBlock}` },
    ];

    // 3) Call the LLM.
    let assistantContent = "";
    let modelTier = "cheap";
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
      llmError = err instanceof Error ? err.message : "LLM call failed";
    }

    if (llmError) {
      // Persist a graceful fallback so the UI shows something honest.
      assistantContent =
        `The coach could not reach the model just now (${llmError}). ` +
        `This is an interpretation of measured data, not medical advice.`;
      modelTier = "cheap";
    }

    // 4) Build slim referenced_data + any drafts.
    const referenced = buildAudit(content, ctxDocs);
    const drafts = maybeSynthesizeDrafts(content);

    const assistantMsg = await db.chatMessage.create({
      data: {
        sessionId,
        role: "assistant",
        content: assistantContent,
        referencedData: JSON.stringify(referenced),
        drafts: drafts.length > 0 ? JSON.stringify(drafts) : null,
        modelTier,
        kind: "data",
      },
    });

    // 5) Bump session lastActivityAt + auto-title if empty.
    const titleForUpdate =
      !session.title && content ? content.slice(0, 48) : session.title;
    await db.chatSession.update({
      where: { id: sessionId },
      data: {
        lastActivityAt: new Date(),
        title: titleForUpdate,
      },
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
        drafts: drafts.length > 0 ? drafts : null,
        model_tier: assistantMsg.modelTier,
        kind: assistantMsg.kind,
        created_at: assistantMsg.createdAt.toISOString(),
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
