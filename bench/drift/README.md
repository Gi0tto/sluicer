# The drift benchmark

What Sluicer's extractors do across real changes to real pages. Each one is
learnt on an old Wayback Machine capture of a listing page and replayed on a
later capture, and an oracle that does not use the extractor's code judges
it. The results, losses first, are in [`docs/drift.md`](../../docs/drift.md).

```bash
uv run --with brotli --with 'scrapling>=0.4' bench/drift/run.py   # then docs/drift.md
uv run --with brotli bench/drift/run.py --no-scrapling --no-anansi   # Sluicer only
```

anansi (mdowis/anansi, Apache-2.0), a self-healing scraper, is asked what
Scrapling is asked, on the same item, in an environment of its own pinned by
`bench/requirements/anansi.txt` (`anansi_tool.py`). It is not on PyPI, so the
first run fetches it from GitHub at the pinned commit.

The first run reads about a hundred captures from the archive, one request a
second, in a few minutes. After that it runs from `bench/cache/drift/`, which
is never committed. `brotli` decodes captures the sites served compressed
with it.

## The files

- `discover.py` proposes the candidate pages and dates and writes
  `discover.log`. It is run once, to choose the pairs.
- `make_pairs.py` turns the log into `pairs.json` by fixed rules, not by hand.
- `pairs.json` is the list the benchmark runs: the page, the captures to learn
  from, the capture to replay on, and where a site redirected.
- `wayback.py` is the polite, cached archive reader.
- `run.py` holds the oracle, the judge of `heal`, the Scrapling and anansi
  comparisons and the page.
- `anansi_tool.py` asks anansi, from its own environment.
- `explanations.json` is written by hand. It explains every silent failure,
  false alarm and wrong heal after reading the pages; a new one shows on the
  page as not yet explained.
