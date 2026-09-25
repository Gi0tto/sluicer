// The try page (docs/try/) loads Pyodide from its CDN, not from this package:
// it must load the version this package pins, and only that file.
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import { ROOT } from "./helpers.mjs";

const html = await readFile(new URL("docs/try/index.html", ROOT), "utf8");
const pinned = JSON.parse(
  await readFile(new URL("js/package.json", ROOT), "utf8"),
).dependencies.pyodide;
const scripts = [...html.matchAll(/<script\b[^>]*>/g)].map((m) => m[0]);
const pyodide = scripts.find((s) => s.includes("pyodide.js"));

test("the try page loads the Pyodide this package pins", () => {
  assert.ok(pyodide, "no script loads pyodide.js");
  assert.match(
    pyodide,
    new RegExp(`src="https://cdn\\.jsdelivr\\.net/pyodide/v${pinned}/full/pyodide\\.js"`),
  );
});

test("the browser refuses a pyodide.js other than the one npm installs", async () => {
  const file = await readFile(new URL("js/node_modules/pyodide/pyodide.js", ROOT));
  const digest = createHash("sha384").update(file).digest("base64");

  assert.match(pyodide, new RegExp(`integrity="sha384-${digest.replace(/[+/]/g, "\\$&")}"`));
  assert.match(pyodide, /crossorigin="anonymous"/);
});

test("the page may reach only itself and the CDN, and nothing may run inline", () => {
  const policy = html.match(
    /<meta http-equiv="Content-Security-Policy" content="([^"]+)"/,
  );
  assert.ok(policy, "no Content-Security-Policy");
  const rules = Object.fromEntries(
    policy[1].split(";").map((rule) => {
      const [name, ...values] = rule.trim().split(/\s+/);
      return [name, values];
    }),
  );

  assert.deepEqual(rules["default-src"], ["'none'"]);
  assert.deepEqual(rules["connect-src"], ["'self'", "https://cdn.jsdelivr.net"]);
  assert.ok(!rules["script-src"].includes("'unsafe-inline'"));
  assert.deepEqual(rules["form-action"], ["'none'"]);
  assert.ok(!scripts.some((s) => !/\bsrc=/.test(s)), "an inline script");
});
