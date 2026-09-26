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
  await loadRequirements(pyodide, wheel.requires.map(nameOf));
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
      mapping("extract's headers", headers, "Object.fromEntries(response.headers)");
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
      mapping("compile's want", want, "{ price: \"41.90\" }");
      mapping("compile's select", select, "{ price: \"span.price::text\" }");
      if (names != null && !Array.isArray(names)) {
        throw new TypeError(`compile's names is an array of strings, not ${describe(names)}`);
      }
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

// Sluicer's requirements, from Pyodide's package repository. loadPackage does
// not throw when a download fails, a network blip or another process writing
// the same wheel into the cache: it logs, resolves, and the first import of
// lxml fails much later, as "No module named 'lxml'". So each package is
// imported here, a failed one is downloaded once more, and one that still
// does not import is an error that says which, from where, and what to do.
async function loadRequirements(pyodide, names) {
  let missing = names;
  let said = [];
  for (let attempt = 0; attempt < 2 && missing.length > 0; attempt += 1) {
    said = [];
    // Pyodide reports every package it loads; a library should not print,
    // and what went wrong is kept for the error.
    await pyodide.loadPackage(missing, {
      messageCallback() {},
      errorCallback(message) {
        said.push(message);
      },
    });
    missing = unimportable(pyodide, names);
  }
  if (missing.length > 0) {
    const where = `https://cdn.jsdelivr.net/pyodide/v${pyodide.version}/full/`;
    throw new SluicerError(
      "PackageNotLoaded",
      `Sluicer could not load ${missing.join(", ")} into Pyodide, tried twice. ` +
        `Pyodide downloads each package from its repository, ${where}, ` +
        "the first time, and reads it from its cache after." +
        (said.length > 0 ? ` Pyodide said: ${said.join(" ")}` : "") +
        " Check that this machine can reach cdn.jsdelivr.net, through its" +
        " proxy if it has one, and call createSluicer() again; or point" +
        " packageCacheDir at a folder that already holds the wheels.",
    );
  }
}

// The packages of `names` that Python cannot import. A requirement's import
// name is its project name, as for each of lxml, click and cssselect.
function unimportable(pyodide, names) {
  const globals = pyodide.toPy({ names });
  try {
    return JSON.parse(
      pyodide.runPython(
        `
import importlib, json
missing = []
for name in names:
    try:
        importlib.import_module(name.lower().replace("-", "_"))
    except ImportError:
        missing.append(name)
json.dumps(missing)
`,
        { globals },
      ),
    );
  } finally {
    globals.destroy();
  }
}

// The markdown extra comes from PyPI through micropip: trafilatura and the
// packages it needs are not in Pyodide's repository. lxml_html_clean is added
// by name: justext asks for lxml[html_clean], and micropip does not install an
// extra of a package Pyodide already ships, so without it trafilatura installs
// and then cannot be imported.
async function installMarkdown(pyodide, wheel) {
  await loadRequirements(pyodide, ["micropip"]);
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

// An option that is an object of names to strings. A Map or a Headers is
// not one: JSON writes either as {}, and what it held would be lost.
function mapping(what, value, example) {
  if (value == null) {
    return;
  }
  const prototype = typeof value === "object" ? Object.getPrototypeOf(value) : undefined;
  if (prototype !== Object.prototype && prototype !== null) {
    throw new TypeError(
      `${what} is a plain object of names to strings, such as ${example},` +
        ` not ${value?.constructor?.name ? `a ${value.constructor.name}` : describe(value)}`,
    );
  }
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
