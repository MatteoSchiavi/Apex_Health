import { expect, test } from "@playwright/test";
import { activity, installApi, night, today } from "./fixtures";

for (const path of ["/app/sleep", `/app/sleep/${today}`]) {
  test(`sleep provider scores keep their attribution on ${path}`, async ({ page }) => {
    await installApi(page);
    await page.goto(path);
    await expect(page.getByText("Device sleep score", { exact: true })).toBeVisible();
    await expect(page.locator("main")).not.toContainText("Calculated estimate");
  });
}

test("inconsistent provider durations never show 100% sleep efficiency", async ({ page }) => {
  await installApi(page);
  const inconsistent = { ...night, total_sleep_s: 28800, awake_s: 7200 };
  await page.route((url) => url.pathname === `/sleep/${today}`, (route) => route.fulfill({
    json: { date: today, session: inconsistent, biometrics: {}, hrv_readings: [] },
  }));
  await page.route((url) => url.pathname === "/sleep", (route) => route.fulfill({
    json: { items: [inconsistent], start_date: today, end_date: today },
  }));
  await page.goto(`/app/sleep/${today}`);
  await expect(page.getByText(/Efficiency and stage percentages are unavailable/)).toBeVisible();
  const efficiency = page.getByText("Efficiency", { exact: true }).locator("../..");
  await expect(efficiency).toContainText("—");
  await expect(efficiency).not.toContainText("100");
  await page.goto("/app/sleep");
  await expect(page.getByText("Stage totals do not match")).toBeVisible();
  await expect(page.locator("tbody tr").first().locator("td").nth(5)).toContainText("—");
});

test("consistent sleep durations retain efficiency", async ({ page }) => {
  await installApi(page);
  await page.goto(`/app/sleep/${today}`);
  await expect(page.getByText("Efficiency", { exact: true }).locator("../..")).toContainText("93.8");
  await expect(page.getByText(/Efficiency and stage percentages are unavailable/)).toHaveCount(0);
});

test("unmapped activities display the recorded provider sport without inventing a category", async ({ page }) => {
  await installApi(page);
  const imported = { ...activity, discipline: null, source_activity_type: "disc_golf" };
  await page.route((url) => url.pathname === "/activities", (route) => route.fulfill({
    json: { items: [imported, { ...activity, id: 2, discipline: null, source_activity_type: null }], total: 2, offset: 0, limit: 50 },
  }));
  await page.route((url) => url.pathname === "/activities/1", (route) => route.fulfill({ json: imported }));
  await page.goto("/app/activities");
  await expect(page.getByText("Disc Golf", { exact: true })).toBeVisible();
  await expect(page.getByText("Unknown activity", { exact: true })).toBeVisible();
  await page.getByText("Disc Golf", { exact: true }).click();
  await expect(page.getByRole("heading", { name: "Disc Golf", exact: true })).toBeVisible();
  await expect(page.getByText(/Sport reported by your connected source/)).toBeVisible();
});

test("challenge members can inspect results, leave and rejoin with the correct period", async ({ page }) => {
  await installApi(page);
  let joined = true;
  const actions: string[] = [];
  await page.route((url) => url.pathname === "/challenges", (route) => route.fulfill({ json: [{
    id: 7, name: "Friends steps", metric: "steps", period: "all_time", starts_at: null, ends_at: null,
    member_count: joined ? 3 : 2, created_by_name: "Friend", is_member: joined,
  }] }));
  await page.route((url) => url.pathname === "/challenges/7", (route) => route.fulfill({ json: {
    entries: [{ user_id: 2, display_name: "Active friend", value: 12000, rank: 1 }],
  } }));
  await page.route((url) => /^\/challenges\/7\/(join|leave)$/.test(url.pathname), (route) => {
    const action = new URL(route.request().url()).pathname.split("/").pop()!;
    joined = action === "join";
    actions.push(action);
    return route.fulfill({ json: { challenge_id: 7, joined } });
  });
  await page.goto("/app/social");
  await expect(page.getByText("Joined", { exact: true })).toBeVisible();
  await expect(page.locator("main")).toContainText("All time");
  await expect(page.locator("main")).not.toContainText("— → —");
  await expect(page.getByRole("button", { name: "Join", exact: true })).toHaveCount(0);
  await page.getByRole("button", { name: "View results", exact: true }).click();
  await expect(page.getByRole("button", { name: "Hide results", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByRole("table", { name: "Results for Friends steps" })).toContainText("Active friend");
  await page.getByRole("button", { name: "Leave", exact: true }).click();
  await expect(page.getByRole("button", { name: "Join", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Join", exact: true }).click();
  await expect(page.getByText("Joined", { exact: true })).toBeVisible();
  expect(actions).toEqual(["leave", "join"]);
});

test("new challenges submit a chosen period and trim the name", async ({ page }) => {
  const { writes } = await installApi(page);
  await page.goto("/app/social");
  await page.getByRole("button", { name: /Create Challenge/ }).click();
  await page.getByLabel("Name", { exact: true }).fill("  Weekend friends  ");
  await page.getByRole("combobox", { name: "Period", exact: true }).selectOption("monthly");
  await page.getByRole("button", { name: "Create Challenge", exact: true }).click();
  await expect.poll(() => writes.find((write) => write.path === "/challenges")?.body).toEqual({ name: "Weekend friends", metric: "steps", period: "monthly" });
});
