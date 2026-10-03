import { afterAll, beforeAll, expect, test } from "bun:test";
import { NextRequest } from "next/server";
import { db } from "../../src/lib/db";
import { GET as list } from "../../src/app/api/activities/route";
import { GET as detail } from "../../src/app/api/activities/[id]/route";
import { GET as weekly } from "../../src/app/api/activities/weekly/route";
import { addCalendarDays, calendarDate, mondayForDate } from "../../src/lib/apex/activityQueries";

const today = calendarDate(new Date(), "Europe/Rome");
const largeId = "9007199254740993123456";
const record = (id: string, userId: number, localDate = today, sources = "Garmin") => ({
  id, userId, localDate, startTime: `${localDate} 08:00:00`, discipline: "cycling",
  title: `Recorded ${id}`, durationS: 600, distanceM: 1000, avgHr: 120, sources,
});
beforeAll(async () => {
  const owner = await db.user.create({ data: { email: process.env.GARMIN_EMAIL!, name: "Owner", password: "fixture-only" } });
  const other = await db.user.create({ data: { email: "other@activity.invalid", name: "Other", password: "fixture-only" } });
  await db.activity.createMany({ data: [
    ...Array.from({ length: 100 }, (_, i) => record(`record-${String(i).padStart(3, "0")}`, owner.id)),
    record(largeId, owner.id), record("combo:activity", owner.id, today, "Strava,Garmin,Whoop"),
    record("substring", owner.id, today, "SuperGarmin"),
    record("last-in-window", owner.id, addCalendarDays(today, -29)),
    record("previous", owner.id, addCalendarDays(today, -30)),
    record("older", owner.id, addCalendarDays(today, -60)),
    record("future", owner.id, addCalendarDays(today, 1)), record("foreign", other.id),
  ] });
});
afterAll(() => db.$disconnect());
const request = (path: string) => new NextRequest(`http://localhost/api/activities${path}`);

for (const query of ["week=2026-02-30", "week=2026-10-04", "days=abc", "days=NaN", "days=99999999999", "days=0", "limit=101", "offset=-1", "offset=1.5", "limit=2junk", "source=Garmin%2CWhoop", "days="]) {
  test(`malformed query returns 400: ${query}`, async () => {
    expect((await list(request(`?${query}`))).status).toBe(400);
  });
}
test("bounded page with complete, equal-period totals", async () => {
  const response = await list(request("?days=30&offset=60&limit=20"));
  const body = await response.json();
  expect(response.status).toBe(200);
  expect(body.activities).toHaveLength(20);
  expect(body.total).toBe(104);
  expect(body.summary).toEqual({ sessions: 104, total_time_s: 62400, total_distance_m: 104000, total_load: 0,
    prev_sessions: 1, prev_total_time_s: 600, prev_total_distance_m: 1000, prev_total_load: 0 });
  expect(body.activities.every((a: any) => typeof a.id === "string")).toBe(true);
});
test("stable pages have no overlap even when start times tie", async () => {
  const a = await (await list(request("?days=30&limit=60"))).json();
  const b = await (await list(request("?days=30&offset=60&limit=60"))).json();
  const ids = [...a.activities, ...b.activities].map((a: any) => a.id);
  expect(new Set(ids).size).toBe(104);
});
test("source filter matches full tokens", async () => {
  const body = await (await list(request("?days=30&source=Garmin"))).json();
  expect(body.total).toBe(103);
  expect(body.activities.some((a: any) => a.id === "substring")).toBe(false);
});
for (const id of [largeId, "combo:activity"]) {
  test(`selected detail keeps exact ID and recorded measurements: ${id}`, async () => {
    const response = await detail(request(`/${id}`), { params: Promise.resolve({ id }) });
    const { activity } = await response.json();
    expect(response.status).toBe(200);
    expect(activity.id).toBe(id);
    expect(activity.title).toBe(`Recorded ${id}`);
    expect(activity.avg_hr).toBe(120);
    expect(activity.route).toBeNull();
    expect(activity.has_streams).toBe(false);
    expect(activity.laps).toEqual([]);
    expect(activity.weather).toBeNull();
    expect(activity.gear).toEqual([]);
    expect(activity.source_metrics).toEqual({});
  });
}
for (const id of ["missing", "foreign"]) {
  test(`unavailable detail returns 404 without fixture fallback: ${id}`, async () => {
    expect((await detail(request(`/${id}`), { params: Promise.resolve({ id }) })).status).toBe(404);
  });
}
test("weekly chart agrees with the list's selected calendar range", async () => {
  const body = await (await weekly(request("/weekly?days=30"))).json();
  expect(body.weekly.reduce((n: number, w: any) => n + w.sessions, 0)).toBe(104);
  const filtered = await (await weekly(request("/weekly?days=30&source=Garmin"))).json();
  expect(filtered.weekly.reduce((n: number, w: any) => n + w.sessions, 0)).toBe(103);
});
test("bad weekly ranges return 400", async () => {
  for (const query of ["weeks=bad", "weeks=53", "days=367"]) {
    expect((await weekly(request(`/weekly?${query}`))).status).toBe(400);
  }
});
test("calendar labels respect user timezone, DST and year boundaries", () => {
  expect(calendarDate(new Date("2026-03-28T23:30:00Z"), "Europe/Rome")).toBe("2026-03-29");
  expect(calendarDate(new Date("2026-03-29T00:30:00Z"), "America/Los_Angeles")).toBe("2026-03-28");
  expect(addCalendarDays("2026-03-29", 1)).toBe("2026-03-30");
  expect(addCalendarDays("2026-10-25", -1)).toBe("2026-10-24");
  expect(mondayForDate("2027-01-03")).toBe("2026-12-28");
});

test("week drill-down queries the full database and keeps period summaries", async () => {
  const week = mondayForDate(addCalendarDays(today, -29));
  const response = await list(request(`?days=30&week=${week}`));
  const body = await response.json();
  expect(body.activities.map((a: any) => a.id)).toEqual(["last-in-window"]);
  expect(body.total).toBe(1);
  expect(body.summary.sessions).toBe(104);
});
