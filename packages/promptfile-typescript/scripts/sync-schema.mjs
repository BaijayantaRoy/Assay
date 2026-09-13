import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const source = resolve(here, "../../../spec/schemas/promptfile-v1.schema.json");
const target = resolve(here, "../schema/promptfile-v1.schema.json");
const expected = await readFile(source);
const check = process.argv.includes("--check");
let actual;
try {
  actual = await readFile(target);
} catch (error) {
  if (error.code !== "ENOENT") throw error;
}

if (actual?.equals(expected)) {
  process.stdout.write("TypeScript PromptFile schema matches the canonical spec\n");
} else if (check) {
  process.stderr.write("TypeScript PromptFile schema is missing or stale\n");
  process.exitCode = 1;
} else {
  await mkdir(dirname(target), { recursive: true });
  await writeFile(target, expected);
  process.stdout.write("Copied canonical PromptFile v1 schema\n");
}
