#!/usr/bin/env node
/**
 * Generates TypeScript types from contracts/schemas/*.json
 * Output: src/types/contracts.ts
 *
 * Run: node scripts/gen-types.mjs
 */

import { compileFromFile } from "json-schema-to-typescript";
import { writeFileSync, mkdirSync, readdirSync } from "fs";
import { resolve, join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(__dirname, "..");
const SCHEMAS_DIR = resolve(ROOT, "..", "contracts", "schemas");
const OUT_FILE = resolve(ROOT, "src", "types", "contracts.ts");

mkdirSync(dirname(OUT_FILE), { recursive: true });

const schemaFiles = readdirSync(SCHEMAS_DIR).filter((f) => f.endsWith(".json"));

const bannerLines = [
  "// AUTO-GENERATED — do not edit manually",
  "// Source: contracts/schemas/*.json",
  `// Generated: ${new Date().toISOString()}`,
  "",
];

const parts = [...bannerLines];

for (const file of schemaFiles) {
  const ts = await compileFromFile(join(SCHEMAS_DIR, file), {
    bannerComment: "",
    style: { singleQuote: true, semi: true },
    unknownAny: false,
  });
  parts.push(ts);
}

writeFileSync(OUT_FILE, parts.join("\n"));
console.log(`✓ Generated ${OUT_FILE}`);
