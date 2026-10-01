import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { writeFile, mkdir } from "fs/promises";
import { existsSync } from "fs";
import path from "path";

/**
 * Document Upload API
 * POST /api/upload — accepts multipart file upload (lab results, medical reports, etc.)
 * Stores the file and creates a UploadedDocument record with status "pending".
 * The /api/parse-document route then processes it with the VLM/LLM.
 *
 * Supported file types: pdf, jpg, jpeg, png, txt, csv
 * Max file size: 10MB
 */

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const SUPPORTED_TYPES = ["pdf", "jpg", "jpeg", "png", "txt", "csv"];
const UPLOAD_DIR = path.join(process.cwd(), "uploads");

export async function POST(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const formData = await req.formData();
    const file = formData.get("file") as File | null;
    if (!file) return NextResponse.json({ ok: false, error: "No file provided" }, { status: 400 });

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json({ ok: false, error: "File too large (max 10MB)" }, { status: 400 });
    }

    // Validate file type
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!SUPPORTED_TYPES.includes(ext)) {
      return NextResponse.json({ ok: false, error: `Unsupported file type: ${ext}. Supported: ${SUPPORTED_TYPES.join(", ")}` }, { status: 400 });
    }

    // Ensure upload directory exists
    if (!existsSync(UPLOAD_DIR)) {
      await mkdir(UPLOAD_DIR, { recursive: true });
    }

    // Save the file
    const fileName = `${Date.now()}-${file.name}`;
    const filePath = path.join(UPLOAD_DIR, fileName);
    const buffer = Buffer.from(await file.arrayBuffer());
    await writeFile(filePath, buffer);

    // Create database record
    const doc = await db.uploadedDocument.create({
      data: {
        userId: user.id,
        fileName: file.name,
        fileType: ext,
        fileSize: file.size,
        filePath: fileName,
        status: "pending",
      },
    });

    return NextResponse.json({ ok: true, documentId: doc.id, fileName: file.name, status: "pending" });
  } catch (err) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}

/**
 * GET /api/upload — list uploaded documents
 */
export async function GET() {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const docs = await db.uploadedDocument.findMany({
      where: { userId: user.id },
      orderBy: { uploadedAt: "desc" },
    });

    return NextResponse.json({ ok: true, documents: docs });
  } catch (err) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}
