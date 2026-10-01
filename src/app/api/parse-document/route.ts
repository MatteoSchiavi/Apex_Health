import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { readFile } from "fs/promises";
import path from "path";
import ZAI from "z-ai-web-dev-sdk";

/**
 * POST /api/parse-document
 *
 * Reads an uploaded document, sends it to the VLM/LLM for extraction, and
 * returns structured JSON that can be used to update system values.
 *
 * Body: { documentId: number }
 *
 * Supported:
 *   - Images (jpg, png) → VLM (vision) extraction
 *   - Text/CSV          → LLM text extraction
 *   - PDF               → pdf-parse for text, then LLM extraction
 *
 * Extraction categories (document_type):
 *   lab_results, medical_report, training_plan, dietary_plan,
 *   prescription, biometric_report, other
 *
 * For training plans / dietary plans, the extracted structure differs:
 *   training_plan → { document_type, date, sessions: [{day, discipline, duration_min, intensity, notes}] }
 *   dietary_plan  → { document_type, date, daily_targets: {calories, protein_g, carbs_g, fat_g, water_ml}, meals: [...] }
 */

const UPLOAD_DIR = path.join(process.cwd(), "uploads");

const EXTRACTION_PROMPT = `You are a health & performance data extraction assistant. Read the document and extract structured data. Return ONLY valid JSON (no markdown fences, no explanation).

Detect the document type and use the matching schema:

1. Lab results / blood work:
{"document_type":"lab_results","date":"YYYY-MM-DD or null","markers":[{"name":"","value":null,"unit":"","ref_low":null,"ref_high":null,"status":"normal|low|high|unknown"}],"notes":""}

2. Medical report:
{"document_type":"medical_report","date":"YYYY-MM-DD or null","findings":[{"category":"","detail":"","severity":"normal|warning|alert"}],"recommendations":[],"notes":""}

3. Training plan:
{"document_type":"training_plan","date_range":{"start":"YYYY-MM-DD","end":"YYYY-MM-DD"},"sessions":[{"day":"YYYY-MM-DD","discipline":"cycling|running|swimming|strength|sailing|boating|hiking|walking|rest","duration_min":null,"intensity":"easy|moderate|hard|threshold|recovery","title":"","notes":""}],"notes":""}

4. Dietary plan:
{"document_type":"dietary_plan","date":"YYYY-MM-DD or null","daily_targets":{"calories":null,"protein_g":null,"carbs_g":null,"fat_g":null,"water_ml":null},"meals":[{"name":"breakfast|lunch|dinner|snack","foods":[],"calories":null}],"notes":""}

5. Prescription:
{"document_type":"prescription","date":"YYYY-MM-DD or null","medications":[{"name":"","dosage":"","frequency":"","duration":""}],"notes":""}

6. Biometric report:
{"document_type":"biometric_report","date":"YYYY-MM-DD or null","markers":[{"name":"","value":null,"unit":"","ref_low":null,"ref_high":null,"status":"normal|low|high|unknown"}],"notes":""}

Rules:
- Pick the schema that best matches the document.
- Use null for missing values; never invent numbers.
- Dates must be YYYY-MM-DD strings.
- Return ONLY the JSON object.`;

export async function POST(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const { documentId } = await req.json();
    if (!documentId) return NextResponse.json({ ok: false, error: "documentId required" }, { status: 400 });

    const doc = await db.uploadedDocument.findFirst({ where: { id: documentId, userId: user.id } });
    if (!doc) return NextResponse.json({ ok: false, error: "Document not found" }, { status: 404 });

    // Update status to "parsing"
    await db.uploadedDocument.update({ where: { id: documentId }, data: { status: "parsing" } });

    const filePath = path.join(UPLOAD_DIR, doc.filePath);
    let extractedData: Record<string, unknown> = {};

    const zai = await ZAI.create();

    if (["jpg", "jpeg", "png"].includes(doc.fileType)) {
      // Image: use VLM to extract data
      const imageBuffer = await readFile(filePath);
      const base64Image = `data:image/${doc.fileType};base64,${imageBuffer.toString("base64")}`;

      const response = await zai.chat.completions.createVision({
        messages: [
          { role: "assistant", content: EXTRACTION_PROMPT },
          {
            role: "user",
            content: [
              { type: "text", text: "Extract all structured data from this document image." },
              { type: "image_url", image_url: { url: base64Image } },
            ],
          },
        ],
        thinking: { type: "disabled" },
      });

      const rawContent = response.choices[0]?.message?.content ?? "";
      extractedData = safeParseJson(rawContent);
    } else if (doc.fileType === "txt" || doc.fileType === "csv") {
      // Text/CSV: use LLM to parse
      const textContent = await readFile(filePath, "utf-8");

      const response = await zai.chat.completions.create({
        messages: [
          { role: "assistant", content: EXTRACTION_PROMPT },
          { role: "user", content: textContent.slice(0, 8000) },
        ],
        thinking: { type: "disabled" },
      });

      const rawContent = response.choices[0]?.message?.content ?? "";
      extractedData = safeParseJson(rawContent);
    } else if (doc.fileType === "pdf") {
      // PDF: extract text with pdf-parse v2, then LLM.
      // Falls back to a raw content-stream scan for simple digital PDFs.
      const pdfBuffer = await readFile(filePath);
      let pdfText = "";

      // Attempt 1: pdf-parse library (handles most digital PDFs)
      try {
        const u8 = new Uint8Array(pdfBuffer);
        const { PDFParse } = await import("pdf-parse");
        const parser = new PDFParse(u8);
        const result = (await parser.getText()) as {
          text?: string;
          pages?: { text?: string }[];
        };
        pdfText = result?.text || "";
        if (!pdfText && result?.pages?.length) {
          pdfText = result.pages.map((p) => p.text || "").join("\n");
        }
      } catch {
        /* fall through to raw extraction */
      }

      // Attempt 2: raw content-stream scan (BT...ET text blocks in Tj/TJ operators)
      if (!pdfText.trim()) {
        try {
          const raw = pdfBuffer.toString("latin1");
          const textChunks: string[] = [];
          // Match (...) Tj and [(...) ...] TJ operators inside BT...ET blocks
          const tjMatches = raw.matchAll(/\(([^()\\]*)\)\s*Tj/g);
          for (const m of tjMatches) textChunks.push(m[1]);
          const tjArrayMatches = raw.matchAll(/\[([^\]]*)\]\s*TJ/g);
          for (const m of tjArrayMatches) {
            const inner = m[1].matchAll(/\(([^()\\]*)\)/g);
            for (const im of inner) textChunks.push(im[1]);
          }
          pdfText = textChunks.join("\n").trim();
        } catch {
          /* give up */
        }
      }

      if (!pdfText.trim()) {
        extractedData = {
          document_type: "other",
          error: "No extractable text in PDF (it may be a scanned image — upload as an image instead).",
        };
      } else {
        const response = await zai.chat.completions.create({
          messages: [
            { role: "assistant", content: EXTRACTION_PROMPT },
            { role: "user", content: pdfText.slice(0, 8000) },
          ],
          thinking: { type: "disabled" },
        });

        const rawContent = response.choices[0]?.message?.content ?? "";
        extractedData = safeParseJson(rawContent);
      }
    } else {
      extractedData = {
        document_type: "other",
        error: `Unsupported file type for parsing: ${doc.fileType}`,
      };
    }

    // Store the parsed data
    await db.uploadedDocument.update({
      where: { id: documentId },
      data: { status: "parsed", parsedData: JSON.stringify(extractedData) },
    });

    return NextResponse.json({ ok: true, parsedData: extractedData });
  } catch (err) {
    // Update status to "error" if we can still read the body
    try {
      const body = await req.clone().json();
      if (body?.documentId) {
        await db.uploadedDocument
          .update({ where: { id: body.documentId }, data: { status: "error" } })
          .catch(() => {});
      }
    } catch {
      /* ignore */
    }
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 },
    );
  }
}

/** Parse LLM output, stripping any markdown fences. */
function safeParseJson(raw: string): Record<string, unknown> {
  const cleaned = raw
    .replace(/^```json\s*/i, "")
    .replace(/^```\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
  try {
    return JSON.parse(cleaned);
  } catch {
    return { document_type: "other", raw_extraction: cleaned };
  }
}
