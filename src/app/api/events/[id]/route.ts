import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";

/**
 * Calendar Event detail API (plan §2 + Phase 0 fix #4)
 *
 * PATCH  /api/events/[id]  → body { title?, date?, endDate?, priority?, taperDays?, kind?, note? }
 *                            Updates an event. Used by the new Edit button.
 * DELETE /api/events/[id]  → delete a single event by id.
 *
 * (GET/POST/DELETE-by-query already live at /api/events/route.ts.)
 */

export async function PATCH(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const id = parseInt(idStr);
    if (!Number.isFinite(id)) {
      return NextResponse.json({ ok: false, error: "invalid id" }, { status: 400 });
    }

    const body = await req.json();
    const { title, date, endDate, priority, taperDays, kind, note } = body || {};

    const data: Record<string, unknown> = {};
    if (typeof title === "string") data.title = title;
    if (typeof date === "string") data.date = date;
    if (typeof endDate === "string") data.endDate = endDate;
    if (endDate === null) data.endDate = null;
    if (typeof priority === "string") data.priority = priority;
    if (typeof taperDays === "number") data.taperDays = taperDays;
    if (taperDays === null) data.taperDays = null;
    if (typeof kind === "string") data.kind = kind;
    if (typeof note === "string") data.note = note;
    if (note === null) data.note = null;

    if (Object.keys(data).length === 0) {
      return NextResponse.json({ ok: false, error: "nothing to update" }, { status: 400 });
    }

    const updated = await db.calendarEvent.update({
      where: { id },
      data,
    });

    return NextResponse.json({ ok: true, event: updated });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}

export async function DELETE(
  _req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id: idStr } = await params;
    const id = parseInt(idStr);
    if (!Number.isFinite(id)) {
      return NextResponse.json({ ok: false, error: "invalid id" }, { status: 400 });
    }

    await db.calendarEvent.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 }
    );
  }
}
