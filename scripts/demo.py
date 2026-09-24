# /// script
# requires-python = ">=3.10"
# dependencies = ["sluicer", "brotli==1.1.0"]
#
# [tool.uv.sources]
# sluicer = { path = "..", editable = true }
# ///
"""Record the README's demo: an extractor meeting a real redesign.

    uv run scripts/demo.py

A software directory, SourceForge's, as the Wayback Machine captured it: two
pages of January 2016 to learn from, one of February 2016 that keeps the
template, and one of June 2024 after the site's redesign. The captures are
fetched from the archive once, as the drift benchmark fetches them -- its own
``bench/drift/wayback.py``, which undoes the archive's compression -- into
``bench/cache/demo/``, and never committed.

Every command below is run for real and its output recorded as it came, into
``docs/assets/demo.cast`` (asciicast v2); only the typing is paced. The cast is
then drawn as ``docs/assets/demo.gif`` by asciinema's agg, version 1.9.0, found
on the PATH or at ``$AGG``.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ROOT / "bench" / "cache" / "demo"
ASSETS = ROOT / "docs" / "assets"
AGG_RELEASE = "https://github.com/asciinema/agg/releases/tag/v1.9.0"
WIDTH, HEIGHT = 118, 30

# The drift benchmark's pair sourceforge-net-directory, short and long. The
# 2024 capture of the directory redirects to its Windows section.
DIRECTORY = "https://sourceforge.net/directory/"
CAPTURES = {
    "2016-01-11.html": "20160111022229",
    "2016-01-17.html": "20160117192101",
    "2016-02-15.html": "20160215235904",
    "2024-06-02.html": "20240602074646",
}

# What is typed, in order: a line starting "#" is a comment for the reader.
SCRIPT = [
    "# A software directory, as the Wayback Machine kept it. Learn from January 2016:",
    "sluicer compile 2016-01-11.html 2016-01-17.html -o directory.json",
    "# A month later, the same template: 25 rows, exit 0.",
    "sluicer run directory.json 2016-02-15.html > rows.json; echo exit $?",
    "# 2024, after the redesign. No nulls for weeks: it fails, loudly.",
    "sluicer run directory.json 2024-06-02.html > rows.json; echo exit $?",
    "# heal says where the listing and each field went, and on what evidence:",
    "sluicer heal directory.json 2024-06-02.html 2>&1 >/dev/null"
    " | grep -E '^(container|member|moved)'",
]


def fetch() -> None:
    """The captures, from the archive, once, as the page's server sent them."""
    sys.path.insert(0, str(ROOT / "bench" / "drift"))
    from wayback import snapshot

    PAGES.mkdir(parents=True, exist_ok=True)
    for name, when in CAPTURES.items():
        target = PAGES / name
        if target.exists():
            continue
        captured = snapshot(DIRECTORY, when)
        if captured is None:
            raise SystemExit(f"the archive holds no capture of {DIRECTORY} at {when}")
        html = captured.html
        target.write_bytes(html if isinstance(html, bytes) else html.encode("utf-8"))
        print(f"fetched {name}, landed at {captured.landed}")


def record() -> Path:
    """Run each line in the pages' folder and write the cast of it."""
    sluicer = Path(sys.executable).parent / "sluicer"
    environment = {
        **os.environ,
        "PATH": f"{sluicer.parent}{os.pathsep}{os.environ['PATH']}",
    }
    events: list[list[object]] = []
    clock = 0.4

    def say(text: str, after: float = 0.0) -> None:
        nonlocal clock
        clock += after
        events.append([round(clock, 3), "o", text])

    for line in SCRIPT:
        say("\x1b[1;32m$\x1b[0m ", 0.5)
        colour = "\x1b[2m" if line.startswith("#") else ""
        say(colour)
        for character in line:
            say(character, 0.018 if line.startswith("#") else 0.03)
        say("\x1b[0m\r\n" if colour else "\r\n", 0.2)
        if line.startswith("#"):
            continue
        result = subprocess.run(
            line,
            shell=True,
            cwd=PAGES,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
            encoding="utf-8",
        )
        output = (result.stderr + result.stdout).replace(str(PAGES) + os.sep, "")
        for out_line in output.splitlines():
            say(out_line + "\r\n", 0.06)
        say("", 1.6)
    say("", 3.0)
    cast = ASSETS / "demo.cast"
    header = {
        "version": 2,
        "width": WIDTH,
        "height": HEIGHT,
        "env": {"TERM": "xterm-256color"},
    }
    lines = [json.dumps(header)] + [json.dumps(event) for event in events]
    cast.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return cast


def draw(cast: Path) -> None:
    agg = os.environ.get("AGG") or shutil.which("agg")
    if agg is None:
        raise SystemExit(f"agg is needed to draw the cast: {AGG_RELEASE}")
    subprocess.run(
        [
            agg,
            "--theme",
            "monokai",
            "--font-size",
            "16",
            "--line-height",
            "1.3",
            "--fps-cap",
            "20",
            "--last-frame-duration",
            "6",
            str(cast),
            str(ASSETS / "demo.gif"),
        ],
        check=True,
        capture_output=True,
    )


def main() -> None:
    fetch()
    draw(record())
    print("wrote docs/assets/demo.cast and docs/assets/demo.gif")


if __name__ == "__main__":
    main()
