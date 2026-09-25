# Speed and weight

How long each tool takes on the scoreboards' pages, how much memory it
holds, and how much it installs, measured one way for every tool, as
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
fixes it under "How a second is measured". Every tool of a table was
timed in one run, on one machine, on the same pages; a scoreboard
prints no second measured otherwise. Regenerated from commit
`a8ca1b1` by `uv run bench/timing.py`.

Install size counts every file each package of the tool's environment
installs, bytecode caches left out (for Sluicer, installed editable, the
files of its package); packages count them, the interpreter's pip,
setuptools and wheel left out, and metascraper's every package under
`node_modules`. Peak memory is the process's peak resident size, the
interpreter and every page read into memory included.

## WCXB's test pages

The tools [the scoreboard](scoreboard.md) scores, on its 511 pages.

Measured on 2026-09-25 by `uv run bench/timing.py wcxb` at commit `a8ca1b1`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | Python 3.12.13 | 0.0023 | 1.18 (1.11–1.62) | 434 | 88.7 MiB | 19.4 MiB | 3 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0316 | 16.13 (14.23–19.21) | 32 | 170.1 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0061 | 3.10 (2.83–6.33) | 165 | 718.0 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0696 | 35.57 (31.58–66.20) | 14 | 217.8 MiB | 39.4 MiB | 22 |

## Fundus's news pages

The tools [news in many languages](scoreboard-news.md) scores, on its 263 pages.

Measured on 2026-09-25 by `uv run bench/timing.py news` at commit `a8ca1b1`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | Python 3.12.13 | 0.0038 | 1.01 (0.96–1.47) | 261 | 194.9 MiB | 19.4 MiB | 3 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0077 | 2.02 (1.98–2.38) | 130 | 250.9 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0093 | 2.44 (2.20–2.51) | 108 | 1500.2 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0623 | 16.38 (15.06–18.00) | 16 | 334.1 MiB | 39.4 MiB | 22 |

## The pages extruct's interface is compared on

The tools [moving from extruct](extruct.md) scores, on its 520 pages.

Measured on 2026-09-25 by `uv run bench/timing.py extruct` at commit `a8ca1b1`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 520 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| extruct 0.18.0 | Python 3.14.6 | 0.0528 | 27.48 (27.22–29.35) | 19 | 312.8 MiB | 25.9 MiB | 21 |
| sluicer.compat.extruct 0.7.1 | Python 3.14.6 | 0.0407 | 21.14 (19.74–22.52) | 25 | 320.7 MiB | 23.1 MiB | 15 |
