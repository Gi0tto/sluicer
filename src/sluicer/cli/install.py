"""``sluicer install`` and ``sluicer doctor``: the second setup step, and what is there.

``pip install sluicer`` is the whole install for every command but one kind of
page: a page a script draws needs a browser, which is a Python package, the
``browser`` extra, and a Chromium Playwright downloads once. The best tools
make that second step a command of their own (``playwright install``,
``scrapling install``), and so does this: ``sluicer install browser`` runs
Playwright's own download with the Python Sluicer runs on, so the browser
lands where this Playwright looks for it, and says how to add the extra when
it is not installed, in the words of whatever installed Sluicer. A package
cannot be installed safely from inside the environment it runs in, so that is
said and not done.

``sluicer doctor`` says in plain words what is installed, what each missing
piece is for, and the one command that adds it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from importlib import metadata

import click

from sluicer import installer
from sluicer.cli.exits import COULD_NOT_READ, _fail
from sluicer.installer import EXTRAS, Installation, _importable, _quoted

_run = subprocess.run
"""How Playwright is run; a test hands in its own."""


def _browser_command(installation: Installation, have: set[str]) -> str:
    """The command that adds the browser extra, and what to run after it."""
    command = installation.command(["browser"], have, then="install browser")
    if installation.kind == "uvx":
        return command
    return f"{command}, then: {_sluicer(installation)} install browser"


def _sluicer(installation: Installation) -> str:
    """How to run this sluicer again: by name, or through its interpreter
    when the ``PATH`` does not lead to its environment."""
    if installation.short or installation.kind not in ("pip", "uv venv"):
        return "sluicer"
    return f"{_quoted(installation.python)} -m sluicer"


@click.command("install")
@click.argument("what", type=click.Choice(["browser"]), metavar="browser")
@click.option(
    "--with-deps",
    is_flag=True,
    help="Also install the system libraries Chromium needs, on Linux; "
    "Playwright may ask for sudo.",
)
def install_command(what: str, with_deps: bool) -> None:
    """Download the Chromium the browser extra drives, once.

    Runs Playwright's own "playwright install chromium" with the Python this
    sluicer runs on, and then asks Playwright whether every part of Chromium
    is there. Run again, it downloads nothing that is already there. Without
    the browser extra, prints the command that adds it for the way sluicer
    was installed (pip, uv tool, pipx or uvx) and exits 2. Exits 2 as well
    when the download fails.
    """
    installation = installer.current()
    if not _importable("playwright"):
        click.echo(
            "Loading a page in a browser needs Playwright, which comes with the "
            "browser extra and is not installed.",
            err=True,
        )
        verb = "Run" if installation.kind == "uvx" else "Install it with"
        click.echo(
            f"{verb}: {_browser_command(installation, installation.kept())}",
            err=True,
        )
        raise SystemExit(COULD_NOT_READ)
    arguments = ["install", *(["--with-deps"] if with_deps else []), "chromium"]
    argv = installer.playwright_argv(*arguments)
    shown = " ".join(["playwright", *arguments])
    click.echo(f"Installing Playwright's Chromium: {shown}", err=True)
    try:
        finished = _run(argv, check=False)
    except OSError as failure:
        _fail(f"{shown} could not start: {failure}", failure)
    if finished.returncode != 0:
        _fail(f"{shown} failed with exit code {finished.returncode}")
    missing = installer.chromium_missing(_run)
    if missing is None:
        click.echo(
            f"{shown} finished, and Playwright could not be asked afterwards "
            "where its Chromium is: sluicer doctor asks again.",
            err=True,
        )
        return
    if missing:
        _fail(
            f"{shown} finished, but Playwright has not completed " + ", ".join(missing)
        )
    click.echo(
        "Chromium is installed: sluicer can load pages that need a browser.",
        err=True,
    )


@dataclass(frozen=True)
class _Piece:
    """One thing ``doctor`` looks for: an extra, or the base install."""

    name: str
    extra: str | None
    modules: tuple[str, ...]
    purpose: str
    then: str = ""
    """The sluicer command that uses it, for a ``uvx`` line, which installs
    nothing to keep and so is the command to run as well."""


_BASE = ("lxml", "click", "cssselect", "protego") + (
    ("tomli",) if sys.version_info < (3, 11) else ()
)

PIECES = (
    _Piece(
        "reading pages",
        None,
        _BASE,
        "extract, select, inspect, audit, diff, compile, run and heal; "
        "fetch, map, crawl, batch and feed over plain HTTP",
    ),
    _Piece(
        "markdown",
        "markdown",
        EXTRAS["markdown"],
        "sluicer markdown, and the MCP server's page_markdown",
        "markdown ...",
    ),
    _Piece(
        "browser",
        "browser",
        EXTRAS["browser"],
        "pages a script draws, which plain HTTP brings back as an empty shell",
    ),
    _Piece(
        "mcp", "mcp", EXTRAS["mcp"], "the MCP server: sluicer mcp, sluicer-mcp", "mcp"
    ),
    _Piece("api", "api", EXTRAS["api"], "the HTTP API: sluicer serve", "serve"),
    _Piece(
        "microformats",
        "microformats",
        EXTRAS["microformats"],
        "microformats2, read with --microformats",
        "extract --microformats ...",
    ),
    _Piece(
        "stealth",
        "stealth",
        EXTRAS["stealth"],
        "the stealth rung, one page at a time with --stealth",
        "fetch --stealth ...",
    ),
)
"""What ``doctor`` reports, in the order it reports it."""


def _browser_state(
    installation: Installation, have: set[str]
) -> tuple[str, str, str | None]:
    """The browser's status, what it means, and its fix, when Playwright is
    installed: the extra is only half of it."""
    chosen = os.environ.get("SLUICER_BROWSER", "").strip().lower()
    if chosen == "none":
        return "off", "SLUICER_BROWSER=none turns the browser rung off", None
    if os.environ.get("SLUICER_CDP_URL", "").strip():
        return "ok", "drives the browser already running at SLUICER_CDP_URL", None
    missing = installer.chromium_missing()
    fix = (
        installation.command(["browser"], have, then="install browser")
        if installation.kind == "uvx"
        else f"{_sluicer(installation)} install browser"
    )
    if missing is None:
        return "unknown", "Playwright could not say whether Chromium is there", fix
    if missing:
        return "missing", "Playwright is installed, its Chromium is not", fix
    return "ok", PIECES[2].purpose, None


def _row(
    piece: _Piece, installation: Installation, have: set[str], there_now: set[str]
) -> tuple[str, str, str, str | None]:
    """One line of ``doctor``: status, name, what it is for, and its fix."""
    if piece.extra is None:
        absent = [module for module in piece.modules if not _importable(module)]
        if not absent:
            return "ok", piece.name, piece.purpose, None
        words = f"{', '.join(absent)} not installed: {piece.purpose}"
        return "missing", piece.name, words, installation.command([], have)
    if piece.extra not in there_now:
        adding = (
            _browser_command(installation, have)
            if piece.extra == "browser"
            else installation.command([piece.extra], have, then=piece.then)
        )
        return "missing", piece.name, piece.purpose, adding
    if piece.extra == "browser":
        status, words, fix = _browser_state(installation, have)
        return status, piece.name, words, fix
    return "ok", piece.name, piece.purpose, None


@click.command("doctor")
def doctor_command() -> None:
    """Say what is installed, what each missing piece is for, and how to add it.

    One line for the base install and one for each extra: ok, missing, or
    off, with what it is for and, when it is not there, the one command that
    adds it for the way sluicer was installed (pip, uv tool, pipx, uvx or a
    uv project). The browser is ok only when Playwright's Chromium is
    downloaded too. Exits 0 when everything a plain install gives works, a
    missing extra included, and 2 when some of it does not.
    """
    installation = installer.current()
    have = installation.kept()
    there_now = installer.present()
    version = metadata.version("sluicer")
    python = ".".join(str(part) for part in sys.version_info[:3])
    click.echo(f"sluicer {version}, on Python {python} at {sys.executable}")
    click.echo(f"installed with {installation.described}")
    click.echo()
    rows = [_row(piece, installation, have, there_now) for piece in PIECES]
    # The base install is broken when a piece of it is missing: markdown has
    # been part of it since 0.10.
    broken = any(
        status == "missing" and name in ("reading pages", "markdown")
        for status, name, _, _ in rows
    )
    status_width = max(len(row[0]) for row in rows)
    name_width = max(len(row[1]) for row in rows)
    indent = " " * (status_width + name_width + 4)
    for status, name, words, fix in rows:
        click.echo(f"{status.ljust(status_width)}  {name.ljust(name_width)}  {words}")
        if fix:
            click.echo(f"{indent}{fix}")
    wanting = {row[1] for row in rows if row[0] == "missing"} & {
        "browser",
        "mcp",
        "api",
        "microformats",
    }
    if len(wanting) > 1:
        click.echo()
        everything = installation.command(["all"], have, then="doctor")
        click.echo(f"Every extra but stealth at once: {everything}")
    if broken:
        raise SystemExit(COULD_NOT_READ)
