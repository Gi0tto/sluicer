"""Command line front door.

``main`` is the group ``sluicer`` runs. Each command is defined in the module
of its group and added to ``main`` at the end of this one:

- ``fetch``: fetch
- ``page``: extract, select, inspect, markdown and diff
- ``audit``: audit
- ``sites``: map, crawl, batch, feed and warc
- ``extractors``: compile, run and heal
- ``servers``: serve and mcp

What they share is beside them: ``exits`` the exit codes every command keeps,
``options`` the options of the commands that fetch, ``source`` reading a URL,
a file or stdin, and ``output`` the lines a person reads.
"""

from __future__ import annotations

import codecs
import io
import logging
import sys

import click

from sluicer.cli.audit import audit_command
from sluicer.cli.exits import (
    CONTRACT_BROKEN,
    COULD_NOT_READ,
    INTERRUPTED,
    NOTHING_FOUND,
)
from sluicer.cli.extractors import compile_command, heal_command, run_command
from sluicer.cli.fetch import fetch_command
from sluicer.cli.page import diff_command, extract, inspect, markdown, select_command
from sluicer.cli.servers import mcp_command, serve
from sluicer.cli.sites import (
    batch_command,
    crawl_command,
    feed_command,
    map_command,
    warc_command,
)
from sluicer.config import ConfiguredGroup

__all__ = [
    "CONTRACT_BROKEN",
    "COULD_NOT_READ",
    "INTERRUPTED",
    "NOTHING_FOUND",
    "SECTIONS",
    "audit_command",
    "batch_command",
    "compile_command",
    "crawl_command",
    "diff_command",
    "extract",
    "feed_command",
    "fetch_command",
    "heal_command",
    "inspect",
    "main",
    "map_command",
    "markdown",
    "mcp_command",
    "run_command",
    "select_command",
    "serve",
    "warc_command",
]

SECTIONS: dict[str, tuple[str, ...]] = {
    "Read a page": (
        "fetch",
        "extract",
        "select",
        "inspect",
        "markdown",
        "diff",
        "audit",
    ),
    "Whole sites": ("map", "crawl", "batch", "feed", "warc"),
    "Extractors": ("compile", "run", "heal"),
    "Servers": ("mcp", "serve"),
}
"""The sections ``sluicer --help`` lists the commands in, each in this order."""


_WHOLE = 10_000
"""A short help this long is never cut: click then stops at the first sentence."""


class _Sectioned(ConfiguredGroup):
    """A group whose help lists its commands by what they are for.

    Sixteen commands in click's one alphabetical list put ``audit`` first and
    ``extract`` between ``diff`` and ``feed``. A command in no section is
    listed under "Other commands" rather than hidden.
    """

    def format_commands(
        self, ctx: click.Context, formatter: click.HelpFormatter
    ) -> None:
        shown = {
            name: command
            for name in self.list_commands(ctx)
            if (command := self.get_command(ctx, name)) is not None
            and not command.hidden
        }
        if not shown:
            return
        widest = max(len(name) for name in shown)
        placed = {name for names in SECTIONS.values() for name in names}
        groups = [
            *SECTIONS.items(),
            ("Other commands", tuple(name for name in shown if name not in placed)),
        ]
        for title, names in groups:
            # Padded to the longest name, so every section's help starts in
            # one column: write_dl aligns only the rows it is given.
            # Each command's whole first sentence, wrapped under itself when
            # it is long: cut to fit one line, "map ... from its sitemaps or
            # its start..." lost "page's links", the words that tell map from
            # crawl, and inspect, diff, audit and the rest lost theirs.
            rows = [
                (name.ljust(widest), shown[name].get_short_help_str(_WHOLE))
                for name in names
                if name in shown
            ]
            if rows:
                with formatter.section(title):
                    formatter.write_dl(rows)


@click.group(cls=_Sectioned)
@click.version_option(package_name="sluicer")
def main() -> None:
    """Turn a web page into structured data with no model in the loop.

    SOURCE is a URL, a saved HTML file, or - for standard input.
    """
    _speak_utf8(sys.stdin, sys.stdout, sys.stderr)
    _quiet_scrapling()


def _speak_utf8(*streams: object) -> None:
    """Read and write UTF-8 on the standard streams, whatever the system's default.

    JSON is UTF-8, and so are the markdown and the pages' own text. Windows
    gives a pipe or a file its ANSI code page, cp1252 across most of Europe:
    ``sluicer extract URL > out.json`` on a page titled in Chinese raised
    UnicodeEncodeError, and a list of addresses piped in was read in cp1252.
    A console there, and every stream on Linux and macOS, is UTF-8 already and
    is left alone, as is a stream a program embedding this one put in place.
    """
    for stream in streams:
        if isinstance(stream, io.TextIOWrapper) and (
            codecs.lookup(stream.encoding).name != "utf-8"
        ):
            stream.reconfigure(encoding="utf-8")


def _quiet_scrapling() -> None:
    """Keep scrapling's own log lines out of this command's stderr.

    Every one of them is said again here, better: a request is part of the
    ladder this command reports, and a failure is the message it exits with.
    Printed as well, a failed fetch read twice, once in scrapling's words.

    A filter and not a level: scrapling sets its logger to INFO when it is
    imported, which happens later, at the first fetch, and would undo a level
    set here. A filter on the logger survives that.
    """
    logging.getLogger("scrapling").addFilter(
        lambda record: record.levelno >= logging.CRITICAL
    )


# Added in the order they were written in when each was declared on ``main``,
# which ``main.commands`` keeps; ``--help`` lists them by SECTIONS whatever it is.
for _command in (
    fetch_command,
    extract,
    select_command,
    inspect,
    diff_command,
    markdown,
    compile_command,
    run_command,
    heal_command,
    serve,
    mcp_command,
    audit_command,
    map_command,
    crawl_command,
    feed_command,
    warc_command,
    batch_command,
):
    main.add_command(_command)
del _command
