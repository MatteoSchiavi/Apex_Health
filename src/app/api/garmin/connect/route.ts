import { NextRequest, NextResponse } from "next/server";
import { db } from "@/lib/db";
import { GarminConnect } from "garmin-connect";

/**
 * POST /api/garmin/connect
 *
 * Validates Garmin credentials by attempting a login, then stores them in the
 * Integration table so future syncs use them (instead of env vars).
 *
 * Body: { email: string, password: string }
 *
 * Returns:
 *   200 { ok: true, connected: true } — credentials valid, stored
 *   401 { ok: false, error: "Invalid email or password" }
 *   401 { ok: false, error: "MFA required — not supported via the web UI" }
 *   500 { ok: false, error: "..." }
 *
 * GET /api/garmin/connect — returns whether Garmin is connected + the email
 */
export async function POST(req: NextRequest) {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    let user = await db.user.findFirst({ where: { email } });
    if (!user) {
      user = await db.user.create({
        data: {
          email,
          name: "Matteo Schiavi",
          password: "",
          timezone: "Europe/Rome",
          locale: "en",
          theme: "dark",
          units: "metric",
          role: "owner",
          aiTier: "pro",
        },
      });
    }

    const body = await req.json();
    const garminEmail = (body?.email as string)?.trim();
    const garminPassword = body?.password as string;

    if (!garminEmail || !garminPassword) {
      return NextResponse.json({ ok: false, error: "Email and password are required" }, { status: 400 });
    }

    // Validate the credentials by attempting a login
    try {
      const client = new GarminConnect({
        username: garminEmail,
        password: garminPassword,
      });
      await client.login();
      // Login succeeded — credentials are valid
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      if (msg.includes("MFA") || msg.includes("mfa") || msg.includes("Ticket not found")) {
        return NextResponse.json(
          { ok: false, error: "Login failed — check your email and password. If you have MFA enabled, Garmin requires a one-time code that this flow can't handle yet." },
          { status: 401 },
        );
      }
      return NextResponse.json(
        { ok: false, error: `Login failed: ${msg}` },
        { status: 401 },
      );
    }

    // Upsert the Integration record with the credentials
    const existing = await db.integration.findFirst({
      where: { userId: user.id, provider: "Garmin" },
    });

    if (existing) {
      await db.integration.update({
        where: { id: existing.id },
        data: {
          garminEmail,
          garminPassword,
          status: "active",
          isMain: true,
        },
      });
    } else {
      await db.integration.create({
        data: {
          userId: user.id,
          provider: "Garmin",
          status: "active",
          isMain: true,
          garminEmail,
          garminPassword,
        },
      });
    }

    return NextResponse.json({ ok: true, connected: true, email: garminEmail });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}

/**
 * GET /api/garmin/connect — returns connection status
 */
export async function GET() {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: true, connected: false });

    const integration = await db.integration.findFirst({
      where: { userId: user.id, provider: "Garmin" },
    });

    return NextResponse.json({
      ok: true,
      connected: !!(integration?.garminEmail && integration?.garminPassword),
      email: integration?.garminEmail || null,
      status: integration?.status || null,
      lastSyncedAt: integration?.lastSyncedAt || null,
    });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}

/**
 * DELETE /api/garmin/connect — disconnects Garmin (clears stored credentials)
 */
export async function DELETE() {
  try {
    const email = process.env.GARMIN_EMAIL || "";
    const user = await db.user.findFirst({ where: { email } });
    if (!user) return NextResponse.json({ ok: true });

    await db.integration.updateMany({
      where: { userId: user.id, provider: "Garmin" },
      data: { garminEmail: null, garminPassword: null, status: "paused" },
    });

    return NextResponse.json({ ok: true });
  } catch (err) {
    return NextResponse.json(
      { ok: false, error: err instanceof Error ? err.message : "Unknown error" },
      { status: 500 },
    );
  }
}
