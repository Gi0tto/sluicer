"""``sluicer fetch``: a page as the ladder brought it back, to be read later.

It reads through ``source``, as every command that reads a page does, but
declares its options itself rather than taking the shared ones: what it is
given is always an address, so it has no ``--url``, and it reads no page, so
it has no ``--respect``.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import click

from sluicer.cli.exits import _fail
from sluicer.cli.options import _with_proxy
from sluicer.cli.output import _kept_line
from sluicer.cli.source import _read_source


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
