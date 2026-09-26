"""Build the wheel the npm package installs into Pyodide, from this checkout.

Run from anywhere, with uv on PATH (``npm run build`` and ``npm pack`` run it):

    python3 js/scripts/build_wheel.py

It builds Sluicer's wheel with the project's own build backend (``uv build``),
the file PyPI would get, and puts it in ``js/python/`` beside ``wheel.json``,
which names the file and the requirements ``index.js`` loads before it: the
base install's, and each extra's. It refuses to build when ``js/package.json``
and ``pyproject.toml`` state different versions: the npm package is the
Python one, and says so by its number. The licence files are copied in beside
it, since the wheel carries two files under licences other than MIT.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

JS = Path(__file__).resolve().parent.parent
ROOT = JS.parent
OUT = JS / "python"
# Base requirements only fetching uses: this package fetches nothing, and
# Pyodide ships none of them. protego, the robots.txt parser, joined the base
# install with fetching over plain HTTP, and every start failed on it.
FETCHING_ONLY = frozenset({"protego"})
# Base requirements only markdown uses, which Pyodide ships none of either:
# trafilatura joined the base install in 0.10, and in Pyodide it stays what the
# `markdown` option installs from PyPI through micropip (index.js), since a
# start that asked Pyodide's repository for it would fail.
MARKDOWN_ONLY = frozenset({"trafilatura"})
# A requirement for some Pythons only, "tomli; python_version < '3.11'", is
# judged against the Python Pyodide runs, which its version names: 314.0.7 is
# Python 3.14.
_PYTHON_MARKER = re.compile(
    r"\s*python_version\s*(<=|>=|<|>|==|!=)\s*'(\d+)\.(\d+)'\s*"
)


def main() -> int:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    found = re.search(r'^version = "(.+)"$', pyproject, re.MULTILINE)
    assert found, "pyproject.toml states no version"
    version = found[1]
    stated = json.loads((JS / "package.json").read_text(encoding="utf-8"))["version"]
    if stated != version:
        print(
            f"js/package.json says {stated}, pyproject.toml says {version}:"
            " the npm package must be the Python package's version",
            file=sys.stderr,
        )
        return 1
    with tempfile.TemporaryDirectory() as scratch:
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", scratch, str(ROOT)],
            check=True,
        )
        [built] = Path(scratch).glob("sluicer-*.whl")
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir()
        wheel = OUT / built.name
        shutil.copyfile(built, wheel)
    requires, extras = _requirements(wheel, version, _pyodide_python())
    requires, fetching = _loaded_at_start(requires, extras)
    (OUT / "wheel.json").write_text(
        json.dumps(
            {
                "file": wheel.name,
                "version": version,
                "requires": requires,
                "fetching": fetching,
                "extras": extras,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    for name in ("LICENSE", "NOTICE"):
        shutil.copyfile(ROOT / name, JS / name)
    if (JS / "LICENSES").exists():
        shutil.rmtree(JS / "LICENSES")
    shutil.copytree(ROOT / "LICENSES", JS / "LICENSES")
    print(f"{wheel.relative_to(ROOT)} ({wheel.stat().st_size:,} bytes)")
    return 0


def _pyodide_python() -> tuple[int, int]:
    """The Python the pinned Pyodide runs: its version 314.0.7 is 3.14."""
    pinned = json.loads((JS / "package.json").read_text(encoding="utf-8"))
    major = pinned["dependencies"]["pyodide"].split(".")[0]
    if not re.fullmatch(r"3\d{2}", major):
        raise SystemExit(f"a Pyodide version this script cannot read: {major}")
    return 3, int(major[1:])


def _requirements(
    wheel: Path, version: str, python: tuple[int, int]
) -> tuple[list[str], dict[str, list[str]]]:
    """The wheel's base requirements, and each extra's, from its METADATA:
    those for another Python than Pyodide's are left out."""
    with zipfile.ZipFile(wheel) as archive:
        metadata = archive.read(f"sluicer-{version}.dist-info/METADATA").decode()
    requires: list[str] = []
    extras: dict[str, list[str]] = {}
    for line in metadata.splitlines():
        if not line.startswith("Requires-Dist: "):
            continue
        requirement, _, marker = line.removeprefix("Requires-Dist: ").partition(";")
        extra = re.fullmatch(r"\s*extra == '([\w-]+)'\s*", marker)
        pythons = _PYTHON_MARKER.fullmatch(marker)
        if pythons:
            wanted = (int(pythons[2]), int(pythons[3]))
            holds = {
                "<": python < wanted,
                "<=": python <= wanted,
                ">": python > wanted,
                ">=": python >= wanted,
                "==": python == wanted,
                "!=": python != wanted,
            }
            if holds[pythons[1]]:
                requires.append(requirement.strip())
            continue
        if marker and not extra:
            raise SystemExit(f"a marker this script cannot read: {line}")
        if extra:
            extras.setdefault(extra[1], []).append(requirement.strip())
        else:
            requires.append(requirement.strip())
    return requires, extras


def _loaded_at_start(
    requires: list[str], extras: dict[str, list[str]]
) -> tuple[list[str], list[str]]:
    """The base requirements every start loads from Pyodide's repository, and
    those only fetching uses. What only markdown uses is left to the
    ``markdown`` extra, which must name it."""
    markdown = {_name(r) for r in extras.get("markdown", [])}
    for requirement in requires:
        if _name(requirement) in MARKDOWN_ONLY and _name(requirement) not in markdown:
            raise SystemExit(f"the markdown extra no longer names {requirement}")
    fetching = [r for r in requires if _name(r) in FETCHING_ONLY]
    left_out = FETCHING_ONLY | MARKDOWN_ONLY
    return [r for r in requires if _name(r) not in left_out], fetching


def _name(requirement: str) -> str:
    """A requirement's project name, as its specifier leaves it."""
    return re.split(r"[<>=!~ ;\[]", requirement, maxsplit=1)[0].lower()


if __name__ == "__main__":
    sys.exit(main())
