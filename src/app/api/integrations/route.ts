/**
 * Integrations API.
 *
 * GET /api/integrations → list of connected integrations for the current
 * user with { provider, status, last_synced_at, is_main, consecutive_failures }.
 *
 * If no integrations exist, seeds Garmin (active) so the "Integration
 * health" Overview card has something to display.
 */

import { NextResponse } from "next/server";
import { db } from "@/lib/db";

async function getOrCreateUser() {
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

export async function GET() {
  try {
    const user = await getOrCreateUser();

    let integrations = await db.integration.findMany({
      where: { userId: user.id },
      orderBy: [{ isMain: "desc" }, { provider: "asc" }],
    });

    if (integrations.length === 0) {
      const seeded = await db.integration.create({
        data: {
          userId: user.id,
          provider: "Garmin",
          status: "active",
          lastSyncedAt: new Date().toISOString(),
          isMain: true,
        },
      });
      integrations = [seeded];
    }

    return NextResponse.json({
      ok: true,
      integrations: integrations.map((i) => ({
        provider: i.provider,
        status: i.status,
        last_synced_at: i.lastSyncedAt,
        is_main: i.isMain,
        // The Integration model has no consecutive_failures column — derive a
        // flag from the status field instead (status === "error" ⇒ 1).
        consecutive_failures: i.status === "error" ? 1 : 0,
      })),
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown" },
      { status: 500 },
    );
  }
}
