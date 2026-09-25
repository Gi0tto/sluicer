// Measure what docs/javascript.md says about the npm package: what npm
// downloads to install it, how long createSluicer() takes in a new process,
// what that first start downloads and from where, and how long a call takes
// once it is warm.
//
//   node scripts/measure.mjs [runs]          (after npm run build and npm ci)
//
// Every start is a new node process, so each is a cold one. "first run" starts
// with an empty package cache, as on a machine that never ran Sluicer: lxml
// and click then come from Pyodide's CDN. "later runs" reuse that cache, as
// every run after the first does. With the markdown extra, micropip also
// installs trafilatura and its pure-Python requirements from PyPI, which no
// cache keeps: they are downloaded on every start.
//
// "since the process started" counts from node's own start (performance's time
// origin), module loading included; "createSluicer" counts the call alone.
// Downloaded bytes are the bodies fetch() handed over, after any
// Content-Encoding was undone; wheels and zips are served as they are.

import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const JS = new URL("../", import.meta.url);
const ROOT = new URL("../../", import.meta.url);

if (process.argv[2] === "--child") {
  await child(process.argv[3], process.argv[4] === "markdown");
} else {
  await parent(Number(process.argv[2] ?? 5));
}

async function child(cache, markdown) {
  // Count what the network hands over, whoever asks for it: Pyodide and
  // micropip both call the global fetch when they need a file.
  const hosts = {};
  let bytes = 0;
  const fetched = globalThis.fetch;
  globalThis.fetch = async (...args) => {
    const response = await fetched(...args);
    const body = await response.arrayBuffer();
    const host = new URL(response.url || String(args[0])).host;
    hosts[host] = (hosts[host] ?? 0) + body.byteLength;
    bytes += body.byteLength;
    return new Response(body, response);
  };
  const { createSluicer } = await import("../index.js");
  const started = performance.now();
  const sluicer = await createSluicer({ packageCacheDir: cache, markdown });
  const ready = performance.now();
  const page = readFileSync(new URL("examples/brake-pads.html", ROOT));
  let t = performance.now();
  sluicer.extract(page);
  const first = performance.now() - t;
  for (let n = 0; n < 20; n++) sluicer.extract(page);
  t = performance.now();
  for (let n = 0; n < 100; n++) sluicer.extract(page);
  const warm = (performance.now() - t) / 100;
  console.log(
    JSON.stringify({
      create: ready - started,
      process: ready,
      first,
      warm,
      downloaded: bytes,
      hosts,
    }),
  );
}

async function parent(runs) {
  const here = fileURLToPath(import.meta.url);
  const once = (cache, markdown = false) => {
    const out = execFileSync(
      process.execPath,
      [here, "--child", cache, markdown ? "markdown" : ""],
      { encoding: "utf8" },
    );
    // The last line is the child's answer, whatever else was printed.
    return JSON.parse(out.trim().split("\n").at(-1));
  };
  const rows = {
    "first run": [],
    "later runs": [],
    "first run, markdown": [],
    "later runs, markdown": [],
  };
  for (let n = 0; n < runs; n++) {
    for (const markdown of [false, true]) {
      const cache = mkdtempSync(join(tmpdir(), "sluicer-js-"));
      const suffix = markdown ? ", markdown" : "";
      try {
        rows[`first run${suffix}`].push(once(cache, markdown));
        rows[`later runs${suffix}`].push(once(cache, markdown));
      } finally {
        rmSync(cache, { recursive: true, force: true });
      }
    }
  }

  console.log(`node ${process.version} on ${process.platform}-${process.arch}`);
  console.log("");
  console.log("What npm downloads to install it");
  for (const line of await installed()) console.log(`  ${line}`);
  console.log("");
  console.log(`Starting, ${runs} new processes each: median (min-max)`);
  for (const [name, found] of Object.entries(rows)) {
    const say = (key, digits) => {
      const xs = found.map((r) => r[key]);
      return `${median(xs).toFixed(digits)} (${Math.min(...xs).toFixed(digits)}-${Math.max(...xs).toFixed(digits)})`;
    };
    console.log(`  ${name}`);
    console.log(`    createSluicer           ${say("create", 0)} ms`);
    console.log(`    since the process began ${say("process", 0)} ms`);
    console.log(`    first extract           ${say("first", 1)} ms`);
    console.log(`    warm extract            ${say("warm", 2)} ms`);
    console.log(`    downloaded              ${say("downloaded", 0)} bytes`);
    const hosts = {};
    for (const r of found) {
      for (const [host, n] of Object.entries(r.hosts)) {
        (hosts[host] ??= []).push(n);
      }
    }
    for (const [host, xs] of Object.entries(hosts)) {
      console.log(`      from ${host.padEnd(22)} ${median(xs)} bytes (median)`);
    }
  }
}

// The npm package as `npm pack` makes it, and the one package it depends on,
// as the registry states it.
async function installed() {
  const [packed] = JSON.parse(
    execFileSync("npm", ["pack", "--dry-run", "--json", "--ignore-scripts"], {
      cwd: fileURLToPath(JS),
      encoding: "utf8",
      stdio: ["ignore", "pipe", "ignore"],
    }),
  );
  const manifest = JSON.parse(readFileSync(new URL("package.json", JS), "utf8"));
  const pyodide = manifest.dependencies.pyodide;
  const dist = JSON.parse(
    execFileSync("npm", ["view", `pyodide@${pyodide}`, "dist", "--json"], {
      encoding: "utf8",
    }),
  );
  const tarball = (await fetch(dist.tarball)).arrayBuffer();
  const pyodidePacked = (await tarball).byteLength;
  return [
    `sluicer ${manifest.version}  packed ${packed.size} bytes, unpacked ${packed.unpackedSize} bytes, ${packed.files.length} files`,
    `pyodide ${pyodide}  packed ${pyodidePacked} bytes, unpacked ${dist.unpackedSize} bytes, ${dist.fileCount} files`,
    `together  packed ${packed.size + pyodidePacked} bytes, unpacked ${packed.unpackedSize + dist.unpackedSize} bytes`,
  ];
}

function median(xs) {
  const sorted = [...xs].sort((a, b) => a - b);
  const half = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[half] : (sorted[half - 1] + sorted[half]) / 2;
}
