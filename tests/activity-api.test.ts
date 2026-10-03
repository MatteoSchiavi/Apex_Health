import { expect, test } from "bun:test";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

// A child process keeps these real SQLite regressions isolated from provider module mocks.
test("activity API against a disposable SQLite database", () => {
  const directory = mkdtempSync(join(tmpdir(), "apex-activities-"));
  const file = join(directory, "test.db");
  writeFileSync(file, "");
  const env = { ...process.env, DATABASE_URL: `file:${file}`, GARMIN_EMAIL: "owner@activity.invalid" };
  try {
    execFileSync(process.execPath, ["node_modules/prisma/build/index.js", "db", "push", "--skip-generate"], { env, stdio: "pipe" });
    const result = spawnSync(process.execPath, ["test", "./tests/fixtures/activity-api.integration.ts"], { env, encoding: "utf8" });
    expect(result.status, result.stdout + result.stderr).toBe(0);
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}, 30_000);
