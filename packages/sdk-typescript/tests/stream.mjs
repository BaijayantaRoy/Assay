import assert from "node:assert/strict";
import { Assay } from "../dist/index.js";

const encoder = new TextEncoder();
let observed;
const fetch = async (url, init) => {
  observed = { url, init };
  const body = new ReadableStream({
    start(controller) {
      controller.enqueue(encoder.encode('data: {"type":"delta","index":0,"delta":"Hello ","buffered":false}\n\n'));
      controller.enqueue(encoder.encode('data: {"type":"tool_call_delta","index":1,"delta":"","tool_call":{"index":0,"id":"call-1","name":"lookup","arguments":"{\\"id\\":"},"buffered":false}\n\n'));
      controller.enqueue(encoder.encode('data: {"type":"delta","index":2,"delta":"Ada","buffered":false}\n\n'));
      controller.enqueue(encoder.encode('data: {"type":"completed","index":3,"delta":"","buffered":false,"result":{"run_id":"run-1","streaming":{"mode":"native"}}}\n\n'));
      controller.enqueue(encoder.encode("data: [DONE]\n\n"));
      controller.close();
    },
  });
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
};

const client = new Assay({ baseUrl: "http://assay.test", fetch });
const events = [];
for await (const event of client.stream("sdk/greet", { name: "Ada" })) events.push(event);

assert.equal(observed.url, "http://assay.test/v1/prompts/sdk/greet/stream");
assert.equal(observed.init.method, "POST");
assert.deepEqual(JSON.parse(observed.init.body).variables, { name: "Ada" });
assert.equal(events.map((event) => event.delta).join(""), "Hello Ada");
assert.equal(events.at(-1).type, "completed");
assert.equal(events[1].type, "tool_call_delta");
assert.equal(events[1].toolCall.name, "lookup");
assert.equal(events[1].toolCall.arguments, '{"id":');
assert.equal(events.at(-1).result.runId, "run-1");
assert.equal(events.at(-1).result.streaming.mode, "native");

process.stdout.write("TypeScript streaming contract passed\n");
