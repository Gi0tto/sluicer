// What the package promises beyond the answers: its version, its errors, its
// inputs.
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { before, test } from "node:test";
import { SluicerError, createSluicer } from "../index.js";

const packageJson = JSON.parse(
  await readFile(new URL("../package.json", import.meta.url), "utf8"),
);
const wheel = JSON.parse(
  await readFile(new URL("../python/wheel.json", import.meta.url), "utf8"),
);
let sluicer;

before(async () => {
  sluicer = await createSluicer();
});

test("the Python package inside is the npm package's version", () => {
  assert.equal(sluicer.version, packageJson.version);
  assert.equal(wheel.version, packageJson.version);
});

test("pyodide is pinned to one version, whose lxml Sluicer accepts", () => {
  assert.match(packageJson.dependencies.pyodide, /^\d+\.\d+\.\d+$/);
  const floor = wheel.requires.find((r) => r.startsWith("lxml")).split(">=")[1];
  const version = (v) => v.split(".").map(Number);
  const [have, need] = [version(sluicer.lxml), version(floor)];
  assert.ok(
    have[0] > need[0] || (have[0] === need[0] && have[1] >= need[1]),
    `lxml ${sluicer.lxml} under the floor ${floor}`,
  );
});

test("a page can be a string, a Buffer, a Uint8Array or an ArrayBuffer", () => {
  const html = "<html><head><title>Één</title></head></html>";
  const bytes = new TextEncoder().encode(html);
  const answers = [
    html,
    Buffer.from(html),
    bytes,
    bytes.buffer,
  ].map((given) => sluicer.extract(given).summary.title.value);

  assert.deepEqual(answers, ["Één", "Één", "Één", "Één"]);
});

test("anything else is refused before it reaches Python", () => {
  assert.throws(() => sluicer.extract(42), TypeError);
  assert.throws(() => sluicer.compile("<html></html>"), TypeError);
});

test("an error Sluicer raises keeps its Python name and words", () => {
  assert.throws(
    () => sluicer.compile([{ html: "<html><body></body></html>" }]),
    (error) =>
      error instanceof SluicerError &&
      error.type === "NothingToLearn" &&
      /declare nothing/.test(error.message),
  );
  assert.throws(
    () => sluicer.run({ format: 1 }, "<html></html>"),
    (error) => error instanceof SluicerError && error.type === "ValueError",
  );
});

test("toMarkdown without the markdown extra says how to get it", () => {
  assert.equal(sluicer.markdown, false);
  assert.throws(
    () => sluicer.toMarkdown("<html></html>"),
    (error) =>
      error instanceof SluicerError &&
      error.type === "MarkdownExtraMissing" &&
      /markdown: true/.test(error.message),
  );
});

test("broken markup is read, never thrown", () => {
  const found = sluicer.extract("<html><head><title>x</title><script type='application/ld+json'>{broken");

  assert.equal(found.summary.title.value, "x");
  assert.deepEqual(found.records, []);
});
