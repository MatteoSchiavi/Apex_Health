/**
 * First-run setup — ensures a fresh clone works out of the box.
 *
 * Runs automatically before `bun run dev`. Fails if any required step fails.
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
import { execFileSync } from "child_process";

const ROOT = process.cwd();
const ENV_PATH = join(ROOT, ".env");
const DB_DIR = join(ROOT, "db");

// Sensible defaults for a fresh clone — no real credentials needed.
const DEFAULT_ENV = `# Apex Health — local development environment.
# Auto-created by scripts/setup.ts on first run. Edit to add real credentials.
DATABASE_URL=file:\${ROOT}/db/custom.db
APEX_DEMO_MODE=true
GARMIN_EMAIL=demo@apexhealth.app
GARMIN_PASSWORD=demo
`;

function log(msg: string) {
  console.log(`[setup] ${msg}`);
}

async function main() {
  // Step 1: Create .env if missing
  const createdEnv = !existsSync(ENV_PATH);
  if (createdEnv) {
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
  // Prisma 6's SQLite engine can fail with an empty "Schema engine error"
  // when the default file is absent. Initialize only our new demo database;
  // never overwrite an existing file or an externally configured database.
  const demoDbPath = join(DB_DIR, "custom.db");
  if (createdEnv && !existsSync(demoDbPath)) {
    writeFileSync(demoDbPath, "", { flag: "wx", mode: 0o600 });
  }

  // Generate before schema push so a fresh install has the required engines.
  execFileSync("bunx", ["prisma", "generate"], { stdio: "inherit", cwd: ROOT });
  log("Prisma client generated.");

  // Never approve data loss automatically. A destructive schema change must
  // stop startup and surface Prisma's diagnostic before any seeding occurs.
  execFileSync("bunx", ["prisma", "db", "push", "--skip-generate"], {
    stdio: "inherit",
    cwd: ROOT,
  });
  log("Database schema is ready.");

  // Step 5: Seed demo data if the DB is empty
  log("Seeding demo data (if needed)...");
  execFileSync("bun", ["run", "scripts/seed-db.ts"], {
    stdio: "inherit",
    cwd: ROOT,
    env: { ...process.env },
  });

  log("Setup complete. Starting dev server...");
}

main().catch((e) => {
  console.error("[setup] Setup failed. Resolve the error above before starting the app.");
  console.error(e instanceof Error ? e.message : "Unknown setup error");
  process.exit(1);
});
