# `@assay/promptfile`

An independent Node.js/TypeScript reader and writer for PromptFile v1. It does not call
`assay-core` or a REST service: YAML/JSON/frontmatter parsing, major-version refusal,
Draft 2020-12 schema validation, unknown-field preservation, and serialization are
implemented in TypeScript.

```ts
import { parsePromptFile, serializePromptFile } from "@assay/promptfile";

const prompt = parsePromptFile(source, "md");
prompt.data["x-my-tool"] = { reviewed: true };
const updated = serializePromptFile(prompt);
```

The package caps source input at 10 MiB, rejects duplicate YAML keys and excessive aliases,
and refuses unsupported spec majors. `npm test` runs the shared cross-language conformance
corpus and proves semantic round trips plus a stable writer fixed point. “Lossless” means
unknown values survive; it does not promise byte-for-byte preservation of comments or YAML
styling.
