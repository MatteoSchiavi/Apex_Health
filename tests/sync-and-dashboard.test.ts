import { beforeEach, describe, expect, mock, test } from "bun:test";
import { NextRequest } from "next/server";

// All provider calls are local fixtures. No Garmin account is contacted.
let userId = 100;
let integration: any;
let sleepFailure = false;
let dailyFailure = false;
let loginFailure = false;
let staleSleep: any = null;
const today = new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Rome", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
const user = () => ({ id: userId, email: "fixture@apex.invalid", timezone: "Europe/Rome" });
const updates = mock(async (_args: any) => ({ count: 1 }));
const integrationCreate = mock(async (_args: any) => ({}));
const labCreate = mock(async (_args: any) => ({}));
const gearCreate = mock(async (_args: any) => ({}));
const biometricWrite = mock(async (_args: any) => ({}));
const login = mock(async () => { if (loginFailure) throw new Error("fixture login failed"); });
const fakeDb = {
  user: { findFirst: mock(async () => user()), create: mock(async () => user()) },
  integration: { findFirst: mock(async () => integration), findMany: mock(async () => []), updateMany: updates, create: integrationCreate },
  activity: { findMany: mock(async () => []), upsert: mock(async () => ({})) },
  sleepSession: {
    findFirst: mock(async (args: any) => args.where.localDate ? (staleSleep?.localDate === args.where.localDate ? staleSleep : null) : staleSleep),
    findMany: mock(async () => staleSleep ? [staleSleep] : []), create: mock(async () => ({})), update: mock(async () => ({})),
  },
  dailyBiometric: { findFirst: mock(async () => ({ date: today, hrvMs: 55, restingHr: 50 })), findMany: mock(async () => []), upsert: biometricWrite },
  hrvReading: { findMany: mock(async () => []) },
  gear: { findMany: mock(async () => []), create: gearCreate },
  labPanel: { findMany: mock(async () => []), findFirst: mock(async () => null), create: labCreate },
};
mock.module("../src/lib/db", () => ({ db: fakeDb }));
mock.module("garmin-connect", () => ({ GarminConnect: class {
  login = login;
  getActivities = async () => [];
  getSleepData = async () => { if (sleepFailure) throw new Error("fixture sleep unavailable"); return {}; };
  getSteps = async () => { if (dailyFailure) throw new Error("fixture stats unavailable"); return 1234; };
  getHeartRate = async () => ({ restingHeartRate: 50 });
} }));

const { syncGarminData, getGarminClient } = await import("../src/lib/garmin/sync");
const { POST: sync } = await import("../src/app/api/garmin/sync/route");
const { GET: dashboard } = await import("../src/app/api/dashboard/route");
const { GET: integrations } = await import("../src/app/api/integrations/route");
const { GET: labs } = await import("../src/app/api/labs/route");
const { GET: gear } = await import("../src/app/api/gear/route");

beforeEach(() => {
  userId += 10;
  integration = { status: "active", garminEmail: "fixture@apex.invalid", garminPassword: "same-prefix-first" };
  sleepFailure = dailyFailure = loginFailure = false;
  staleSleep = null;
  updates.mockClear(); integrationCreate.mockClear(); biometricWrite.mockClear(); login.mockClear();
  labCreate.mockClear(); gearCreate.mockClear();
});

describe("sync never disguises failed work as success", () => {
  test("provider login failure returns 502 and preserves the success timestamp", async () => {
    loginFailure = true;
    const response = await sync(new NextRequest("http://localhost/api/garmin/sync", { method: "POST" }));
    const body = await response.json();
    expect(response.status).toBe(502);
    expect(body.ok).toBe(false);
    expect(body.error).toContain("fixture login failed");
    expect(updates.mock.calls[0][0].data).toEqual({ status: "error" });
  });
  test("individual sleep failures are reported, while daily data still syncs", async () => {
    sleepFailure = true;
    const report = await syncGarminData(userId);
    expect(report.errors).toHaveLength(14);
    expect(report.errors[0]).toContain("fixture sleep unavailable");
    expect(report.dailyStats).toBe(7);
  });
  test("daily stats failures are reported instead of overwriting measurements", async () => {
    dailyFailure = true;
    const report = await syncGarminData(userId);
    expect(report.errors).toHaveLength(7);
    expect(report.dailyStats).toBe(0);
    expect(biometricWrite).not.toHaveBeenCalled();
  });
  test("complete sync returns 200 and records a successful timestamp", async () => {
    const response = await sync(new NextRequest("http://localhost/api/garmin/sync", { method: "POST" }));
    expect(response.status).toBe(200);
    expect((await response.json()).ok).toBe(true);
    expect(updates.mock.calls[0][0].data.lastSyncedAt).toBeString();
  });
  test("changing the password after its first two characters invalidates the cache", async () => {
    const first = await getGarminClient(userId);
    integration.garminPassword = "same-prefix-second";
    expect(await getGarminClient(userId)).not.toBe(first);
    expect(login).toHaveBeenCalledTimes(2);
  });
  test("two users do not share a cached provider session", async () => {
    expect(await getGarminClient(userId)).not.toBe(await getGarminClient(userId + 1));
    expect(login).toHaveBeenCalledTimes(2);
  });
  test("a paused integration blocks sync even with cached credentials", async () => {
    await getGarminClient(userId);
    integration.status = "paused";
    expect((await syncGarminData(userId)).errors[0]).toContain("No Garmin credentials");
    expect(login).toHaveBeenCalledTimes(1);
  });
  test("a sync attempt cannot replace disconnected state with error", async () => {
    integration.status = "paused";
    const response = await sync(new NextRequest("http://localhost/api/garmin/sync", { method: "POST" }));
    expect(response.status).toBe(502);
    expect(updates.mock.calls[0][0].where.status).toEqual({ not: "paused" });
    expect(login).not.toHaveBeenCalled();
  });
});

describe("status is based on measured data", () => {
  test("old sleep cannot generate today's readiness or full completeness", async () => {
    staleSleep = { localDate: "2020-01-01", sleepScore: 90, totalSleepS: 28800 };
    const body = await (await dashboard()).json();
    expect(body.ok).toBe(true);
    expect(body.overview.sleep_score.value).toBeNull();
    expect(body.overview.readiness.value).toBeNull();
    expect(body.overview.data_completeness).toBe("partial");
  });
  test("reading empty integrations does not fabricate a connected device", async () => {
    const body = await (await integrations()).json();
    expect(body.integrations).toEqual([]);
    expect(integrationCreate).not.toHaveBeenCalled();
  });
  test("reading empty labs never fabricates medical history", async () => {
    const body = await (await labs()).json();
    expect(body.ok).toBe(true);
    expect(body.panels).toEqual([]);
    expect(labCreate).not.toHaveBeenCalled();
  });
  test("reading empty gear never creates equipment or service alerts", async () => {
    const body = await (await gear()).json();
    expect(body.ok).toBe(true);
    expect(body.gear).toEqual([]);
    expect(gearCreate).not.toHaveBeenCalled();
  });
});
