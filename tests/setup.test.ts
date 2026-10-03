import { afterEach, describe, expect, test } from "bun:test";
import { mkdtempSync, mkdirSync, writeFileSync, readFileSync, existsSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import { spawnSync } from "node:child_process";

const setup = resolve("scripts/setup.ts");
const dirs: string[] = [];
afterEach(() => { for (const dir of dirs.splice(0)) rmSync(dir, { recursive: true, force: true }); });

function runSetup(fail: "generate" | "push" | "seed" | null) {
  const dir = mkdtempSync(join(tmpdir(), "apex-setup-"));
  dirs.push(dir);
  const bin = join(dir, "bin");
  mkdirSync(bin);
  const commands = join(dir, "commands");
  const seeded = join(dir, "seeded");
  writeFileSync(join(bin, "bunx"), '#!/bin/sh\nprintf "%s\\n" "$*" >> "$APEX_TEST_COMMANDS"\nif [ "$APEX_TEST_FAIL" = "generate" ] && [ "$2" = "generate" ]; then echo "engine generation failed" >&2; exit 42; fi\nif [ "$APEX_TEST_FAIL" = "push" ] && [ "$2" = "db" ]; then echo "schema change would drop data" >&2; exit 43; fi\n', { mode: 0o755 });
  writeFileSync(join(bin, "bun"), '#!/bin/sh\nif [ "$APEX_TEST_FAIL" = "seed" ]; then echo "seed failed" >&2; exit 44; fi\ntouch "$APEX_TEST_SEEDED"\n', { mode: 0o755 });
  const result = spawnSync(process.execPath, [setup], {
    cwd: dir,
    encoding: "utf8",
    env: { ...process.env, PATH: `${bin}:${process.env.PATH}`, APEX_TEST_COMMANDS: commands, APEX_TEST_SEEDED: seeded, APEX_TEST_FAIL: fail ?? "" },
  });
  return { result, commands: readFileSync(commands, "utf8"), seeded: existsSync(seeded) };
}

describe("setup stops on failures before starting the app", () => {
  test("a dangerous schema change is not auto-approved or seeded", () => {
    const { result, commands, seeded } = runSetup("push");
    expect(result.status).toBe(1);
    expect(commands).not.toContain("--accept-data-loss");
    expect(seeded).toBe(false);
    expect(result.stderr).toContain("schema change would drop data");
    expect(result.stdout).not.toContain("Setup complete");
  });
  test("engine generation failure stops schema push", () => {
    const { result, commands, seeded } = runSetup("generate");
    expect(result.status).toBe(1);
    expect(commands).not.toContain("db push");
    expect(seeded).toBe(false);
  });
  test("seed failure fails startup", () => {
    expect(runSetup("seed").result.status).toBe(1);
  });
  test("successful setup generates before pushing and then seeds", () => {
    const { result, commands, seeded } = runSetup(null);
    expect(result.status).toBe(0);
    expect(commands).toBe("prisma generate\nprisma db push --skip-generate\n");
    expect(seeded).toBe(true);
  });
});
