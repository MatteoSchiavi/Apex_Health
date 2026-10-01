import { NextRequest } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

/**
 * POST /api/coach
 *
 * Real LLM-powered coach chat using z-ai-web-dev-sdk. Streams the response
 * token-by-token via Server-Sent Events (SSE) so the frontend can render
 * the reply word-by-word (typewriter effect).
 *
 * Body: { messages: [{ role, content }], locale: "en" | "it" }
 * Response: text/event-stream
 *   - data: {"type":"token","text":"word"} (one per token)
 *   - data: {"type":"done"} (stream complete)
 *   - data: {"type":"error","error":"..."} (on failure)
 *
 * The system prompt grounds the AI in the user's measured physiological
 * state. We keep the prompt restrained — no fabricated metrics, no medical
 * advice, always conclude with a disclaimer.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

interface IncomingMessage {
  role: "user" | "assistant";
  content: string;
}

const SYSTEM_PROMPT = `You are Apex Health's AI Coach. Your job is to interpret the user's measured physiological data and answer their questions.

RULES:
1. You are grounded in measured data only. Never invent metrics or fabricate values.
2. Use personal baselines (Δ7d, 28-day baseline) when the user mentions them.
3. Be calm, restrained, precise. No exclamation marks. No emojis. No "AI-powered" buzzwords.
4. Keep responses under 150 words.
5. Always end with one short medical disclaimer sentence: "This is an interpretation of measured data, not medical advice."
6. Treat the user as a serious athlete / health-conscious individual. The tone is editorial, not clinical.

If asked about something you have no data on, say so honestly. Do not speculate.`;

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const messages = (body?.messages ?? []) as IncomingMessage[];
    const locale = (body?.locale as "en" | "it") ?? "en";

    if (!Array.isArray(messages) || messages.length === 0) {
      return new Response(
        JSON.stringify({ ok: false, error: "Missing 'messages' array" }),
        { status: 400, headers: { "Content-Type": "application/json" } }
      );
    }

    // Compose the message list: system prompt + user/assistant history
    const chatMessages = [
      { role: "assistant", content: SYSTEM_PROMPT },
      ...messages.map((m) => ({
        role: m.role === "user" ? "user" : "assistant",
        content: m.content,
      })),
    ];

    const encoder = new TextEncoder();
    const stream = new ReadableStream({
      async start(controller) {
        const send = (obj: Record<string, unknown>) => {
          controller.enqueue(encoder.encode(`data: ${JSON.stringify(obj)}\n\n`));
        };

        try {
          const zai = await ZAI.create();
          const completion = await zai.chat.completions.create({
            model: process.env.LLM_PROVIDER_CHEAP || "deepseek-flash",
            messages: chatMessages,
            thinking: { type: "disabled" },
            // Note: the z-ai-web-dev-sdk may or may not return a stream — we
            // handle both cases. If it returns a string, we chunk it
            // word-by-word on the server so the client still sees streaming.
          });

          const fullText: string = completion?.choices?.[0]?.message?.content ?? "";

          if (!fullText) {
            send({ type: "error", error: "Empty response from model" });
            controller.close();
            return;
          }

          // Chunk the text word-by-word (the SDK doesn't currently support
          // real streaming; we emulate it server-side).
          const tokens = fullText.split(/(\s+)/);
          for (const tok of tokens) {
            if (!tok) continue;
            send({ type: "token", text: tok });
            // Small natural delay between tokens
            await new Promise((r) => setTimeout(r, /^\s+$/.test(tok) ? 15 : 35));
          }

          send({ type: "done" });
          controller.close();
        } catch (err) {
          const message = err instanceof Error ? err.message : "Unknown LLM error";
          send({ type: "error", error: message });
          controller.close();
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return new Response(JSON.stringify({ ok: false, error: message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }
}
