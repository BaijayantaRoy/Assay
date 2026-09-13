import { readFileSync } from "node:fs";
import Ajv2020Module, { type ErrorObject, type ValidateFunction } from "ajv/dist/2020.js";
import { parseDocument, stringify } from "yaml";

export type PromptFileFormat = "md" | "yaml" | "json";
export type PromptFileData = Record<string, unknown>;

export interface PromptFileDocument {
  data: PromptFileData;
  body: string;
  sourceFormat: PromptFileFormat;
}

export type PromptFileErrorCode = "parse" | "validation" | "unsupported_version" | "too_large";

export class PromptFileError extends Error {
  constructor(
    message: string,
    readonly code: PromptFileErrorCode,
    readonly details: string[] = [],
  ) {
    super(message);
    this.name = "PromptFileError";
  }
}

const MAX_SOURCE_BYTES = 10 * 1024 * 1024;
const schema = JSON.parse(readFileSync(
  new URL("../schema/promptfile-v1.schema.json", import.meta.url),
  "utf8",
)) as object;
const Ajv2020 = Ajv2020Module as unknown as new (options?: object) => {
  compile(schema: object): ValidateFunction;
};
const ajv = new Ajv2020({ allErrors: true, strict: false, validateFormats: false });
const validateSchema: ValidateFunction = ajv.compile(schema);

function asMapping(value: unknown, context: string): PromptFileData {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    throw new PromptFileError(`${context} must be a mapping`, "parse");
  }
  return value as PromptFileData;
}

function parseYaml(source: string, context: string): PromptFileData {
  const document = parseDocument(source, {
    prettyErrors: true,
    uniqueKeys: true,
  });
  if (document.errors.length) {
    throw new PromptFileError(
      `Invalid ${context}: ${document.errors[0]?.message ?? "YAML error"}`,
      "parse",
      document.errors.map((error) => error.message),
    );
  }
  return asMapping(document.toJS({ maxAliasCount: 100 }), context);
}

function parseMarkdown(source: string): { data: PromptFileData; body: string } {
  const withoutBom = source.replace(/^\uFEFF/, "");
  const match = /^---\s*\r?\n([\s\S]*?)\r?\n---\s*(?:\r?\n([\s\S]*))?$/.exec(withoutBom);
  if (!match) {
    throw new PromptFileError(
      "Missing YAML frontmatter; a .prompt.md file must start with ---",
      "parse",
    );
  }
  return {
    data: parseYaml(match[1] ?? "", "frontmatter"),
    body: (match[2] ?? "").replace(/^(?:\r?\n)+|(?:\r?\n)+$/g, ""),
  };
}

function assertSupportedVersion(data: PromptFileData): void {
  const version = data.promptfile;
  if (version !== 1) {
    throw new PromptFileError(
      `This reader implements PromptFile v1; file declares ${String(version)}`,
      "unsupported_version",
    );
  }
}

export function validatePromptFile(document: PromptFileDocument): void {
  const value = { ...document.data, ...(document.body ? { body: document.body } : {}) };
  if (validateSchema(value)) return;
  const details = (validateSchema.errors ?? []).map(formatValidationError);
  throw new PromptFileError(
    `PromptFile validation failed: ${details[0] ?? "unknown schema error"}`,
    "validation",
    details,
  );
}

function formatValidationError(error: ErrorObject): string {
  return `${error.instancePath || "/"} ${error.message ?? "is invalid"}`;
}

export function parsePromptFile(
  source: string,
  format?: PromptFileFormat,
): PromptFileDocument {
  if (Buffer.byteLength(source, "utf8") > MAX_SOURCE_BYTES) {
    throw new PromptFileError("PromptFile exceeds the 10 MiB reader limit", "too_large");
  }
  const detected = format ?? sniffFormat(source);
  let data: PromptFileData;
  let body = "";
  if (detected === "md") {
    ({ data, body } = parseMarkdown(source));
  } else if (detected === "json") {
    let value: unknown;
    try {
      value = JSON.parse(source);
    } catch (error) {
      throw new PromptFileError(`Invalid JSON: ${(error as Error).message}`, "parse");
    }
    data = asMapping(value, "JSON document");
    body = typeof data.body === "string" ? data.body : "";
    delete data.body;
  } else {
    data = parseYaml(source, "YAML document");
    body = typeof data.body === "string" ? data.body : "";
    delete data.body;
  }
  assertSupportedVersion(data);
  const document = { data, body, sourceFormat: detected } satisfies PromptFileDocument;
  validatePromptFile(document);
  return document;
}

export function serializePromptFile(
  document: PromptFileDocument,
  format: PromptFileFormat = document.sourceFormat,
): string {
  assertSupportedVersion(document.data);
  validatePromptFile(document);
  if (format === "json") {
    return JSON.stringify(
      { ...document.data, ...(document.body ? { body: document.body } : {}) },
      null,
      2,
    ) + "\n";
  }
  if (format === "yaml") {
    return stringify(
      { ...document.data, ...(document.body ? { body: document.body } : {}) },
      { lineWidth: 100 },
    );
  }
  const frontmatter = stringify(document.data, { lineWidth: 100 });
  return document.body
    ? `---\n${frontmatter}---\n\n${document.body}\n`
    : `---\n${frontmatter}---\n`;
}

export function sniffFormat(source: string): PromptFileFormat {
  const stripped = source.replace(/^\uFEFF/, "").trimStart();
  if (stripped.startsWith("{")) return "json";
  if (stripped.startsWith("---")) return "md";
  return "yaml";
}
