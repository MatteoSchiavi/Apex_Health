/**
 * Apex Health — Gear DB helpers (plan §6).
 *
 * The `defaultFor` column on the Gear table is read/written via raw SQL
 * because the running dev server's cached Prisma client was created before
 * the column was added to the schema (server restart is out of scope for
 * this task). Raw SQL bypasses the engine's schema validation, so the column
 * is accessible until the dev server is restarted with the regenerated
 * client. After a restart, all of this can be replaced with the standard
 * typed Prisma access (the column is already in `prisma/schema.prisma`).
 */

import { db } from "@/lib/db";

/** Set defaultFor for a single gear row (JSON-encoded string). */
export async function setDefaultFor(gearId: number, value: string): Promise<void> {
  await db.$executeRawUnsafe(
    `UPDATE Gear SET defaultFor = ?, updatedAt = ? WHERE id = ?`,
    value,
    new Date().toISOString(),
    gearId,
  );
}

/** Read defaultFor for many gear ids at once. Returns a map id → string. */
export async function readDefaultForMany(ids: number[]): Promise<Map<number, string>> {
  const out = new Map<number, string>();
  if (ids.length === 0) return out;
  // SQLite parameter placeholders are 1-indexed; build a comma list of ?
  const placeholders = ids.map(() => "?").join(",");
  const sql = `SELECT id, defaultFor FROM Gear WHERE id IN (${placeholders})`;
  const rows = (await db.$queryRawUnsafe(sql, ...ids)) as Array<{
    id: number;
    defaultFor: string;
  }>;
  for (const r of rows) {
    out.set(r.id, r.defaultFor ?? "[]");
  }
  return out;
}

/** Parse the JSON-encoded defaultFor column into a discipline array. */
export function parseDefaultFor(raw: string | null | undefined): string[] {
  if (!raw) return [];
  try {
    const v = JSON.parse(raw);
    if (Array.isArray(v) && v.every((x) => typeof x === "string")) return v;
  } catch {
    /* ignore */
  }
  return [];
}

/** Serialize a discipline array back into the JSON-encoded column shape. */
export function serializeDefaultFor(list: string[]): string {
  return JSON.stringify(Array.isArray(list) ? list : []);
}
