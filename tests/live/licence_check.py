"""Every licence in the installed tree, and a failure for one nobody has read.

Run by CI in an environment holding sluicer and every extra, nothing else. The
README names the three non-permissive licences the extras bring in; this is
what keeps that sentence true. A new dependency under a licence not listed
below fails the job until someone reads it and either lists it or drops it.

    python tests/live/licence_check.py
"""

from __future__ import annotations

import importlib.metadata as md
import re
import sys

PERMISSIVE = frozenset(
    {
        "0bsd",
        "apache-2.0",
        "apache license",
        "apache software license",
        "bsd",
        "bsd license",
        "bsd-2-clause",
        "bsd-3-clause",
        "cnri-python",
        "isc",
        "isc license (iscl)",
        "mit",
        "mit license",
        "mit-0",
        "psf-2.0",
        "python software foundation license",
        "the unlicense (unlicense)",
        "unlicense",
    }
)
"""Licences that ask nothing of the code that uses them beyond a notice."""

READ = {
    "sluicer": "MIT AND CC-BY-SA-3.0: CC BY-SA 3.0 on one file of schema.org's"
    " names, sluicer/audit/schema_org.py, and MIT on the rest",
    "certifi": "MPL-2.0: file-level copyleft on certifi's own files, unmodified",
    "orjson": "MPL-2.0 AND (Apache-2.0 OR MIT): the same, for its bundled parts",
    "tld": "MPL-1.1 OR GPL-2.0-only OR LGPL-2.1-or-later: taken under MPL-1.1",
}
"""Packages whose licence is not permissive, read, and why they are acceptable.

Each is named in the README's licence section. A package added here without a
matching sentence there is a claim the README no longer makes.
"""

_OPERATORS = re.compile(r"\s+(?:AND|OR|WITH)\s+|[()]")


def licence_of(dist: md.Distribution) -> str:
    """The licence a distribution declares: its SPDX expression, else its trove
    classifiers, else its free-text field."""
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [
        c.split(" :: ")[-1]
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    if classifiers:
        return " AND ".join(classifiers)
    text = (meta.get("License") or "").strip().splitlines()
    return text[0] if text else ""


def permissive(licence: str) -> bool:
    """Whether every licence named in ``licence`` is permissive.

    ``OR`` is read as strictly as ``AND``: a choice that includes a copyleft
    licence is one a person has to make, so it is listed in ``READ``.
    """
    names = [part.strip().lower() for part in _OPERATORS.split(licence)]
    names = [name for name in names if name]
    if not names:
        return False
    return all(
        name in PERMISSIVE or name.startswith(("bsd ", "the bsd ", "mit "))
        for name in names
    )


def main() -> int:
    rows = sorted(
        {
            (str(dist.metadata["Name"]).lower(), licence_of(dist))
            for dist in md.distributions()
        }
    )
    unread = []
    for name, licence in rows:
        if name in READ:
            verdict = "read: " + READ[name]
        elif permissive(licence):
            verdict = "permissive"
        else:
            verdict = "NOT READ"
            unread.append(name)
        print(f"{name:28} {licence[:48]:48} {verdict}")
    for name in unread:
        print(f"FAIL: {name} is under a licence nobody has read; see READ above")
    stale = sorted(set(READ) - {name for name, _ in rows})
    for name in stale:
        print(f"note: {name} is listed as read but no longer installed")
    return 1 if unread else 0


if __name__ == "__main__":
    sys.exit(main())
