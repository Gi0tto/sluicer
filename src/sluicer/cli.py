"""Command line front door.

Exit codes follow grep: 0 when something was found -- a record, or at least one
summary answer -- 1 when the page was read and gives nothing at all, 2 when it
could not be read. A script can tell "this page gives nothing" from "the fetch
failed" without parsing English. ``run`` and ``heal`` add 3: a page broke the
extractor's contract, or healing lost a field, and that is never a success.
"""

from __future__ import annotations

import json
import logging
import sys
from collections.abc import Mapping
from dataclasses import asdict
from pathlib import Path
from typing import Any, NoReturn

import click

from sluicer.api import Extraction, extract as extract_html
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.declared.readers import READERS
from sluicer.extractor import (
    LOSSES,
    Extractor,
    NothingToLearn,
    compile_extractor,
    heal as heal_extractor,
    run_extractor,
)
from sluicer.fetch import FetchFailed, RobotsRefused, fetch as fetch_url
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


@click.group()
@click.version_option(package_name="sluicer")
def main() -> None:
    """Turn a web page into structured data with no model in the loop.

    SOURCE is a URL, a saved HTML file, or - for standard input.
    """
    _quiet_scrapling()


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
) -> tuple[str | bytes, str | None, Fetched | None]:
    """Return the HTML of ``source``, the URL to attribute it to, and the fetch record.

    ``source`` is a URL, a path, or ``-`` for standard input. Every way of
    failing to read it -- a missing extra, a refusal, a failed fetch, a missing,
    empty or non-file path -- exits here with a message and ``COULD_NOT_READ``,
    one place for both commands. The fetch record is None for a file or stdin.
    """
    if source.lower().startswith(("http://", "https://")):
        # Only FetchExtraMissing, not ImportError: an import failure inside a
        # working scrapling install is a bug and keeps its traceback.
        try:
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
@_with_fetch_options
def extract(
    source: str,
    induce: bool,
    microformats: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
) -> None:
    """Read the structured data a URL, a file or stdin declares."""
    html, url, fetched = _read_source(source, stealth, no_robots, base_url)
    try:
        result = extract_html(html, url=url, induce=induce, microformats=microformats)
    except MicroformatsExtraMissing as missing:
        _fail(str(missing), missing)
    if not result.records and not result.summary:
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
    if fetched is not None:
        payload["fetch"] = {
            "rung": fetched.rung,
            "status": fetched.status,
            "climbs": [asdict(climb) for climb in fetched.climbs],
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
@_with_fetch_options
def inspect(
    source: str,
    induce: bool,
    microformats: bool,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
) -> None:
    """Show, for a person, what a page declares and where each answer came from.

    The same reading as ``extract``, laid out to be read rather than parsed:
    what the fetch cost, which vocabularies said something, every record with
    the source of each field, and every summary answer with its source and
    key. Exit codes are ``extract``'s.
    """
    html, url, fetched = _read_source(source, stealth, no_robots, base_url)
    try:
        result = extract_html(html, url=url, induce=induce, microformats=microformats)
    except MicroformatsExtraMissing as missing:
        _fail(str(missing), missing)
    shown = "standard input" if source == "-" else (url or source)
    click.echo(_inspection(shown, result, fetched, microformats, not no_robots))
    if not result.records and not result.summary:
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
        for climb in fetched.climbs:
            lines.append(
                f"          {climb.from_rung} -> {climb.to_rung} after "
                f"{climb.seconds:.2f} s: {climb.reason}"
            )
        lines.append(
            "robots    allowed by the site's robots.txt"
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


@main.command()
@click.argument("source")
@_with_fetch_options
def markdown(source: str, stealth: bool, no_robots: bool, base_url: str | None) -> None:
    """Print the main content of a URL, a file or stdin as markdown."""
    html, url, _fetched = _read_source(source, stealth, no_robots, base_url)
    # MarkdownExtraMissing: trafilatura is not installed; the message says how.
    try:
        content = to_markdown(html, url=url)
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
@click.option("--stealth", is_flag=True, help="Allow the stealth rung.")
@click.option("--no-robots", is_flag=True, help="Fetch even where robots.txt says no.")
def compile_command(
    sources: tuple[str, ...],
    output: str,
    listing: bool | None,
    stealth: bool,
    no_robots: bool,
) -> None:
    """Learn an extractor from pages of one template, and write it to a file."""
    pages = _read_pages(sources, stealth, no_robots)
    try:
        extractor = compile_extractor(pages, listing=listing, names=list(sources))
    except NothingToLearn as nothing:
        click.echo(f"Learnt nothing: {nothing}.", err=True)
        raise SystemExit(NOTHING_FOUND) from nothing
    _write(output, extractor.to_json())
    learnt = []
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
            f"Did not write {output}: healing lost data. Pass --force to write it.",
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
