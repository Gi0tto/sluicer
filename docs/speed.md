# Speed and weight

How long each tool takes on the scoreboards' pages, how much memory it
holds, and how much it installs, measured one way for every tool, as
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
fixes it under "How a second is measured". Every tool of a table was
timed in one run, on one machine, on the same pages; a scoreboard
prints no second measured otherwise. Regenerated from commit
`f042855` by `uv run bench/timing.py`.

Install size counts every file each package of the tool's environment
installs, bytecode caches left out (for Sluicer, installed editable, the
files of its package); packages count them, the interpreter's pip,
setuptools and wheel left out, and metascraper's every package under
`node_modules`. Peak memory is the process's peak resident size, the
interpreter and every page read into memory included.

## WCXB's test pages

The tools [the scoreboard](scoreboard.md) scores, on its 511 pages.

Measured on 2026-09-25 by `uv run bench/timing.py wcxb` at commit `f042855`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | Python 3.12.13 | 0.0021 | 1.08 (1.02–1.12) | 474 | 90.2 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0290 | 14.83 (14.11–16.06) | 34 | 169.5 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0054 | 2.76 (2.55–3.16) | 185 | 718.8 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0602 | 30.77 (29.35–35.35) | 17 | 217.8 MiB | 39.4 MiB | 22 |

## Fundus's news pages

The tools [news in many languages](scoreboard-news.md) scores, on its 263 pages.

Measured on 2026-09-25 by `uv run bench/timing.py news` at commit `f042855`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.7.1 | Python 3.12.13 | 0.0046 | 1.21 (0.96–1.25) | 217 | 195.6 MiB | 19.5 MiB | 5 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0092 | 2.42 (2.05–2.58) | 109 | 247.2 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0117 | 3.07 (2.22–3.16) | 86 | 1398.5 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0690 | 18.14 (15.98–19.39) | 14 | 333.0 MiB | 39.4 MiB | 22 |

## The pages extruct's interface is compared on

The tools [moving from extruct](extruct.md) scores, on its 520 pages.

Measured on 2026-09-25 by `uv run bench/timing.py extruct` at commit `f042855`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 520 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| extruct 0.18.0 | Python 3.14.6 | 0.0571 | 29.69 (27.91–38.33) | 18 | 309.5 MiB | 25.9 MiB | 21 |
| sluicer.compat.extruct 0.7.1 | Python 3.14.6 | 0.0427 | 22.21 (21.56–23.51) | 23 | 326.7 MiB | 23.2 MiB | 17 |
