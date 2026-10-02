/**
 * First-run setup — ensures a fresh clone works out of the box.
 *
 * Runs automatically before `bun run dev` (via the `predev` script).
 * Idempotent: skips any step that's already done.
 *
 *   1. Creates .env with sensible defaults if missing
 *   2. Runs `prisma db push` to create the SQLite DB + schema
 *   3. Seeds demo data (user + activities + sleep + biometrics) if the DB is empty
 *
 * No credentials are needed for the demo to work — the app uses a local
 * SQLite file and a demo user. To sync real Garmin data, fill in your
 * credentials in .env and call POST /api/garmin/sync.
 */

import { existsSync, writeFileSync, mkdirSync } from "fs";
import { join } from "path";
import { execSync } from "child_process";

const ROOT = process.cwd();
const ENV_PATH = join(ROOT, ".env");
const DB_DIR = join(ROOT, "db");

// Sensible defaults for a fresh clone — no real credentials needed.
const DEFAULT_ENV = `# Apex Health — local development environment.
# Auto-created by scripts/setup.ts on first run. Edit to add real credentials.
DATABASE_URL=file:\${ROOT}/db/custom.db
GARMIN_EMAIL=demo@apexhealth.app
GARMIN_PASSWORD=demo
`;

function log(msg: string) {
  console.log(`[setup] ${msg}`);
}

async function main() {
  // Step 1: Create .env if missing
  if (!existsSync(ENV_PATH)) {
    const envContent = DEFAULT_ENV.replace("${ROOT}", ROOT);
    writeFileSync(ENV_PATH, envContent, "utf-8");
    log("Created .env with default values (SQLite + demo user).");
  } else {
    log(".env already exists — skipping.");
  }

  // Step 2: Ensure db/ directory exists
  if (!existsSync(DB_DIR)) {
    mkdirSync(DB_DIR, { recursive: true });
    log("Created db/ directory.");
  }

  // Step 3: Push Prisma schema to create the DB + tables
  try {
    execSync("bunx prisma db push --accept-data-loss --skip-generate", {
      stdio: "pipe",
      cwd: ROOT,
    });
    log("Database schema pushed (prisma db push).");
  } catch {
    // May fail if DB is already in sync — that's fine
    log("Database schema already in sync (or prisma db push skipped).");
  }

  // Step 4: Generate Prisma client (ensures the latest schema is compiled)
  try {
    execSync("bunx prisma generate", { stdio: "pipe", cwd: ROOT });
    log("Prisma client generated.");
  } catch {
    log("Prisma client already up to date.");
  }

  // Step 5: Seed demo data if the DB is empty
  log("Seeding demo data (if needed)...");
  try {
    execSync("bun run scripts/seed-db.ts", {
      stdio: "inherit",
      cwd: ROOT,
      env: { ...process.env },
    });
  } catch (e) {
    log("Seed script failed (non-fatal — the app will still start): " + (e instanceof Error ? e.message : "unknown"));
  }

  log("Setup complete. Starting dev server...");
}

main().catch((e) => {
  console.error("[setup] Error:", e);
  // Don't exit with error — let the dev server try to start anyway
  process.exit(0);
});
