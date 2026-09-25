"""Write the documentation site's llms.txt, and each page's markdown beside it.

A hook ``mkdocs.yml`` names, like ``docs_demo.py``. Once the site is built it
writes ``llms.txt`` at the site's root in llmstxt.org's format: the site's name
as the H1, its description as the summary, then one H2 per section of the nav
and one link per page, with the page's first paragraph as the link's note. And
it copies every page's markdown to the same path in the site, ``agents.md``
beside ``agents/``, since the proposal asks for links an agent can read as
markdown rather than HTML. A page's relative links keep working there, because
the copies keep the layout of ``docs/``.

Both are made from the nav and the pages at every build, so neither can fall
behind them. The suite reads the nav from ``mkdocs.yml`` with ``nav_of``,
which the build holds to MkDocs' own reading of it, and holds the result to
the format with Sluicer's own llms.txt reader. Standard library only, apart
from the hook's arguments.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

Entry = tuple[str, str, str]
"""A page of the nav: its section, its title and its path under docs/."""

START = "Start"
"""The section of the pages the nav lists outside any section."""

# A title as YAML writes it plain, or in double quotes where it holds a colon:
# "Conformance: JSON-LD in HTML".
_NAV_LINE = re.compile(
    r'^(?P<indent> *)- (?:"(?P<quoted>[^"\\]*)"|(?P<title>[^:"]+)):'
    r"(?: (?P<path>\S+\.md))?$"
)
_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")


def nav_of(mkdocs_yml: str) -> list[Entry]:
    """The pages ``mkdocs.yml``'s nav lists, in its order.

    Only the shape this site's nav has: a page, or a section of pages, one
    ``- Title: path.md`` a line. Anything else stops, rather than being read
    as something it is not.
    """
    start = re.search(r"^nav:\n", mkdocs_yml, re.MULTILINE)
    if not start:
        raise ValueError("mkdocs.yml has no nav")
    lines = mkdocs_yml[start.end() :].splitlines()
    entries: list[Entry] = []
    section = START
    top = None
    for line in lines:
        if not line.strip():
            break
        found = _NAV_LINE.match(line)
        if not found:
            raise ValueError(f"a nav line this reader does not know: {line!r}")
        title = found["quoted"] if found["quoted"] is not None else found["title"]
        path = found["path"]
        top = found["indent"] if top is None else top
        if found["indent"] == top:
            if path is None:
                section = title
                continue
            section = START
        entries.append((section, title, path))
    return entries


def nav_from_config(nav: list[Any]) -> list[Entry]:
    """The same list, from the nav MkDocs read."""
    entries: list[Entry] = []
    for item in nav:
        [(title, value)] = item.items()
        if isinstance(value, str):
            entries.append((START, title, value))
        else:
            for page in value:
                [(inner, path)] = page.items()
                entries.append((title, inner, path))
    return entries


def summary_of(markdown: str) -> str:
    """A page's first paragraph of prose, on one line, its links made text.

    The paragraph between the page's title and its first section: a page
    that opens on a section, as the FAQ opens on its first question, has
    none, rather than one that answers something else. HTML blocks, such as
    the README's logo and badges, and code are skipped.
    """
    paragraph: list[str] = []
    skipping = None
    for line in markdown.splitlines():
        stripped = line.strip()
        if skipping == "fence":
            if stripped.startswith(("```", "~~~")):
                skipping = None
            continue
        if not stripped:
            if paragraph:
                break
            skipping = None
            continue
        if skipping == "html":
            continue
        if paragraph and stripped.startswith("#"):
            break
        if stripped.startswith(("```", "~~~")):
            skipping = "fence"
        elif stripped.startswith("<"):
            skipping = "html"
        elif stripped.startswith("# "):
            continue
        elif stripped.startswith("#"):
            return ""
        elif not stripped.startswith(("|", "-", "*", ">", "!")):
            paragraph.append(stripped)
    text = _LINK.sub(r"\1", " ".join(paragraph))
    return re.sub(r":$", ".", text)


def llms_txt(
    name: str,
    description: str,
    site_url: str,
    entries: list[Entry],
    read: Callable[[str], str],
) -> str:
    """The llms.txt the site serves, for the pages ``entries`` lists."""
    base = site_url.rstrip("/") + "/"
    lines = [
        f"# {name}",
        "",
        f"> {description}",
        "",
        "Every link below is a page's markdown source, served beside the page;",
        "the site shows the same page as HTML.",
    ]
    section = None
    for where, title, path in entries:
        if where != section:
            section = where
            lines += ["", f"## {section}", ""]
        note = summary_of(read(path))
        link = f"- [{title}]({base}{path})"
        lines.append(f"{link}: {note}" if note else link)
    return "\n".join(lines) + "\n"


def on_post_build(config: Any) -> None:
    """Write llms.txt and the pages' markdown into the built site."""
    docs = Path(config.docs_dir)
    site = Path(config.site_dir)
    entries = nav_from_config(config.nav)
    written = nav_of(Path(config.config_file_path).read_text(encoding="utf-8"))
    if written != entries:
        raise ValueError(
            "nav_of reads mkdocs.yml's nav otherwise than MkDocs: "
            f"{written} against {entries}"
        )

    def read(path: str) -> str:
        return (docs / path).read_text(encoding="utf-8")

    text = llms_txt(
        config.site_name, config.site_description, config.site_url, entries, read
    )
    (site / "llms.txt").write_text(text, encoding="utf-8")
    for _section, _title, path in entries:
        target = site / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(read(path), encoding="utf-8")
