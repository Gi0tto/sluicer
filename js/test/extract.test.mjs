// extract() in Pyodide gives the native package's answer, field for field.
import assert from "node:assert/strict";
import { before, describe, test } from "node:test";
import { createSluicer } from "../index.js";
import { expected, page } from "./helpers.mjs";

const cases = await expected("extract");
let sluicer;

before(async () => {
  sluicer = await createSluicer();
});

describe("the brake-pads example", () => {
  test("gives the summary the Python package gives", async () => {
    const native = cases.find((c) => c.name === "brake-pads");
    const found = sluicer.extract(await page(native.page), { url: native.url });

    assert.deepEqual(found.summary, native.answer.summary);
    assert.deepEqual(found.summary.price, {
      value: "41.90",
      source: "jsonld",
      key: "Product.offers.price",
      where: "/html/head/script[1]#/offers/price",
    });
  });

  test("reports its two prices as a conflict, the summary's first", async () => {
    const found = sluicer.extract(await page("examples/brake-pads.html"));

    assert.deepEqual(
      found.conflicts.map((c) => [c.question, c.answers.map((a) => a.value)]),
      [["price", ["41.90", "39.90"]]],
    );
  });

  test("has every field of Python's Extraction", async () => {
    const found = sluicer.extract(await page("examples/brake-pads.html"));

    assert.deepEqual(Object.keys(found), [
      "url",
      "summary",
      "normalised",
      "conflicts",
      "records",
      "sources",
      "links",
      "rights",
      "visible",
    ]);
  });
});

describe("every page gives the native answer whole", () => {
  for (const native of cases) {
    test(`${native.name} (${native.page}, as ${native.as})`, async () => {
      const found = sluicer.extract(await page(native.page, native.as), {
        url: native.url ?? undefined,
        ...native.options,
      });

      assert.deepEqual(found, native.answer);
    });
  }
});

test("every reader is held to a native answer", () => {
  const read = new Set(cases.flatMap((c) => c.answer.sources));

  // microformats is the one reader behind an extra; the JS package does not
  // offer it.
  for (const reader of [
    "jsonld",
    "microdata",
    "rdfa",
    "dublincore",
    "opengraph",
    "twitter",
    "html",
    "induced",
  ]) {
    assert.ok(read.has(reader), reader);
  }
});
