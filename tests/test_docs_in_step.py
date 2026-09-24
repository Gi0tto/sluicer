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


def test_the_readme_s_quick_start_prints_what_it_says(monkeypatch):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    section = readme.split("## Quick start", 1)[1].split("\n## ", 1)[0]
    blocks = re.findall(r"```python\n(.*?)```", section, re.DOTALL)
    assert blocks, "the quick start has no python block"
    monkeypatch.chdir(ROOT)
    parser = doctest.DocTestParser()
    runner = doctest.DocTestRunner(optionflags=doctest.ELLIPSIS)
    for number, block in enumerate(blocks):
        test = parser.get_doctest(block, {}, f"README quick start {number}", None, 0)
        runner.run(test)
    assert runner.failures == 0, f"{runner.failures} line(s) of the quick start differ"
    assert os.path.exists(ROOT / "examples" / "brake-pads.html")
