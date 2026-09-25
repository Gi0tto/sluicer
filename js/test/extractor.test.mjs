// compile() and run() in Pyodide learn and replay what the native package does.
import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createSluicer } from "../index.js";
import { expected, page } from "./helpers.mjs";

const cases = await expected("extractor");
const compiled = cases.find((c) => c.name === "compiled");
let sluicer;

before(async () => {
  sluicer = await createSluicer();
});

async function learnt() {
  return sluicer.compile(
    await Promise.all(
      compiled.pages.map(async (p) => ({ html: await page(p.page), url: p.url })),
    ),
  );
}

test("compile learns the extractor the Python package learns", async () => {
  assert.deepEqual(await learnt(), compiled.answer);
});

for (const native of cases.filter((c) => c.name.startsWith("run-"))) {
  test(`run replays it as Python does: ${native.page}`, async () => {
    const run = sluicer.run(compiled.answer, await page(native.page), {
      url: native.url,
    });

    assert.deepEqual(run, native.answer);
  });
}

test("a page that drifted is a run that failed, and says which check", async () => {
  const run = sluicer.run(
    await learnt(),
    await page("tests/fixtures/drift/shop_prices_gone.html"),
  );

  assert.equal(run.ok, false);
  assert.ok(run.checks.some((check) => !check.ok));
});

test("the extractor's file, as text, replays the same", async () => {
  const extractor = await learnt();
  const html = await page("tests/fixtures/drift/shop_v1.html");

  assert.deepEqual(
    sluicer.run(JSON.stringify(extractor), html),
    sluicer.run(extractor, html),
  );
});
