"""Write the licences of every Python distribution installed beside Sluicer.

    python packaging/third_party.py OUT

An image is a binary distribution of everything installed in it, and most of
what Sluicer's extras bring asks for its licence to travel with a copy of it:
BSD's and MIT's texts say so outright, Apache-2.0 wants its text and any
NOTICE, and lxml's wheel carries libxml2's and libxslt's. So the image carries
them in one file, beside Sluicer's own LICENSE, NOTICE and LICENSES/: for each
distribution in the environment that runs this, its name, version and the
licence it declares, then the text of every licence file it installed.

It exits 1, naming them, when a distribution installed no licence file at
all: a declared name is not the text a licence asks to be given, and an image
that shipped without it would be one nobody may redistribute. Standard
library only, since it runs inside the image being built.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from importlib import metadata
from pathlib import Path

# What wheels name their licence files, when they do not put them under
# .dist-info/licenses/ as PEP 639 asks: LICENSE, LICENSE.txt, LICENCE.md,
# COPYING, NOTICE, and the like.
LICENCE_NAME = re.compile(r"(?i)^(licen[cs]e|copying|notice)")


def declared(distribution: metadata.Distribution) -> str:
    """The licence a distribution's metadata names, most precise first."""
    meta = distribution.metadata
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    free_text = (meta.get("License") or "").strip()
    if free_text and "\n" not in free_text and len(free_text) <= 100:
        return free_text
    classifiers = [
        line.split("::")[-1].strip()
        for line in meta.get_all("Classifier") or []
        if line.startswith("License ::")
    ]
    return ", ".join(classifiers) or "not declared"


def licence_files(distribution: metadata.Distribution) -> list[metadata.PackagePath]:
    """The licence files a distribution installed in its .dist-info."""
    found = []
    for path in distribution.files or []:
        if not any(part.endswith(".dist-info") for part in path.parts):
            continue
        if "licenses" in path.parts or LICENCE_NAME.match(path.name):
            found.append(path)
    return sorted(found, key=str)


def inventory(
    distributions: Iterable[metadata.Distribution],
) -> tuple[str, list[str]]:
    """The text to write, and the distributions that installed no licence."""
    sections = []
    missing = []
    for distribution in sorted(
        distributions, key=lambda each: each.metadata["Name"].lower()
    ):
        name = distribution.metadata["Name"]
        files = licence_files(distribution)
        if not files:
            missing.append(name)
            continue
        section = [
            "=" * 78,
            f"{name} {distribution.version}",
            f"Licence: {declared(distribution)}",
        ]
        for path in files:
            text = Path(str(distribution.locate_file(path))).read_text(
                encoding="utf-8", errors="replace"
            )
            section += ["", f"--- {path.name}", "", text.rstrip("\n")]
        sections.append("\n".join(section))
    header = (
        "The licences of the Python distributions installed in this image,\n"
        "as each installed them. Sluicer's own are beside this file.\n"
    )
    return header + "\n\n".join(sections) + "\n", missing


def main(argv: list[str]) -> None:
    if len(argv) != 1:
        raise SystemExit(__doc__)
    text, missing = inventory(metadata.distributions())
    if missing:
        print(
            "these distributions installed no licence file: " + ", ".join(missing),
            file=sys.stderr,
        )
        raise SystemExit(1)
    Path(argv[0]).write_text(text, encoding="utf-8")
    print(f"{text.count('=' * 78)} distributions' licences in {argv[0]}")


if __name__ == "__main__":
    main(sys.argv[1:])
