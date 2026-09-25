"""Publish, beside the try page, the files it runs Sluicer from.

docs/try/index.html runs Sluicer in the reader's browser, in Pyodide, on the
HTML they paste. It needs the wheel of the commit the site is built from, the
bridge the npm package calls into, and an example page. They are built, not
kept in docs/: this hook, named in mkdocs.yml, runs js/scripts/build_wheel.py
(the npm package's own build, which refuses a version other than pyproject's)
and adds each file under try/. ``try_files`` is what scripts/check_try_page.py
serves the page with, so the page is checked with the files the site gets.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mkdocs.config.defaults import MkDocsConfig
    from mkdocs.structure.files import Files

ROOT = Path(__file__).resolve().parent.parent
JS = ROOT / "js"


def try_files() -> dict[str, Path]:
    """Build the wheel, and name each file the try page reads, by its path
    under try/."""
    subprocess.run(
        [sys.executable, str(JS / "scripts" / "build_wheel.py")],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    built = JS / "python"
    return {
        **{f"try/{path.name}": path for path in sorted(built.iterdir())},
        "try/bridge.py": JS / "bridge.py",
        "try/example.html": ROOT / "examples" / "brake-pads.html",
    }


def on_files(files: Files, config: MkDocsConfig) -> Files:
    from mkdocs.structure.files import File

    for uri, path in try_files().items():
        files.append(File.generated(config, uri, abs_src_path=str(path)))
    return files
