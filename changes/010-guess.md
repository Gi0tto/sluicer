### Changed

- The guesses read off the visible page are on by default: `extract()` and `aextract()` take `visible=True` unless told `visible=False`, `sluicer extract`, `inspect`, `crawl`, `batch` and `warc` guess unless given `--no-visible`, and the MCP tool `extract_declared`, the HTTP API and the npm package's `extract` guess unless sent `visible: false`. The guesses stay in their own `visible` field, each naming its element and rule, never in the summary. `visible=True` and `--visible` still work and change nothing. `crawl` and `batch` lines now carry `visible`, empty with `--no-visible`. A page that declares nothing but shows a heading now exits 0 with its guess, as it did with `--visible`; `--no-visible` keeps the old exit 1. On WCXB's development pages the guesses add 2 to 3 ms to a page at the median and 8 to 10 ms at the 95th percentile, about four fifths more time.

### Fixed

- `--visible` took a box whose class says there is no byline ("no-byline"), or the page's `<body>` itself, for a byline and read the first capitalised words in it as the author, and took the "By" line on another article's card, inside its link, for the page's own. None of them is read as the author now.
