"""The options the commands that fetch share, and the headers and cookies they send.

``--stealth``, ``--no-robots``, ``--url``, ``--respect``, ``--cache``,
``--max-age`` and ``--at`` are declared once here for every command that reads
one page; ``--proxy``, ``--header`` and ``--cookie`` for every command that
fetches at all, crawls included. A command that spells an option differently,
as ``fetch`` does ``--at``, declares its own.
"""

from __future__ import annotations

import functools
import os
from typing import Any, ClassVar

import click

from sluicer.fetch.http_rung import PROXY_ENV


def _a_date(ctx: click.Context, param: click.Parameter, value: str | None) -> Any:
    """``--at``, read when the command line is: until 0.9.1 a date that is
    not one failed at fetch time, "Could not fetch URL: ValueError: ...",
    as if the site were at fault."""
    if value is None:
        return None
    from sluicer.fetch.archive import timestamp

    try:
        timestamp(value)
    except ValueError as unread:
        raise click.BadParameter(str(unread)) from None
    return value


def _a_proxy(ctx: click.Context, param: click.Parameter, value: str | None) -> Any:
    """``--proxy``, read when the command line is, as ``--header`` is."""
    if value is None or not value.strip():
        return value
    from sluicer.fetch.wire import Proxy, UnusableProxy

    try:
        Proxy.parse(value.strip())
    except UnusableProxy as unusable:
        raise click.BadParameter(str(unusable)) from None
    return value


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
        callback=_a_date,
        help="Read a URL as the Wayback Machine captured it nearest to DATE "
        "(2025, 2025-06, 2025-06-01), not from its site.",
    ),
]


_proxy_option = click.option(
    "--proxy",
    metavar="URL",
    callback=_a_proxy,
    help="Fetch through this proxy (http://host:port, socks5h://host:port); "
    "the environment's HTTPS_PROXY is never used. Same as SLUICER_PROXY.",
)


_header_option = click.option(
    "--header",
    "-H",
    "headers",
    multiple=True,
    metavar="'NAME: VALUE'",
    help="Send this header to the site asked, and to no other it redirects to; "
    "again for more. Never User-Agent: Sluicer always says who it is.",
)

_cookie_option = click.option(
    "--cookie",
    "cookies",
    multiple=True,
    metavar="NAME=VALUE",
    help="Send this cookie to the site asked, as --header does; again for more.",
)


class _Sending:
    """The headers and cookies this command sends, as its options gave them.

    Held here, as ``--proxy`` is held in ``SLUICER_PROXY``, so that every
    fetch the command makes sends them without each reader of a page having
    to be handed them. Set again by every command that takes the options.
    """

    headers: ClassVar[dict[str, str]] = {}
    cookies: ClassVar[dict[str, str]] = {}


def _sent() -> dict[str, Any]:
    """``fetch``'s ``headers`` and ``cookies``, as this command's options say."""
    return {"headers": dict(_Sending.headers), "cookies": dict(_Sending.cookies)}


def _sending(headers: tuple[str, ...], cookies: tuple[str, ...]) -> None:
    """Read ``--header`` and ``--cookie``, refusing, before anything is asked,
    what could not be sent."""
    from sluicer.fetch.identity import outgoing

    named: dict[str, str] = {}
    for given in headers:
        name, colon, value = given.partition(":")
        if not colon or not name.strip():
            raise click.BadParameter(
                f"{given!r} is not a header: write 'NAME: VALUE'", param_hint="--header"
            )
        named[name.strip()] = value.strip()
    crumbs: dict[str, str] = {}
    for given in cookies:
        name, equals, value = given.partition("=")
        if not equals or not name.strip():
            raise click.BadParameter(
                f"{given!r} is not a cookie: write NAME=VALUE", param_hint="--cookie"
            )
        crumbs[name.strip()] = value.strip()
    try:
        outgoing(named, crumbs)
    except ValueError as refused:
        raise click.BadParameter(str(refused)) from None
    _Sending.headers, _Sending.cookies = named, crumbs


def _with_proxy(command: click.decorators.FC) -> click.decorators.FC:
    """``--proxy``, ``--header`` and ``--cookie``, taken before the command
    runs: every fetch it makes, of a page, a robots.txt, a sitemap or a site's
    files, reads ``SLUICER_PROXY``, and every page it asks for sends the
    headers and cookies."""

    @functools.wraps(command)
    def through(
        *args: Any,
        proxy: str | None = None,
        headers: tuple[str, ...] = (),
        cookies: tuple[str, ...] = (),
        **kwargs: Any,
    ) -> Any:
        if proxy is not None:
            os.environ[PROXY_ENV] = proxy
        _sending(headers, cookies)
        return command(*args, **kwargs)

    return _proxy_option(_header_option(_cookie_option(through)))  # type: ignore[return-value]


def _with_fetch_options(command: click.decorators.FC) -> click.decorators.FC:
    for option in reversed(_fetch_options):
        command = option(command)
    return _with_proxy(command)
