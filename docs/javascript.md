# In JavaScript

`sluicer` on npm is the Python package itself, run in
[Pyodide](https://pyodide.org), Python compiled to WebAssembly. Nothing is
rewritten in JavaScript: the package carries the wheel built from the same
commit as the Python release of the same version, installs it into Pyodide
when it starts, and hands every call to it. The answers are the Python
package's, field for field: its tests hold them to the native package's in
29 cases on 19 pages, a page for each reader and a case for each option.

To see it without installing anything, [try it in your browser](try/index.html): paste
a page's HTML, and Sluicer reads it in the tab, sending it nowhere.

## Install

```bash
npm install sluicer
```

It needs Node 18 or later, and is an ES module. It brings one dependency,
`pyodide`, pinned to one version. The first `createSluicer()` on a machine
downloads lxml, click and cssselect, 2.27 MB, from Pyodide's package repository on
jsDelivr; later ones download nothing. A package that does not load is
downloaded once more, and one that still does not is a `SluicerError` of
type `PackageNotLoaded` that names it and where it comes from.

```js
import { readFile } from "node:fs/promises";
import { createSluicer, SluicerError } from "sluicer";

const sluicer = await createSluicer();   // about a second
const html = await readFile("brake-pads.html");
const found = sluicer.extract(html, { url: "https://example.com/p/bp-2210" });

found.summary.price;
// { value: '41.90', source: 'jsonld', key: 'Product.offers.price',
//   where: '/html/head/script[1]#/offers/price' }
found.normalised;   // { price: '41.90', currency: 'EUR', gtin: '4006381333931' }
found.conflicts.map((c) => c.question);   // [ 'price' ]
```

## API

`createSluicer(options)` starts Pyodide, installs Sluicer in it and resolves
to an object whose calls are synchronous: start it once and keep it. Its
options:

| Option | |
|---|---|
| `markdown` | Also install the markdown extra (trafilatura) from PyPI, for `toMarkdown`. Adds about three seconds and 14 MB of downloads to every start. |
| `packageCacheDir` | Where Pyodide keeps the packages it downloads. By default, beside Pyodide in `node_modules`. |
| `pyodide` | A Pyodide instance of your own, of the pinned version, to install into. |

The object it resolves to:

| | |
|---|---|
| `extract(html, { url, induce, visible, headers })` | What the page declares, as Python's `sluicer.extract`: the summary, each answer's source and place, conflicts, records, links and rights. `induce: true` also reads the rows a page repeats, `visible`, on unless `false`, guesses the heading, byline and dates it shows, apart from the summary, `headers` are the response's, when the page came over HTTP, as a plain object: `Object.fromEntries(response.headers)`. |
| `compile(pages, { listing, want, names, select, rows })` | An extractor learnt from pages of one template, each `{ html, url }`: the file `sluicer compile` writes, as an object. `want` gives example values by name, as `--want`; `select` writes the fields by selector instead, `{ price: "span.price::text" }`, and `rows` the selector of a listing's rows, as `--select` and `--rows`; with `select`, `pages` may be empty. |
| `run(extractor, html, { url })` | That extractor replayed on a page, as `sluicer run`: `ok` is false when a check failed, and `checks` says which. The extractor is the object, or its JSON text: a file written by the Python CLI runs here, and one written here runs there. |
| `toMarkdown(html, { url })` | The page's main text as Markdown. Only after `createSluicer({ markdown: true })`. |
| `version`, `python`, `lxml` | The Sluicer, Python and lxml versions inside. |
| `pyodide` | The Pyodide instance it runs in. |

Every call takes only the options it names. One it does not know, a
misspelt `induce` or an option of another call, is thrown as a `TypeError`
that names it, rather than ignored.

A page is a string, or its bytes: a `Uint8Array`, a Node `Buffer` or an
`ArrayBuffer`. Give bytes when you have them: the page's own charset
declaration is still in them. `url` is never fetched; it resolves the page's
links. Answers are plain objects with the Python field names, in snake_case,
the JSON `sluicer extract` prints; `index.d.ts` types them.

An error Sluicer raises is thrown as a `SluicerError`, with the Python
exception's name in `type` and its words in `message`:

```js
try {
  sluicer.compile([{ html: "<html><body></body></html>" }]);
} catch (error) {
  if (!(error instanceof SluicerError)) throw error;
  error.type;      // 'NothingToLearn'
  error.message;   // 'these pages declare nothing and repeat nothing an extractor could keep'
}
```

An extractor learnt from two pages of a shop's listing, and replayed on a page
whose prices are gone:

```js
const extractor = sluicer.compile([
  { html: await readFile("shop_v1.html"), url: "https://shop.example/c/1" },
  { html: await readFile("shop_v1_page2.html"), url: "https://shop.example/c/2" },
]);
const run = sluicer.run(extractor, await readFile("shop_prices_gone.html"));
run.ok;   // false: a check failed, and run.checks says which
```

## What it does not do

It reads pages you hand it; it does not fetch them. Sluicer's fetching is more
than a request: it refuses private addresses, reads robots.txt, keeps one
request per site at a time, and chooses how to fetch. None of that is in
this first version, rather than a fetch without those guards. Fetch the page
yourself, and hand over its bytes, address and headers:

```js
const response = await fetch(url);
const found = sluicer.extract(new Uint8Array(await response.arrayBuffer()), {
  url: response.url,
  headers: Object.fromEntries(response.headers),
});
```

Nor does it offer what is built on fetching or on files: crawl, map, batch,
feeds, web archives, audit, diff, heal, the command line, the MCP server and
the HTTP API. The microformats reader, behind an extra in Python, is not
offered either. For those, the Python package: `uvx sluicer`, or
`sluicer serve` for [the HTTP API](http-api.md) from any language.

It runs in Node. The package reads its wheel from its own folder with
`node:fs`, so a bundler will not carry it into a browser as it is; the
[try page](try/index.html) shows how the same wheel runs in a browser, in
`docs/try/try.js`.

## Versions

The npm package's version is the Python package's: `sluicer@0.10.0` on npm
is the wheel of `sluicer==0.10.0`, built from the same commit. The build
refuses to run when `js/package.json` and `pyproject.toml` differ, and a
test on each side, Python's and Node's, holds them equal. CI
(`.github/workflows/js.yml`) runs the Node tests on Node 18, 22 and 24, writes
the native answers they compare with again and fails on any difference, and
opens the try page in Chromium; a release tag publishes the package to npm
only after all of them pass, from the tag whose version it carries. Pyodide is pinned to one version, Pyodide
314.0.7, with Python 3.14.2 and lxml 6.1.3 inside, the lxml the
repository's lockfile pins; a new Pyodide comes with a release of this package,
never under it. `sluicer.version`, `.python` and `.lxml` say what is running.

The package's licence is the Python package's, `MIT AND CC-BY-SA-3.0 AND
Unicode-3.0`: the wheel holds two data files under the other two, which
`LICENSES/` carries.

## Measured

On an Apple M4, Node 26.1.0, sluicer 0.7.1 with Pyodide 314.0.7:
`node js/scripts/measure.mjs 5` in a checkout, after `npm run build` and
`npm ci` in `js/`. Every start is a new process; medians of five, with the
lowest and highest.

What `npm install sluicer` downloads, as the registry serves it:

| Package | Packed | Unpacked |
|---|---:|---:|
| sluicer 0.7.1 | 378 KB | 410 KB |
| pyodide 314.0.7 | 6.5 MB | 13.9 MB |
| Together | 6.9 MB | 14.3 MB |

What `createSluicer()` takes, in a new Node process:

| | `createSluicer()` | Downloaded |
|---|---:|---:|
| First run on a machine | 1.30 s (1.28-1.37) | 2.25 MB, from cdn.jsdelivr.net |
| Every later run | 1.14 s (1.10-1.26) | nothing |
| First run, `markdown: true` | 4.0 s (3.9-4.4) | 17.9 MB |
| Every later run, `markdown: true` | 3.9 s (3.3-4.0) | 14.3 MB, from PyPI |

The first run downloads lxml, click and cssselect, Sluicer's requirements, from
Pyodide's own package repository on jsDelivr, and keeps them in Pyodide's
package cache (by default beside Pyodide in `node_modules`). The markdown extra
installs trafilatura and its requirements from PyPI with micropip on every
start, since that cache keeps only Pyodide's own packages; ten of its 14 MB are
babel, which courlan (trafilatura's URL reader) needs.

Once started, `extract()` of the brake-pads example (1.2 KB) takes
7 ms the first time and 0.78 ms (0.76-0.91) after; the native package takes
0.31 ms on the same machine.

In a browser, the [try page](try/index.html) was opened in Chromium by
Playwright with an empty cache (`python scripts/check_try_page.py`): ready in
1.8 s, after 8.9 MB over the wire, 8.5 MB of it Pyodide, its standard library
and lxml from jsDelivr, and 0.38 MB the wheel from the site; reloaded, 1.0 s.
It made 14 requests, every one a GET before Sluicer was ready, and none after
16 pages were pasted.
