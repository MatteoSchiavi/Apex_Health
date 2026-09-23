#!/usr/bin/env node
/**
 * i18n completeness check — CI-grade hygiene for the two-locale law:
 *  1. en.json and it.json expose EXACTLY the same key sets (both directions).
 *  2. Placeholder parity: every {{var}} used in one locale exists in the other.
 *
 * Exit 1 on any violation. Run: npm run check:i18n
 */
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const flat = (obj, prefix = "") =>
  Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null ? flat(v, `${prefix}${k}.`) : [`${prefix}${k}`],
  );

const en = JSON.parse(readFileSync(join(root, "src/locales/en.json"), "utf8"));
const it = JSON.parse(readFileSync(join(root, "src/locales/it.json"), "utf8"));
const enKeys = new Set(flat(en));
const itKeys = new Set(flat(it));

let failed = false;
for (const k of enKeys) if (!itKeys.has(k)) { console.error(`MISSING in it.json: ${k}`); failed = true; }
for (const k of itKeys) if (!enKeys.has(k)) { console.error(`MISSING in en.json: ${k}`); failed = true; }

// Placeholder parity
const ph = (s) => new Set(String(s).match(/\{\{\s*\w+\s*\}\}/g) ?? []);
for (const key of enKeys) {
  if (!itKeys.has(key)) continue;
  const get = (obj) => key.split(".").reduce((o, k) => (o ? o[k] : undefined), obj);
  const a = ph(get(en)), b = ph(get(it));
  for (const p of a) if (!b.has(p)) { console.error(`PLACEHOLDER ${p} missing in it.json: ${key}`); failed = true; }
  for (const p of b) if (!a.has(p)) { console.error(`PLACEHOLDER ${p} missing in en.json: ${key}`); failed = true; }
}

if (failed) process.exit(1);
console.log(`i18n OK — ${enKeys.size} keys, en/it in parity`);
