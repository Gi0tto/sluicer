"""The README says what the code does, and the site's home says what it says.

The README's quick start is run as it is written, so its output cannot fall
behind the library. And ``docs/index.md`` is the README with its links made
links within the site (``scripts/docs_home.py``): it had fallen behind twice
while it was kept by hand, once by three changes, once by a licence.
"""

from __future__ import annotations

import doctest
import importlib.util
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _generator():
    spec = importlib.util.spec_from_file_location(
        "docs_home", ROOT / "scripts" / "docs_home.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_docs_home_is_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    home = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert home == _generator().home(readme), "run: uv run scripts/docs_home.py"


def test_the_docs_home_leaves_no_link_into_the_repository_s_docs():
    home = (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    assert "blob/main/docs/" not in home


def _run_python_blocks(text: str, name: str) -> None:
    blocks = re.findall(r"```python\n(.*?)```", text, re.DOTALL)
    assert blocks, f"{name} has no python block"
    parser = doctest.DocTestParser()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for number, block in enumerate(blocks):
        runner.run(parser.get_doctest(block, {}, f"{name} {number}", None, 0))
    assert runner.failures == 0, f"{runner.failures} line(s) of {name} differ"


def test_the_readme_s_quick_start_prints_what_it_says(monkeypatch):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    monkeypatch.chdir(ROOT)
    assert os.path.exists(ROOT / "examples" / "brake-pads.html")
    _run_python_blocks(section, "the README's quick start")


def test_the_getting_started_guide_prints_what_it_says(monkeypatch):
    guide = (ROOT / "docs" / "getting-started.md").read_text(encoding="utf-8")
    monkeypatch.chdir(ROOT)
    _run_python_blocks(guide, "the getting started guide")


def _assets():
    spec = importlib.util.spec_from_file_location(
        "readme_assets", ROOT / "scripts" / "readme_assets.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_readme_s_numbers_are_the_scoreboards():
    """The dates chart said metascraper found 0.811 and its alt text 0.384,
    and the README 1.4 s where the scoreboard said 1.50: the alt texts and the
    timings were written by hand, the charts from the scoreboards."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert readme == _assets().readme(readme), "run: uv run scripts/readme_assets.py"


def test_every_number_in_the_readme_s_scoreboard_table_is_in_its_scoreboard():
    """The README's one benchmark table is written by hand, one row per
    scoreboard: each number in a row must be in the scoreboard it links to,
    so a number copied wrong, or left behind by a new run, fails here."""
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Measured, losses included", 1)[1].split("\n## ", 1)[0]
    rows = [line for line in section.splitlines() if line.startswith("| [")]
    assert len(rows) == 7
    for row in rows:
        page = re.search(r"/docs/([\w-]+\.md)\)", row)
        assert page is not None, row
        board = (ROOT / "docs" / page.group(1)).read_text(encoding="utf-8")
        for number in re.findall(r"\d[\d,]*(?:\.\d+)?", row.split(")", 1)[1]):
            assert re.search(rf"(?<![\d.,]){re.escape(number)}(?![\d]|\.\d)", board), (
                f"{number} is not in {page.group(1)}"
            )
