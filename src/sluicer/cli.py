"""Command line front door.

Exit codes follow grep: 0 when something was found, 1 when the page was read
and holds nothing to report, 2 when it could not be read at all. A script can
tell "this page declares nothing" from "the fetch failed" without parsing
English.
"""

from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path

import click

from sluicer.api import extract as extract_html
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.fetch import FetchFailed, RobotsRefused, fetch as fetch_url
from sluicer.fetch.result import Fetched
from sluicer.fetch.scrapling_rungs import FetchExtraMissing
from sluicer.markdown import MarkdownExtraMissing, to_markdown

NOTHING_FOUND = 1
COULD_NOT_READ = 2


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


def _fail(message: str, cause: BaseException | None = None) -> None:
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
    if not result.records:
        click.echo("This page declares no structured data.", err=True)
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
