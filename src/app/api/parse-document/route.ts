import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { readFile } from "fs/promises";
import path from "path";
import ZAI from "z-ai-web-dev-sdk";

/**
 * POST /api/parse-document
 *
 * Reads an uploaded document, sends it to the VLM (Vision Language Model) for
 * extraction, and returns structured JSON that can be used to update system
 * values (lab markers, biometrics, etc.).
 *
 * Body: { documentId: number }
 *
 * Workflow:
 * 1. User uploads a document (lab results, medical report) via POST /api/upload
 * 2. This route reads the file and sends it to the VLM
 * 3. The VLM extracts structured data (marker names, values, units, reference ranges)
 * 4. The parsed JSON is stored in UploadedDocument.parsedData
 * 5. The frontend can then display the parsed data and let the user confirm
 *    which values to import into the system
 *
 * Supported file types for VLM: images (jpg, png) — PDFs are read as text.
 */

const UPLOAD_DIR = path.join(process.cwd(), "uploads");

export async function POST(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "[REDACTED]";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const { documentId } = await req.json();
    if (!documentId) return NextResponse.json({ ok: false, error: "documentId required" }, { status: 400 });

    const doc = await db.uploadedDocument.findFirst({
      where: { id: documentId, userId: user.id },
    });
    if (!doc) return NextResponse.json({ ok: false, error: "Document not found" }, { status: 404 });

    // Update status to "parsing"
    await db.uploadedDocument.update({
      where: { id: documentId },
      data: { status: "parsing" },
    });

    const filePath = path.join(UPLOAD_DIR, doc.filePath);
    let extractedData: Record<string, unknown> = {};

    if (["jpg", "jpeg", "png"].includes(doc.fileType)) {
      // Image: use VLM to extract data
      const imageBuffer = await readFile(filePath);
      const base64Image = `data:image/${doc.fileType};base64,${imageBuffer.toString("base64")}`;

      const zai = await ZAI.create();
      const response = await zai.chat.completions.createVision({
        messages: [
          {
            role: "assistant",
            content: `You are a medical data extraction assistant. Extract all health/biometric data from this document image. Return ONLY valid JSON with this structure:
{
  "document_type": "lab_results" | "medical_report" | "prescription" | "other",
  "date": "YYYY-MM-DD or null",
  "markers": [
    {
      "name": "marker name (e.g. HDL Cholesterol)",
      "value": number or null,
      "unit": "unit string (e.g. mg/dL)",
      "ref_low": number or null,
      "ref_high": number or null,
      "status": "normal" | "low" | "high" | "unknown"
    }
  ],
  "notes": "any relevant notes from the document"
}

Rules:
- Extract ALL visible markers, values, and reference ranges
- Use null for missing values
- Determine status by comparing value to reference range
- Return ONLY the JSON, no markdown or explanation`,
          },
          {
            role: "user",
            content: [
              { type: "text", text: "Extract all health data from this document." },
              { type: "image_url", image_url: { url: base64Image } },
            ],
          },
        ],
        thinking: { type: "disabled" },
      });

      const rawContent = response.choices[0]?.message?.content ?? "";
      // Clean markdown fences if present
      const cleaned = rawContent.replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/\s*```$/i, "").trim();
      try {
        extractedData = JSON.parse(cleaned);
      } catch {
        extractedData = { raw_extraction: cleaned };
      }
    } else if (doc.fileType === "txt" || doc.fileType === "csv") {
      // Text/CSV: use LLM to parse
      const textContent = await readFile(filePath, "utf-8");

      const zai = await ZAI.create();
      const response = await zai.chat.completions.create({
        messages: [
          {
            role: "assistant",
            content: `You are a medical data extraction assistant. Extract all health/biometric data from this text. Return ONLY valid JSON with this structure:
{
  "document_type": "lab_results" | "medical_report" | "prescription" | "other",
  "date": "YYYY-MM-DD or null",
  "markers": [{"name": "", "value": null, "unit": "", "ref_low": null, "ref_high": null, "status": "normal"}],
  "notes": ""
}`,
          },
          { role: "user", content: textContent.slice(0, 8000) },
        ],
        thinking: { type: "disabled" },
      });

      const rawContent = response.choices[0]?.message?.content ?? "";
      const cleaned = rawContent.replace(/^```json\s*/i, "").replace(/^```\s*/i, "").replace(/\s*```$/i, "").trim();
      try {
        extractedData = JSON.parse(cleaned);
      } catch {
        extractedData = { raw_extraction: cleaned };
      }
    } else if (doc.fileType === "pdf") {
      // PDF: would need a PDF parser (not available in this environment)
      extractedData = {
        document_type: "other",
        error: "PDF parsing requires a PDF library. Please upload as image or text.",
      };
    }

    // Store the parsed data
    await db.uploadedDocument.update({
      where: { id: documentId },
      data: {
        status: "parsed",
        parsedData: JSON.stringify(extractedData),
      },
    });

    return NextResponse.json({ ok: true, parsedData: extractedData });
  } catch (err) {
    // Update status to "error"
    const { documentId } = await req.json().catch(() => ({ documentId: 0 }));
    if (documentId) {
      await db.uploadedDocument.update({
        where: { id: documentId },
        data: { status: "error" },
      }).catch(() => {});
    }
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}
