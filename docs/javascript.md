# In JavaScript

`sluicer` on npm is the Python package itself, run in
[Pyodide](https://pyodide.org), Python compiled to WebAssembly. Nothing is
rewritten in JavaScript: the package carries the wheel built from the same
commit as the Python release of the same version, installs it into Pyodide
when it starts, and hands every call to it. The answers are the Python
package's, field for field.

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

The first run downloads lxml and click, Sluicer's two requirements, from
Pyodide's own package repository on jsDelivr, and keeps them in Pyodide's
package cache (by default beside Pyodide in `node_modules`). The markdown extra
installs trafilatura and its requirements from PyPI with micropip on every
start, since that cache keeps only Pyodide's own packages; ten of its 14 MB are
babel, which courlan (trafilatura's URL reader) needs.

Once started, `extract()` of the brake-pads example (1.2 KB) takes
7 ms the first time and 0.78 ms (0.76-0.91) after; the native package takes
0.31 ms on the same machine.
