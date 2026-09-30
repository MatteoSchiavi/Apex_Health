import { NextRequest, NextResponse } from "next/server";
import ZAI from "z-ai-web-dev-sdk";

/**
 * POST /api/recovery-scan
 *
 * Generates a daily recovery scan from the user's overview data using the
 * z-ai-web-dev-sdk LLM. The frontend sends the overview payload; the backend
 * constructs the prompt and returns a structured summary.
 *
 * The AI is grounded in measured data only — no fabrication. Returns:
 *   - one_sentence_summary
 *   - highlights[] (positive findings)
 *   - watch_items[] (warning-level items to monitor)
 *   - recommendation (a single, restrained actionable insight)
 *   - disclaimer (always present — medical-safe framing)
 */

interface OverviewPayload {
  date: string;
  readiness: { value: number | null; delta_7d: number | null };
  recovery: { value: number | null; delta_7d: number | null };
  strain: { value: number | null; delta_7d: number | null };
  sleep_score: { value: number | null; delta_7d: number | null };
  sleep_hours: number | null;
  hrv_ms: number | null;
  hrv_baseline_ms: number | null;
  resting_hr: number | null;
  resting_hr_delta_7d: number | null;
  spo2_avg: number | null;
  respiration_avg: number | null;
  steps: number | null;
  weight_kg: number | null;
  vo2max: number | null;
  acute_load: number | null;
  chronic_load: number | null;
  acwr: number | null;
  training_load_7d: number | null;
  alerts: { type: string; severity: string; message: string }[];
}

export async function POST(req: NextRequest) {
  try {
    const body = (await req.json()) as OverviewPayload;

    // Compose a concise data summary the LLM can interpret honestly
    const dataDigest = `
DATE: ${body.date}
READINESS: ${body.readiness.value ?? "—"} /100 (Δ7d ${body.readiness.delta_7d ?? "—"})
RECOVERY: ${body.recovery.value ?? "—"} /100 (Δ7d ${body.recovery.delta_7d ?? "—"})
STRAIN: ${body.strain.value ?? "—"} /100 (Δ7d ${body.strain.delta_7d ?? "—"})
SLEEP SCORE: ${body.sleep_score.value ?? "—"} /100 (Δ7d ${body.sleep_score.delta_7d ?? "—"})
SLEEP HOURS: ${body.sleep_hours ?? "—"}
HRV: ${body.hrv_ms ?? "—"} ms (baseline ${body.hrv_baseline_ms ?? "—"} ms)
RESTING HR: ${body.resting_hr ?? "—"} bpm (Δ7d ${body.resting_hr_delta_7d ?? "—"})
SpO2 AVG: ${body.spo2_avg ?? "—"} %
RESPIRATION: ${body.respiration_avg ?? "—"} brpm
STEPS: ${body.steps ?? "—"}
WEIGHT: ${body.weight_kg ?? "—"} kg
VO2MAX: ${body.vo2max ?? "—"} ml/kg/min
ACUTE LOAD (7d): ${body.acute_load ?? "—"} TSS
CHRONIC LOAD (28d): ${body.chronic_load ?? "—"} TSS
ACWR: ${body.acwr ?? "—"} ratio (optimal 0.80–1.30)
TRAINING LOAD 7d: ${body.training_load_7d ?? "—"} TSS
ALERTS:
${body.alerts.map((a) => `- [${a.severity}] ${a.type}: ${a.message}`).join("\n")}
`.trim();

    const systemPrompt = `You are Apex Health's recovery analyst. Your job is to interpret the user's measured physiological data and produce a calm, honest, daily recovery scan.

RULES:
1. You are grounded in the provided data ONLY. Do not invent metrics. Do not reference data not provided.
2. Use personal baselines (Δ7d, 28-day baseline) when available — context over judgement.
3. Be calm, restrained, and precise. No exclamation marks. No "AI-powered" buzzwords. No emojis.
4. Your output MUST be valid JSON with this exact shape:
{
  "one_sentence_summary": "A single calm sentence (max 30 words) answering 'how am I doing right now?'",
  "highlights": ["2-3 short factual observations of positive findings, each max 15 words"],
  "watch_items": ["0-2 short factual items worth monitoring, each max 15 words. Empty array if nothing."],
  "recommendation": "A single restrained, actionable recommendation (max 30 words). Always grounded in the data.",
  "disclaimer": "This is an interpretation of measured data, not medical advice. Consult a clinician for any medical concern."
}
5. Return ONLY the JSON. No markdown fences, no preamble.
6. If a value is missing (—), do not interpret it. Mention only what's actually present.`;

    const zai = await ZAI.create();
    const completion = await zai.chat.completions.create({
      messages: [
        { role: "assistant", content: systemPrompt },
        { role: "user", content: dataDigest },
      ],
      thinking: { type: "disabled" },
    });

    const raw = completion.choices[0]?.message?.content ?? "";

    // Parse JSON (LLM may include code fences despite instructions — strip them)
    let parsed: Record<string, unknown>;
    const cleaned = raw
      .replace(/^```json\s*/i, "")
      .replace(/^```\s*/i, "")
      .replace(/\s*```$/i, "")
      .trim();
    try {
      parsed = JSON.parse(cleaned);
    } catch {
      // Fallback: return raw text wrapped as the summary
      parsed = {
        one_sentence_summary: cleaned.slice(0, 300),
        highlights: [],
        watch_items: [],
        recommendation: "",
        disclaimer:
          "This is an interpretation of measured data, not medical advice. Consult a clinician for any medical concern.",
      };
    }

    return NextResponse.json({ ok: true, scan: parsed, raw });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json(
      { ok: false, error: message },
      { status: 500 }
    );
  }
}
