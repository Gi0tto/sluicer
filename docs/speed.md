# Speed and weight

How long each tool takes on the scoreboards' pages, how much memory it
holds, and how much it installs, measured one way for every tool, as
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
fixes it under "How a second is measured". Every tool of a table was
timed in one run, on one machine, on the same pages; a scoreboard
prints no second measured otherwise. Regenerated from commit
`10211f3` by `uv run bench/timing.py`.

Install size counts every file each package of the tool's environment
installs, bytecode caches left out (for Sluicer, installed editable, the
files of its package); packages count them, the interpreter's pip,
setuptools and wheel left out, and metascraper's every package under
`node_modules`. Peak memory is the process's peak resident size, the
interpreter and every page read into memory included.

## WCXB's test pages

The tools [the scoreboard](scoreboard.md) scores, on its 511 pages.

Measured on 2026-09-25 by `uv run bench/timing.py wcxb` at commit `10211f3`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.9.0 | Python 3.12.13 | 0.0020 | 1.01 (1.01–1.03) | 503 | 89.9 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0270 | 13.80 (13.70–13.85) | 37 | 168.2 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0049 | 2.50 (2.49–2.51) | 205 | 698.4 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0572 | 29.21 (29.03–29.43) | 17 | 217.0 MiB | 39.4 MiB | 22 |

## Fundus's news pages

The tools [news in many languages](scoreboard-news.md) scores, on its 263 pages.

Measured on 2026-09-25 by `uv run bench/timing.py news` at commit `10211f3`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.9.0 | Python 3.12.13 | 0.0035 | 0.91 (0.91–0.91) | 290 | 193.9 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0075 | 1.98 (1.98–1.98) | 133 | 243.8 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0083 | 2.18 (2.17–2.19) | 121 | 1378.4 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0573 | 15.08 (15.03–15.16) | 17 | 331.8 MiB | 39.4 MiB | 22 |

## The pages extruct's interface is compared on

The tools [moving from extruct](extruct.md) scores, on its 520 pages.

Measured on 2026-09-25 by `uv run bench/timing.py extruct` at commit `10211f3`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 520 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| extruct 0.18.0 | Python 3.14.6 | 0.0519 | 26.99 (26.88–27.09) | 19 | 312.5 MiB | 25.9 MiB | 21 |
| sluicer.compat.extruct 0.9.0 | Python 3.14.6 | 0.0369 | 19.17 (19.10–19.18) | 27 | 326.3 MiB | 23.2 MiB | 17 |
