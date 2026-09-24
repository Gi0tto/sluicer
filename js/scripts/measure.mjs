// Measure what the README says: how long createSluicer() takes in a new
// process, what it downloads, and how long a call takes once it is warm.
//
//   node scripts/measure.mjs [runs]          (after npm run build)
//
// Every run is a new node process, so each start is a cold one. "first ever"
// starts with an empty package cache, as on a machine that never ran Sluicer:
// lxml and click then come from Pyodide's CDN. "cached" reuses that cache.

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = new URL("../../", import.meta.url);

if (process.argv[2] === "--child") {
  await child(process.argv[3], process.argv[4] === "markdown");
} else {
  parent(Number(process.argv[2] ?? 5));
}

async function child(cache, markdown) {
  // Count what the network hands over, whoever asks for it.
  let bytes = 0;
  const fetched = globalThis.fetch;
  globalThis.fetch = async (...args) => {
    const response = await fetched(...args);
    const body = await response.arrayBuffer();
    bytes += body.byteLength;
    return new Response(body, response);
  };
  const { createSluicer } = await import("../index.js");
  const started = performance.now();
  const sluicer = await createSluicer({ packageCacheDir: cache, markdown });
  const ready = performance.now() - started;
  const page = readFileSync(new URL("examples/brake-pads.html", ROOT));
  let t = performance.now();
  sluicer.extract(page);
  const first = performance.now() - t;
  for (let n = 0; n < 20; n++) sluicer.extract(page);
  t = performance.now();
  for (let n = 0; n < 100; n++) sluicer.extract(page);
  const warm = (performance.now() - t) / 100;
  console.log(JSON.stringify({ ready, first, warm, downloaded: bytes }));
}

function parent(runs) {
  const here = fileURLToPath(import.meta.url);
  const once = (cache, markdown = false) =>
    JSON.parse(
      execFileSync(process.execPath, [here, "--child", cache, markdown ? "markdown" : ""], {
        encoding: "utf8",
      }),
    );
  const rows = { "first ever": [], cached: [], "cached, with markdown": [] };
  for (let n = 0; n < runs; n++) {
    const cache = mkdtempSync(join(tmpdir(), "sluicer-js-"));
    try {
      rows["first ever"].push(once(cache));
      rows.cached.push(once(cache));
      rows["cached, with markdown"].push(once(cache, true));
    } finally {
      rmSync(cache, { recursive: true, force: true });
    }
  }
  const median = (xs) => [...xs].sort((a, b) => a - b)[Math.floor(xs.length / 2)];
  console.log(`node ${process.version}, ${runs} runs each, medians (min-max)`);
  for (const [name, found] of Object.entries(rows)) {
    const say = (key, digits) => {
      const xs = found.map((r) => r[key]);
      return `${median(xs).toFixed(digits)} (${Math.min(...xs).toFixed(digits)}-${Math.max(...xs).toFixed(digits)})`;
    };
    console.log(
      `${name.padEnd(22)} createSluicer ${say("ready", 0)} ms, first extract ${say("first", 1)} ms, ` +
        `warm extract ${say("warm", 2)} ms, downloaded ${say("downloaded", 0)} bytes`,
    );
  }
}
