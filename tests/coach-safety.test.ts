import { expect, test } from "bun:test";
import { spawnSync } from "node:child_process";

test("coach failure and draft regressions with isolated provider fixtures", () => {
  const result = spawnSync(process.execPath, ["test", "./tests/fixtures/coach-safety.integration.ts"], { env: process.env, encoding: "utf8" });
  expect(result.status, result.stdout + result.stderr).toBe(0);
}, 15_000);
