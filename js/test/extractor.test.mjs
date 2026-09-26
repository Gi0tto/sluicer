// compile() and run() in Pyodide learn and replay what the native package does.
import assert from "node:assert/strict";
import { before, test } from "node:test";
import { SluicerError, createSluicer } from "../index.js";
import { expected, page } from "./helpers.mjs";

const cases = await expected("extractor");
const compiled = cases.find((c) => c.name === "compiled");
const written = await expected("written");
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

async function pagesOf(native) {
  return Promise.all(
    native.pages.map(async (p) => ({ html: await page(p.page), url: p.url })),
  );
}

test("compile with examples and names learns what Python learns", async () => {
  const native = cases.find((c) => c.name === "compiled-want");

  assert.deepEqual(sluicer.compile(await pagesOf(native), native.options), native.answer);
});

// select and rows are passed on to Python's compile_extractor, as want is:
// before, compile ignored them and learnt a listing of its own choosing.
for (const name of ["compiled", "compiled-from-no-page"]) {
  test(`compile with selectors writes what Python writes: ${name}`, async () => {
    const native = written.find((c) => c.name === name);
    const extractor = sluicer.compile(await pagesOf(native), native.options);

    assert.deepEqual(extractor, native.answer);
    assert.ok(extractor.select, "no select in the extractor");
  });
}

for (const native of written.filter((c) => c.name.startsWith("run-"))) {
  test(`an extractor written by selectors replays as Python's: ${native.name}`, async () => {
    const from = written.find(
      (c) => c.name === (native.name === "run-from-no-page" ? "compiled-from-no-page" : "compiled"),
    );
    const run = sluicer.run(from.answer, await page(native.page), { url: native.url });

    assert.deepEqual(run, native.answer);
  });
}

test("selectors with examples is refused, as in Python", () => {
  assert.throws(
    () => sluicer.compile([{ html: "<h1>x</h1>" }], { select: { a: "h1" }, want: { a: "x" } }),
    (error) => error instanceof SluicerError && error.type === "ValueError",
  );
});
