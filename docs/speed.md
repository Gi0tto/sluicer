# Speed and weight

How long each tool takes on the scoreboards' pages, how much memory it
holds, and how much it installs, measured one way for every tool, as
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
fixes it under "How a second is measured". Every tool of a table was
timed in one run, on one machine, on the same pages; a scoreboard
prints no second measured otherwise. Regenerated from commit
`a6e42e6` by `uv run bench/timing.py`.

Install size counts every file each package of the tool's environment
installs, bytecode caches left out (for Sluicer, installed editable, the
files of its package); packages count them, the interpreter's pip,
setuptools and wheel left out, and metascraper's every package under
`node_modules`. Peak memory is the process's peak resident size, the
interpreter and every page read into memory included.

## WCXB's test pages

The tools [the scoreboard](scoreboard.md) scores, on its 511 pages.

Measured on 2026-09-25 by `uv run bench/timing.py wcxb` at commit `a6e42e6`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.8.0 | Python 3.12.13 | 0.0020 | 1.02 (1.01–1.02) | 501 | 90.2 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0269 | 13.76 (13.74–13.95) | 37 | 168.2 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0049 | 2.51 (2.51–2.52) | 204 | 714.0 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0570 | 29.11 (29.03–29.17) | 18 | 217.2 MiB | 39.4 MiB | 22 |

## Fundus's news pages

The tools [news in many languages](scoreboard-news.md) scores, on its 263 pages.

Measured on 2026-09-25 by `uv run bench/timing.py news` at commit `a6e42e6`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.8.0 | Python 3.12.13 | 0.0035 | 0.91 (0.91–0.91) | 290 | 192.6 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0076 | 1.99 (1.97–1.99) | 132 | 245.7 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0083 | 2.18 (2.17–2.19) | 121 | 1428.9 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0572 | 15.04 (14.99–15.23) | 17 | 331.8 MiB | 39.4 MiB | 22 |

## The pages extruct's interface is compared on

The tools [moving from extruct](extruct.md) scores, on its 520 pages.

Measured on 2026-09-25 by `uv run bench/timing.py extruct` at commit `a6e42e6`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 520 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| extruct 0.18.0 | Python 3.14.6 | 0.0520 | 27.03 (26.85–27.06) | 19 | 314.0 MiB | 25.9 MiB | 21 |
| sluicer.compat.extruct 0.8.0 | Python 3.14.6 | 0.0369 | 19.16 (19.08–19.82) | 27 | 329.3 MiB | 23.2 MiB | 17 |
