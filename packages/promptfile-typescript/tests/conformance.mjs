import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { parsePromptFile, serializePromptFile, PromptFileError } from "../dist/index.js";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "../../../spec/conformance");
const manifest = JSON.parse(await readFile(resolve(root, "manifest.json"), "utf8"));

const atPath = (value, path) => path.split(".").reduce((current, part) => {
  if (Array.isArray(current) && /^\d+$/.test(part)) return current[Number(part)];
  return current?.[part];
}, value);

for (const fixture of manifest.valid) {
  const source = await readFile(resolve(root, fixture.file), "utf8");
  const parsed = parsePromptFile(source, fixture.format);
  assert.equal(parsed.data.id, fixture.id);
  assert.ok(parsed.body.includes(fixture.body_contains));
  for (const [path, expected] of Object.entries(fixture.unknown)) {
    assert.deepEqual(atPath(parsed.data, path), expected, `${fixture.file}: ${path}`);
  }
  const serialized = serializePromptFile(parsed, fixture.format);
  const reparsed = parsePromptFile(serialized, fixture.format);
  assert.deepEqual(reparsed, parsed, `${fixture.file}: semantic round trip`);
  assert.equal(
    serializePromptFile(reparsed, fixture.format),
    serialized,
    `${fixture.file}: writer fixed point`,
  );
}

for (const fixture of manifest.invalid) {
  const source = await readFile(resolve(root, fixture.file), "utf8");
  assert.throws(
    () => parsePromptFile(source, fixture.format),
    (error) => error instanceof PromptFileError && error.code === fixture.error,
    `${fixture.file}: expected ${fixture.error}`,
  );
}

process.stdout.write(
  `PromptFile TypeScript conformance: ${manifest.valid.length} valid, ${manifest.invalid.length} invalid\n`,
);
