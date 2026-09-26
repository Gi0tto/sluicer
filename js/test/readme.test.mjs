// js/README.md is the page npmjs.com shows: its example is run as it is
// written, on the page it names, and must print what the README says.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ROOT } from "./helpers.mjs";

const readme = await readFile(new URL("js/README.md", ROOT), "utf8");
const [, code] = readme.match(/```js\n([\s\S]*?)```/);
const [, printed] = readme.match(/prints\n\n```text\n([\s\S]*?)```/);

test("the README's example prints what the README says", () => {
  const run = code
    .replace('from "sluicer"', `from ${JSON.stringify(new URL("js/index.js", ROOT).href)}`)
    .replace('"brake-pads.html"', JSON.stringify(fileURLToPath(new URL("examples/brake-pads.html", ROOT))));
  assert.notEqual(run, code);
  const output = execFileSync(process.execPath, ["--input-type=module", "-e", run], {
    encoding: "utf8",
  });

  assert.equal(output, printed);
});

test("the README's example is five lines", () => {
  assert.equal(code.trim().split("\n").length, 5);
});
