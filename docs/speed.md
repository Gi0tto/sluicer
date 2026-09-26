# Speed and weight

How long each tool takes on the scoreboards' pages, how much memory it
holds, and how much it installs, measured one way for every tool, as
[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)
fixes it under "How a second is measured". Every tool of a table was
timed in one run, on one machine, on the same pages; a scoreboard
prints no second measured otherwise. Regenerated from commit
`5e97f6b` by `uv run bench/timing.py`.

Install size counts every file each package of the tool's environment
installs, bytecode caches left out (for Sluicer, installed editable, the
files of its package); packages count them, the interpreter's pip,
setuptools and wheel left out, and metascraper's every package under
`node_modules`. Peak memory is the process's peak resident size, the
interpreter and every page read into memory included.

## WCXB's test pages

The tools [the scoreboard](scoreboard.md) scores, on its 511 pages.

Measured on 2026-09-26 by `uv run bench/timing.py wcxb` at commit `5e97f6b`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 511 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.10.0 | Python 3.12.13 | 0.0015 | 0.78 (0.78–0.79) | 657 | 92.3 MiB | 58.7 MiB | 21 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0270 | 13.81 (13.70–13.82) | 37 | 168.1 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0049 | 2.50 (2.49–2.51) | 204 | 707.9 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0571 | 29.19 (29.13–29.55) | 18 | 217.2 MiB | 39.4 MiB | 22 |

## Fundus's news pages

The tools [news in many languages](scoreboard-news.md) scores, on its 263 pages.

Measured on 2026-09-26 by `uv run bench/timing.py news` at commit `5e97f6b`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 263 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.10.0 | Python 3.12.13 | 0.0024 | 0.64 (0.64–0.65) | 409 | 168.6 MiB | 58.7 MiB | 21 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0075 | 1.98 (1.98–1.99) | 133 | 245.3 MiB | 58.2 MiB | 17 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0083 | 2.18 (2.17–2.22) | 121 | 2772.8 MiB | 55.5 MiB | 125 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0574 | 15.10 (15.02–15.24) | 17 | 331.6 MiB | 39.4 MiB | 22 |

## WCXB's pages as served, every tool

The tools [every tool on the same pages](scoreboard-tools.md) scores, on its 360 pages.

Measured on 2026-09-26 by `uv run bench/timing.py tools` at commit `5e97f6b`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 360 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| sluicer 0.10.0 | Python 3.12.13 | 0.0246 | 8.85 (8.82–8.86) | 41 | 241.0 MiB | 58.7 MiB | 21 |
| trafilatura 2.2.0 | Python 3.12.13 | 0.0567 | 20.41 (20.36–20.51) | 18 | 287.1 MiB | 58.2 MiB | 17 |
| newspaper4k 0.9.6 | Python 3.12.13 | 0.0641 | 23.07 (22.87–23.13) | 16 | 333.3 MiB | 39.4 MiB | 22 |
| markitdown 0.1.8 | Python 3.12.13 | 0.0267 | 9.60 (9.52–10.12) | 37 | 223.1 MiB | 129.3 MiB | 20 |
| scrapling 0.4.15 | Python 3.12.13 | 0.0201 | 7.23 (7.17–7.27) | 50 | 352.1 MiB | 296.8 MiB | 26 |
| metascraper 5.58.1 | Node 26.1.0 | 0.0077 | 2.79 (2.77–2.83) | 129 | 990.3 MiB | 55.5 MiB | 125 |

## The pages extruct's interface is compared on

The tools [moving from extruct](extruct.md) scores, on its 533 pages.

Measured on 2026-09-26 by `uv run bench/timing.py extruct` at commit `5e97f6b`, on macOS-26.6.2-arm64-arm-64bit-Mach-O, Apple M4, 10 cores, 16 GiB of memory: 5 rounds, each running every tool once in a fresh process of its own environment, the order turned by one place each round. A process reads every page once untimed, then times one pass of the extraction call alone.

| tool | runtime | seconds per page | seconds for all 533 pages, median (fastest–slowest) | pages per second | peak memory | install size | packages |
|---|---|---|---|---|---|---|---|
| extruct 0.18.0 | Python 3.14.6 | 0.0507 | 27.05 (26.96–27.21) | 20 | 319.1 MiB | 25.9 MiB | 21 |
| sluicer.compat.extruct 0.10.0 | Python 3.14.6 | 0.0360 | 19.21 (19.10–19.35) | 28 | 335.7 MiB | 60.6 MiB | 29 |
