# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Regenerate ``src/sluicer/calendar_names.py`` from the Unicode CLDR.

    uv run scripts/cldr_calendar.py

Reads the month and weekday names of every locale CLDR rates ``modern`` --
its highest coverage level -- from the npm packages ``cldr-dates-full`` and
``cldr-core`` at the pinned release, each checked against the integrity npm
publishes for it. A month keeps its wide and abbreviated names, in their
formatting and stand-alone forms (Russian's "мая" and "май" are both May),
casefolded, without a trailing full stop, and without the preposition
Catalan writes into them ("de gener"). A name holding a digit is left out:
Chinese, Japanese and Korean write "5月" and "5월", which the date reader
takes as numbers. A name that means two months in two locales is left out
too: "listopad" is November in Polish and Czech and October in Croatian.

The output is sorted, so the same release always writes the same file.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import tarfile
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

RELEASE = "48.2.0"
PACKAGES = {
    "cldr-dates-full": "sha512-zMrKvjMO414HDftLr6vKH1fNQHakFNe+F1h4S0eg+zmL4WRi9"
    "pI41fxB3UrTJDY42MEM87jCuAw/qlqCgYKcAQ==",
    "cldr-core": "sha512-zfmLothncSwfv2jlevoSrgI2VGgH8SDGHXst6jUEotHA8nq9Igeg9jzdJ"
    "DFtBso9pgJuG89DK16TzrmZDdo2Bg==",
}
OUT = Path(__file__).resolve().parent.parent / "src" / "sluicer" / "calendar_names.py"
# Catalan's "de gener", "d\u2019abril": the preposition is not the month.
_PREPOSITION = re.compile("^(?:de |d\u2019|d')")


def _tarball(name: str) -> tarfile.TarFile:
    url = f"https://registry.npmjs.org/{name}/-/{name}-{RELEASE}.tgz"
    with urllib.request.urlopen(url) as response:
        data = response.read()
    digest = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
    if digest != PACKAGES[name]:
        raise SystemExit(f"{name} {RELEASE}: integrity {digest}, not the pinned one")
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def _json(tar: tarfile.TarFile, member: str) -> dict:
    handle = tar.extractfile(member)
    assert handle is not None, member
    return json.loads(handle.read().decode("utf-8"))


def _spelt(name: str) -> str | None:
    word = unicodedata.normalize("NFC", name).casefold().strip()
    word = _PREPOSITION.sub("", word).rstrip(".")
    if not word or any(ch.isdigit() for ch in word):
        return None
    return word


def main() -> None:
    core = _tarball("cldr-core")
    levels = _json(core, "package/coverageLevels.json")["effectiveCoverageLevels"]
    modern = sorted(locale for locale, level in levels.items() if level == "modern")
    dates = _tarball("cldr-dates-full")
    present = set(dates.getnames())
    months: dict[str, set[int]] = defaultdict(set)
    weekdays: set[str] = set()
    read = []
    for locale in modern:
        member = f"package/main/{locale}/ca-gregorian.json"
        if member not in present:
            continue
        read.append(locale)
        calendar = _json(dates, member)["main"][locale]["dates"]["calendars"]
        gregorian = calendar["gregorian"]
        for context in ("format", "stand-alone"):
            for width in ("wide", "abbreviated"):
                for number, name in gregorian["months"][context][width].items():
                    if (word := _spelt(name)) is not None:
                        months[word].add(int(number))
                for name in gregorian["days"][context][width].values():
                    if (word := _spelt(name)) is not None:
                        weekdays.add(word)
    kept = {
        word: next(iter(numbers))
        for word, numbers in months.items()
        if len(numbers) == 1
    }
    left_out = sorted(word for word, numbers in months.items() if len(numbers) > 1)
    # A weekday that is also a month is no weekday to strip: Spanish "mar" is
    # martes and marzo both, and "mar 5, 2025" is March.
    weekdays -= set(months)
    OUT.write_text(_module(kept, sorted(weekdays), read, left_out), encoding="utf-8")
    print(
        f"{len(read)} locales, {len(kept)} month names, {len(weekdays)} weekday names,"
    )
    print(
        f"{len(left_out)} names left out as meaning two months: {', '.join(left_out)}"
    )


def _module(
    months: dict[str, int], weekdays: list[str], read: list[str], left_out: list[str]
) -> str:
    lines = [
        "# SPDX-License-Identifier: Unicode-3.0",
        "# Month and weekday names from the Unicode Common Locale Data Repository",
        f"# (CLDR), release {RELEASE}, published by Unicode, Inc. under the Unicode",
        "# License v3. This file, unlike most of sluicer, is distributed under that",
        "# licence: see LICENSES/Unicode-3.0.txt. Regenerate it with",
        "# scripts/cldr_calendar.py; do not edit it by hand.",
        "# ruff: noqa: RUF001 -- names in their own scripts, Cyrillic and Greek too.",
        '"""Month and weekday names in every language CLDR covers at its modern level.',
        "",
        f"{len(read)} locales, CLDR {RELEASE}: each month's wide and abbreviated",
        "names, in their formatting and stand-alone forms, casefolded, without a",
        "trailing full stop. Names holding a digit are not here -- Chinese,",
        "Japanese and Korean write months as numbers -- nor the names that mean",
        f"two months in two locales: {', '.join(left_out)}.",
        '"""',
        "",
        "MONTHS: dict[str, int] = {",
        *(
            f"    {json.dumps(word, ensure_ascii=False)}: {number},"
            for word, number in sorted(months.items())
        ),
        "}",
        "",
        "WEEKDAYS: frozenset[str] = frozenset(",
        "    {",
        *(f"        {json.dumps(word, ensure_ascii=False)}," for word in weekdays),
        "    }",
        ")",
        "",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    main()
