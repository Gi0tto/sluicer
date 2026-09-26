"""Reading what a command is given: a URL, a saved file, or - for standard input.

Every way of failing to read it ends here, with a message and
``COULD_NOT_READ``, so that each command fails the same way for the same cause.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from click.core import ParameterSource

from sluicer.cli.exits import _fail
from sluicer.cli.options import _Sending, _sent
from sluicer.fetch import (
    AddressRefused,
    FetchFailed,
    RobotsRefused,
    fetch as fetch_url,
)
from sluicer.fetch.http_rung import PROXY_ENV
from sluicer.fetch.result import Fetched, ResponseTooLarge
from sluicer.fetch.rungs import FetchExtraMissing
from sluicer.fetch.wire import UnusableProxy


def _read_source(
    source: str,
    stealth: bool = False,
    no_robots: bool = False,
    base_url: str | None = None,
    at: str | None = None,
    respect: tuple[str, ...] = (),
    cache_dir: str | None = None,
    max_age: float | None = None,
    error_page: bool = False,
) -> tuple[str | bytes, str | None, Fetched | None]:
    """``_read_page``, then refused when ``respect`` names a reservation the
    page makes: its text and data mining rights, for ``tdm``.

    An address the site answered with a status outside 2xx exits with
    ``COULD_NOT_READ``, naming the status: a 404's answer is the site's
    error, not the page, and until 0.9.1 ``extract`` printed its "404 Not
    Found" as the page's title and exited 0. ``error_page`` keeps it, for
    the commands whose answer is about whatever the site sent: ``fetch``
    and ``audit``.
    """
    if max_age is not None and cache_dir is None:
        if _from_a_file("max_age"):
            # A file's max-age is a default for the runs that keep pages, and
            # this one keeps none: set at the top of a file, it stopped every
            # command, a local file's included, naming a flag nobody typed.
            max_age = None
        else:
            _fail("--max-age says how long a kept page is good for; it needs --cache.")
    if cache_dir is not None and at is not None:
        _fail("--cache keeps live pages; a capture read with --at never changes.")
    html, url, fetched = _read_page(
        source, stealth, no_robots, base_url, at, cache_dir, max_age
    )
    if not error_page and fetched is not None and not 200 <= fetched.status < 300:
        _fail(
            f"Could not read {source}: the site answered status "
            f"{fetched.status}, which is its error, not the page. "
            + _read_anyway(source, fetched.url, stealth, no_robots, at)
        )
    if "tdm" in respect:
        _refuse_reserved(html, url, fetched, obey_robots=not no_robots)
    return html, url, fetched


# The commands that read one page from standard input, with --url for its
# address: the error page can be piped to them from `sluicer fetch`.
_PIPED = ("extract", "inspect", "markdown", "feed")


def _read_anyway(
    source: str, landed: str, stealth: bool, no_robots: bool, at: str | None
) -> str:
    """How to read an error page anyway, said after the refusal: ``sluicer
    fetch`` gives whatever the site sent, and a command reads it from there.

    Until the hostile review of 0.9.1 the refusal named no way forward, and
    reading a 404 on purpose -- to see what a site says for a page it lost --
    was a thing no command did.
    """
    import shlex

    fetch = f"sluicer fetch {shlex.quote(source)}"
    if at is not None:
        fetch += f" --at {shlex.quote(at)}"
    if stealth:
        fetch += " --stealth"
    if no_robots:
        fetch += " --no-robots"
    context = click.get_current_context(silent=True)
    command = context.info_name if context is not None else None
    if command in _PIPED:
        return (
            f"To read the error page anyway: {fetch} | sluicer {command} - "
            f"--url {shlex.quote(landed)}"
        )
    return (
        f"To read the error page anyway, keep it in a file and give "
        f"{command or 'the command'} the file: {fetch} -o error-page.html"
    )


def _from_a_file(name: str) -> bool:
    """Whether the running command's ``name`` came from a configuration file."""
    context = click.get_current_context(silent=True)
    source = context.get_parameter_source(name) if context is not None else None
    return source is ParameterSource.DEFAULT_MAP


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
    if at is not None and (_Sending.headers or _Sending.cookies):
        _fail(
            "--at reads the archive, which is not the site: --header and --cookie "
            "are for the site, and are never sent to web.archive.org."
        )
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
                    **_sent(),
                )
            else:
                fetched = fetch_url(
                    source, stealth=stealth, obey_robots=not no_robots, **_sent()
                )
        except FetchExtraMissing as missing:
            _fail(str(missing), missing)
        except RobotsRefused as refused:
            # The site told us no: an answer, not a malfunction.
            _fail(str(refused), refused)
        except AddressRefused as refused:
            # Not on the web: an address, or where a redirect pointed, that is
            # not http or https. Until 0.9.1 it was a traceback and exit 1.
            _fail(str(refused), refused)
        except FetchFailed as failed:
            # Every rung failed, whatever library it was built on: a browser's
            # timeout, for one, is not an OSError.
            _fail(str(failed), failed)
        except ResponseTooLarge as heavy:
            _fail(str(heavy), heavy)
        except UnusableProxy as unusable:
            # --proxy is read with the command line; this is the variable.
            _fail(f"{PROXY_ENV}: {unusable}", unusable)
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


def _read_pages(
    sources: tuple[str, ...], stealth: bool, no_robots: bool, pages_only: bool = True
) -> list[tuple[str | bytes, str | None]]:
    """Each of ``sources``, read. An address the site answered with a status
    outside 2xx exits with ``COULD_NOT_READ``, naming it -- a 404's or a
    503's answer is not a page to learn from or to hold an extractor to --
    unless ``pages_only`` is false."""
    read = []
    for source in sources:
        html, url, _fetched = _read_source(
            source, stealth, no_robots, None, error_page=not pages_only
        )
        read.append((html, url))
    return read
