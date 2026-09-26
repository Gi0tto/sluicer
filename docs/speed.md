# Speed and weight

How long each tool takes on the scoreboards' pages, how much memory it
holds, and how much it installs, measured one way for every tool, as
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
fixes it under "How a second is measured". Every tool of a table was
timed in one run, on one machine, on the same pages; a scoreboard
prints no second measured otherwise. Regenerated from commit
`8a426a2` by `uv run bench/timing.py`.

Install size counts every file each package of the tool's environment
installs, bytecode caches left out (for Sluicer, installed editable, the
files of its package); packages count them, the interpreter's pip,
setuptools and wheel left out, and metascraper's every package under
`node_modules`. Peak memory is the process's peak resident size, the
interpreter and every page read into memory included.

## WCXB's test pages

The tools [the scoreboard](scoreboard.md) scores, on its 511 pages.

Measured on 2026-09-26 by `uv run bench/timing.py wcxb` at commit `8a426a2`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.9.1 | Python 3.12.13 | 0.0036 | 1.85 (1.23–2.08) | 277 | 91.8 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0452 | 23.10 (20.38–28.05) | 22 | 171.0 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0091 | 4.63 (3.83–5.52) | 110 | 719.6 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0914 | 46.69 (35.08–55.63) | 11 | 217.5 MiB | 39.4 MiB | 22 |

## Fundus's news pages

The tools [news in many languages](scoreboard-news.md) scores, on its 263 pages.

Measured on 2026-09-26 by `uv run bench/timing.py news` at commit `8a426a2`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.9.1 | Python 3.12.13 | 0.0048 | 1.27 (1.06–1.49) | 207 | 196.2 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0107 | 2.81 (2.33–3.40) | 94 | 253.7 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0134 | 3.53 (2.82–4.13) | 75 | 1454.4 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0833 | 21.92 (18.68–26.30) | 12 | 331.1 MiB | 39.4 MiB | 22 |

## The pages extruct's interface is compared on

The tools [moving from extruct](extruct.md) scores, on its 530 pages.

Measured on 2026-09-26 by `uv run bench/timing.py extruct` at commit `8a426a2`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 530 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| extruct 0.18.0 | Python 3.14.6 | 0.0690 | 36.57 (34.00–61.82) | 14 | 320.3 MiB | 25.9 MiB | 21 |
| sluicer.compat.extruct 0.9.1 | Python 3.14.6 | 0.0511 | 27.06 (25.83–28.91) | 20 | 332.6 MiB | 23.2 MiB | 17 |
