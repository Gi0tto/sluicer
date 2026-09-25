// What `npm pack` puts in the package: the code, the wheel it installs, and
// the licences of what that wheel holds. Nothing the tests or the build read.
import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { fileURLToPath } from "node:url";

const JS = new URL("../", import.meta.url);
const [packed] = JSON.parse(
  execFileSync("npm", ["pack", "--dry-run", "--json", "--ignore-scripts"], {
    cwd: fileURLToPath(JS),
    encoding: "utf8",
    stdio: ["ignore", "pipe", "ignore"],
  }),
);
const wheel = JSON.parse(
  await readFile(new URL("python/wheel.json", JS), "utf8"),
);

test("the package carries the code, the wheel and the licences, and nothing else", () => {
  assert.deepEqual(packed.files.map((f) => f.path).sort(), [
    "LICENSE",
    "LICENSES/CC-BY-SA-3.0.txt",
    "LICENSES/Unicode-3.0.txt",
    "NOTICE",
    "bridge.py",
    "index.d.ts",
    "index.js",
    "package.json",
    `python/${wheel.file}`,
    "python/wheel.json",
  ]);
});

test("the package is the wheel and little more", () => {
  const whl = packed.files.find((f) => f.path === `python/${wheel.file}`);

  // The wheel is compressed already; the rest is a few text files. A package
  // much larger than its wheel carries something it should not.
  assert.ok(
    packed.unpackedSize < whl.size + 64 * 1024,
    `${packed.unpackedSize} bytes unpacked for a ${whl.size}-byte wheel`,
  );
});
