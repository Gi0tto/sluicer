"""A crawl's pages, and a map's addresses, as the rows of a table.

JSON Lines is a crawl's output and its state; a table is for reading it in a
spreadsheet. Each page becomes one row of fixed columns, so the header can be
written before the first page is fetched and every file of every crawl has
the same one:

* the page: ``url``, ``ok``, ``depth``, ``found_on``, ``landed``, ``status``,
  ``rung``, ``seconds``, ``canonical``;
* counts of what its line lists: ``climbs``, ``retries``, ``records``,
  ``links``;
* ``error`` and ``message``, its error's code and sentence, empty when it
  has none;
* ``sources`` and ``types``, the readers that found something and the types
  its records declared, each written once, a space between;
* ``summary.<question>`` for each of ``sluicer.summary.FIELDS``, in their
  order: the answer's value alone. Its reader, key and place are in the JSON
  line, and a table of them would be four columns a question.

True and false are ``true`` and ``false``; nothing is an empty cell.

The pages are other people's, and a cell that begins with ``=``, ``+``,
``-``, ``@``, a tab or a carriage return is a formula to a spreadsheet: a
title of ``=HYPERLINK(...)`` would run in the reader's. Such a cell is written
with a ``'`` before it, as OWASP advises, unless it is a number; the JSON
Lines are never changed.
"""

from __future__ import annotations

import csv
import re
import unicodedata
from collections.abc import Callable, Mapping
from typing import IO, Any

from sluicer.summary import FIELDS

PAGE_COLUMNS: tuple[str, ...] = (
    "url",
    "ok",
    "depth",
    "found_on",
    "landed",
    "status",
    "rung",
    "seconds",
    "climbs",
    "retries",
    "error",
    "message",
    "canonical",
    "sources",
    "types",
    "records",
    "links",
    *(f"summary.{name}" for name in FIELDS),
)
"""The columns of a page's row, in order."""

SITE_URL_COLUMNS: tuple[str, ...] = ("url", "lastmod", "sitemap")
"""The columns of a map's row: one address, as ``sluicer.crawl.SiteUrl``."""

_FORMULA = ("=", "+", "-", "@", "\t", "\r")
_NUMBER = re.compile(r"[+-]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][+-]?\d+)?", re.ASCII)
# What a spreadsheet may trim off a cell before it reads it: spaces and line
# breaks, a no-break space and the other Unicode spaces among them.
_SPACE = re.compile(r"^[\s\u00a0\u2000-\u200b\u202f\u205f\u3000\ufeff]+")


def cell(value: Any) -> str:
    """``value`` as one cell: text, ``true``/``false``, empty for None, and
    never a formula.

    A cell is judged as a spreadsheet may read it: behind the spaces it may
    trim, and with a fullwidth equals or plus sign (U+FF1D, U+FF0B) as the
    sign it looks like. A
    number is ASCII's: a minus before digits of another script is a formula.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value)
    read = unicodedata.normalize("NFKC", _SPACE.sub("", text))
    for seen in (text, read):
        if seen.startswith(_FORMULA) and not _NUMBER.fullmatch(seen):
            return "'" + text
    return text


def page_row(line: Mapping[str, Any]) -> dict[str, str]:
    """A page's line, as a crawl writes it, flattened into ``PAGE_COLUMNS``."""
    fetched = line.get("fetch") or {}
    error = line.get("error") or {}
    records = line.get("records") or []
    summary = line.get("summary") or {}
    ok = bool(line.get("ok"))
    types = dict.fromkeys(
        kind for record in records for kind in record.get("types") or ()
    )
    row: dict[str, Any] = {
        "url": line.get("url"),
        "ok": ok,
        "depth": line.get("depth"),
        "found_on": line.get("found_on"),
        "landed": line.get("landed"),
        "status": fetched.get("status"),
        "rung": fetched.get("rung"),
        "seconds": fetched.get("seconds"),
        "climbs": len(fetched.get("climbs") or ()) if fetched else None,
        "retries": len(line.get("retries") or ()),
        "error": error.get("code"),
        "message": error.get("message"),
        "canonical": line.get("canonical"),
        "sources": " ".join(dict.fromkeys(line.get("sources") or ())) or None,
        "types": " ".join(types) or None,
        "records": len(records) if ok else None,
        "links": len(line.get("links") or ()) if ok else None,
    }
    for name in FIELDS:
        answer = summary.get(name)
        row[f"summary.{name}"] = answer.get("value") if answer else None
    return {column: cell(row[column]) for column in PAGE_COLUMNS}


def site_url_row(address: Mapping[str, Any]) -> dict[str, str]:
    """One address of a map, as ``dataclasses.asdict`` of a ``SiteUrl``."""
    return {column: cell(address.get(column)) for column in SITE_URL_COLUMNS}


def write_csv(
    out: IO[str], columns: tuple[str, ...]
) -> Callable[[Mapping[str, str]], None]:
    """Write the header of ``columns`` to ``out`` now, and return what writes
    one row, flushed, so a stopped crawl leaves every row it wrote whole."""
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    out.flush()

    def write(row: Mapping[str, str]) -> None:
        writer.writerow(row)
        out.flush()

    return write
