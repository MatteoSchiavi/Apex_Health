/**
 * GET  /api/labs       — list the user's lab panels, newest first.
 * POST /api/labs       — create a panel (blood test or donation).
 *
 * Per plan §7. If the user has no panels, seeds three demo panels so the
 * page has real data to show on first visit:
 *   1. Blood test from ~3 months ago (Hb 14.8, ferritin 38, etc).
 *   2. Blood test from ~3 weeks ago (Hb 14.2, ferritin 28 — low-ish).
 *   3. Donation from ~6 weeks ago (whole-blood, with nextEligibleDate).
 */

import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import {
  CORE_MARKERS,
  DEFAULT_RANGES,
  parseExtra,
  parseRanges,
  serializeExtra,
  serializeRanges,
} from "@/lib/apex/labsHelpers";
import type { LabPanel } from "@/lib/apex/types";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

/* ------------------------------------------------------------ ensure-user */

async function ensureUser() {
  const email = process.env.GARMIN_EMAIL || "";
  let user = await db.user.findFirst({ where: { email } });
  if (!user) {
    user = await db.user.create({
      data: {
        email,
        name: "Matteo Schiavi",
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

/* ------------------------------------------------------------ shape */

type LabRow = Awaited<ReturnType<typeof db.labPanel.findFirst>>;

function shape(row: NonNullable<LabRow>): LabPanel {
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

/* ------------------------------------------------------------ seed demo */

async function seedDemoPanels(userId: number): Promise<NonNullable<LabRow>[]> {
  const now = new Date();
  const iso = (offsetDays: number) => {
    const d = new Date(now);
    d.setDate(d.getDate() - offsetDays);
    return d.toISOString().slice(0, 10);
  };

  const referenceRanges = serializeRanges(DEFAULT_RANGES);

  const items: Array<{
    panelDate: string;
    panelType: "blood_test" | "donation";
    donationType: string | null;
    hemoglobin: number | null;
    hematocrit: number | null;
    ferritin: number | null;
    iron: number | null;
    wbc: number | null;
    plt: number | null;
    nextEligibleDate: string | null;
    source: string;
    notes: string | null;
    extraMarkers: string | null;
    referenceRanges: string;
  }> = [
    {
      // 3 months ago — baseline panel
      panelDate: iso(90),
      panelType: "blood_test",
      donationType: null,
      hemoglobin: 14.8,
      hematocrit: 44,
      ferritin: 62,
      iron: 95,
      wbc: 6.4,
      plt: 235,
      nextEligibleDate: null,
      source: "manual",
      notes: "Annual physical — values all in range. Iron supplement continuing.",
      extraMarkers: serializeExtra([
        { key: "vit_d",  label: "Vitamin D", value: 28, unit: "ng/mL", ref_low: 30, ref_high: 100 },
        { key: "hba1c",  label: "HbA1c",     value: 5.2, unit: "%",    ref_low: 4.0, ref_high: 5.6 },
      ]),
      referenceRanges,
    },
    {
      // 6 weeks ago — whole-blood donation
      panelDate: iso(42),
      panelType: "donation",
      donationType: "whole_blood",
      hemoglobin: 14.5,
      hematocrit: 43,
      ferritin: 48,
      iron: 88,
      wbc: 6.1,
      plt: 220,
      // 56-day deferral from the donation date
      nextEligibleDate: iso(42 - 56),
      source: "manual",
      notes: "Pre-donation check. Eligible again ~14 days ago.",
      extraMarkers: null,
      referenceRanges,
    },
    {
      // ~3 weeks ago — follow-up test showing ferritin dipping
      panelDate: iso(21),
      panelType: "blood_test",
      donationType: null,
      hemoglobin: 14.1,
      hematocrit: 42,
      ferritin: 27,
      iron: 72,
      wbc: 6.8,
      plt: 248,
      nextEligibleDate: null,
      source: "manual",
      notes: "Post-donation follow-up. Ferritin borderline low — consider supplement.",
      extraMarkers: serializeExtra([
        { key: "vit_d",  label: "Vitamin D", value: 33, unit: "ng/mL", ref_low: 30, ref_high: 100 },
        { key: "crp",    label: "hs-CRP",    value: 0.6, unit: "mg/L", ref_low: 0, ref_high: 1.0 },
      ]),
      referenceRanges,
    },
  ];

  const created: NonNullable<LabRow>[] = [];
  for (const it of items) {
    const row = await db.labPanel.create({ data: { userId, ...it } });
    created.push(row);
  }
  return created;
}

/* ------------------------------------------------------------ GET */

export async function GET() {
  try {
    const user = await ensureUser();
    let rows = await db.labPanel.findMany({
      where: { userId: user.id },
      orderBy: { panelDate: "desc" },
    });
    if (rows.length === 0) {
      rows = await seedDemoPanels(user.id);
    }
    // newest first (panel_date desc, ties broken by id desc)
    rows.sort((a, b) => {
      if (a.panelDate === b.panelDate) return b.id - a.id;
      return a.panelDate < b.panelDate ? 1 : -1;
    });
    return NextResponse.json({ ok: true, panels: rows.map(shape) });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/* ------------------------------------------------------------ POST */

interface CreateBody {
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

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export async function POST(req: NextRequest) {
  try {
    const user = await ensureUser();
    const body = (await req.json().catch(() => ({}))) as CreateBody;

    const panelDate = (body.panelDate ?? "").toString().trim();
    if (!panelDate) {
      return NextResponse.json({ ok: false, error: "panelDate is required" }, { status: 400 });
    }
    const panelType: "blood_test" | "donation" = body.panelType === "donation" ? "donation" : "blood_test";
    const donationType =
      panelType === "donation" && typeof body.donationType === "string" && body.donationType.trim()
        ? body.donationType.trim()
        : null;

    // Persist reference ranges: merge the user's submission over the defaults
    // so the Add form's "pre-filled from last panel" + any edits land in DB.
    const mergedRanges: Record<string, { low: number | null; high: number | null; unit: string }> = { ...DEFAULT_RANGES };
    if (body.referenceRanges && typeof body.referenceRanges === "object") {
      for (const [k, v] of Object.entries(body.referenceRanges)) {
        if (v && typeof v === "object") {
          mergedRanges[k] = {
            low: num(v.low),
            high: num(v.high),
            unit: typeof v.unit === "string" ? v.unit : "",
          };
        }
      }
    }
    const extraMarkers = Array.isArray(body.extraMarkers)
      ? body.extraMarkers.filter((m) => m && typeof m.key === "string" && m.key.trim())
      : [];

    const created = await db.labPanel.create({
      data: {
        userId: user.id,
        panelDate,
        panelType,
        donationType,
        hemoglobin: num(body.hemoglobin),
        hematocrit: num(body.hematocrit),
        ferritin: num(body.ferritin),
        iron: num(body.iron),
        wbc: num(body.wbc),
        plt: num(body.plt),
        nextEligibleDate:
          typeof body.nextEligibleDate === "string" && body.nextEligibleDate.trim()
            ? body.nextEligibleDate.trim()
            : null,
        source: "manual",
        notes: typeof body.notes === "string" ? body.notes.trim() || null : null,
        extraMarkers: extraMarkers.length ? serializeExtra(extraMarkers) : null,
        referenceRanges: serializeRanges(mergedRanges),
      },
    });

    return NextResponse.json({ ok: true, panel: shape(created) }, { status: 201 });
  } catch (err) {
    const message = err instanceof Error ? err.message : "Unknown error";
    return NextResponse.json({ ok: false, error: message }, { status: 500 });
  }
}

/* re-export for any caller that wants the marker catalog */
export { CORE_MARKERS };
