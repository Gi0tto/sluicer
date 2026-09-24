"""Command line front door.

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

import codecs
import io
import json
import logging
import re
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, NoReturn

import click

from sluicer.api import Extraction, extract as extract_html
from sluicer.audit import (
    Audit,
    Finding,
    LlmsTxt,
    RecordAudit,
    SiteFile,
    answered_with,
    audit as audit_page,
)
from sluicer.crawl import Crawl, crawl as crawl_site, extract_many
from sluicer.crawl.pages import MAX_DEPTH, MAX_PAGES
from sluicer.crawl.schedule import DEFAULT_DELAY_SECONDS
from sluicer.crawl.sitemaps import MAX_SITEMAP_URLS, map_site
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.declared.readers import READERS
from sluicer.diff import compare
from sluicer.extractor import (
    LOSSES,
    Extractor,
    NothingToLearn,
    compile_extractor,
    heal as heal_extractor,
    run_extractor,
)
from sluicer.fetch import AddressRefused, FetchFailed, RobotsRefused, fetch as fetch_url
from sluicer.fetch.result import Fetched, ResponseTooLarge
from sluicer.fetch.scrapling_rungs import FetchExtraMissing
from sluicer.http_api import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    TIME_BUDGET_SECONDS,
    TOKEN_ENV,
    ApiExtraMissing,
    Unprotected,
    serve as serve_http,
)
from sluicer.markdown import MarkdownExtraMissing, to_markdown

NOTHING_FOUND = 1
COULD_NOT_READ = 2
CONTRACT_BROKEN = 3
INTERRUPTED = 130


@click.group()
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


def _fail(message: str, cause: BaseException | None = None) -> NoReturn:
    click.echo(message, err=True)
    raise SystemExit(COULD_NOT_READ) from cause


_fetch_options = [
    click.option(
        "--stealth",
        is_flag=True,
        help="Allow the stealth rung, which does not announce itself.",
    ),
    click.option(
        "--no-robots",
        is_flag=True,
        help="Fetch even where the site's robots.txt says no.",
    ),
    click.option(
        "--url",
        "base_url",
        metavar="URL",
        help="The address a file or stdin came from, to resolve its links.",
    ),
    click.option(
        "--respect",
        type=click.Choice(["tdm"]),
        multiple=True,
        help="Refuse a page whose rights are reserved: tdm reads TDMRep's "
        "tdmrep.json, headers and meta tags.",
    ),
    click.option(
        "--cache",
        "cache_dir",
        metavar="DIR",
        help="Keep fetched pages in DIR, and ask the site with their ETag or "
        "Last-Modified whether a page changed before fetching it again.",
    ),
    click.option(
        "--max-age",
        type=click.FloatRange(min=0),
        metavar="SECONDS",
        help="With --cache, give a page kept for less than SECONDS back without "
        "asking its site at all.",
    ),
    click.option(
        "--at",
        metavar="DATE",
        help="Read a URL as the Wayback Machine captured it nearest to DATE "
        "(2025, 2025-06, 2025-06-01), not from its site.",
    ),
]


def _with_fetch_options(command: click.decorators.FC) -> click.decorators.FC:
    for option in reversed(_fetch_options):
        command = option(command)
    return command


def _read_source(
    source: str,
    stealth: bool = False,
    no_robots: bool = False,
    base_url: str | None = None,
    at: str | None = None,
    respect: tuple[str, ...] = (),
    cache_dir: str | None = None,
    max_age: float | None = None,
) -> tuple[str | bytes, str | None, Fetched | None]:
    """``_read_page``, then refused when ``respect`` names a reservation the
    page makes: its text and data mining rights, for ``tdm``."""
    if max_age is not None and cache_dir is None:
        _fail("--max-age says how long a kept page is good for; it needs --cache.")
    if cache_dir is not None and at is not None:
        _fail("--cache keeps live pages; a capture read with --at never changes.")
    html, url, fetched = _read_page(
        source, stealth, no_robots, base_url, at, cache_dir, max_age
    )
    if "tdm" in respect:
        _refuse_reserved(html, url, fetched, obey_robots=not no_robots)
    return html, url, fetched


def _refuse_reserved(
    html: str | bytes, url: str | None, fetched: Fetched | None, obey_robots: bool
) -> None:
    """Exit with ``COULD_NOT_READ`` when TDMRep reserves the page's TDM rights.

    The site's tdmrep.json is read for a page fetched live; an archived
    capture and a file are judged by their own headers and meta tags.
    """
    from sluicer.declared.headers import lowered, read_header_rights
    from sluicer.declared.rights import read_rights
    from sluicer.declared.tdmrep import read_tdmrep, reservation
    from sluicer.document import load

    headers = lowered(fetched.headers) if fetched is not None else {}
    rights = read_rights(
        load(html, url=url), read_header_rights(headers) if headers else None
    )
    rules = []
    if fetched is not None and fetched.archived is None and url:
        from sluicer.fetch.site import read_tdmrep_file

        rules = read_tdmrep(read_tdmrep_file(url, obey_robots=obey_robots).text)
    found = reservation(rules, url, rights)
    if found is not None and found.reserved:
        policy = f", policy {found.policy}" if found.policy else ""
        _fail(
            f"{url or 'The page'} reserves its text and data mining rights "
            f"(TDMRep, by its {found.source}{policy}), and --respect tdm was given."
        )


def _read_page(
    source: str,
    stealth: bool = False,
    no_robots: bool = False,
    base_url: str | None = None,
    at: str | None = None,
    cache_dir: str | None = None,
    max_age: float | None = None,
) -> tuple[str | bytes, str | None, Fetched | None]:
    """Return the HTML of ``source``, the URL to attribute it to, and the fetch record.

    ``source`` is a URL, a path, or ``-`` for standard input. Every way of
    failing to read it -- a missing extra, a refusal, a failed fetch, a missing,
    empty or non-file path -- exits here with a message and ``COULD_NOT_READ``,
    one place for both commands. The fetch record is None for a file or stdin.
    """
    is_url = source.lower().startswith(("http://", "https://"))
    if at is not None and not is_url:
        _fail(f"--at reads an address from the Wayback Machine; {source} is not one.")
    if at is not None and stealth:
        _fail("--at reads the archive over plain HTTP; --stealth has no rung there.")
    if is_url:
        # Only FetchExtraMissing, not ImportError: an import failure inside a
        # working scrapling install is a bug and keeps its traceback.
        try:
            if at is not None:
                from sluicer.fetch.archive import fetch_archived

                fetched = fetch_archived(source, at, obey_robots=not no_robots)
            elif cache_dir is not None:
                from sluicer.fetch.cache import Cache, fetch_cached

                fetched = fetch_cached(
                    source,
                    Cache(cache_dir, max_age),
                    stealth=stealth,
                    obey_robots=not no_robots,
                )
            else:
                fetched = fetch_url(source, stealth=stealth, obey_robots=not no_robots)
        except FetchExtraMissing as missing:
            _fail(str(missing), missing)
        except RobotsRefused as refused:
            # The site told us no: an answer, not a malfunction.
            _fail(str(refused), refused)
        except FetchFailed as failed:
            # Every rung failed, whatever library it was built on: a browser's
            # timeout, for one, is not an OSError.
            _fail(str(failed), failed)
        except ResponseTooLarge as heavy:
            _fail(str(heavy), heavy)
        except (OSError, ValueError) as failure:
            # An operational failure is a message and a bug is a traceback.
            # OSError covers down, unresolvable and timed out; ValueError is a
            # rung that came back with no HTML. Anything else keeps its
            # traceback, deliberately.
            _fail(
                f"Could not fetch {source}: {type(failure).__name__}: {failure}",
                failure,
            )
        return fetched.html, fetched.url, fetched

    if source == "-":
        data = sys.stdin.buffer.read()
        if not data.strip():
            _fail("Standard input contains no HTML.")
        return data, base_url, None

    path = Path(source)

    # By hand, not click.Path(exists=True): the same argument also takes a URL.
    if not path.is_file():
        _fail(
            f"{source} is not a file." if path.exists() else f"{source} does not exist."
        )

    # Bytes, not text: decoding here would pick the process default before
    # the page's own charset declaration is read, and destroy every byte that
    # was not UTF-8. extract() and to_markdown() both decode bytes properly.
    data = path.read_bytes()

    # An empty file is a user mistake and gets a message about the file;
    # load() would quietly read it as a page that declares nothing.
    if not data.strip():
        _fail("This file contains no HTML.")

    # A path is not an address: handed to the readers as the page's URL it
    # would resolve every relative link against the file name.
    return data, base_url, None


@main.command()
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


@main.command()
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
        raise SystemExit(NOTHING_FOUND)


def _kept_line(hit: Any) -> str:
    """How a page came from the cache, said for a person."""
    if hit.revalidated:
        return "kept, and the site said it has not changed (304)"
    return f"kept {hit.age:.0f} s ago, within --max-age: the site was not asked"


def _moment(stamp: str) -> str:
    """An archive's ``YYYYMMDDhhmmss``, as far as it goes, written as ISO."""
    parts = [stamp[:4], stamp[4:6], stamp[6:8]]
    day = "-".join(part for part in parts if part)
    time_ = ":".join(p for p in (stamp[8:10], stamp[10:12], stamp[12:14]) if p)
    return f"{day} {time_}" if time_ else day


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


def _brief(value: object, limit: int = 72) -> str:
    """A value on one line: text as it is, a nested value as compact JSON."""
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


@main.command("diff")
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
    reported as rewritten.
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


@main.command()
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


def _read_pages(
    sources: tuple[str, ...], stealth: bool, no_robots: bool
) -> list[tuple[str | bytes, str | None]]:
    return [_read_source(source, stealth, no_robots, None)[:2] for source in sources]


def _load_extractor(path: str) -> Extractor:
    try:
        return Extractor.from_json(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError) as failure:
        _fail(f"{path} is not an extractor: {failure}", failure)


@main.command("compile")
@click.argument("sources", nargs=-1, required=True)
@click.option("-o", "--output", required=True, help="Where to write the extractor.")
@click.option(
    "--listing/--no-listing",
    default=None,
    help="Learn the rows the pages repeat (default: only if they declare no thing).",
)
@click.option(
    "--want",
    "wanted",
    multiple=True,
    metavar="NAME=VALUE",
    help="A value one row holds, and the column's name: --want price=41.90. "
    "Chooses the listing and keeps only the columns named.",
)
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
def compile_command(
    sources: tuple[str, ...],
    output: str,
    listing: bool | None,
    wanted: tuple[str, ...],
    stealth: bool,
    no_robots: bool,
) -> None:
    """Learn an extractor from pages of one template, and write it to a file.

    With --want, the examples say which repeated group is the listing and
    what its columns are called: --want title="Brake pad set" --want
    price=41.90 learns the listing whose rows hold both, with those two
    columns. When no repeated group holds them -- a product page -- or with
    --no-listing, they are the page's own values, each learnt where it sits.
    A value that is nowhere is an error that names it.
    """
    want: dict[str, str] | None = None
    if wanted:
        want = {}
        for pair in wanted:
            name, equals, value = pair.partition("=")
            if not equals or not name.strip() or not value.strip():
                _fail(f"--want takes NAME=VALUE, not {pair!r}.")
            want[name.strip()] = value
    pages = _read_pages(sources, stealth, no_robots)
    try:
        extractor = compile_extractor(
            pages, listing=listing, names=list(sources), want=want
        )
    except NothingToLearn as nothing:
        click.echo(f"Learnt nothing: {nothing}.", err=True)
        raise SystemExit(NOTHING_FOUND) from nothing
    _write(output, extractor.to_json())
    learnt = []
    if extractor.fields:
        learnt.append(
            f"{len(extractor.fields)} page fields ("
            + ", ".join(
                f"{f.name} after {f.anchor.label!r}"
                if f.anchor
                else f"{f.name} at {f.path}"
                for f in extractor.fields
            )
            + ")"
        )
    if extractor.listing is not None:
        rows = extractor.listing.rows
        learnt.append(
            f"a listing at {extractor.listing.container}, {rows[0]}-{rows[1]} rows "
            f"of {len(extractor.listing.fields)} fields"
        )
    if extractor.summary:
        learnt.append(f"{len(extractor.summary)} summary answers")
    if extractor.types:
        learnt.append("declared " + ", ".join(extractor.types))
    click.echo(f"Learnt {'; '.join(learnt)}. Wrote {output}.", err=True)
    for note in extractor.notes:
        click.echo(f"Note: {note}.", err=True)


def _write(path: str, text: str) -> None:
    try:
        Path(path).write_text(text, encoding="utf-8")
    except OSError as failure:
        _fail(f"Could not write {path}: {failure.strerror or failure}", failure)


@main.command("run")
@click.argument("extractor_file")
@click.argument("sources", nargs=-1, required=True)
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
def run_command(
    extractor_file: str, sources: tuple[str, ...], stealth: bool, no_robots: bool
) -> None:
    """Replay an extractor on pages, and exit 3 if any page broke its contract."""
    extractor = _load_extractor(extractor_file)
    pages = []
    broken = False
    for source, (html, url) in zip(
        sources, _read_pages(sources, stealth, no_robots), strict=True
    ):
        run = run_extractor(extractor, html, url=url)
        failed = [asdict(check) for check in run.checks if not check.ok]
        pages.append(
            {
                "source": source,
                "url": run.url,
                "ok": run.ok,
                "rows": run.rows,
                "fields": run.fields,
                "summary": run.summary,
                "failed": failed,
            }
        )
        for check in run.checks:
            if not check.ok:
                broken = True
                click.echo(
                    f"FAILED {source}: expected {check.expected}, got {check.got}",
                    err=True,
                )
    click.echo(
        json.dumps(
            {"extractor": extractor_file, "pages": pages}, indent=2, ensure_ascii=False
        )
    )
    if broken:
        raise SystemExit(CONTRACT_BROKEN)


@main.command("heal")
@click.argument("extractor_file")
@click.argument("sources", nargs=-1, required=True)
@click.option("-o", "--output", help="Where to write the healed extractor.")
@click.option(
    "--force",
    is_flag=True,
    help="Write the healed extractor even when healing lost something.",
)
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
def heal_command(
    extractor_file: str,
    sources: tuple[str, ...],
    output: str | None,
    force: bool,
    stealth: bool,
    no_robots: bool,
) -> None:
    """Learn pages again and say what moved; write the result only with -o.

    Exits 3 when a field, a summary answer, a type or the listing was lost for
    good: healing moved what it could, and what it could not needs a person.
    Nothing is written then without --force, so a lossy extractor never
    quietly replaces the one that would have kept failing.
    """
    extractor = _load_extractor(extractor_file)
    pages = _read_pages(sources, stealth, no_robots)
    try:
        healed, changes = heal_extractor(extractor, pages, names=list(sources))
    except NothingToLearn as nothing:
        click.echo(f"The pages hold nothing to heal from: {nothing}.", err=True)
        raise SystemExit(CONTRACT_BROKEN) from nothing
    for change in changes:
        if change.kind == "kept":
            continue
        if change.before and change.after:
            said = f"{change.kind}: {change.before} -> {change.after}"
            if change.evidence and change.evidence["samples"]:
                e = change.evidence
                said += (
                    f" ({e['seen']} of {e['samples']} learnt values found there;"
                    f" the next best place had {e['runner_up']})"
                )
            click.echo(said, err=True)
        else:
            click.echo(f"{change.kind}: {change.before or change.after}", err=True)
    lost = any(c.kind in LOSSES for c in changes)
    if output and (force or not lost):
        _write(output, healed.to_json())
        click.echo(f"Wrote {output}.", err=True)
    elif output:
        click.echo(
            f"Did not write {output}: healing lost data or left a move for you "
            "to decide. Pass --force to write it.",
            err=True,
        )
    click.echo(
        json.dumps(
            {"changes": [asdict(c) for c in changes]}, indent=2, ensure_ascii=False
        )
    )
    if lost:
        raise SystemExit(CONTRACT_BROKEN)


@main.command()
@click.option(
    "--host",
    default=DEFAULT_HOST,
    show_default=True,
    help=f"Where to listen. Anything but loopback needs {TOKEN_ENV}.",
)
@click.option(
    "--port", default=DEFAULT_PORT, show_default=True, type=click.IntRange(0, 65535)
)
@click.option(
    "--timeout",
    default=TIME_BUDGET_SECONDS,
    show_default=True,
    type=click.FloatRange(min=0, min_open=True),
    help="Seconds a request may take before it is answered 504.",
)
@click.option(
    "--allow-unauthenticated",
    is_flag=True,
    help="Listen beyond loopback with no token, behind something that already "
    "decides who may call.",
)
def serve(host: str, port: int, timeout: float, allow_unauthenticated: bool) -> None:
    """Serve the MCP server's tools over HTTP (needs sluicer[api]).

    POST /v1/tools/<name> with the tool's arguments as a JSON object answers
    what the tool answers; GET /v1/tools and /openapi.json describe them. The
    token, when SLUICER_API_TOKEN is set, goes in "Authorization: Bearer".
    Private addresses are refused unless SLUICER_ALLOW_PRIVATE=1, as for the
    MCP server. Exits 2 without listening when it cannot serve safely.
    """
    try:
        serve_http(
            host, port, timeout=timeout, allow_unauthenticated=allow_unauthenticated
        )
    except (ApiExtraMissing, Unprotected) as refused:
        _fail(str(refused), refused)


@main.command("mcp")
@click.option(
    "--tools",
    help="Register only these tools, comma-separated: "
    "--tools extract_declared,page_markdown. All ten by default.",
)
def mcp_command(tools: str | None) -> None:
    """Run the MCP server over stdio (needs sluicer[mcp]), as sluicer-mcp does.

    For a client that starts a package's own command, as the MCP Registry's
    entry does: uvx --with "sluicer[mcp]" sluicer mcp. Each tool registered
    costs an agent context whether it is called or not; --tools, or the
    SLUICER_MCP_TOOLS variable, keeps only those named.
    """
    from sluicer.mcp_server import main as run

    if tools is None:
        run()
    else:
        run(tools=[name.strip() for name in tools.split(",") if name.strip()])


@main.command("audit")
@click.argument("source")
@click.option("--json", "as_json", is_flag=True, help="Print the audit as JSON.")
@click.option(
    "--no-site",
    is_flag=True,
    help="Do not read the site's robots.txt and llms.txt for a URL.",
)
@_with_fetch_options
def audit_command(
    source: str,
    as_json: bool,
    no_site: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Check what a page declares against what Google documents, and more.

    For every record JSON-LD, microdata and RDFa declare: the rich-result
    features its type is documented for, the required and recommended
    properties it lacks, and the values in a form the documentation refuses.
    Then what the page lacks -- a title, a description, a canonical, OpenGraph
    -- and where two vocabularies contradict each other. For a URL, also which
    AI agents the site's robots.txt admits and whether its llms.txt keeps to
    llmstxt.org's format; a file or stdin reads no site.

    Exits 3 when anything is an error -- a required property missing, a value
    refused, an llms.txt with no name -- whatever else is true, since that is a
    page breaking a stated rule. Otherwise 1 when no record was declared, since
    there was nothing to audit, and 0. 2, as everywhere, when the page could
    not be read.
    """
    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    site = None
    try:
        if fetched is not None and not no_site and fetched.archived is None:
            from sluicer.fetch.site import read_site

            site = read_site(fetched.url, obey_robots=not no_robots)
        result = audit_page(html, url=url, site=site)
    except FetchExtraMissing as missing:
        _fail(str(missing), missing)
    if fetched is not None and fetched.archived is not None and not no_site:
        result.not_checked.insert(
            0,
            "The site's robots.txt and llms.txt: the page is a capture of "
            f"{fetched.archived.captured}, and today's files say nothing of it.",
        )
    if fetched is not None and not 200 <= fetched.status < 300:
        result.not_checked.insert(0, answered_with(fetched.status))
    if as_json:
        payload = asdict(result)
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
                    {"cached": asdict(fetched.cached)}
                    if fetched.cached is not None
                    else {}
                ),
            }
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        shown = "standard input" if source == "-" else (url or source)
        click.echo(_audit_report(shown, result, fetched, not no_robots, no_site))
    if result.errors:
        raise SystemExit(CONTRACT_BROKEN)
    if not result.records:
        raise SystemExit(NOTHING_FOUND)


# Findings a feature's own line already reports, as its missing properties.
_SUMMED = frozenset({"missing-required", "missing-recommended", "incomplete-part"})


def _audit_report(
    shown: str,
    result: Audit,
    fetched: Fetched | None,
    obeyed_robots: bool,
    no_site: bool,
) -> str:
    """The report ``audit`` prints, deterministic for a given page and site."""
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
    lines.append("")
    by_source: dict[str, int] = {}
    for record in result.records:
        by_source[record.source] = by_source.get(record.source, 0) + 1
    counted = ", ".join(f"{name} {n}" for name, n in by_source.items())
    records = len(result.records)
    lines.append(
        f"records   {records} audited"
        + (f" ({counted})" if counted else ", none declared")
    )
    for record in result.records:
        lines.extend(_record_lines(record))
    lines.append("")
    lines.append(f"page      {_counted(len(result.page), 'finding')}")
    lines.extend(_finding_line(finding) for finding in result.page)
    if result.robots_txt is not None:
        lines.append("")
        lines.extend(_agent_lines(result, result.robots_txt))
    if result.llms_txt is not None and result.llms_full_txt is not None:
        lines.append("")
        lines.extend(_llms_lines("llms.txt", result.llms_txt))
        lines.extend(_llms_lines("llms-full", result.llms_full_txt))
    if result.tdm is not None:
        said = "reserved" if result.tdm.reserved else "not reserved"
        policy = f", policy {result.tdm.policy}" if result.tdm.policy else ""
        lines.append(
            f"tdm       text and data mining {said} "
            f"(TDMRep, by its {result.tdm.source}{policy})"
        )
    notes = list(result.not_checked)
    if fetched is None and not no_site:
        notes = [
            note.replace("the site was not read.", "the site is read only for a URL.")
            for note in notes
        ]
    elif no_site:
        notes = [
            note.replace("the site was not read.", "not asked (--no-site).")
            for note in notes
        ]
    if notes:
        lines.append("")
        lines.append("not checked")
        lines.extend(f"  {note}" for note in notes)
    lines.append("")
    lines.append(
        f"summary   {_counted(result.errors, 'error')}, "
        f"{_counted(result.warnings, 'warning')}, {_counted(result.notes, 'note')}"
    )
    return "\n".join(lines)


def _counted(n: int, what: str) -> str:
    return f"{n} {what}{'s' if n != 1 else ''}"


def _record_lines(record: RecordAudit) -> list[str]:
    kind = " / ".join(record.types) or "no type"
    lines = [f"  {kind}  ({record.source} record {record.index})"]
    if not record.features:
        lines.append("    no rich-result feature is documented for this type")
    width = max((len(feature.name) for feature in record.features), default=0)
    for feature in record.features:
        if feature.requirements_met is None:
            verdict = f"retired: {feature.note}"
        elif feature.missing_required:
            missing = feature.missing_required
            verdict = f"{len(missing)} required missing: {_collapsed(missing)}"
        elif feature.requirements_met:
            verdict = "requirements met"
        else:
            verdict = "a value this feature refuses"
        if feature.status == "limited":
            verdict += "  (limited: see the note in --json)"
        lines.append(f"    {feature.name:{width}}  {verdict}")
        if feature.missing_recommended:
            lines.append(
                f"    {'':{width}}  recommended, missing: "
                + _collapsed(feature.missing_recommended)
            )
        if feature.incomplete_parts:
            lines.append(
                f"    {'':{width}}  optional parts unusable, missing: "
                + _collapsed(feature.incomplete_parts)
            )
    for name in record.not_checked:
        lines.append(f"    not checked here: {name}")
    lines.extend(
        "  " + _finding_line(finding)
        for finding in record.findings
        if finding.code not in _SUMMED
    )
    return lines


def _collapsed(paths: list[str]) -> str:
    """Paths with their list positions folded: twenty reviews lacking a date are
    one entry, ``review[].datePublished (20)``. ``--json`` keeps every one."""
    counted: dict[str, int] = {}
    for path in paths:
        folded = re.sub(r"\[[0-9]+\]", "[]", path)
        counted[folded] = counted.get(folded, 0) + 1
    return ", ".join(path + (f" ({n})" if n > 1 else "") for path, n in counted.items())


def _finding_line(finding: Finding) -> str:
    where = (
        f"{finding.path}: "
        if finding.path and finding.path not in finding.message
        else ""
    )
    rule = f"  [{finding.rule}]" if finding.rule else ""
    return f"  {finding.severity:7}  {where}{finding.message}{rule}"


def _agent_lines(result: Audit, robots: SiteFile) -> list[str]:
    if robots.status is not None:
        state = f"status {robots.status}"
        if 400 <= robots.status < 500:
            state += ", none published: everything is allowed"
    else:
        state = f"not read: {robots.error}"
    lines = [f"agents    robots.txt {robots.url}, {state}"]
    token = max((len(verdict.agent) for verdict in result.crawlers), default=0)
    vendor = max((len(verdict.vendor) for verdict in result.crawlers), default=0)
    for verdict in result.crawlers:
        allowed = {True: "allowed", False: "disallowed", None: "unknown"}[
            verdict.allowed
        ]
        group = f"User-agent: {verdict.group}" if verdict.group else "no group applies"
        caveat = "  (may ignore robots.txt)" if verdict.honours_robots is False else ""
        lines.append(
            f"  {verdict.agent:{token}}  {verdict.vendor:{vendor}}  "
            f"{verdict.use:8}  {allowed:10}  {group}{caveat}"
        )
    # A group states its preferences for every agent it decides for, so they
    # are said once per group, not once per agent.
    stated: dict[str, list[str]] = {}
    for verdict in result.crawlers:
        for label, said in (
            ("content-usage", verdict.content_usage),
            ("content-signal", verdict.content_signal),
        ):
            if said and verdict.group is not None:
                line = f"{label} " + ", ".join(f"{k}={v}" for k, v in said.items())
                if line not in stated.setdefault(verdict.group, []):
                    stated[verdict.group].append(line)
    for group, statements in stated.items():
        for line in statements:
            lines.append(f"          User-agent: {group} states {line}")
    if result.other_agents:
        lines.append(
            "          also named, by no agent documented here: "
            + ", ".join(result.other_agents)
        )
    return lines


def _llms_lines(label: str, llms: LlmsTxt) -> list[str]:
    if not llms.present:
        answered = f"status {llms.status}" if llms.status is not None else "no answer"
        lines = [f"{label:9} {llms.url}: not served ({answered})"]
    elif label == "llms.txt":
        described = f'"{llms.name}"' if llms.name else "no name"
        lines = [
            f"{label:9} {llms.url}: {described}, "
            f"{_counted(len(llms.sections), 'section')}, {_counted(llms.links, 'link')}"
        ]
    else:
        lines = [f"{label:9} {llms.url}: {llms.length:,} characters"]
    lines.extend(_finding_line(finding) for finding in llms.findings)
    return lines


@main.command("map")
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
def map_command(url: str, limit: int, plain: bool) -> None:
    """List a site's addresses, from its sitemaps or its start page's links.

    Each sitemap is asked politely, through robots.txt and after the site's
    delay, and stderr says what became of each one.
    """
    try:
        found = map_site(url, limit=limit)
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


@main.command("crawl")
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
@_with_many_options
def crawl_command(
    url: str,
    max_pages: int,
    max_depth: int,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    any_site: bool,
    out: str | None,
    resume: bool,
    delay: float,
    induce: bool,
    respect: tuple[str, ...],
) -> None:
    """Crawl a site from URL, politely, one JSON line per page.

    Breadth first, on URL's site unless --any-site, every page through
    robots.txt and one request at a time with the site's delay between. Run
    twice, it takes the same pages in the same order.
    """
    _check_out(out, resume)
    try:
        pages = crawl_site(
            url,
            max_pages,
            max_depth,
            same_site=not any_site,
            include=include,
            exclude=exclude,
            state=out,
            induce=induce,
            respect_tdm="tdm" in respect,
            min_delay=delay,
        )
    except (FetchExtraMissing, ValueError) as failure:
        _fail(str(failure), failure)
    _report(pages, out)


@main.command("feed")
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


@main.command("warc")
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


@main.command("batch")
@click.argument("urls_file")
@_with_many_options
def batch_command(
    urls_file: str,
    out: str | None,
    resume: bool,
    delay: float,
    induce: bool,
    respect: tuple[str, ...],
) -> None:
    """Read every address in URLS_FILE, politely, one JSON line per page.

    One address a line, blank lines and # comments skipped; - reads stdin,
    so `sluicer map URL --plain | sluicer batch -` reads a site's sitemap.
    No link is followed. Several sites are asked at once, each one request at
    a time, and the pages come out in the order the file lists them.
    """
    _check_out(out, resume)
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
            state=out,
            induce=induce,
            respect_tdm="tdm" in respect,
            min_delay=delay,
        )
    except (FetchExtraMissing, ValueError) as failure:
        _fail(str(failure), failure)
    _report(pages, out)


def _check_out(out: str | None, resume: bool) -> None:
    """Refuse to append to a file that holds pages unless asked to continue it.

    A crawl's file is hours of other people's servers' time; writing a second
    crawl onto its end would make both unusable.
    """
    if resume and out is None:
        _fail("--resume needs --out: the file is what the crawl continues from.")
    if out is not None and not resume:
        path = Path(out)
        if path.is_file() and path.stat().st_size > 0:
            _fail(
                f"{out} already holds pages. Pass --resume to continue that "
                "crawl, or name another file."
            )


def _report(pages: Crawl, out: str | None) -> None:
    """Write each page as its turn comes, say how it went, and exit by it.

    The verdict is the whole crawl's, pages resumed from the file included, so
    a crawl finished in two runs exits as it would have in one.
    """
    if pages.resumed:
        click.echo(f"Resuming after the {pages.resumed} pages {out} holds.", err=True)
    tally = _Tally()
    count = pages.resumed
    try:
        for page in pages:
            count += 1
            line = page.to_json()
            if out is None:
                click.echo(json.dumps(line, ensure_ascii=False))
                tally.add(line)
            said = page.error.code if page.error else f"{page.status} {page.rung}"
            click.echo(f"{count:>5}  {said}  {page.url}", err=True)
    except KeyboardInterrupt:
        kept = f"; {out} holds them, and --resume continues" if out else ""
        click.echo(f"Stopped after {count} pages{kept}.", err=True)
        raise SystemExit(INTERRUPTED) from None
    except FetchExtraMissing as missing:
        _fail(str(missing), missing)
    except OSError as failure:
        _fail(f"Could not write {out}: {failure.strerror or failure}", failure)
    if out is not None:
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
