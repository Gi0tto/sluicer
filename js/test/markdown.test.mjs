// toMarkdown() with the markdown extra, which micropip installs from PyPI.
// Set SLUICER_JS_OFFLINE=1 to skip it where PyPI cannot be reached.
import assert from "node:assert/strict";
import { before, test } from "node:test";
import { createSluicer } from "../index.js";
import { expected, page } from "./helpers.mjs";

const offline = Boolean(process.env.SLUICER_JS_OFFLINE);
const cases = await expected("markdown");
let sluicer;

before(async () => {
  if (!offline) {
    sluicer = await createSluicer({ markdown: true });
  }
});

for (const native of cases) {
  test(`toMarkdown gives the native markdown: ${native.page}`, { skip: offline }, async () => {
    const markdown = sluicer.toMarkdown(await page(native.page, native.as), {
      url: native.url,
    });

    assert.equal(markdown, native.answer);
  });
}
