"""Month and weekday names in every language CLDR covers at its modern level.

The names are data, in ``calendar_names.json`` beside this module, which
``scripts/cldr_calendar.py`` writes from a pinned release of the Unicode
Common Locale Data Repository. That file is distributed under the Unicode
License v3 (see LICENSES/Unicode-3.0.txt); this module, which only reads it,
is MIT like the rest of sluicer. Each month's wide and abbreviated names, in
their formatting and stand-alone forms, casefolded, without a trailing full
stop. Names holding a digit are not there -- Chinese, Japanese and Korean
write months as numbers -- nor the names that mean two months in two
locales, which the file lists as ``left_out``.

Read once, at import, with the standard library's JSON parser, from the
file beside this one: ``importlib.resources`` is asked only when there is no
such file, as in a zip, because importing it costs more than reading the
names. No module of 2,700 lines is compiled where no bytecode is cached, as
in Pyodide.
"""

from __future__ import annotations

import json
import os


def _text() -> str:
    try:
        path = os.path.join(os.path.dirname(__file__), "calendar_names.json")
        with open(path, encoding="utf-8") as data:
            return data.read()
    except OSError:
        from importlib.resources import files

        return files("sluicer").joinpath("calendar_names.json").read_text("utf-8")


_DATA = json.loads(_text())

MONTHS: dict[str, int] = _DATA["months"]
"""Each month name, casefolded, and the month it names, 1 to 12."""

WEEKDAYS: frozenset[str] = frozenset(_DATA["weekdays"])
"""Every weekday name, casefolded; none of them is also a month's."""

del _DATA
