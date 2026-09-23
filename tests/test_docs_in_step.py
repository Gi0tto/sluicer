"""The site's home repeats the README's commands, and must not fall behind it.

``docs/index.md`` cannot be a link to the README -- the README's relative links
would break under ``docs/`` -- so it is a copy, and it had fallen three
changes behind before this test.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _commands(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    section = text.split("## Use it", 1)[1]
    block = re.search(r"```bash\n(.*?)```", section, re.DOTALL)
    assert block, f"{path.name} has no command block under Use it"
    return block.group(1)


def test_the_docs_home_lists_the_readmes_commands():
    assert _commands(ROOT / "docs" / "index.md") == _commands(ROOT / "README.md")
