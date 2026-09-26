# /// script
# requires-python = ">=3.10"
# dependencies = ["python-dateutil==2.9.0.post0"]
# ///
"""Time every tool of a table in one run, on one machine, on the same pages.

    uv run bench/timing.py                 # every table, then docs/speed.md
    uv run bench/timing.py wcxb news       # these tables, then docs/speed.md
    uv run bench/timing.py --publish       # docs/speed.md from the last records

``bench/PREREG.md`` fixes how a second is measured, after commit ``b8f525e``
re-timed Sluicer alone "on a quieter machine" and printed its new time beside
the other tools' older ones:

- every tool of a table is timed in one run: five rounds, each running every
  tool once, the order turned by one place each round, so that a machine that
  slows down weighs on all of them;
- each run is a fresh process in the tool's own environment, which reads
  every page once untimed and then times one pass, the extraction call only
  (``bench/tools/timing_worker.py``, and ``bench/metascraper/run.js --timing``);
- printed: the median of the five passes, the fastest and the slowest beside
  it, pages per second over the median, and the largest peak resident size of
  the five processes; and the day, the platform, the CPU, its cores, the
  memory, each tool's runtime and version, and the commit.

A record is written per table into ``bench/cache/timing/``. A generator prints
a timing only through ``published``, which refuses one that is not all one
run of the commit the page names, on a clean tree, of the versions whose
answers the page scores.
"""

from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import statistics
import subprocess
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))

import run as board  # noqa: E402
import stats  # noqa: E402

ROUNDS = 5
RECORDS = HERE / "cache" / "timing"
DOC = ROOT / "docs" / "speed.md"
WORKER = HERE / "tools" / "timing_worker.py"
# The interpreter the extruct comparison runs both sides on: its own, since
# urljoin itself changed between Python versions (bench/extruct_compat.py).
EXTRUCT_PYTHON = f"{sys.version_info.major}.{sys.version_info.minor}"


@dataclass(frozen=True)
class Table:
    """Pages, and the tools a scoreboard times on them."""

    title: str
    pages: Callable[[], Path]
    tools: tuple[str, ...]
    python: str
    page: str
    # A harness of its own per tool, where the table asks more than the
    # tool's scoreboard harness does, and the environment each tool is given.
    harnesses: dict[str, str] = field(default_factory=dict)
    requirements: Callable[[str], list[str]] = board.requirements


def _wcxb() -> Path:
    import corpus

    return corpus.ensure()


def _news() -> Path:
    import news

    return news.ensure()


def _tools() -> Path:
    import tools_compare

    return tools_compare.ensure_served()


def _tools_environment(tool: str) -> list[str]:
    import tools_compare

    return tools_compare.environment(tool)


def _extruct() -> Path:
    """The pages ``bench/extruct_compat.py`` compares on, listed as it lists
    them: that script and Sluicer's readers need the checkout's own
    dependencies, so this table is measured from its environment."""
    import extruct_compat

    RECORDS.mkdir(parents=True, exist_ok=True)
    pages = RECORDS / "extruct-pages.json"
    pages.write_text(json.dumps(extruct_compat.pages(), indent=1), encoding="utf-8")
    return pages


TABLES = {
    "wcxb": Table(
        "WCXB's test pages",
        _wcxb,
        board.TOOLS,
        board.PYTHON,
        "[the scoreboard](scoreboard.md)",
    ),
    "news": Table(
        "fundus's news pages",
        _news,
        board.TOOLS,
        board.PYTHON,
        "[news in many languages](scoreboard-news.md)",
    ),
    "tools": Table(
        "WCXB's pages as served, every tool",
        _tools,
        (
            "sluicer",
            "trafilatura",
            "newspaper4k",
            "markitdown",
            "scrapling",
            "metascraper",
        ),
        board.PYTHON,
        "[every tool on the same pages](scoreboard-tools.md)",
        harnesses={
            "sluicer": "compare_sluicer",
            "trafilatura": "compare_trafilatura",
            "newspaper4k": "compare_newspaper4k",
            "markitdown": "compare_markitdown",
            "scrapling": "compare_scrapling",
        },
        requirements=_tools_environment,
    ),
    "extruct": Table(
        "the pages extruct's interface is compared on",
        _extruct,
        ("extruct", "sluicer.compat.extruct"),
        EXTRUCT_PYTHON,
        "[moving from extruct](extruct.md)",
    ),
}


def order(tools: list[str] | tuple[str, ...], round_: int) -> list[str]:
    """The tools in round ``round_``: the first round's order turned by one
    place for each round before it."""
    turn = round_ % len(tools)
    return [*tools[turn:], *tools[:turn]]


def measure(
    table: str,
    tools: list[str] | tuple[str, ...],
    run_one: Callable[[str, int], dict[str, Any]],
    *,
    pages: int,
    rounds: int = ROUNDS,
) -> dict[str, Any]:
    """Every tool timed ``rounds`` times, in one run."""
    run = uuid.uuid4().hex
    found: dict[str, dict[str, Any]] = {}
    for round_ in range(rounds):
        for tool in order(tools, round_):
            one = run_one(tool, round_)
            print(f"  round {round_ + 1}: {tool} {one['seconds']:.2f} s", flush=True)
            kept = found.setdefault(
                tool,
                {
                    "run": run,
                    "version": one["version"],
                    "runtime": one["runtime"],
                    "packages": one["packages"],
                    "install_bytes": one["install_bytes"],
                    "seconds": [],
                    "peak_rss": [],
                },
            )
            if one["version"] != kept["version"]:
                raise SystemExit(f"{tool} changed version between two rounds")
            kept["seconds"].append(one["seconds"])
            kept["peak_rss"].append(one["peak_rss"])
    return {
        "table": table,
        "pages": pages,
        "rounds": rounds,
        "run": run,
        "tools": {tool: found[tool] for tool in tools},
    }


def summary(tool: dict[str, Any], pages: int) -> dict[str, float]:
    median = statistics.median(tool["seconds"])
    return {
        "median": median,
        "fastest": min(tool["seconds"]),
        "slowest": max(tool["seconds"]),
        "per_page": median / pages,
        "pages_per_second": pages / median if median else 0.0,
        "peak_rss": max(tool["peak_rss"]),
    }


def refusals(
    record: dict[str, Any], versions: dict[str, str], commit: str
) -> list[str]:
    """Every reason a page naming ``commit`` and scoring these ``versions``
    may not print ``record``: none when it may."""
    said = []
    for tool, version in versions.items():
        timed = record["tools"].get(tool)
        if timed is None:
            said.append(f"{tool} is not in the timing")
            continue
        if timed["run"] != record["run"]:
            said.append(f"{tool} was timed in another run than the others")
        if timed["version"] != version:
            said.append(
                f"{tool} was timed at {timed['version']}, the page scores {version}"
            )
    if not (record["commit"].startswith(commit) or commit.startswith(record["commit"])):
        said.append(f"it was measured at commit {record['commit'][:7]}, not {commit}")
    if record["dirty"]:
        said.append("it was measured on a tree with uncommitted changes")
    return said


def _mib(size: float) -> str:
    return f"{size / 2**20:.1f} MiB"


def table(record: dict[str, Any]) -> list[str]:
    """A record as a page prints it: what it was measured on, and a row per
    tool."""
    pages = record["pages"]
    lines = [
        f"Measured on {record['measured']} by `uv run bench/timing.py "
        f"{record['table']}` at commit `{record['commit'][:7]}`, on "
        f"{record['platform']}, {record['cpu']}, {record['cores']} cores, "
        f"{record['memory_bytes'] / 2**30:.0f} GiB of memory: {record['rounds']} "
        "rounds, each running every tool once in a fresh process of its own "
        "environment, the order turned by one place each round. A process reads "
        "every page once untimed, then times one pass of the extraction call "
        "alone.",
        "",
        f"| tool | runtime | seconds per page | seconds for all {pages} pages, "
        f"median (fastest{stats.DASH}slowest) | pages per second | peak memory | "
        "install size | packages |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for tool, timed in record["tools"].items():
        s = summary(timed, pages)
        lines.append(
            f"| {tool} {timed['version']} | {timed['runtime']} | "
            f"{s['per_page']:.4f} | {s['median']:.2f} "
            f"({s['fastest']:.2f}{stats.DASH}{s['slowest']:.2f}) | "
            f"{s['pages_per_second']:.0f} | {_mib(s['peak_rss'])} | "
            f"{_mib(timed['install_bytes'])} | {timed['packages']} |"
        )
    return lines


def leaders(record: dict[str, Any]) -> str:
    """The fastest median pass, and the smallest install, from one run.
    A tie would make "smallest" mean "first listed"; every one is named."""

    def least(key: Callable[[str], float]) -> str:
        best = min(key(tool) for tool in record["tools"])
        return " and ".join(tool for tool in record["tools"] if key(tool) == best)

    tools = record["tools"]
    fastest = least(lambda tool: statistics.median(tools[tool]["seconds"]))
    smallest = least(lambda tool: tools[tool]["install_bytes"])
    fewest = least(lambda tool: tools[tool]["packages"])
    return (
        f"Fastest median pass: {fastest}. Smallest install: {smallest}; fewest "
        f"packages: {fewest}."
    )


def read(name: str, records: Path = RECORDS) -> dict[str, Any] | None:
    path = records / f"{name}.json"
    if not path.exists():
        return None
    loaded: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return loaded


def published(
    name: str,
    runs: dict[str, dict[str, Any]],
    commit: str,
    *,
    records: Path = RECORDS,
) -> list[str]:
    """``name``'s timing as a page scoring ``runs`` prints it, or a refusal:
    a generator publishes no second it did not measure this way."""
    record = read(name, records)
    versions = {tool: run["version"] for tool, run in runs.items()}
    said = (
        refusals(record, versions, commit)
        if record is not None
        else ["there is no timing"]
    )
    if said:
        raise SystemExit(
            f"refusing to print the {name} timing: " + "; ".join(said) + ". Run "
            f"`uv run bench/timing.py {name}` on a clean checkout of this commit."
        )
    assert record is not None
    return table(record)


# --- measuring ------------------------------------------------------------------


def _machine() -> dict[str, Any]:
    def sysctl(key: str) -> str:
        found = subprocess.run(
            ["sysctl", "-n", key],
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        return found.stdout.strip()

    if sys.platform == "darwin":
        cpu, memory = sysctl("machdep.cpu.brand_string"), int(sysctl("hw.memsize"))
    else:
        info = Path("/proc/cpuinfo").read_text(encoding="utf-8", errors="replace")
        cpu = next(
            (
                line.split(":", 1)[1].strip()
                for line in info.splitlines()
                if line.startswith("model name")
            ),
            platform.processor(),
        )
        memory = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES")
    return {
        "platform": platform.platform(),
        "cpu": cpu,
        "cores": os.cpu_count(),
        "memory_bytes": memory,
    }


def interpreter(version: str) -> str:
    """A uv-managed Python ``version``, found from outside this checkout:
    asked from inside it, uv finds the checkout's own ``.venv`` first, and an
    environment made on it holds every package the checkout's does -- extruct
    was timed with 87 packages where its pins hold 22."""
    env = {key: value for key, value in os.environ.items() if key != "VIRTUAL_ENV"}
    found = subprocess.run(
        ["uv", "python", "find", "--managed-python", version],
        cwd="/",
        env=env,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return found.stdout.strip()


def _run_one(table: Table, pages: Path) -> Callable[[str, int], dict[str, Any]]:
    python = interpreter(table.python)

    def run_one(tool: str, _round: int) -> dict[str, Any]:
        env = dict(os.environ)
        if tool == "metascraper":
            env["NODE_PATH"] = str(board._install_metascraper())
            command = [
                "node",
                str(HERE / "metascraper" / "run.js"),
                "--timing",
                str(pages),
            ]
        else:
            harness = [table.harnesses[tool]] if tool in table.harnesses else []
            command = [
                "uv", "run", "--no-project", "--python", python,
                *table.requirements(tool), "python", str(WORKER), tool, str(pages),
                *harness,
            ]  # fmt: skip
        found = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        answer: dict[str, Any] = json.loads(found.stdout.strip().splitlines()[-1])
        return answer

    return run_one


def run_table(name: str) -> dict[str, Any]:
    table = TABLES[name]
    pages = table.pages()
    count = len(json.loads(pages.read_text(encoding="utf-8")))
    print(f"timing {name}: {', '.join(table.tools)} on {count} pages", flush=True)
    record = measure(name, table.tools, _run_one(table, pages), pages=count)
    record.update(
        _machine(),
        measured=datetime.date.today().isoformat(),
        commit=board._git("rev-parse", "HEAD"),
        dirty=bool(board.changed()),
        python=table.python,
    )
    RECORDS.mkdir(parents=True, exist_ok=True)
    (RECORDS / f"{name}.json").write_text(
        json.dumps(record, indent=1) + "\n", encoding="utf-8"
    )
    return record


def publish() -> None:
    """``docs/speed.md``: every table's record, each all one run of this
    commit on a clean tree, or none."""
    commit = board._git("rev-parse", "--short", "HEAD")
    sections = []
    for name, table in TABLES.items():
        record = read(name)
        if record is None:
            raise SystemExit(f"no {name} timing: run `uv run bench/timing.py {name}`")
        versions = {tool: record["tools"][tool]["version"] for tool in record["tools"]}
        missing = [tool for tool in table.tools if tool not in versions]
        said = [f"{tool} is not in the timing" for tool in missing]
        said += refusals(record, versions, commit)
        if said:
            raise SystemExit(f"refusing to print the {name} timing: " + "; ".join(said))
        heading = table.title[0].upper() + table.title[1:]
        sections += [f"## {heading}", "", *table_lines(name, record)]
    lines = [
        "# Speed and weight",
        "",
        "How long each tool takes on the scoreboards' pages, how much memory it",
        "holds, and how much it installs, measured one way for every tool, as",
        "[`bench/PREREG.md`](https://github.com/Gi0tto/sluicer/blob/main/bench/PREREG.md)",
        'fixes it under "How a second is measured". Every tool of a table was',
        "timed in one run, on one machine, on the same pages; a scoreboard",
        "prints no second measured otherwise. Regenerated from commit",
        f"`{commit}` by `uv run bench/timing.py`.",
        "",
        "Install size counts every file each package of the tool's environment",
        "installs, bytecode caches left out (for Sluicer, installed editable, the",
        "files of its package); packages count them, the interpreter's pip,",
        "setuptools and wheel left out, and metascraper's every package under",
        "`node_modules`. Peak memory is the process's peak resident size, the",
        "interpreter and every page read into memory included.",
        "",
        *sections,
    ]
    DOC.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {DOC.relative_to(ROOT)}")


def table_lines(name: str, record: dict[str, Any]) -> list[str]:
    return [
        f"The tools {TABLES[name].page} scores, on its {record['pages']} pages.",
        "",
        *table(record),
        "",
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tables", nargs="*", help=f"of {', '.join(TABLES)}")
    parser.add_argument(
        "--publish", action="store_true", help="write docs/speed.md, time nothing"
    )
    args = parser.parse_args()
    unknown = sorted(set(args.tables) - set(TABLES))
    if unknown:
        parser.error(f"no such table: {', '.join(unknown)}")
    if not args.publish:
        for name in args.tables or list(TABLES):
            run_table(name)
    publish()


if __name__ == "__main__":
    main()
