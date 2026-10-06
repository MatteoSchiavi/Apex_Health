import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("COROS MCP shows setup guidance when the server is not configured", async ({
  page,
}) => {
  await installApi(page);
  const requestedPaths: string[] = [];
  page.on("request", (request) => {
    requestedPaths.push(new URL(request.url()).pathname);
  });
  await page.route(
    "**/settings/integrations/coros/mcp/status",
    (route) => route.fulfill({ json: { configured: false } }),
  );
  await page.goto("/app/settings?tab=devices");

  const corosRow = page.getByText("COROS · MCP", { exact: true }).locator(
    "xpath=../../..",
  );
  await corosRow.getByRole("button", { name: "Connect" }).click();
  await expect(
    page.getByText(/administrator must first configure the MCP URL/i),
  ).toBeVisible();
  await expect(page.getByLabel("Your MCP access token")).toHaveCount(0);
  expect(
    requestedPaths.some((path) => path === "/settings/integrations/coros/authorize"),
  ).toBe(false);
});

test("COROS MCP submits the account token without an OAuth authorize request", async ({
  page,
}) => {
  await installApi(page);
  const requestedPaths: string[] = [];
  let submitted: { access_token?: string } | undefined;
  page.on("request", (request) => {
    requestedPaths.push(new URL(request.url()).pathname);
  });
  await page.route(
    "**/settings/integrations/coros/mcp/status",
    (route) => route.fulfill({ json: { configured: true } }),
  );
  await page.route(
    "**/settings/integrations/coros/mcp/connect",
    async (route) => {
      submitted = route.request().postDataJSON() as { access_token?: string };
      await route.fulfill({ json: { connected: true } });
    },
  );
  await page.goto("/app/settings?tab=devices");

  const corosRow = page.getByText("COROS · MCP", { exact: true }).locator(
    "xpath=../../..",
  );
  await corosRow.getByRole("button", { name: "Connect" }).click();
  const token = page.getByLabel("Your MCP access token");
  await expect(token).toBeVisible();
  await token.fill("account-specific-mcp-token");
  await page.getByRole("button", { name: "Connect" }).last().click();

  await expect
    .poll(() => submitted?.access_token)
    .toBe("account-specific-mcp-token");
  expect(
    requestedPaths.some((path) => path === "/settings/integrations/coros/authorize"),
  ).toBe(false);
  expect(
    requestedPaths.includes("/settings/integrations/coros/mcp/status"),
  ).toBe(true);
  expect(
    requestedPaths.includes("/settings/integrations/coros/mcp/connect"),
  ).toBe(true);
});
