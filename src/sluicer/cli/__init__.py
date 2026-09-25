"""Command line front door.

What the commands share lives beside this module: ``exits`` the exit codes
they keep, ``options`` the options of the commands that fetch, ``source``
reading a URL, a file or stdin, and ``output`` the lines a person reads.
"""

from __future__ import annotations

import codecs
import contextlib
import io
import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from sluicer.api import Extraction, extract as extract_html
from sluicer.cli.audit import audit_command
from sluicer.cli.exits import COULD_NOT_READ, INTERRUPTED, NOTHING_FOUND, _fail
from sluicer.cli.extractors import compile_command, heal_command, run_command
from sluicer.cli.options import _sent, _with_fetch_options, _with_proxy
from sluicer.cli.output import _brief, _kept_line, _moment
from sluicer.cli.servers import mcp_command, serve
from sluicer.cli.source import _read_source
from sluicer.config import ConfiguredGroup
from sluicer.crawl import Crawl, crawl as crawl_site, extract_many
from sluicer.crawl.pages import MAX_DEPTH, MAX_PAGES
from sluicer.crawl.schedule import CONCURRENCY, DEFAULT_DELAY_SECONDS, RETRIES
from sluicer.crawl.sitemaps import MAX_SITEMAP_URLS, map_site
from sluicer.crawl.table import (
    PAGE_COLUMNS,
    SITE_URL_COLUMNS,
    page_row,
    site_url_row,
    write_csv,
)
from sluicer.crawl.templates import TEMPLATES, shopify_products, sitemap_pages
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.declared.readers import READERS
from sluicer.diff import compare
from sluicer.fetch import AddressRefused, FetchFailed, RobotsRefused
from sluicer.fetch.result import Fetched, ResponseTooLarge
from sluicer.fetch.rungs import FetchExtraMissing
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


@click.command("fetch")
@click.argument("url")
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False),
    help="Write the page to this file rather than to stdout.",
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help="Print one JSON object: the page, where it landed, its status, "
    "rung, climbs and headers.",
)
@click.option(
    "--stealth",
    is_flag=True,
    help="Allow the stealth rung, which does not announce itself.",
)
@click.option(
    "--no-robots",
    is_flag=True,
    help="Fetch even where the site's robots.txt says no.",
)
@click.option(
    "--cache",
    "cache_dir",
    metavar="DIR",
    help="Keep fetched pages in DIR, and ask the site with their ETag or "
    "Last-Modified whether a page changed before fetching it again.",
)
@click.option(
    "--max-age",
    type=click.FloatRange(min=0),
    metavar="SECONDS",
    help="With --cache, give a page kept for less than SECONDS back without "
    "asking its site at all.",
)
@click.option(
    "--at",
    metavar="DATE",
    help="Read the URL as the Wayback Machine captured it nearest to DATE.",
)
@_with_proxy
def fetch_command(
    url: str,
    output: str | None,
    as_json: bool,
    stealth: bool,
    no_robots: bool,
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Fetch a URL and print the page, as the ladder brought it back.

    The HTML goes to stdout, or to --output, and what it cost -- each climb,
    where the page landed, its status and rung -- to stderr; with --json, all
    of it is one object on stdout. The input compile, extract and the rest
    can then read from a file, the same bytes every time. Exits 0 with a
    page, whatever its status, and 2 when none could be fetched.
    """
    if not url.lower().startswith(("http://", "https://")):
        _fail(f"fetch takes an http(s) address; {url} is not one.")
    html, _, fetched = _read_source(
        url, stealth, no_robots, None, at, (), cache_dir, max_age
    )
    if fetched is None:  # pragma: no cover -- an address is always fetched
        _fail(f"fetch takes an http(s) address; {url} is not one.")
    page = html if isinstance(html, str) else html.decode("utf-8", "replace")
    if as_json:
        answer: dict[str, Any] = {
            "url": fetched.url,
            "status": fetched.status,
            "rung": fetched.rung,
            "seconds": round(fetched.seconds, 3),
            "climbs": [asdict(climb) for climb in fetched.climbs],
            "headers": fetched.headers,
        }
        if fetched.cached is not None:
            answer["cached"] = asdict(fetched.cached)
        if fetched.archived is not None:
            answer["archived"] = asdict(fetched.archived)
        answer["html"] = page
        text = json.dumps(answer, indent=2, ensure_ascii=False)
    else:
        text = page
        for climb in fetched.climbs:
            click.echo(
                f"{climb.from_rung} -> {climb.to_rung} after {climb.seconds:.2f} s: "
                f"{climb.reason}",
                err=True,
            )
        kept = f", {_kept_line(fetched.cached)}" if fetched.cached else ""
        click.echo(
            f"{fetched.url}: {fetched.status}, from the {fetched.rung} rung in "
            f"{fetched.seconds:.2f} s{kept}",
            err=True,
        )
    if output is None:
        click.echo(text)
        return
    try:
        Path(output).write_text(text, encoding="utf-8")
    except OSError as failure:
        _fail(f"Could not write {output}: {failure.strerror or failure}", failure)
    if not as_json:
        click.echo(f"written to {output}", err=True)


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


@click.command("map")
@click.argument("url")
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=MAX_SITEMAP_URLS,
    show_default=True,
    help="The most addresses listed.",
)
@click.option(
    "--plain", is_flag=True, help="One address a line, for `sluicer batch -`."
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "csv"]),
    default="json",
    show_default=True,
    help="json: the map as one object; csv: a row per address (url, lastmod, sitemap).",
)
@_with_proxy
def map_command(url: str, limit: int, plain: bool, output_format: str) -> None:
    """List a site's addresses, from its sitemaps or its start page's links.

    Each sitemap is asked politely, through robots.txt and after the site's
    delay, and stderr says what became of each one.
    """
    if plain and output_format != "json":
        raise click.UsageError("--plain is one address a line; --format is another")
    try:
        found = map_site(url, limit=limit, **_sent())
    except (
        FetchExtraMissing,
        RobotsRefused,
        AddressRefused,
        FetchFailed,
        ResponseTooLarge,
    ) as failure:
        _fail(str(failure), failure)
    for read in found.sitemaps:
        said = read.error or f"{read.entries} entries ({read.kind})"
        click.echo(f"sitemap {read.url}: {said}", err=True)
    where = "its sitemaps" if found.source == "sitemaps" else "the start page's links"
    cut = ", cut short by a bound" if found.truncated else ""
    click.echo(f"Found {len(found.urls)} addresses in {where}{cut}.", err=True)
    if plain:
        for address in found.urls:
            click.echo(address.url)
    elif output_format == "csv":
        write = write_csv(sys.stdout, SITE_URL_COLUMNS)
        for address in found.urls:
            write(site_url_row(asdict(address)))
    else:
        click.echo(json.dumps(asdict(found), indent=2, ensure_ascii=False))
    if not found.urls:
        raise SystemExit(NOTHING_FOUND)


_many_options = [
    click.option(
        "-o",
        "--out",
        metavar="FILE",
        help="Write one JSON line per page here, not to stdout; the file is the "
        "state --resume continues from.",
    ),
    click.option(
        "--format",
        "output_format",
        type=click.Choice(["jsonl", "csv"]),
        default="jsonl",
        show_default=True,
        help="jsonl: a JSON line per page; csv: a row per page, its summary "
        "flattened into a column a question (docs/crawling.md says which).",
    ),
    click.option(
        "--resume",
        is_flag=True,
        help="Continue what --out already holds, fetching none of it again.",
    ),
    click.option(
        "--delay",
        type=click.FloatRange(min=0),
        default=DEFAULT_DELAY_SECONDS,
        show_default=True,
        help="The least seconds between two requests to one site; its "
        "robots.txt Crawl-delay wins when longer.",
    ),
    click.option(
        "--retries",
        type=click.IntRange(min=0),
        default=RETRIES,
        show_default=True,
        help="Ask a page again this many times when it did not answer, or "
        "answered 429 or a 5xx, each time twice as late; never a 4xx.",
    ),
    click.option(
        "--jobs",
        type=click.IntRange(min=1),
        default=CONCURRENCY,
        show_default=True,
        help="How many sites are asked at once, each still one request at a time.",
    ),
    click.option(
        "--induce",
        is_flag=True,
        help="Also read the rows a page repeats when it declares nothing about them.",
    ),
    click.option(
        "--respect",
        type=click.Choice(["tdm"]),
        multiple=True,
        help="Give a page whose rights are reserved as an error, not its data: "
        "tdm reads TDMRep's tdmrep.json, headers and meta tags.",
    ),
]


def _with_many_options(command: click.decorators.FC) -> click.decorators.FC:
    for option in reversed(_many_options):
        command = option(command)
    return command


@click.command("crawl")
@click.argument("url")
@click.option(
    "--max-pages",
    type=click.IntRange(min=1),
    default=MAX_PAGES,
    show_default=True,
    help="The most addresses taken, whatever becomes of them.",
)
@click.option(
    "--max-depth",
    type=click.IntRange(min=0),
    default=MAX_DEPTH,
    show_default=True,
    help="The most links from URL; 0 reads URL alone.",
)
@click.option(
    "--include",
    multiple=True,
    metavar="REGEX",
    help="Follow only links whose address this is found in; repeatable.",
)
@click.option(
    "--exclude",
    multiple=True,
    metavar="REGEX",
    help="Do not follow links whose address this is found in; repeatable.",
)
@click.option(
    "--any-site", is_flag=True, help="Follow links that leave URL's site too."
)
@click.option(
    "--template",
    type=click.Choice(TEMPLATES),
    help="A ready crawl: sitemap reads the pages URL's sitemaps list; shopify "
    "reads a Shopify shop's /products.json, a line per product.",
)
@_with_many_options
@_with_proxy
def crawl_command(
    url: str,
    max_pages: int,
    max_depth: int,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    any_site: bool,
    template: str | None,
    out: str | None,
    output_format: str,
    resume: bool,
    delay: float,
    retries: int,
    jobs: int,
    induce: bool,
    respect: tuple[str, ...],
) -> None:
    """Crawl a site from URL, politely, one JSON line per page.

    Breadth first, on URL's site unless --any-site, every page through
    robots.txt and one request at a time with the site's delay between. Run
    twice, it takes the same pages in the same order. --template sitemap
    reads the pages the site's sitemaps list instead, --include and
    --exclude choosing among them; --template shopify reads a Shopify shop's
    products from its /products.json, --max-pages of them at 250 a page.
    """
    table = output_format == "csv"
    if template is not None:
        _refuse_unused(template, include=include, induce=induce, respect=respect)
    _check_out(out, resume, table)
    state = None if table else out
    total: int | None = max_pages
    label = "Crawling"
    try:
        if template == "shopify":
            total, label = None, "Reading products"
            pages = shopify_products(
                url,
                max_pages,
                state=state,
                min_delay=delay,
                retries=retries,
                **_sent(),
            )
        elif template == "sitemap":
            label = "Reading"
            pages = sitemap_pages(
                url,
                max_pages,
                include=include,
                exclude=exclude,
                state=state,
                induce=induce,
                respect_tdm="tdm" in respect,
                min_delay=delay,
                retries=retries,
                concurrency=jobs,
                **_sent(),
            )
        else:
            pages = crawl_site(
                url,
                max_pages,
                max_depth,
                same_site=not any_site,
                include=include,
                exclude=exclude,
                state=state,
                induce=induce,
                respect_tdm="tdm" in respect,
                min_delay=delay,
                retries=retries,
                concurrency=jobs,
                **_sent(),
            )
    except (
        FetchExtraMissing,
        ValueError,
        RobotsRefused,
        AddressRefused,
        FetchFailed,
        ResponseTooLarge,
    ) as failure:
        _fail(str(failure), failure)
    _report(pages, out, table, total=total, label=label)


def _refuse_unused(template: str, **given: tuple[str, ...] | bool) -> None:
    """Refuse, before anything is asked, an option ``template`` would not use:
    ignored, it would read as obeyed."""
    context = click.get_current_context()
    unused = {
        "max_depth": "--max-depth",
        "any_site": "--any-site",
    }
    if template == "shopify":
        unused |= {
            "include": "--include",
            "exclude": "--exclude",
            "induce": "--induce",
            "respect": "--respect",
        }
    for name, option in unused.items():
        source = context.get_parameter_source(name)
        if source is not None and source.name not in ("DEFAULT", "DEFAULT_MAP"):
            raise click.UsageError(
                f"{option} does not apply to --template {template}: "
                + (
                    "a sitemap lists the pages, no link is followed"
                    if name in ("max_depth", "any_site")
                    else "a shop's products are read from its products.json, "
                    "not from pages"
                )
            )


@click.command("feed")
@click.argument("source")
@_with_fetch_options
def feed_command(
    source: str,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Read a feed's items: RSS, Atom or JSON Feed, from a URL, a file or stdin.

    A page that is not a feed but declares one, with <link rel=alternate>, is
    followed to it. Prints the feed as JSON: what it says about itself and
    every item, dates also normalised. Exits 1 for a feed with no item, 2 for
    what is not a feed.
    """
    from sluicer.declared.links import read_links
    from sluicer.document import load
    from sluicer.feeds import read_feed

    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    feed = read_feed(html, url=url)
    if feed is None:
        declared = read_links(load(html, url=url)).get("feeds", [])
        if not declared:
            _fail(f"{url or source} is not RSS, Atom or JSON Feed, and declares none.")
        followed = declared[0]["href"]
        click.echo(f"Reading the feed the page declares: {followed}", err=True)
        html, url, fetched = _read_source(
            followed, stealth, no_robots, None, at, respect, cache_dir, max_age
        )
        feed = read_feed(html, url=url)
        if feed is None:
            _fail(f"{followed}, which the page declares as a feed, is not one.")
    payload = {"url": url, **asdict(feed)}
    if fetched is not None:
        payload["fetch"] = {"rung": fetched.rung, "status": fetched.status}
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    if not feed.items:
        raise SystemExit(NOTHING_FOUND)


@click.command("warc")
@click.argument("files", nargs=-1, required=True)
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
def warc_command(files: tuple[str, ...], induce: bool, microformats: bool) -> None:
    """Read every page the WARC FILES hold, one JSON line per page.

    Plain or gzipped, as web archives and Common Crawl write them; - reads
    stdin. Each line is extract's answer, read with the headers the page was
    served with, and a "warc" object naming the file and the record. Nothing
    is fetched. Records that are not pages are passed over, and those left
    out -- revisits, non-HTML bodies, error answers -- are counted at the end.
    """
    from sluicer.warc import Skipped, WarcError, extract_warc

    read = 0
    for name in files:
        skipped = Skipped()
        count = 0
        try:
            for page, extraction in extract_warc(
                name, induce=induce, microformats=microformats, skipped=skipped
            ):
                count += 1
                payload = asdict(extraction)
                record = {
                    "file": "-" if name == "-" else name,
                    "record_id": page.record_id,
                    "date": page.date,
                    "digest": page.digest,
                    "status": page.status,
                }
                if page.truncated:
                    record["truncated"] = page.truncated
                click.echo(
                    json.dumps(
                        {"url": payload.pop("url"), "warc": record, **payload},
                        ensure_ascii=False,
                    )
                )
        except MicroformatsExtraMissing as missing:
            _fail(str(missing), missing)
        except (OSError, WarcError) as failure:
            _fail(f"{failure}; {count} pages were read before it.", failure)
        read += count
        said = f"; skipped {skipped}" if skipped else ""
        click.echo(f"{name}: {count} pages{said}.", err=True)
    if not read:
        raise SystemExit(NOTHING_FOUND)


@click.command("batch")
@click.argument("urls_file")
@_with_many_options
@_with_proxy
def batch_command(
    urls_file: str,
    out: str | None,
    output_format: str,
    resume: bool,
    delay: float,
    retries: int,
    jobs: int,
    induce: bool,
    respect: tuple[str, ...],
) -> None:
    """Read every address in URLS_FILE, politely, one JSON line per page.

    One address a line, blank lines and # comments skipped; - reads stdin,
    so `sluicer map URL --plain | sluicer batch -` reads a site's sitemap.
    No link is followed. Several sites are asked at once, each one request at
    a time, and the pages come out in the order the file lists them.
    """
    table = output_format == "csv"
    _check_out(out, resume, table)
    try:
        text = (
            sys.stdin.read()
            if urls_file == "-"
            else Path(urls_file).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError) as failure:
        _fail(f"Could not read {urls_file}: {failure}", failure)
    listed = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not listed:
        _fail(f"{urls_file} lists no address.")
    try:
        pages = extract_many(
            listed,
            state=None if table else out,
            induce=induce,
            respect_tdm="tdm" in respect,
            min_delay=delay,
            retries=retries,
            concurrency=jobs,
            **_sent(),
        )
    except (FetchExtraMissing, ValueError) as failure:
        _fail(str(failure), failure)
    _report(pages, out, table, total=len(listed), label="Reading")


def _check_out(out: str | None, resume: bool, table: bool = False) -> None:
    """Refuse to append to a file that holds pages unless asked to continue it.

    A crawl's file is hours of other people's servers' time; writing a second
    crawl onto its end would make both unusable. A table is not a state: it
    holds no page's links, so there is nothing to continue from.
    """
    if resume and out is None:
        _fail("--resume needs --out: the file is what the crawl continues from.")
    if resume and table:
        _fail(
            "--resume reads JSON Lines: a table holds no page's links to "
            "continue from. Write --format jsonl, and turn it into a table after."
        )
    if out is not None and not resume:
        path = Path(out)
        if path.is_file() and path.stat().st_size > 0:
            _fail(
                f"{out} already holds pages. Pass --resume to continue that "
                "crawl, or name another file."
            )


def _stderr_is_a_terminal() -> bool:
    """Whether a person is watching stderr, who is shown a bar, not a log."""
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _report(
    pages: Crawl,
    out: str | None,
    table: bool = False,
    total: int | None = None,
    label: str = "Crawling",
) -> None:
    """Write each page as its turn comes, say how it went, and exit by it.

    Each page is a JSON line, or with ``table`` a row of ``PAGE_COLUMNS``, on
    stdout or in ``out``. stderr says what became of each page, a line each,
    or, to a terminal, on one bar of ``total`` pages. The verdict is the whole
    crawl's, pages resumed from the file included, so a crawl finished in two
    runs exits as it would have in one.
    """
    if pages.resumed:
        click.echo(f"Resuming after the {pages.resumed} pages {out} holds.", err=True)
    tally = _Tally()
    count = pages.resumed
    watched = _stderr_is_a_terminal()
    try:
        with contextlib.ExitStack() as held:
            write = None
            if table:
                sink = (
                    held.enter_context(
                        Path(out).open("w", encoding="utf-8", newline="")
                    )
                    if out is not None
                    else sys.stdout
                )
                write = write_csv(sink, PAGE_COLUMNS)
            bar = (
                held.enter_context(
                    click.progressbar(
                        length=max(total or 0, count, 1),
                        label=label,
                        file=sys.stderr,
                        show_pos=True,
                        item_show_func=lambda said: said,
                    )
                )
                if watched
                else None
            )
            if bar is not None and count:
                bar.update(count)
            for page in pages:
                count += 1
                line = page.to_json()
                if write is not None:
                    write(page_row(line))
                    tally.add(line)
                elif out is None:
                    click.echo(json.dumps(line, ensure_ascii=False))
                    tally.add(line)
                said = page.error.code if page.error else f"{page.status} {page.rung}"
                if page.retries:
                    said += f", asked {len(page.retries) + 1} times"
                if bar is not None:
                    if bar.length is not None and count > bar.length:
                        bar.length = count
                    bar.update(1, f"{said}  {page.url}")
                else:
                    click.echo(f"{count:>5}  {said}  {page.url}", err=True)
            if bar is not None:
                # A crawl that ran out of links ends short of its budget: the
                # bar ends full at what it took.
                bar.length = bar.pos = max(count, 1)
                bar.render_progress()
    except KeyboardInterrupt:
        kept = ""
        if out is not None:
            kept = f"; {out} holds them" + ("" if table else ", and --resume continues")
        click.echo(f"Stopped after {count} pages{kept}.", err=True)
        raise SystemExit(INTERRUPTED) from None
    except FetchExtraMissing as missing:
        _fail(str(missing), missing)
    except OSError as failure:
        _fail(f"Could not write {out}: {failure.strerror or failure}", failure)
    if out is not None and not table:
        with Path(out).open(encoding="utf-8") as written:
            for raw in written:
                if raw.strip():
                    tally.add(json.loads(raw))
    why = {
        "max_pages": "; the page budget left links unfollowed",
        "time_budget": "; the time ran out",
    }.get(pages.stopped or "", "")
    click.echo(f"{tally}{why}." + (f" Wrote {out}." if out else ""), err=True)
    if not tally.read:
        raise SystemExit(COULD_NOT_READ)
    if not tally.found:
        raise SystemExit(NOTHING_FOUND)


class _Tally:
    """What a run of pages came to, counted one line at a time."""

    def __init__(self) -> None:
        self.pages = self.read = self.found = 0
        self.failed: dict[str, int] = {}

    def add(self, line: dict[str, object]) -> None:
        self.pages += 1
        error = line.get("error")
        if isinstance(error, dict):
            code = str(error.get("code"))
            self.failed[code] = self.failed.get(code, 0) + 1
            return
        self.read += 1
        self.found += bool(line.get("records") or line.get("summary"))

    def __str__(self) -> str:
        said = f"{self.pages} pages: {self.read} read"
        if self.failed:
            codes = ", ".join(f"{n} {code}" for code, n in sorted(self.failed.items()))
            said += f", {self.pages - self.read} failed ({codes})"
        return said


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
