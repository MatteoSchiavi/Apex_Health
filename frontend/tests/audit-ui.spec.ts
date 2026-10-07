import { expect, test } from "@playwright/test";
import { installApi, today } from "./fixtures";

test("public landing preview labels every value as illustrative and uses no sample measurements", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("Illustrative · no personal data")).toBeVisible();
  await expect(page.getByText("Connect a source to see your own measurements.")).toBeVisible();
  const preview = page.getByLabel("Example dashboard");
  await expect(preview.getByText("—", { exact: true })).toHaveCount(3);
});

test("overview checklist reflects active integrations and real sleep history, and stays dismissible", async ({ page }) => {
  await installApi(page);
  await page.route((url) => url.pathname === "/settings/devices", (route) => route.fulfill({ json: [] }));
  await page.goto("/app");
  await expect(page.getByRole("heading", { name: "Make your workspace useful" })).toBeVisible();
  await expect(page.getByText("No connected source yet")).toBeVisible();
  await expect(page.getByText(/\d+\/14 recorded nights in the last 28 days/)).toBeVisible();
  await page.getByRole("button", { name: "Dismiss setup checklist" }).click();
  await expect(page.getByRole("heading", { name: "Make your workspace useful" })).toHaveCount(0);
  await page.reload();
  await expect(page.getByRole("heading", { name: "Make your workspace useful" })).toHaveCount(0);
});

test("historical overview requests a stored decision for its selected day", async ({ page }) => {
  await installApi(page);
  let requested: string | null = null;
  await page.route((url) => url.pathname === "/lab/decision" && url.searchParams.has("day"), async (route) => {
    requested = new URL(route.request().url()).searchParams.get("day");
    await route.fulfill({ json: null });
  });
  const day = "2026-09-29";
  await page.goto(`/app?date=${day}`);
  await expect.poll(() => requested).toBe(day);
  await expect(page.getByText(`No stored decision is available for ${day}.`)).toBeVisible();
  await expect(page.getByRole("button", { name: "Followed", exact: true })).toHaveCount(0);
});

test("CSV import sends the selected file as multipart to the existing CSV endpoint", async ({ page }) => {
  await installApi(page);
  let contentType = "";
  let body = "";
  await page.route((url) => url.pathname === "/imports/csv", async (route) => {
    contentType = route.request().headers()["content-type"] ?? "";
    body = route.request().postData() ?? "";
    await route.fulfill({ json: { filename: "training.csv", records_seen: 1 } });
  });
  await page.goto("/app/settings?tab=data-health");
  await page.getByLabel("Choose file").setInputFiles({ name: "training.csv", mimeType: "text/csv", buffer: Buffer.from("date,sport\n2026-09-28,cycling\n") });
  await page.getByRole("button", { name: "Import", exact: true }).click();
  await expect.poll(() => contentType).toContain("multipart/form-data");
  expect(body).toContain("training.csv");
  expect(body).toContain("2026-09-28,cycling");
});

test("report markdown renders safe semantic text and escapes raw HTML", async ({ page }) => {
  await installApi(page);
  await page.route((url) => url.pathname === "/lab/reports", (route) => route.fulfill({ json: [{ id: 1, type: "weekly", start: today, end: today, source_policy: "recorded_data", content: "## Recorded summary\n\n**Sleep trend** is descriptive.\n\n- Seven nights\n- <img src=x onerror=alert(1)>" }] }));
  await page.goto("/app/lab?tab=reports");
  await expect(page.getByRole("heading", { name: "Recorded summary" })).toBeVisible();
  await expect(page.locator("strong").getByText("Sleep trend")).toBeVisible();
  await expect(page.getByRole("listitem").filter({ hasText: "Seven nights" })).toBeVisible();
  await expect(page.locator("img")).toHaveCount(0);
  await expect(page.getByText("<img src=x onerror=alert(1)>")).toBeVisible();
});

test("lab document dropzone advertises and enforces the backend 5 MB file contract", async ({ page }) => {
  await installApi(page);
  let uploads = 0;
  let contentType = "";
  let body = "";
  await page.route((url) => url.pathname === "/lab/documents" && url.search === "", async (route) => {
    if (route.request().method() === "POST") {
      uploads += 1;
      contentType = route.request().headers()["content-type"] ?? "";
      body = route.request().postData() ?? "";
      await route.fulfill({ status: 201, json: { id: 4 } });
    } else await route.fulfill({ json: [] });
  });
  await page.goto("/app/lab?tab=documents");
  await expect(page.getByText("TXT · MD · PDF · maximum 5 MB")).toBeVisible();
  await page.getByLabel("Choose file").setInputFiles({ name: "results.txt", mimeType: "text/plain", buffer: Buffer.from("Ferritin: 42") });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect.poll(() => contentType).toContain("multipart/form-data");
  expect(body).toContain("results.txt");
  expect(body).toContain("Ferritin: 42");
  await page.getByLabel("Choose file").setInputFiles({ name: "oversized.pdf", mimeType: "application/pdf", buffer: Buffer.alloc(5 * 1024 * 1024 + 1) });
  await page.getByRole("button", { name: "Upload", exact: true }).click();
  await expect(page.getByText("The file exceeds the 5 MB limit.")).toBeVisible();
  expect(uploads).toBe(1);
});
