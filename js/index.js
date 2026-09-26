// Sluicer for JavaScript: the Python package itself, run inside Pyodide.
//
// Nothing here reimplements Sluicer. createSluicer() starts Pyodide, loads the
// wheel's requirements from Pyodide's own package repository, installs the
// wheel this npm package carries (built from the same commit as the Python
// release of the same version), and hands every call to bridge.py, which
// answers in JSON. The answers are therefore the Python package's, field for
// field: the tests hold them to the native package's on the same pages.

import { readFile } from "node:fs/promises";
import { loadPyodide } from "pyodide";

const HERE = new URL("./", import.meta.url);
// Pyodide reports every package it loads; a library should not print.
const QUIET = { messageCallback() {}, errorCallback() {} };

/** An error Sluicer raised, with the Python exception's name in `type`. */
export class SluicerError extends Error {
  constructor(type, message) {
    super(message);
    this.name = "SluicerError";
    this.type = type;
  }
}

/**
 * Start Pyodide and install Sluicer in it. Takes about a second (1.1 to 1.4
 * measured in Node, docs/javascript.md), four with the markdown extra; every
 * call on the returned object after that is synchronous and takes
 * milliseconds.
 */
export async function createSluicer(options) {
  options = known("createSluicer", options, ["markdown", "packageCacheDir", "pyodide"]);
  const wheel = JSON.parse(
    await readFile(new URL("python/wheel.json", HERE), "utf8"),
  );
  const pyodide =
    options.pyodide ??
    (await loadPyodide({
      ...(options.packageCacheDir && { packageCacheDir: options.packageCacheDir }),
      stdout() {},
      stderr() {},
    }));
  await pyodide.loadPackage(wheel.requires.map(nameOf), QUIET);
  const site = pyodide.runPython(
    "import sysconfig; sysconfig.get_paths()['purelib']",
  );
  pyodide.unpackArchive(
    new Uint8Array(await readFile(new URL(`python/${wheel.file}`, HERE))),
    "wheel",
    { extractDir: site },
  );
  const markdown = Boolean(options.markdown);
  if (markdown) {
    await installMarkdown(pyodide, wheel);
  }
  const bridge = pyodide.toPy({});
  pyodide.runPython(await readFile(new URL("bridge.py", HERE), "utf8"), {
    globals: bridge,
  });
  const call = (name, ...args) => {
    const answer = JSON.parse(bridge.get(name)(...args));
    if (answer.error) {
      throw new SluicerError(answer.error.type, answer.error.message);
    }
    return answer.ok;
  };
  const about = JSON.parse(bridge.get("about")());

  return {
    version: about.sluicer,
    python: about.python,
    lxml: about.lxml,
    markdown,
    pyodide,

    extract(html, options) {
      const { url, induce, visible, headers } = known("extract", options, [
        "url",
        "induce",
        "visible",
        "headers",
      ]);
      return call(
        "extract",
        page(html),
        JSON.stringify({ url, induce, visible, headers }),
      );
    },

    toMarkdown(html, options) {
      const { url } = known("toMarkdown", options, ["url"]);
      if (!markdown) {
        throw new SluicerError(
          "MarkdownExtraMissing",
          "toMarkdown needs the markdown extra: createSluicer({ markdown: true })",
        );
      }
      return call("to_markdown", page(html), JSON.stringify({ url }));
    },

    compile(pages, options) {
      const { listing, want, names, select, rows } = known("compile", options, [
        "listing",
        "want",
        "names",
        "select",
        "rows",
      ]);
      if (!Array.isArray(pages)) {
        throw new TypeError("compile takes an array of { html, url } pages");
      }
      pages.forEach((p, n) => known(`compile's page ${n}`, p, ["html", "url"], "a page"));
      return call(
        "compile",
        pages.map((p) => page(p.html)),
        JSON.stringify({
          urls: pages.map((p) => p.url ?? null),
          listing,
          want,
          names,
          select,
          rows,
        }),
      );
    },

    run(extractor, html, options) {
      const { url } = known("run", options, ["url"]);
      const text =
        typeof extractor === "string" ? extractor : JSON.stringify(extractor);
      return call("run", text, page(html), JSON.stringify({ url }));
    },
  };
}

// The markdown extra comes from PyPI through micropip: trafilatura and the
// packages it needs are not in Pyodide's repository. lxml_html_clean is added
// by name: justext asks for lxml[html_clean], and micropip does not install an
// extra of a package Pyodide already ships, so without it trafilatura installs
// and then cannot be imported.
async function installMarkdown(pyodide, wheel) {
  await pyodide.loadPackage("micropip", QUIET);
  const micropip = pyodide.pyimport("micropip");
  const wanted = pyodide.toPy([...(wheel.extras.markdown ?? []), "lxml_html_clean"]);
  try {
    await micropip.install(wanted);
  } finally {
    wanted.destroy();
    micropip.destroy();
  }
}

// A call's options, an object of the keys it knows or nothing. An option it
// does not know is refused rather than ignored: ignored, a misspelt `induce`
// or an option another call takes gives an answer to another question, with
// nothing to say so.
function known(call, options, names, what = "options") {
  if (options === undefined && what === "options") {
    return {};
  }
  if (options === null || typeof options !== "object" || Array.isArray(options)) {
    throw new TypeError(
      `${call} takes ${what === "options" ? "its options" : what} as an object` +
        ` of ${names.join(", ")}, not ${describe(options)}`,
    );
  }
  const unknown = Object.keys(options).filter((key) => !names.includes(key));
  if (unknown.length > 0) {
    const noun = what === "options" ? "option" : "key";
    throw new TypeError(
      `${call} has no ${noun} ${unknown.map((key) => `"${key}"`).join(", ")}:` +
        ` the ${noun}s it knows are ${names.join(", ")}`,
    );
  }
  return options;
}

function describe(value) {
  return value === null ? "null" : Array.isArray(value) ? "an array" : `a ${typeof value}`;
}

function nameOf(requirement) {
  return requirement.match(/^[A-Za-z0-9._-]+/)[0];
}

// A string, or the page's bytes: bytes let Sluicer honour the page's charset.
// A Node Buffer is handed over as the plain Uint8Array under it.
function page(html) {
  if (typeof html === "string") {
    return html;
  }
  if (html instanceof Uint8Array) {
    return html.constructor === Uint8Array
      ? html
      : new Uint8Array(html.buffer, html.byteOffset, html.byteLength);
  }
  if (html instanceof ArrayBuffer) {
    return new Uint8Array(html);
  }
  throw new TypeError("a page is a string, a Uint8Array or an ArrayBuffer");
}
