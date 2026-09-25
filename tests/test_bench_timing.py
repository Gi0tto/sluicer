"""A second is measured one way, and a scoreboard prints no other
(``bench/PREREG.md``, "How a second is measured").

Commit ``b8f525e`` re-timed Sluicer alone "on a quieter machine" and printed
its new time beside the other tools' older ones. These hold
``bench/timing.py`` to the rule: every tool of a table in one run, five
rounds whose order turns, the median with the fastest and slowest, and a
refusal to publish a timing that is not all one run of this commit. The
harness is not in the sdist: without it, this skips.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

BENCH = Path(__file__).resolve().parent.parent / "bench"
if not (BENCH / "timing.py").exists():
    pytest.skip("the benchmark harness is not in the sdist", allow_module_level=True)
pytest.importorskip("dateutil")
sys.path.insert(0, str(BENCH))

import timing  # noqa: E402

TOOLS = ["sluicer", "trafilatura", "metascraper", "newspaper4k"]
MACHINE = {
    "platform": "macOS-26.0-arm64",
    "cpu": "Apple M4",
    "cores": 10,
    "memory_bytes": 16 * 2**30,
}


def test_each_round_turns_the_order_by_one_place():
    orders = [timing.order(TOOLS, n) for n in range(5)]
    assert orders[0] == TOOLS
    assert orders[1] == ["trafilatura", "metascraper", "newspaper4k", "sluicer"]
    assert orders[4] == orders[0]
    # Over four rounds every tool runs first once.
    assert {order[0] for order in orders[:4]} == set(TOOLS)


def _fake_runs():
    """A fake tool process: the seconds it took depend on the round, and it
    records the order it was called in."""
    calls = []

    def run_one(tool: str, round_: int) -> dict:
        calls.append((round_, tool))
        return {
            "tool": tool,
            "version": {"sluicer": "0.7.1"}.get(tool, "1.0"),
            "runtime": "Python 3.12.0",
            "seconds": [3.0, 1.0, 2.0, 5.0, 4.0][round_],
            "peak_rss": 1000 + round_,
            "packages": 3,
            "install_bytes": 5_000_000,
        }

    return run_one, calls


def test_every_tool_is_timed_in_every_round_of_one_run():
    run_one, calls = _fake_runs()
    found = timing.measure("wcxb", TOOLS, run_one, pages=100, rounds=5)
    assert [tool for _, tool in calls[:4]] == TOOLS
    assert [tool for _, tool in calls[4:8]] == TOOLS[1:] + TOOLS[:1]
    assert len(calls) == 20
    runs = {tool["run"] for tool in found["tools"].values()}
    assert len(runs) == 1 and found["run"] in runs


def test_the_median_is_printed_with_the_fastest_and_the_slowest():
    run_one, _ = _fake_runs()
    record = timing.measure("wcxb", TOOLS, run_one, pages=100, rounds=5)
    summary = timing.summary(record["tools"]["sluicer"], record["pages"])
    assert (summary["median"], summary["fastest"], summary["slowest"]) == (
        3.0,
        1.0,
        5.0,
    )
    assert summary["per_page"] == pytest.approx(0.03)
    assert summary["pages_per_second"] == pytest.approx(100 / 3)
    # The largest peak of the five processes.
    assert summary["peak_rss"] == 1004


def _record(**changes):
    run_one, _ = _fake_runs()
    record = timing.measure("wcxb", TOOLS, run_one, pages=100, rounds=5)
    record.update(MACHINE, commit="abc1234def", dirty=False, measured="2026-09-25")
    record.update(changes)
    return record


VERSIONS = {"sluicer": "0.7.1", "trafilatura": "1.0", "metascraper": "1.0"}


def test_a_timing_of_this_commit_all_one_run_is_published():
    versions = {**VERSIONS, "newspaper4k": "1.0"}
    assert timing.refusals(_record(), versions, "abc1234def") == []


def test_a_timing_is_refused_for_each_reason_prereg_gives():
    versions = {**VERSIONS, "newspaper4k": "1.0"}
    # A tool of the table missing from the record.
    record = _record()
    del record["tools"]["newspaper4k"]
    assert "newspaper4k" in " ".join(timing.refusals(record, versions, "abc1234def"))
    # A tool timed in another run than the others.
    record = _record()
    record["tools"]["trafilatura"]["run"] = "another"
    assert "another run" in " ".join(timing.refusals(record, versions, "abc1234def"))
    # A version other than the one whose answers the page scores.
    said = timing.refusals(_record(), {**versions, "sluicer": "0.7.0"}, "abc1234def")
    assert "0.7.0" in " ".join(said)
    # A commit other than the one the page names.
    assert "commit" in " ".join(timing.refusals(_record(), versions, "fff0000"))
    # A tree with uncommitted changes.
    said = timing.refusals(_record(dirty=True), versions, "abc1234def")
    assert "uncommitted" in " ".join(said)


def test_a_generator_refuses_rather_than_prints_a_timing_it_may_not(tmp_path):
    runs = {tool: {"tool": tool, "version": "1.0"} for tool in TOOLS}
    with pytest.raises(SystemExit, match=r"bench/timing\.py wcxb"):
        timing.published("wcxb", runs, "abc1234def", records=tmp_path)


def test_the_table_says_the_machine_and_every_version():
    lines = "\n".join(timing.table(_record()))
    for said in ("Apple M4", "10 cores", "16 GiB", "Python 3.12.0", "abc1234"):
        assert said in lines
    row = next(line for line in lines.splitlines() if line.startswith("| sluicer"))
    # Seconds per page, the median pass, its fastest and slowest, pages per
    # second, peak memory, install size, packages.
    assert "| 0.0300 |" in row and "| 3.00 (1.00\u20135.00) |" in row
    assert "| 4.8 MiB |" in row and row.endswith("| 3 |")


def test_a_tool_s_interpreter_is_found_outside_this_checkout(monkeypatch):
    """Asked from the checkout, uv finds its .venv first, and an environment
    made on it holds every package of the checkout's own: extruct was timed
    with 87 packages installed where its pins hold 22."""
    asked = []

    def run(command, **kwargs):
        asked.append((command, kwargs))

        class Found:
            stdout = "/managed/bin/python3.14\n"

        return Found()

    monkeypatch.setattr(timing.subprocess, "run", run)
    assert timing.interpreter("3.14") == "/managed/bin/python3.14"
    command, kwargs = asked[0]
    assert command[:4] == ["uv", "python", "find", "--managed-python"]
    assert kwargs["cwd"] == "/" and "VIRTUAL_ENV" not in kwargs["env"]


def test_the_extruct_interface_is_timed_with_the_microformats_it_reads():
    """Its default call reads microformats, the one reader behind an extra:
    timed on the base install, every call raised MicroformatsExtraMissing
    and the table printed how fast it raised, 5 s against extruct's 78."""
    import run as board

    assert "mf2py==2.0.2" in board.requirements("sluicer.compat.extruct")
    assert "mf2py==2.0.2" not in board.requirements("sluicer")
    harness = (BENCH / "tools" / "compat_tool.py").read_text(encoding="utf-8")
    assert "import mf2py" in harness
