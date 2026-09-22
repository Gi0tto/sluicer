"""Command line front door."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import click

from sluicer.api import extract as extract_html


@click.group()
@click.version_option(package_name="sluicer")
def main() -> None:
    """Turn a web page into structured data with no model in the loop."""


@main.command()
@click.argument("source", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def extract(source: Path) -> None:
    """Read the declared structured data of a saved HTML file."""
    text = source.read_text(errors="replace")

    # This guard is not a duplicate of the one in load(). It answers a
    # different question: a file with nothing in it is a user mistake and
    # deserves a message about the file. load() answers for the library,
    # promising it never raises on anything else lxml refuses to parse.
    if not text.strip():
        click.echo("This file contains no HTML.", err=True)
        raise SystemExit(1)

    result = extract_html(text, url=str(source))
    if not result.records:
        click.echo("This page declares no structured data.", err=True)
        raise SystemExit(1)
    click.echo(json.dumps(asdict(result), indent=2, ensure_ascii=False))
