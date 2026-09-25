"""The exit codes every command keeps, and the one way out for input it cannot read.

Exit codes follow grep: 0 when something was found -- a record, or at least one
summary answer, a ``<title>`` alone included, or with ``--visible`` a guess --
1 when the page was read and gives nothing at all, 2 when it could not be
read. A script can tell "this page gives nothing" from "the fetch failed"
without parsing English. ``run`` and ``heal`` add 3: a page broke the
extractor's contract, or healing lost a field, and that is never a success.
``audit`` uses 3 in the same sense: the page was read and breaks a rule it is
held to, here one its documentation states.

``map``, ``crawl`` and ``batch`` read many pages and keep the same three: 0 when
an address was found or a page gave something, 1 when pages were read and none
gave anything, 2 when nothing could be read at all. A page that failed is a
line of the output with its reason, never a reason to stop; a crawl stopped by
Ctrl-C exits 130 with what it wrote intact, and ``--resume`` continues it.
"""

from __future__ import annotations

from typing import NoReturn

import click

from sluicer.fetch.address import shown

NOTHING_FOUND = 1
COULD_NOT_READ = 2
CONTRACT_BROKEN = 3
INTERRUPTED = 130


def _fail(message: str, cause: BaseException | None = None) -> NoReturn:
    """Say ``message`` and exit ``COULD_NOT_READ``; a password in an address
    it names is written ``***``."""
    click.echo(shown(message), err=True)
    raise SystemExit(COULD_NOT_READ) from cause
