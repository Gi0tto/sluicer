# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Regenerate ``src/sluicer/calendar_names.json`` from the Unicode CLDR.

    uv run scripts/cldr_calendar.py            # write the file
    uv run scripts/cldr_calendar.py --check    # exit 1 if it is not this

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

The names are data, not code: a JSON file shipped in the package, which
``sluicer.calendar_names`` loads. The output is sorted, one name a line, so
the same release always writes the same file and a new one diffs by name.
``--check`` is what CI runs where the network is: the committed file must be
exactly what the pinned release gives.
"""

from __future__ import annotations

import base64
import hashlib
import io
import json
import re
import sys
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
OUT = Path(__file__).resolve().parent.parent / "src" / "sluicer" / "calendar_names.json"
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


def names(
    core: tarfile.TarFile, dates: tarfile.TarFile
) -> tuple[dict[str, int], list[str], int, list[str]]:
    """The names CLDR's ``core`` and ``dates`` packages give: each month name
    and its number, the weekday names, how many locales were read, and the
    names left out as meaning two months."""
    levels = _json(core, "package/coverageLevels.json")["effectiveCoverageLevels"]
    modern = sorted(locale for locale, level in levels.items() if level == "modern")
    present = set(dates.getnames())
    months: dict[str, set[int]] = defaultdict(set)
    weekdays: set[str] = set()
    read = 0
    for locale in modern:
        member = f"package/main/{locale}/ca-gregorian.json"
        if member not in present:
            continue
        read += 1
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
    return kept, sorted(weekdays), read, left_out


def rendered(
    months: dict[str, int], weekdays: list[str], locales: int, left_out: list[str]
) -> str:
    """The file's text: the release and licence first, then every name sorted,
    one a line, in its own script."""
    data = {
        "licence": "Unicode-3.0",
        "source": "Unicode CLDR, https://cldr.unicode.org/, under the Unicode "
        "License v3: see LICENSES/Unicode-3.0.txt. Written by "
        "scripts/cldr_calendar.py; do not edit it by hand.",
        "cldr": RELEASE,
        "locales": locales,
        "left_out": sorted(left_out),
        "months": dict(sorted(months.items())),
        "weekdays": sorted(weekdays),
    }
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def main(argv: list[str] | None = None) -> int:
    check = "--check" in (sys.argv[1:] if argv is None else argv)
    months, weekdays, locales, left_out = names(
        _tarball("cldr-core"), _tarball("cldr-dates-full")
    )
    text = rendered(months, weekdays, locales, left_out)
    if check:
        if OUT.read_text(encoding="utf-8") != text:
            print(f"{OUT.name} is not what CLDR {RELEASE} gives: run the script")
            return 1
        print(f"{OUT.name} is what CLDR {RELEASE} gives")
        return 0
    OUT.write_text(text, encoding="utf-8")
    print(
        f"{locales} locales, {len(months)} month names, {len(weekdays)} weekday names,"
    )
    print(
        f"{len(left_out)} names left out as meaning two months: {', '.join(left_out)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
