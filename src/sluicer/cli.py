"""Command line front door."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from sluicer.api import extract as extract_html
from sluicer.fetch.ladder import fetch as fetch_url
from sluicer.fetch.scrapling_rungs import FetchExtraMissing


@click.group()
@click.version_option(package_name="sluicer")
def main() -> None:
    """Turn a web page into structured data with no model in the loop."""


@main.command()
@click.argument("source")
def extract(source: str) -> None:
    """Read the declared structured data of a URL or a saved HTML file."""
    if source.startswith("http://") or source.startswith("https://"):
        # FetchExtraMissing means the optional fetch stack (scrapling) is
        # not installed. Its message already names the fix, so it is
        # printed as-is. Catching only this type -- not ImportError itself
        # -- matters: a real import failure from inside a working scrapling
        # install must surface as the bug it is, not be mistaken for the
        # extra simply being absent, and a wider except would also risk
        # swallowing a real fetch failure, which the ladder already decides
        # what to do with.
        try:
            fetched = fetch_url(source)
        except FetchExtraMissing as missing:
            click.echo(str(missing), err=True)
            raise SystemExit(1) from missing
        except (OSError, ValueError) as failure:
            # At the command line an operational failure is a message and a
            # bug is a traceback. OSError is the operational family: the site
            # was down, the name did not resolve, the connection timed out
            # (ConnectionError and TimeoutError are both OSError). ValueError
            # is what a rung raises when it comes back with no HTML. Anything
            # else -- a broken install, a wrong type -- is a bug and keeps its
            # full diagnostics, so it is deliberately not caught here.
            click.echo(
                f"Could not fetch {source}: {type(failure).__name__}: {failure}",
                err=True,
            )
            raise SystemExit(1) from failure
        result = extract_html(fetched.html, url=fetched.url)
        if not result.records:
            click.echo("This page declares no structured data.", err=True)
            # A file that declares nothing and a page that took three
            # climbs to reach a rung that also declares nothing are not the
            # same event: the whole point of the ladder is to say what a
            # page cost, so that cost is reported here even when the
            # answer is "nothing found".
            click.echo(f"Fetch reached the '{fetched.rung}' rung.", err=True)
            for climb in fetched.climbs:
                click.echo(f"  {climb.from_rung} -> {climb.to_rung}: {climb.reason}", err=True)
            raise SystemExit(1)
        payload = asdict(result)
        payload["fetch"] = {
            "rung": fetched.rung,
            "status": fetched.status,
            "climbs": [asdict(climb) for climb in fetched.climbs],
        }
        click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    path = Path(source)

    # click.Path(exists=True) used to guard this. A plain string argument no
    # longer gets that check for free, since the same argument must also
    # accept a URL, so the existence check is made by hand here -- and it
    # must fail with a clear message, not a traceback from read_text().
    if not path.is_file():
        if path.exists():
            click.echo(f"{source} is not a file.", err=True)
        else:
            click.echo(f"{source} does not exist.", err=True)
        raise SystemExit(1)

    text = path.read_text(errors="replace")

    # This guard is not a duplicate of the one in load(). It answers a
    # different question: a file with nothing in it is a user mistake and
    # deserves a message about the file. load() answers for the library,
    # promising it never raises on anything else lxml refuses to parse.
    if not text.strip():
        click.echo("This file contains no HTML.", err=True)
        raise SystemExit(1)

    result = extract_html(text, url=str(path))
    if not result.records:
        click.echo("This page declares no structured data.", err=True)
        raise SystemExit(1)
    click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
