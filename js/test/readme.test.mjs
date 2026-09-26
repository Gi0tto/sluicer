// js/README.md is the page npmjs.com shows: its example is run as it is
// written, on the page it names, and must print what the README says. And
// docs/javascript.md's count of the native answers is the count.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readdir, readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";
import { ROOT, expected } from "./helpers.mjs";

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

test("docs/javascript.md counts the native answers the tests hold the package to", async () => {
  // It said 22 pages when there were 22 answers on 19 pages.
  const kinds = await readdir(new URL("js/test/expected/", ROOT));
  const answers = (await Promise.all(kinds.map((kind) => expected(kind)))).flat();
  const pages = new Set(answers.flatMap((a) => [a.page, ...(a.pages ?? []).map((p) => p.page)]));
  pages.delete(undefined);
  const guide = await readFile(new URL("docs/javascript.md", ROOT), "utf8");

  assert.match(
    guide.replace(/\s+/g, " "),
    new RegExp(`in ${answers.length} cases on ${pages.size} pages`),
  );
});
