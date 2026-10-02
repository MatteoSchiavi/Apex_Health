/**
 * GET    /api/labs/[id]  — panel detail (with parsed extraMarkers + referenceRanges).
 * PATCH  /api/labs/[id]  — partial update (any of: panelDate, panelType,
 *                          donationType, the six core markers, nextEligibleDate,
 *                          notes, extraMarkers, referenceRanges).
 * DELETE /api/labs/[id]  — delete a panel.
 *
 * Per plan §7 finding: "no update or delete route, so a typo in a panel
 * cannot be corrected." This file closes that gap.
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  DEFAULT_RANGES,
  parseExtra,
  parseRanges,
  serializeExtra,
  serializeRanges,
} from "@/lib/apex/labsHelpers";
import type { LabPanel } from "@/lib/apex/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

async function ensureUser() {
  const email = process.env.GARMIN_EMAIL || "";
  let user = await db.user.findFirst({ where: { email } });
  if (!user) {
    user = await db.user.create({
      data: {
        email,
        name: "Apex Athlete",
        password: process.env.GARMIN_PASSWORD || "",
        timezone: "Europe/Rome",
        locale: "en",
        theme: "dark",
        units: "metric",
        role: "owner",
        aiTier: "pro",
      },
    });
  }
  return user;
}

type LabRow = NonNullable<Awaited<ReturnType<typeof db.labPanel.findFirst>>>;

function shape(row: LabRow): LabPanel {
  return {
    id: row.id,
    panel_date: row.panelDate,
    panel_type: row.panelType as "blood_test" | "donation",
    donation_type: row.donationType,
    hemoglobin: row.hemoglobin,
    hematocrit: row.hematocrit,
    ferritin: row.ferritin,
    iron: row.iron,
    wbc: row.wbc,
    plt: row.plt,
    next_eligible_date: row.nextEligibleDate,
    source: row.source,
    notes: row.notes,
    extra_markers: parseExtra(row.extraMarkers),
    reference_ranges: parseRanges(row.referenceRanges),
  };
}

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/* ------------------------------------------------------------ GET */

export async function GET(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const row = await db.labPanel.findFirst({ where: { id, userId: user.id } });
    if (!row) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });
    return NextResponse.json({ ok: true, panel: shape(row) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/* ------------------------------------------------------------ PATCH */

interface PatchBody {
  panelDate?: string;
  panelType?: "blood_test" | "donation";
  donationType?: string | null;
  hemoglobin?: number | null;
  hematocrit?: number | null;
  ferritin?: number | null;
  iron?: number | null;
  wbc?: number | null;
  plt?: number | null;
  nextEligibleDate?: string | null;
  notes?: string | null;
  extraMarkers?: { key: string; label: string; value: number | null; unit: string; ref_low: number | null; ref_high: number | null }[];
  referenceRanges?: Record<string, { low: number | null; high: number | null; unit: string }>;
}

export async function PATCH(req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const existing = await db.labPanel.findFirst({ where: { id, userId: user.id } });
    if (!existing) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    const body = (await req.json().catch(() => ({}))) as PatchBody;
    const data: Record<string, unknown> = {};

    if (typeof body.panelDate === "string" && body.panelDate.trim()) data.panelDate = body.panelDate.trim();
    if (body.panelType === "blood_test" || body.panelType === "donation") data.panelType = body.panelType;
    if (body.donationType !== undefined) {
      data.donationType =
        typeof body.donationType === "string" && body.donationType.trim() ? body.donationType.trim() : null;
    }
    if (body.hemoglobin !== undefined) data.hemoglobin = num(body.hemoglobin);
    if (body.hematocrit !== undefined) data.hematocrit = num(body.hematocrit);
    if (body.ferritin !== undefined) data.ferritin = num(body.ferritin);
    if (body.iron !== undefined) data.iron = num(body.iron);
    if (body.wbc !== undefined) data.wbc = num(body.wbc);
    if (body.plt !== undefined) data.plt = num(body.plt);
    if (body.nextEligibleDate !== undefined) {
      data.nextEligibleDate =
        typeof body.nextEligibleDate === "string" && body.nextEligibleDate.trim()
          ? body.nextEligibleDate.trim()
          : null;
    }
    if (body.notes !== undefined) {
      data.notes = typeof body.notes === "string" ? body.notes.trim() || null : null;
    }
    if (Array.isArray(body.extraMarkers)) {
      const filtered = body.extraMarkers.filter((m) => m && typeof m.key === "string" && m.key.trim());
      data.extraMarkers = filtered.length ? serializeExtra(filtered) : null;
    }
    if (body.referenceRanges && typeof body.referenceRanges === "object") {
      const merged: Record<string, { low: number | null; high: number | null; unit: string }> = { ...DEFAULT_RANGES };
      for (const [k, v] of Object.entries(body.referenceRanges)) {
        if (v && typeof v === "object") {
          merged[k] = { low: num(v.low), high: num(v.high), unit: typeof v.unit === "string" ? v.unit : "" };
        }
      }
      data.referenceRanges = serializeRanges(merged);
    }

    if (Object.keys(data).length > 0) {
      await db.labPanel.update({ where: { id }, data });
    }
    const updated = await db.labPanel.findFirst({ where: { id, userId: user.id } });
    if (!updated) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });
    return NextResponse.json({ ok: true, panel: shape(updated) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/* ------------------------------------------------------------ DELETE */

export async function DELETE(_req: NextRequest, ctx: { params: Promise<{ id: string }> }) {
  try {
    const user = await ensureUser();
    const { id: idStr } = await ctx.params;
    const id = parseInt(idStr);
    if (!id) return NextResponse.json({ ok: false, error: "Bad id" }, { status: 400 });

    const existing = await db.labPanel.findFirst({ where: { id, userId: user.id } });
    if (!existing) return NextResponse.json({ ok: false, error: "Not found" }, { status: 404 });

    await db.labPanel.delete({ where: { id } });
    return NextResponse.json({ ok: true });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}
