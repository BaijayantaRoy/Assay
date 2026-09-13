# assay — TypeScript SDK

Zero dependencies. Uses the platform `fetch`, so it runs in Node 18+, Deno, Bun, Cloudflare
Workers, Vercel Edge and the browser with no bundler shim.

```bash
npm install @assay/sdk
```

```ts
import { Assay } from "assay";

const assay = new Assay({ baseUrl: "http://127.0.0.1:8001" });

const result = await assay.run("support/refund-triage", { message: "refund please" });
console.log(result.output, result.costUsd, result.usage.totalTokens);
```

Snake_case from the API is converted to camelCase, so it reads like a native TypeScript
library rather than a transport layer.

## API

```ts
assay.list({ prefix, tag, status })        // Promise<PromptRef[]>
assay.get(id, version?)                    // full source + parsed document
assay.render(id, variables, model?)        // no model call
assay.run(id, variables, { model, params })// Promise<RunResult>
assay.stream(id, variables, { model, params }) // AsyncGenerator<StreamEvent>
assay.evaluate(id, { model, maxWorkers: 4 })   // Promise<EvalReport>
assay.create(id, body, fields)
assay.update(id, changes)
assay.models(provider?)
assay.health()
```

```ts
for await (const event of assay.stream("support/refund-triage", { message: "refund" })) {
  if (event.type === "delta") process.stdout.write(event.delta);
  else if (event.type === "tool_call_delta") console.log(event.toolCall);
  else console.log(event.result?.streaming);
}
```

A stream may carry portable tool-call fragments as well as text. It can be intentionally
buffered when output controls need the complete answer. `buffered` and the final streaming
evidence make that distinction explicit.

Everything is fully typed. Failures throw `AssayError` carrying `status` and the server's
structured `detail`.

```ts
const report = await assay.evaluate("support/refund-triage");
if (!report.passed) throw new Error(`${report.failedAssertions} assertions failed`);
```

## Configuration

```ts
new Assay({
  baseUrl: "https://prompts.acme.internal",
  apiKey: process.env.ASSAY_API_KEY,
  timeoutMs: 60_000,
  fetch: myInstrumentedFetch,   // bring your own for retries, proxying or tracing
});
```

## License

MIT
