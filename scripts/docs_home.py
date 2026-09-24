# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Write ``docs/index.md``, the documentation's home, from the README.

    uv run scripts/docs_home.py

The home is the README, with the README's links into the repository made
links within the site: the README's own must be absolute, since PyPI shows it
too, and the site's must be relative, or they would leave the site. A test
holds the two to this, so they cannot drift apart again.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BLOB = "https://github.com/Gi0tto/sluicer/blob/main/"
# The repository's own documents the site carries under a name of its own.
IN_THE_SITE = {
    "ROADMAP.md": "roadmap.md",
    "CHANGELOG.md": "changelog.md",
    "SECURITY.md": "security.md",
    "CONTRIBUTING.md": "contributing.md",
}


def home(readme: str) -> str:
    """The home page ``readme`` makes."""
    page = readme.replace(BLOB + "docs/", "")
    for name, there in IN_THE_SITE.items():
        page = page.replace(BLOB + name, there)
    return page


def main() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    (ROOT / "docs" / "index.md").write_text(home(readme), encoding="utf-8")
    print("wrote docs/index.md")


if __name__ == "__main__":
    main()
