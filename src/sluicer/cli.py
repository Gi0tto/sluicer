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
    """Keep scrapling's per-request INFO lines out of stderr.

    A filter and not a level: scrapling sets its logger to INFO when it is
    imported, which happens later, at the first fetch, and would undo a level
    set here. A filter on the logger survives that.
    """
    logging.getLogger("scrapling").addFilter(
        lambda record: record.levelno >= logging.WARNING
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

    ``source`` is either a URL or a path to a saved HTML file, exactly as
    ``extract`` and ``markdown`` both accept it. A URL is fetched through the
    same ``fetch_url`` seam; a path is read from disk. Every operational
    failure along the way -- a missing fetch extra, a site's own robots.txt
    refusing us, an operational fetch failure, a missing file, a directory,
    an empty file -- is reported here with the message and exit code both
    commands share, so lifting this out keeps that behaviour in one place
    instead of two.

    The third element is the ``Fetched`` record when ``source`` was a URL, or
    ``None`` for a file, since only the URL case has a ladder to report on.
    """
    if source.startswith(("http://", "https://")):
        # FetchExtraMissing means the optional fetch stack (scrapling) is
        # not installed. Its message already names the fix, so it is
        # printed as-is. Catching only this type -- not ImportError itself
        # -- matters: a real import failure from inside a working scrapling
        # install must surface as the bug it is, not be mistaken for the
        # extra simply being absent, and a wider except would also risk
        # swallowing a real fetch failure, which the ladder already decides
        # what to do with.
        try:
            fetched = fetch_url(source, stealth=stealth, obey_robots=not no_robots)
        except FetchExtraMissing as missing:
            _fail(str(missing), missing)
        except RobotsRefused as refused:
            # The site was reachable and told us no. That is an answer, not
            # a malfunction, so it gets the same message-and-exit treatment
            # as the operational failures below rather than a traceback.
            _fail(str(refused), refused)
        except FetchFailed as failed:
            # Every rung failed, whatever library it was built on: a browser's
            # timeout is not an OSError, and was a traceback until this.
            _fail(str(failed), failed)
        except (OSError, ValueError) as failure:
            # At the command line an operational failure is a message and a
            # bug is a traceback. OSError is the operational family: the site
            # was down, the name did not resolve, the connection timed out
            # (ConnectionError and TimeoutError are both OSError). ValueError
            # is what a rung raises when it comes back with no HTML. Anything
            # else -- a broken install, a wrong type -- is a bug and keeps its
            # full diagnostics, so it is deliberately not caught here.
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

    # click.Path(exists=True) used to guard this. A plain string argument no
    # longer gets that check for free, since the same argument must also
    # accept a URL, so the existence check is made by hand here -- and it
    # must fail with a clear message, not a traceback from read_text().
    if not path.is_file():
        _fail(
            f"{source} is not a file." if path.exists() else f"{source} does not exist."
        )

    # Read as bytes, not text: a file's own declared encoding (a <meta
    # charset>, an XML declaration) is only visible to lxml and trafilatura
    # when they get to make that decision themselves. Decoding here first --
    # even tolerantly, with errors="replace" -- picks the process default
    # (UTF-8) before either reader is ever called, and permanently destroys
    # any byte that was not already UTF-8. extract() and to_markdown() both
    # accept str | bytes and both do better with bytes for exactly this
    # reason; document.load() already relies on this happening.
    data = path.read_bytes()

    # This guard is not a duplicate of the one in load(). It answers a
    # different question: a file with nothing in it is a user mistake and
    # deserves a message about the file. load() answers for the library,
    # promising it never raises on anything else lxml refuses to parse.
    # b"   ".strip() is falsy exactly as the text version was, so this still
    # catches an all-whitespace file.
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
            # A file that declares nothing and a page that took three
            # climbs to reach a rung that also declares nothing are not the
            # same event: the whole point of the ladder is to say what a
            # page cost, so that cost is reported here even when the
            # answer is "nothing found".
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
    # MarkdownExtraMissing means trafilatura is not installed. Its message
    # already names the fix, so it is printed as-is, the same way
    # FetchExtraMissing is handled in _read_source above.
    try:
        content = to_markdown(html, url=url)
    except MarkdownExtraMissing as missing:
        _fail(str(missing), missing)
    if not content:
        click.echo("This page has no main content.", err=True)
        raise SystemExit(NOTHING_FOUND)
    click.echo(content)
