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

test("the npm package's version is pyproject.toml's", async () => {
  // As tests/test_package.py holds it from the Python side: the npm package
  // is the Python package of the same number, never another.
  const pyproject = await readFile(new URL("../../pyproject.toml", import.meta.url), "utf8");
  const [, version] = pyproject.match(/^version = "(.+)"$/m);

  assert.equal(packageJson.version, version);
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

test("every package index.js loads is one Pyodide ships", async () => {
  // protego joined the base install with fetching over plain HTTP, and
  // Pyodide has no protego: every start failed. What only fetching needs is
  // listed apart, since this package fetches nothing.
  const lock = JSON.parse(
    await readFile(new URL("../node_modules/pyodide/pyodide-lock.json", import.meta.url), "utf8"),
  );
  for (const requirement of wheel.requires) {
    const name = requirement.split(/[<>=!~ ;[]/)[0].toLowerCase();
    assert.ok(name in lock.packages, `${name} is not a Pyodide package`);
  }
  assert.ok(wheel.fetching.some((r) => r.startsWith("protego")));
  // tomli is for Pythons older than 3.11, and Pyodide's is 3.14.
  assert.ok(!wheel.requires.some((r) => r.startsWith("tomli")));
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
