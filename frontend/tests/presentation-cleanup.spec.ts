import { expect, test } from "@playwright/test";
import { installApi } from "./fixtures";

test("sleep durations use clock-style hours and minutes", async ({ page }) => {
  await installApi(page);
  await page.goto("/app/sleep");
  await expect(page.locator("tbody tr").first()).toContainText("7:30 h");
});

test("native select options use the active theme's readable colors", async ({
  page,
}) => {
  await installApi(page);
  await page.goto("/app/lab");
  const colors = await page.locator("select").first().evaluate((select) => {
    const option = select.querySelector("option");
    return {
      selectColor: getComputedStyle(select).color,
      optionColor: option ? getComputedStyle(option).color : "",
      optionBackground: option ? getComputedStyle(option).backgroundColor : "",
    };
  });
  expect(colors).toEqual({
    selectColor: "rgb(36, 36, 32)",
    optionColor: "rgb(36, 36, 32)",
    optionBackground: "rgb(255, 254, 250)",
  });
});
