"""Command line front door.

What the commands share lives beside this module: ``exits`` the exit codes
they keep, ``options`` the options of the commands that fetch, ``source``
reading a URL, a file or stdin, and ``output`` the lines a person reads.
"""

from __future__ import annotations

import codecs
import io
import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import asdict
from typing import Any

import click

from sluicer.api import Extraction, extract as extract_html
from sluicer.cli.audit import audit_command
from sluicer.cli.exits import NOTHING_FOUND, _fail
from sluicer.cli.extractors import compile_command, heal_command, run_command
from sluicer.cli.fetch import fetch_command
from sluicer.cli.options import _with_fetch_options
from sluicer.cli.output import _brief, _kept_line, _moment
from sluicer.cli.servers import mcp_command, serve
from sluicer.cli.sites import (
    batch_command,
    crawl_command,
    feed_command,
    map_command,
    warc_command,
)
from sluicer.cli.source import _read_source
from sluicer.config import ConfiguredGroup
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.declared.readers import READERS
from sluicer.diff import compare
from sluicer.fetch.result import Fetched
from sluicer.markdown import MarkdownExtraMissing, to_markdown
from sluicer.selectors import SelectorError, parse as parse_page


def _what_to_try(source: str, induce: bool, visible: bool) -> str:
    """What may still read a page that gives nothing, less the options tried.

    A page declaring nothing may still repeat rows (``--induce``), show a
    byline and dates only to a reader (``--visible``), or hold values a
    person can point to, which ``compile --want`` learns by example.
    """
    page = "PAGE" if source == "-" else source
    tries = [
        *(["  --induce    the rows it repeats, as a listing's"] if not induce else []),
        *(
            ["  --visible   the title, byline and dates it shows a reader"]
            if not visible
            else []
        ),
        f"  sluicer compile {page} --want NAME=VALUE -o page.json",
        "              the fields you name, each by a value the page shows",
    ]
    return "\n".join(["What may still read it:", *tries])


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
        limit = formatter.width - 6 - widest
        placed = {name for names in SECTIONS.values() for name in names}
        groups = [
            *SECTIONS.items(),
            ("Other commands", tuple(name for name in shown if name not in placed)),
        ]
        for title, names in groups:
            # Padded to the longest name, so every section's help starts in
            # one column: write_dl aligns only the rows it is given.
            rows = [
                (name.ljust(widest), shown[name].get_short_help_str(limit))
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


@click.command()
@click.argument("source")
@click.option(
    "--induce",
    is_flag=True,
    help="Also read the rows a page repeats when it declares nothing about them.",
)
@click.option(
    "--microformats",
    is_flag=True,
    help="Also read microformats2 (needs sluicer[microformats]).",
)
@click.option(
    "--visible",
    is_flag=True,
    help="Also guess the title, byline and dates the page shows, not in the summary.",
)
@_with_fetch_options
def extract(
    source: str,
    induce: bool,
    microformats: bool,
    visible: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Read the structured data a URL, a file or stdin declares."""
    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    try:
        result = extract_html(
            html,
            url=url,
            induce=induce,
            microformats=microformats,
            headers=fetched.headers if fetched else None,
            visible=visible,
        )
    except MicroformatsExtraMissing as missing:
        _fail(str(missing), missing)
    if not result.records and not result.summary and not result.visible:
        click.echo("This page gives nothing: no record and no summary.", err=True)
        click.echo(_what_to_try(source, induce, visible), err=True)
        if fetched is not None:
            # What the page cost is reported even when it declared nothing.
            click.echo(f"Fetch reached the '{fetched.rung}' rung.", err=True)
            for climb in fetched.climbs:
                click.echo(
                    f"  {climb.from_rung} -> {climb.to_rung}: {climb.reason}",
                    err=True,
                )
        raise SystemExit(NOTHING_FOUND)
    payload = asdict(result)
    if not visible:
        del payload["visible"]
    if fetched is not None:
        payload["fetch"] = {
            "rung": fetched.rung,
            "status": fetched.status,
            "climbs": [asdict(climb) for climb in fetched.climbs],
            **(
                {"archived": asdict(fetched.archived)}
                if fetched.archived is not None
                else {}
            ),
            **(
                {"cached": asdict(fetched.cached)} if fetched.cached is not None else {}
            ),
        }
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))


@click.command("select")
@click.argument("source")
@click.argument("selector")
@click.option(
    "--json", "as_json", is_flag=True, help="Print the values as a JSON list."
)
@_with_fetch_options
def select_command(
    source: str,
    selector: str,
    as_json: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Print what a CSS or XPath selector gives on a page, and where.

    One value a line, a tab, then the XPath of its element: 'h1',
    'span.price::text', 'a::attr(href)' or '//li/a/@href'. A selector that
    cannot be read exits 2 naming it, before any page is fetched; one that
    gives nothing exits 1.
    """
    from sluicer.selectors import selector as read_selector

    try:
        read_selector(selector)
    except SelectorError as unread:
        _fail(f"{unread}.", unread)
    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    page = parse_page(html, url, fetched.headers if fetched else None)
    try:
        found = page.select(selector)
    except SelectorError as unread:
        _fail(f"{unread}.", unread)
    if not found:
        click.echo(f"{selector!r} gives nothing on this page.", err=True)
        raise SystemExit(NOTHING_FOUND)
    if as_json:
        values = [{"value": one.value, "where": one.where} for one in found]
        click.echo(json.dumps(values, indent=2, ensure_ascii=False))
        return
    for one in found:
        click.echo(f"{one.value}\t{one.where}")


@click.command()
@click.argument("source")
@click.option(
    "--induce",
    is_flag=True,
    help="Also read the rows a page repeats when it declares nothing about them.",
)
@click.option(
    "--microformats",
    is_flag=True,
    help="Also read microformats2 (needs sluicer[microformats]).",
)
@click.option(
    "--visible",
    is_flag=True,
    help="Also guess the title, byline and dates the page shows, not in the summary.",
)
@_with_fetch_options
def inspect(
    source: str,
    induce: bool,
    microformats: bool,
    visible: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Show, for a person, what a page declares and where each answer came from.

    The same reading as ``extract``, laid out to be read rather than parsed:
    what the fetch cost, which vocabularies said something, every record with
    the source of each field, and every summary answer with its source and
    key. Exit codes are ``extract``'s.
    """
    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    try:
        result = extract_html(
            html,
            url=url,
            induce=induce,
            microformats=microformats,
            headers=fetched.headers if fetched else None,
            visible=visible,
        )
    except MicroformatsExtraMissing as missing:
        _fail(str(missing), missing)
    shown = "standard input" if source == "-" else (url or source)
    click.echo(_inspection(shown, result, fetched, microformats, not no_robots))
    if not result.records and not result.summary and not result.visible:
        click.echo(_what_to_try(source, induce, visible), err=True)
        raise SystemExit(NOTHING_FOUND)


def _inspection(
    shown: str,
    result: Extraction,
    fetched: Fetched | None,
    microformats: bool,
    obeyed_robots: bool,
) -> str:
    """The report ``inspect`` prints, deterministic for a given page."""
    lines = [f"page      {shown}"]
    if fetched is not None:
        lines.append(
            f"fetch     {fetched.rung} rung, status {fetched.status}, "
            f"{fetched.seconds:.2f} s"
        )
        if fetched.cached is not None:
            lines.append(f"cached    {_kept_line(fetched.cached)}")
        if fetched.archived is not None:
            capture = fetched.archived
            lines.append(
                f"archived  {capture.archive} capture of {capture.url} at "
                f"{_moment(capture.captured)}, asked for {_moment(capture.asked)}"
            )
        for climb in fetched.climbs:
            lines.append(
                f"          {climb.from_rung} -> {climb.to_rung} after "
                f"{climb.seconds:.2f} s: {climb.reason}"
            )
        whose = (
            f"{fetched.archived.archive}'s"
            if fetched.archived is not None
            else "the site's"
        )
        lines.append(
            f"robots    allowed by {whose} robots.txt"
            if obeyed_robots
            else "robots    not asked (--no-robots)"
        )
    records_by: dict[str, int] = {}
    fields_by: dict[str, int] = {}
    for record in result.records:
        if record.source:
            records_by[record.source] = records_by.get(record.source, 0) + 1
        for found in record.fields.values():
            fields_by[found.source] = fields_by.get(found.source, 0) + 1
    said = []
    for name in [reader.name for reader in READERS] + ["induced"]:
        if name in fields_by:
            fields = fields_by[name]
            counted = f"{fields} field{'s' if fields != 1 else ''}"
            if name in records_by:
                n = records_by[name]
                counted = f"{n} record{'s' if n != 1 else ''}, {counted}"
            said.append(f"{name} ({counted})")
    silent = [
        reader.name
        for reader in READERS
        if reader.name not in fields_by and (reader.optional is None or microformats)
    ]
    lines.append("readers   " + (", ".join(said) if said else "none said anything"))
    if silent:
        lines.append("          silent: " + ", ".join(silent))
    if not microformats:
        lines.append("          not read: microformats (--microformats)")
    lines.extend(_link_lines(result.links))
    lines.extend(_rights_lines(result.rights))
    lines.append("")
    records = len(result.records)
    lines.append(f"records   {records}" + ("" if records else ", nothing declared"))
    for record in result.records:
        kind = " / ".join(record.types) or "no type"
        lines.append(f"  {kind}" + (f"  ({record.source})" if record.source else ""))
        rows = [
            (name, _brief(found.value), found.source)
            for name, found in record.fields.items()
        ]
        lines.extend(_columns(rows, indent="    "))
    lines.append("")
    answers = len(result.summary)
    lines.append(f"summary   {answers} answer{'s' if answers != 1 else ''}")
    rows = [
        (
            question,
            _brief(answer.value)
            + (
                f" = {result.normalised[question]}"
                if result.normalised.get(question, answer.value) != answer.value
                else ""
            ),
            f"{answer.source} {answer.key}",
        )
        for question, answer in result.summary.items()
    ]
    lines.extend(_columns(rows, indent="  "))
    for conflict in result.conflicts:
        # The page answers this question twice, meaning two things: every
        # answer beside the summary's, so a person sees which to trust.
        lines.append(f"  conflict: {conflict.question} is declared two ways")
        lines.extend(
            _columns(
                [
                    ("", _brief(answer.value), f"{answer.source} {answer.key}")
                    for answer in conflict.answers
                ],
                indent="    ",
            )
        )
    if result.visible:
        # Guesses, not declarations: a section of their own, each naming the
        # rule that read it, so none is taken for what the page declares.
        lines.append("")
        shown_answers = len(result.visible)
        lines.append(
            f"visible   {shown_answers} guess{'es' if shown_answers != 1 else ''}"
            " from what the page shows, not declared"
        )
        lines.extend(
            _columns(
                [
                    (question, _brief(guess.value), f"guess: {guess.rule}")
                    for question, guess in result.visible.items()
                ],
                indent="  ",
            )
        )
    return "\n".join(lines)


def _link_lines(links: Mapping[str, Any]) -> list[str]:
    """What the page's ``<link>`` elements declare, one relation a line."""
    said = []
    for relation in ("canonical", "next", "prev", "amphtml", "manifest"):
        if relation in links:
            said.append(f"{relation} {links[relation]}")
    if links.get("alternates"):
        languages = ", ".join(a["hreflang"] for a in links["alternates"])
        said.append(f"{len(links['alternates'])} alternates: {_brief(languages)}")
    for feed in links.get("feeds", []):
        said.append(f"{feed['format']} feed {feed['href']}")
    for endpoint in links.get("oembed", []):
        said.append(f"oembed {endpoint}")
    return [
        ("links     " if n == 0 else "          ") + line for n, line in enumerate(said)
    ]


def _rights_lines(rights: Mapping[str, Any]) -> list[str]:
    """What the page's tags declare about its use; one line saying so if nothing.

    What the response's headers declared follows, each line marked as theirs.
    """
    said = _directives(rights)
    said += [f"{line}  [http header]" for line in _directives(rights.get("http", {}))]
    if not said:
        return ["rights    none declared in the page"]
    return [
        ("rights    " if n == 0 else "          ") + line for n, line in enumerate(said)
    ]


def _directives(rights: Mapping[str, Any]) -> list[str]:
    said = []
    if rights.get("robots"):
        said.append("robots " + ", ".join(rights["robots"]))
    for agent, rules in rights.get("agents", {}).items():
        said.append(f"{agent} " + ", ".join(rules))
    if "tdm_reservation" in rights:
        said.append(f"tdm-reservation {rights['tdm_reservation']}")
    if "tdm_policy" in rights:
        said.append(f"tdm-policy {rights['tdm_policy']}")
    for category, preference in rights.get("content_usage", {}).items():
        said.append(f"content-usage {category}={preference}")
    for licence in rights.get("license", []):
        said.append(f"license {licence}")
    return said


def _columns(rows: list[tuple[str, str, str]], indent: str) -> list[str]:
    """Name, value and source, the first two padded to line the third up."""
    name = max((len(row[0]) for row in rows), default=0)
    value = max((len(row[1]) for row in rows), default=0)
    return [f"{indent}{row[0]:{name}}  {row[1]:{value}}  [{row[2]}]" for row in rows]


@click.command("diff")
@click.argument("before")
@click.argument("after")
@click.option("--json", "as_json", is_flag=True, help="Print the differences as JSON.")
@_with_fetch_options
def diff_command(
    before: str,
    after: str,
    as_json: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Say what changed between two readings of a page, question by question.

    BEFORE and AFTER are each a URL, a file or - for stdin; --at reads
    BEFORE as the Wayback Machine captured it, so `sluicer diff URL URL --at
    2024-01` is what changed since then. Exit codes are diff's: 0 when
    nothing differs, 1 when something does, 2 when either could not be read.
    A value written differently with the same meaning (41.90 and 41.9) is
    reported as rewritten; a price in another currency (£41.90 and $41.90)
    is changed.
    """
    readings = []
    for source, when in ((before, at), (after, None)):
        html, url, fetched = _read_source(
            source, stealth, no_robots, base_url, when, respect, cache_dir, max_age
        )
        readings.append(
            extract_html(html, url=url, headers=fetched.headers if fetched else None)
        )
    differences = compare(readings[0], readings[1])
    if as_json:
        click.echo(
            json.dumps([asdict(d) for d in differences], indent=2, ensure_ascii=False)
        )
    else:
        for d in differences:
            if d.kind == "added":
                click.echo(f"+ {d.question}: {_brief(d.after)}  [{d.after_source}]")
            elif d.kind == "removed":
                click.echo(f"- {d.question}: {_brief(d.before)}  [{d.before_source}]")
            else:
                click.echo(
                    f"{'~' if d.kind == 'rewritten' else '*'} {d.question}: "
                    f"{_brief(d.before)} -> {_brief(d.after)}  [{d.after_source}]"
                )
    if differences:
        raise SystemExit(1)


@click.command()
@click.argument("source")
@click.option(
    "--front-matter",
    is_flag=True,
    help="Open with a YAML block of what the page declares, and where from.",
)
@_with_fetch_options
def markdown(
    source: str,
    front_matter: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Print the main content of a URL, a file or stdin as markdown."""
    html, url, _fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    # MarkdownExtraMissing: trafilatura is not installed; the message says how.
    try:
        content = (
            to_markdown(html, url=url, front_matter=True)
            if front_matter
            else to_markdown(html, url=url)
        )
    except MarkdownExtraMissing as missing:
        _fail(str(missing), missing)
    if not content:
        click.echo("This page has no main content.", err=True)
        raise SystemExit(NOTHING_FOUND)
    click.echo(content)


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
