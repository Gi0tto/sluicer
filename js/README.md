# sluicer

Sluicer reads the structured data a web page declares (JSON-LD, microdata,
RDFa, OpenGraph, Twitter cards, Dublin Core, HTML meta) and tells you where
each value came from. This npm package is the Python package itself, run in
[Pyodide](https://pyodide.org): the same code, the same answers.

## Install

```bash
npm install sluicer
```

It needs Node 18 or later and is an ES module. The first `createSluicer()` on
a machine downloads lxml, click and cssselect (about 2.3 MB) from Pyodide's
package repository on cdn.jsdelivr.net; later ones download nothing.

## Example

`brake-pads.html` is
[examples/brake-pads.html](https://github.com/Gi0tto/sluicer/blob/main/examples/brake-pads.html)
in the repository: a product page whose JSON-LD says 41.90 and whose
OpenGraph says 39.90.

```js
import { readFile } from "node:fs/promises";
import { createSluicer } from "sluicer";
const sluicer = await createSluicer();
const found = sluicer.extract(await readFile("brake-pads.html"), { url: "https://example.com/p/bp-2210" });
console.log(found.summary.price, found.conflicts.map((c) => c.question));
```

prints

```text
{
  value: '41.90',
  source: 'jsonld',
  key: 'Product.offers.price',
  where: '/html/head/script[1]#/offers/price'
} [ 'price' ]
```

`compile()` learns an extractor from a few pages of one template, and `run()`
replays it on another page, with `ok: false` and the failed check when the
layout has changed.

## What it does not do

It does not fetch pages: fetch them yourself and hand over the HTML, as a
string or as bytes, with its address. Crawling, feeds, web archives, audit,
diff, heal, the command line, the MCP server, the HTTP API and the
microformats reader are in the Python package only (`uvx sluicer`). It runs
in Node; a bundler will not carry it into a browser as it is.

## More

The full guide, with every call and option:
[docs/javascript.md](https://github.com/Gi0tto/sluicer/blob/main/docs/javascript.md),
also at <https://gi0tto.github.io/sluicer/javascript/>. The npm package's
version is the Python package's: each npm release carries the wheel of the
PyPI release of the same number, built from the same commit.

Licence: `MIT AND CC-BY-SA-3.0 AND Unicode-3.0`; see `LICENSE`, `NOTICE` and
`LICENSES/`.
