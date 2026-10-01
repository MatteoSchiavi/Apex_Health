import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { writeFile, mkdir, unlink } from "fs/promises";
import { existsSync } from "fs";
import path from "path";

/**
 * Document Upload API
 *
 * POST /api/upload — accepts multipart file upload with a category.
 *   Categories: lab_test, medical_report, training_plan, dietary_plan,
 *               prescription, blood_work, other
 *   Supported file types: pdf, jpg, jpeg, png, txt, csv
 *   Max file size: 10MB
 *   formData: { file: File, category: string }
 *
 * GET /api/upload — list uploaded documents (newest first)
 *
 * DELETE /api/upload?id=N — delete a document + its file
 */

const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB
const SUPPORTED_TYPES = ["pdf", "jpg", "jpeg", "png", "txt", "csv"];
const UPLOAD_DIR = path.join(process.cwd(), "uploads");

export const CATEGORIES = [
  "lab_test",
  "medical_report",
  "training_plan",
  "dietary_plan",
  "prescription",
  "blood_work",
  "other",
] as const;
export type DocCategory = (typeof CATEGORIES)[number];

export async function POST(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const formData = await req.formData();
    const file = formData.get("file") as File | null;
    if (!file) return NextResponse.json({ ok: false, error: "No file provided" }, { status: 400 });

    const category = (formData.get("category") as string) || "other";
    const validCategory = CATEGORIES.includes(category as DocCategory) ? category : "other";

    // Validate file size
    if (file.size > MAX_FILE_SIZE) {
      return NextResponse.json({ ok: false, error: "File too large (max 10MB)" }, { status: 400 });
    }

    // Validate file type
    const ext = file.name.split(".").pop()?.toLowerCase() || "";
    if (!SUPPORTED_TYPES.includes(ext)) {
      return NextResponse.json(
        { ok: false, error: `Unsupported file type: ${ext}. Supported: ${SUPPORTED_TYPES.join(", ")}` },
        { status: 400 },
      );
    }

    // Ensure upload directory exists
    if (!existsSync(UPLOAD_DIR)) {
      await mkdir(UPLOAD_DIR, { recursive: true });
    }

    // Save the file
    const fileName = `${Date.now()}-${file.name.replace(/[^a-zA-Z0-9._-]/g, "_")}`;
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
        category: validCategory,
        source: "manual",
        status: "pending",
      },
    });

    return NextResponse.json({ ok: true, documentId: doc.id, fileName: file.name, status: "pending", category: validCategory });
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

/**
 * DELETE /api/upload?id=N — delete a document + its file
 */
export async function DELETE(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const id = Number(new URL(req.url).searchParams.get("id"));
    if (!id) return NextResponse.json({ ok: false, error: "id required" }, { status: 400 });

    const doc = await db.uploadedDocument.findFirst({ where: { id, userId: user.id } });
    if (!doc) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    // Delete the file (ignore errors if already gone)
    const filePath = path.join(UPLOAD_DIR, doc.filePath);
    if (existsSync(filePath)) {
      await unlink(filePath).catch(() => {});
    }

    await db.uploadedDocument.delete({ where: { id } });

    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}
