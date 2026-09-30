import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

/**
 * POST /api/asr
 *
 * Speech-to-text transcription for the Coach page voice input.
 * Accepts: { audio: "<base64-encoded audio data>" }
 * Returns: { ok: true, text: "<transcription>" }
 *
 * Uses z-ai-web-dev-sdk's audio.asr.create() — backend only, never client-side.
 */

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { audio } = body as { audio?: string };

    if (!audio || typeof audio !== "string") {
      return NextResponse.json(
        { ok: false, error: "Missing 'audio' (base64) field" },
        { status: 400 }
      );
    }

    // Strip the data URL prefix if present (e.g. "data:audio/webm;base64,...")
    const base64 = audio.includes(",") ? audio.split(",")[1] : audio;

    const zai = await ZAI.create();
    const response = await zai.audio.asr.create({
      file_base64: base64,
    });

    const text = (response as { text?: string }).text?.trim() ?? "";

    return NextResponse.json({ ok: true, text });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown ASR error";
    return NextResponse.json(
      { ok: false, error: message },
      { status: 500 }
    );
  }
}
