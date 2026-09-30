import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Calendar Events API
 * GET  /api/events — list all events for the user
 * POST /api/events — create a new event
 * DELETE /api/events?id=N — delete an event
 */

export async function GET() {
  try {
    const email = process.env.GARMIN_EMAIL || "[REDACTED]";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const events = await db.calendarEvent.findMany({
      where: { userId: user.id },
      orderBy: { date: "asc" },
    });

    return NextResponse.json({ ok: true, events });
  } catch (err) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}

export async function POST(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "[REDACTED]";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: false, error: "No user" }, { status: 404 });

    const body = await req.json();
    const { title, kind, date, endDate, priority, taperDays, note } = body;

    if (!title || !date) {
      return NextResponse.json({ ok: false, error: "title and date are required" }, { status: 400 });
    }

    const event = await db.calendarEvent.create({
      data: {
        userId: user.id,
        title,
        kind: kind || "session",
        date,
        endDate: endDate || null,
        priority: priority || "normal",
        taperDays: taperDays || null,
        note: note || null,
      },
    });

    return NextResponse.json({ ok: true, event });
  } catch (err) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}

export async function DELETE(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const id = parseInt(searchParams.get("id") || "0");
    if (!id) return NextResponse.json({ ok: false, error: "id required" }, { status: 400 });

    await db.calendarEvent.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json({ ok: false, error: err instanceof Error ? err.message : "Unknown" }, { status: 500 });
  }
}
