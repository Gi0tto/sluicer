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
    requires, extras = _requirements(wheel, version)
    (OUT / "wheel.json").write_text(
        json.dumps(
            {
                "file": wheel.name,
                "version": version,
                "requires": requires,
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


def _requirements(wheel: Path, version: str) -> tuple[list[str], dict[str, list[str]]]:
    """The wheel's base requirements, and each extra's, from its METADATA."""
    with zipfile.ZipFile(wheel) as archive:
        metadata = archive.read(f"sluicer-{version}.dist-info/METADATA").decode()
    requires: list[str] = []
    extras: dict[str, list[str]] = {}
    for line in metadata.splitlines():
        if not line.startswith("Requires-Dist: "):
            continue
        requirement, _, marker = line.removeprefix("Requires-Dist: ").partition(";")
        extra = re.fullmatch(r"\s*extra == '([\w-]+)'\s*", marker)
        if marker and not extra:
            raise SystemExit(f"a marker this script cannot read: {line}")
        if extra:
            extras.setdefault(extra[1], []).append(requirement.strip())
        else:
            requires.append(requirement.strip())
    return requires, extras


if __name__ == "__main__":
    sys.exit(main())
