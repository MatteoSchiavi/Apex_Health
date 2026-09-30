import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

/**
 * POST /api/tts
 *
 * Text-to-speech endpoint using z-ai-web-dev-sdk. Used by the Coach page to
 * read assistant messages aloud.
 *
 * Body: { text: string, voice?: string, speed?: number }
 * Returns: audio/wav binary
 *
 * Constraints:
 *  - Max 1024 chars per request (per the TTS API). We chunk longer text.
 *  - Speed 0.5–2.0 (default 1.0).
 *  - Voice: tongtong (default), chuichui, xiaochen, jam, kazi, douji, luodo.
 */

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const MAX_CHARS = 1024;

/** Split long text into chunks at sentence boundaries, each ≤ MAX_CHARS. */
function splitText(text: string): string[] {
  const trimmed = text.trim();
  if (trimmed.length <= MAX_CHARS) return [trimmed];
  const sentences = trimmed.match(/[^.!?]+[.!?]+/g) ?? [trimmed];
  const chunks: string[] = [];
  let cur = "";
  for (const s of sentences) {
    if ((cur + s).length <= MAX_CHARS) {
      cur += s;
    } else {
      if (cur) chunks.push(cur.trim());
      // If the sentence itself is too long, hard-split it
      if (s.length > MAX_CHARS) {
        for (let i = 0; i < s.length; i += MAX_CHARS) {
          chunks.push(s.slice(i, i + MAX_CHARS));
        }
        cur = "";
      } else {
        cur = s;
      }
    }
  }
  if (cur) chunks.push(cur.trim());
  return chunks;
}

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const text = (body?.text ?? "") as string;
    const voice = (body?.voice as string) ?? "tongtong";
    const speed = typeof body?.speed === "number" ? body.speed : 1.0;

    if (!text || !text.trim()) {
      return NextResponse.json(
        { ok: false, error: "Missing 'text' field" },
        { status: 400 }
      );
    }

    if (speed < 0.5 || speed > 2.0) {
      return NextResponse.json(
        { ok: false, error: "Speed must be between 0.5 and 2.0" },
        { status: 400 }
      );
    }

    const zai = await ZAI.create();
    const chunks = splitText(text);

    // For single chunk (common case), return the audio directly
    if (chunks.length === 1) {
      const response = await zai.audio.tts.create({
        input: chunks[0],
        voice,
        speed,
        response_format: "wav",
        stream: false,
      });
      const arrayBuffer = await response.arrayBuffer();
      const buffer = Buffer.from(new Uint8Array(arrayBuffer));
      return new NextResponse(buffer, {
        status: 200,
        headers: {
          "Content-Type": "audio/wav",
          "Content-Length": buffer.length.toString(),
          "Cache-Control": "no-cache",
        },
      });
    }

    // For multi-chunk, concatenate the wav buffers (naive concat — works for
    // playback since wav headers can be skipped after the first chunk)
    const buffers: Buffer[] = [];
    for (const chunk of chunks) {
      const response = await zai.audio.tts.create({
        input: chunk,
        voice,
        speed,
        response_format: "wav",
        stream: false,
      });
      const arrayBuffer = await response.arrayBuffer();
      buffers.push(Buffer.from(new Uint8Array(arrayBuffer)));
    }
    // Strip wav header (first 44 bytes) from all but the first buffer
    const merged = Buffer.concat([
      buffers[0],
      ...buffers.slice(1).map((b) => b.subarray(44)),
    ]);
    return new NextResponse(merged, {
      status: 200,
      headers: {
        "Content-Type": "audio/wav",
        "Content-Length": merged.length.toString(),
        "Cache-Control": "no-cache",
      },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown TTS error";
    return NextResponse.json(
      { ok: false, error: message },
      { status: 500 }
    );
  }
}
