"""Sluicer as a tool an agent can call, over the Model Context Protocol.

Twelve tools -- ``extract_declared``, ``page_markdown``, ``fetch_page``,
``compile_extractor``, ``run_extractor``, ``heal_extractor``, ``audit_page``,
``read_feed``, ``map_site``, ``crawl_site``, ``extract_many`` and
``select_values`` -- expose what the library does and add no logic of their
own beyond bounds: a map, a crawl or a list of pages an agent starts is small
and has a clock.
Run it with ``sluicer-mcp``; it needs the ``mcp`` extra.

Every answer carries ``ok``, true exactly when it can be used as it is, and has
an output schema (``sluicer.mcp_answers``). No ``from __future__ import
annotations`` here: the tools are defined inside ``build_server``, and the SDK
reads their return types as objects to build those schemas.
"""

import functools
import importlib
import inspect
import json
import logging
import os
import re
import sys
from collections.abc import Callable, Iterable
from dataclasses import asdict
from typing import Annotated, Any, cast

from sluicer import __version__, crawl as crawling, extractor as extractor_module
from sluicer.api import _extract as extract
from sluicer.audit import answered_with, audit
from sluicer.extras import MissingExtra, import_extra
from sluicer.fetch import (
    AddressRefused,
    FetchFailed,
    PaymentRequired,
    RobotsRefused,
    SiteRefused,
)
from sluicer.fetch.address import shown
from sluicer.fetch.archive import NotArchived
from sluicer.fetch.http_rung import PROXY_ENV, chosen_proxy
from sluicer.fetch.result import MAX_RESPONSE_BYTES, ResponseTooLarge
from sluicer.fetch.wire import Proxy, UnusableProxy
from sluicer.isolated import TookTooLong, isolated
from sluicer.markdown import to_markdown
from sluicer.selectors import (
    SelectorError,
    parse as parse_page,
    selector as read_selector,
)

MOST_CHARS = 60_000
"""The most characters of a page, or of its markdown, one answer carries.

Claude Code keeps a tool's answer to 25,000 tokens and puts a larger one in a
file instead of the conversation; at about three characters a token, with
room for JSON's escaping, this stays under it. The 200,000 characters
``fetch_page`` used to return were over it on 302 of 386 real pages. A longer
page is read in slices: each answer says where the next one starts.
"""
DEFAULT_CHARS = 30_000
"""A slice's length when the agent names none."""
MOST_ANSWER_BYTES = 75_000
"""The most any tool's answer may weigh, in UTF-8 bytes of its JSON.

About 25,000 tokens, what Claude Code keeps in the conversation, at three bytes
a token. Past it a tool leaves out what an answer can do without -- records,
the longest summary answers, the last of a list -- and says what it left out:
a count in ``<list>_left_out``, the names in ``<mapping>_left_out``, or, for a
slice of a page, a ``next_offset`` that comes sooner. An answer that still
weighs more, such as an extractor learnt from a page with a two-megabyte
title, is ``too_large`` rather than an answer the client cannot hold. Before
0.7.1 only ``extract_declared``'s records were bounded, and a page with a long
enough ``<title>`` made a two-megabyte answer even with ``records=False``.
"""

ALLOW_PRIVATE_ENV = "SLUICER_ALLOW_PRIVATE"
"""Set to 1 to let the server fetch addresses off the public internet.

Off by default: an agent reading untrusted pages can be told to fetch
``http://localhost:8080/admin`` or a cloud metadata endpoint, and this server
runs on a machine that can reach both.
"""


MAP_LIMIT = 1000
"""The most addresses ``map_site`` hands an agent. A thousand short ones are
about 80 KB, over ``MOST_ANSWER_BYTES``: the answer keeps the first that fit
and counts the rest in ``urls_left_out``."""

MAP_SITEMAPS = 10
"""The most sitemap files one ``map_site`` reads."""

CRAWL_PAGES = 25
"""The most pages one ``crawl_site`` takes."""

CRAWL_DEPTH = 3
"""The most links from its start one ``crawl_site`` goes."""

MANY_URLS = 25
"""The most addresses one ``extract_many`` reads. Measured on the 140 pages of
the product benchmark, a page's summary weighs 2.3 KB at the median, and its
records 4.2 KB more: twenty-five summaries fit ``MOST_ANSWER_BYTES``, and
twenty-five pages' records do not, so records are asked for and cut first."""
FEED_ITEMS = 500
"""The most items one ``read_feed`` answers with."""

TIME_BUDGET_SECONDS = 60.0
"""How long ``map_site``, ``crawl_site`` and ``extract_many`` may keep starting
requests. A page
already started finishes, so an answer can take a little longer."""

CRAWL_MAX_DELAY_SECONDS = 10.0
"""The longest ``Crawl-delay`` ``map_site`` and ``crawl_site`` wait for; a site
asking for more is answered ``crawl_delay_too_long`` rather than holding the
agent a minute a page, and one whose Retry-After asks for more, ``rate_limited``."""


class McpExtraMissing(MissingExtra):
    """The optional ``mcp`` extra is not installed, as opposed to broken."""


class UnknownTool(ValueError):
    """A tool asked for by name is not one of the twelve."""


def _server_class() -> Any:
    """Return the SDK's ``MCPServer`` class, or say the extra is not installed.

    ``Any``, because ``mcp`` is never imported at module level and there is no
    class here to name. The extra pins ``mcp>=2``: 2.x renamed ``FastMCP`` to
    ``MCPServer`` and removed the old name.

    Only a missing top-level ``mcp`` counts as the extra being absent. mcp 2.x
    ships ``mcp/server/fastmcp.py`` solely to raise ``ModuleNotFoundError``
    with a migration guide; a wider match would report that as "install
    sluicer[mcp]" to someone who has it, and throw the guide away.
    """
    return import_extra(
        "mcp.server.mcpserver",
        "mcp",
        doing="Running the MCP server",
        package="the mcp package",
        error=McpExtraMissing,
    ).MCPServer


def _answers_instead_of_raising(tool: Callable[..., Any]) -> Callable[..., Any]:
    """Return the answerable failures as the tool's result, never as its content.

    Each is ``{"ok": false, "error": {"code", "message", "retryable"}}``, with
    ``url`` or ``extra`` when there is one, because the codes call for different
    responses: ``missing_extra`` (install what the message says),
    ``refused_by_robots`` (do not work around it), ``refused_by_site`` (a
    challenge page on every rung: nor that), ``payment_required`` (a 402,
    which Sluicer never pays), ``refused_address`` (a
    private address, refused by default), ``fetch_failed`` (worth trying
    later: the only retryable one, unless the archive holds no capture or
    what failed would fail again, a redirect loop for one),
    ``too_large`` and ``bad_input``. Raised
    instead, each reached the agent as the SDK's bare "Error executing tool".

    An error is never where a tool's content goes: returned as text, "Turning a
    page into markdown needs trafilatura" sat exactly where a page's words go,
    and an agent would summarise it as the page. A real bug inside a tool still
    raises.
    """

    @functools.wraps(tool)
    def guarded(*args: Any, **kwargs: Any) -> Any:
        try:
            return _held_to_the_bound(tool.__name__, tool(*args, **kwargs))
        except MissingExtra as missing:
            return _error("missing_extra", missing, extra=missing.extra)
        except RobotsRefused as refused:
            return _error("refused_by_robots", refused, url=refused.url)
        except AddressRefused as refused:
            return _error("refused_address", refused, url=refused.url)
        except ResponseTooLarge as heavy:
            fetched = heavy.url.startswith(("http://", "https://"))
            return _error("too_large", heavy, url=heavy.url if fetched else None)
        except SiteRefused as refused:
            return _error("refused_by_site", refused, url=refused.url)
        except PaymentRequired as unpaid:
            return _error("payment_required", unpaid, url=unpaid.url)
        except NotArchived as missing:
            # Asking again will not make the archive have held the page.
            return _error("fetch_failed", missing, url=missing.url)
        except FetchFailed as failed:
            return _error(
                "fetch_failed", failed, retryable=failed.transient, url=failed.url
            )
        except _BadInput as bad:
            return _error("bad_input", bad)
        except TookTooLong as slow:
            # The caller's selector, not the page or the server: asked again,
            # it runs as long again.
            return _error("bad_input", slow)
        except _Reserved as reserved:
            return _error("tdm_reserved", reserved, url=reserved.url)

    return guarded


def _held_to_the_bound(name: str, answer: Any) -> Any:
    """The answer, or ``too_large`` when it weighs more than any answer may.

    The last word on every tool's answer, after the tool has left out what it
    can: whatever a tool forgot to bound, no answer reaches a client past
    ``MOST_ANSWER_BYTES``.
    """
    weight = _bytes_of(answer)
    if weight <= MOST_ANSWER_BYTES:
        return answer
    return _error(
        "too_large",
        ValueError(
            f"{name}'s answer would weigh {weight:,} bytes, over the "
            f"{MOST_ANSWER_BYTES:,} one answer may; the command line has no "
            f"such bound"
        ),
    )


def _error(
    code: str, failure: Exception, retryable: bool = False, **detail: str | None
) -> dict[str, Any]:
    # The last word on every error: an address handed in is named with its
    # password hidden, whatever raised.
    known = {key: shown(value) for key, value in detail.items() if value is not None}
    return {
        "ok": False,
        "error": {
            "code": code,
            "message": shown(str(failure)),
            "retryable": retryable,
            **known,
        },
    }


class _BadInput(ValueError):
    """A tool was handed something it cannot take."""


class _Reserved(Exception):
    """The page reserves its text and data mining rights, and the call said to
    respect that."""

    def __init__(self, url: str | None, message: str) -> None:
        super().__init__(message)
        self.url = url


def _respect_tdm(
    html: str,
    url: str | None,
    fetched: dict[str, Any] | None,
    headers: dict[str, str] | None,
) -> None:
    """Raise ``_Reserved`` when TDMRep reserves the page's TDM rights."""
    from sluicer.declared.headers import lowered, read_header_rights
    from sluicer.declared.rights import read_rights
    from sluicer.declared.tdmrep import read_tdmrep, reservation
    from sluicer.document import load_and_keep

    sent = lowered(headers) if headers else {}
    rights = read_rights(
        load_and_keep(html, url=url), read_header_rights(sent) if sent else None
    )
    rules = []
    if fetched is not None and "archived" not in fetched and url:
        from sluicer.fetch.site import read_tdmrep_file

        rules = read_tdmrep(read_tdmrep_file(url, allow_private=_allow_private()).text)
    found = reservation(rules, url, rights)
    if found is not None and found.reserved:
        policy = f", policy {found.policy}" if found.policy else ""
        raise _Reserved(
            url,
            f"{url or 'The page'} reserves its text and data mining rights "
            f"(TDMRep, by its {found.source}{policy})",
        )


def _allow_private() -> bool:
    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in {"1", "true", "yes"}


def _html_of(
    html_or_url: str,
    at: str | None = None,
    error_page: bool = False,
    expect_html: bool = True,
) -> tuple[str, str | None, dict[str, Any] | None]:
    """Return the page's HTML, the URL to attribute it to, and the fetch record.

    The URL is where the fetch landed, after redirects, since that is what the
    page's relative links resolve against; for literal HTML it is None. Literal
    HTML is held to the bound a fetched page is.
    """
    html, url, record, _headers = _page_of(html_or_url, at, error_page, expect_html)
    return html, url, record


def _check_address(url: str) -> None:
    """Refuse, as ``bad_input``, an http(s) address that names no host.

    ``http:///x`` is a typo, not a site that is down: until 0.9.1 it was
    answered ``fetch_failed``, ``retryable`` true, blaming its robots.txt.
    """
    from urllib.parse import urlsplit

    try:
        host = urlsplit(url).hostname
    except ValueError as invalid:
        raise _BadInput(f"{url!r} is not a valid address: {invalid}") from invalid
    if not host:
        raise _BadInput(
            f"{url!r} names no host: an address is written https://example.com/page"
        )


def _page_of(
    html_or_url: str,
    at: str | None = None,
    error_page: bool = False,
    expect_html: bool = True,
) -> tuple[str, str | None, dict[str, Any] | None, dict[str, str] | None]:
    """``_html_of``, and the response's headers for a URL.

    The headers are read into the answer -- a canonical in ``Link``,
    ``X-Robots-Tag`` -- and never sent back raw: a response's cookies are not
    the agent's to see. ``at`` reads a URL as the Wayback Machine captured it
    nearest to that date, and the record then says which capture it was.

    A URL the site answered with a status outside 2xx is ``fetch_failed``
    naming the status, retryable for a 429 or a 5xx: its answer is the
    site's error, not the page, and until 0.9.1 ``extract_declared`` said
    ``ok`` true with "404 Not Found" as its title. ``error_page`` keeps it,
    for the tools whose answer is about whatever the site sent:
    ``fetch_page`` and ``audit_page``. Text that is neither a URL nor HTML,
    with no ``<`` in it -- ``example.com``, an empty string -- is
    ``bad_input`` unless ``expect_html`` is false, for a feed, whose JSON
    has none.
    """
    is_url = html_or_url.strip().lower().startswith(("http://", "https://"))
    if at is not None and not is_url:
        raise _BadInput("at reads an address from the Wayback Machine, not HTML")
    if is_url:
        _check_address(html_or_url.strip())
    if is_url and at is not None:
        from sluicer.fetch.archive import fetch_archived

        try:
            fetched = fetch_archived(
                html_or_url.strip(), at, allow_private=_allow_private()
            )
        except ValueError as bad:
            raise _BadInput(str(bad)) from bad
    elif is_url:
        from sluicer.fetch import fetch

        fetched = fetch(html_or_url, allow_private=_allow_private())
    if is_url and not error_page and not 200 <= fetched.status < 300:
        raise FetchFailed(
            fetched.url,
            [],
            f"the site answered status {fetched.status}, which is its error, "
            "not the page. To read the error page anyway: fetch_page answers "
            "with it as it is, and extract_declared, or any tool that takes a "
            "page's HTML, reads the html it gives",
            transient=fetched.status == 429 or fetched.status >= 500,
        )
    if is_url:
        return (
            fetched.html,
            fetched.url,
            {
                "rung": fetched.rung,
                "status": fetched.status,
                "seconds": round(fetched.seconds, 3),
                "climbs": [
                    {**asdict(climb), "seconds": round(climb.seconds, 3)}
                    for climb in fetched.climbs
                ],
                **(
                    {"archived": asdict(fetched.archived)}
                    if fetched.archived is not None
                    else {}
                ),
            },
            fetched.headers,
        )
    if len(html_or_url) > MAX_RESPONSE_BYTES:
        raise ResponseTooLarge("the HTML handed in", MAX_RESPONSE_BYTES)
    if expect_html and "<" not in html_or_url:
        raise _BadInput(_neither_url_nor_html(html_or_url))
    return html_or_url, None, None, None


def _neither_url_nor_html(text: str) -> str:
    """What to say of text that is neither an http(s) URL nor HTML: until
    0.9.1, extract_declared("example.com") answered ok true with nothing in
    it, a page whose whole text was "example.com"."""
    given = text.strip()
    shown_given = repr(given[:80] + ("..." if len(given) > 80 else ""))
    said = f"{shown_given} is neither an http(s) URL nor HTML"
    if not given:
        return "html_or_url is empty: give an http(s) URL or the HTML itself"
    if re.fullmatch(r"(?:www\.)?[\w-]+(?:\.[\w-]+)+(?:[/?#]\S*)?", given):
        return f"{said}: an address needs its scheme, as https://{given}"
    return f"{said}: give an http(s) URL to fetch, or the page's HTML"


def build_server(tools: Iterable[str] | None = None) -> Any:
    """Build the server with its twelve tools registered.

    ``tools`` names the ones to register, when a client wants fewer: each
    registered tool costs an agent context whether it is called or not. A
    name that is not one of the twelve, or a list that names none, is an
    ``UnknownTool``, a ``ValueError``, that lists them.

    Returns the SDK's ``MCPServer``, typed ``Any`` because ``mcp`` is never
    imported at module level.

    A ``SLUICER_PROXY`` it cannot use is an ``UnusableProxy``, raised here
    rather than by the first tool that fetches: there it was an internal
    error, and its traceback wrote the proxy's password into the log. A
    ``SLUICER_BROWSER`` that is neither ``chromium`` nor ``none`` is an
    ``UnknownBrowser``, raised here too.
    """
    through = chosen_proxy()
    if through is not None:
        try:
            Proxy.parse(through)
        except UnusableProxy as unusable:
            raise UnusableProxy(f"{PROXY_ENV}: {unusable}") from None
    from sluicer.fetch.browser import browser_wanted

    # An UnknownBrowser, a ValueError, here rather than at the first fetch.
    browser_wanted()
    wanted = None if tools is None else list(tools)
    seen: list[str] = []
    server_class = _server_class()
    # After the SDK: typing_extensions arrives with it, and the answers need it.
    from sluicer import mcp_answers as answers

    server = server_class(
        "sluicer",
        version=__version__,
        instructions=(
            "Deterministic extraction of the structured data a web page already "
            "declares, with no model in the loop. Every field names the vocabulary "
            "it came from and where on the page it was declared. Every tool only "
            "reads. Every answer carries ok; false means do not use it as it is, "
            "and the answer says why. Fetching obeys robots.txt and refuses "
            "private addresses; a map or a crawl asks a site one request at a "
            "time, a second apart or its Crawl-delay, and is bounded in size and "
            "time."
        ),
    )

    # The SDK's model for the hints, asked for the way the server class is:
    # an import statement for an extra would fail the base install's check.
    annotations = import_extra(
        "mcp.types",
        "mcp",
        doing="Running the MCP server",
        package="the mcp package",
        error=McpExtraMissing,
    ).ToolAnnotations

    # The SDK builds a tool's schema with pydantic, which arrives with it; the
    # suite's stand-in for the SDK needs none, and a base install has none.
    try:
        field = importlib.import_module("pydantic").Field
    except ModuleNotFoundError:
        field = None

    def described(function: Callable[..., Any]) -> Callable[..., Any]:
        """Give each parameter, in the schema a client reads, what the tool's
        docstring says of it; a parameter it says nothing of is a bug."""
        signature = inspect.signature(function)
        notes = _parameter_notes(function.__doc__ or "", signature.parameters)
        unsaid = [name for name in signature.parameters if name not in notes]
        if unsaid:
            raise TypeError(f"{function.__name__} does not say what {unsaid} are")
        if field is None:
            return function
        function.__signature__ = signature.replace(  # type: ignore[attr-defined]
            parameters=[
                one.replace(
                    annotation=Annotated[
                        one.annotation, field(description=notes[one.name])
                    ]
                )
                for one in signature.parameters.values()
            ]
        )
        return function

    def tool(title: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        """Register a tool under its title, saying what every one of them is.

        Each reads -- a page given, or the web -- and changes nothing
        anywhere, so a client that asks before a tool writes, as Codex's
        ``writes`` mode and Claude Code do, can run it without asking.
        """
        register = server.tool(
            title=title,
            annotations=annotations(
                title=title,
                read_only_hint=True,
                destructive_hint=False,
                idempotent_hint=True,
                open_world_hint=True,
            ),
        )

        def chosen(function: Callable[..., Any]) -> Callable[..., Any]:
            seen.append(function.__name__)
            if wanted is not None and function.__name__ not in wanted:
                return function
            return cast(Callable[..., Any], register(described(function)))

        return chosen

    @tool("Extract a page's declared data")
    @_answers_instead_of_raising
    def extract_declared(
        html_or_url: str,
        induce: bool = False,
        at: str | None = None,
        respect_tdm: bool = False,
        records: bool = True,
        visible: bool = False,
    ) -> answers.ExtractAnswer:
        """Read the structured data a page declares, with where each value came from.

        html_or_url: an http(s) URL to fetch, or the HTML itself.
        induce: also read repeated rows (a listing, a feed) from a page that
        declares nothing about them; those fields say source "induced".
        at: a date (2024, 2024-06, 2024-06-01): read the URL as the Wayback
        Machine captured it nearest to then; "fetch" says which capture.
        respect_tdm: answer tdm_reserved instead of the page when the site
        reserves its text and data mining rights (TDMRep: its tdmrep.json,
        headers or meta tags).
        records: also return every record, not only the summary and what
        was normalised; false keeps the answer small. Records that would
        make the answer larger than 75,000 bytes are left out and counted in
        records_left_out.
        visible: also guess the title, author, publication and update dates
        the page shows a reader, in "visible", each {"value", "where",
        "rule"}; guesses, never part of the summary, which holds only what
        the page declares.

        Returns {"ok", "url", "summary", "records", "sources"}, and "fetch"
        for a URL. records are typed fields, each {"value", "source",
        "where"}: source is the vocabulary that declared it (jsonld,
        microdata, opengraph, html, ...), where the XPath of the element that
        did -- for JSON-LD the <script> block's, with a JSON pointer after
        "#" -- or null for a meta tag, whose key is its place. A nested value
        such as a price inside "offers" arrives whole. summary answers title,
        author, date, price and the rest, one value each, naming its source,
        key and where. conflicts lists each question the page answers two
        ways that mean different things -- a price of 41.90 in JSON-LD and
        39.90 in OpenGraph -- the summary's answer first: say so rather than
        trusting either. On failure ok is false and "error" says why; there
        is never a record. An answer weighs at most 75,000 bytes: past it the
        records go first, counted in records_left_out, then the conflicts,
        counted in conflicts_left_out, then the heaviest summary, visible,
        normalised and links entries, each named in summary_left_out,
        visible_left_out, normalised_left_out or links_left_out.
        """
        html, url, fetched, headers = _page_of(html_or_url, at)
        if respect_tdm:
            _respect_tdm(html, url, fetched, headers)
        read = extract(html, url=url, induce=induce, headers=headers, visible=visible)
        result = {"ok": True, **asdict(read)}
        if not visible:
            del result["visible"]
        if not records:
            del result["records"]
        if fetched is not None:
            result["fetch"] = fetched
        _bounded(
            result,
            _cut_leaving_all("records"),
            _cut_list("conflicts"),
            _cut_largest("summary"),
            _cut_largest("visible"),
            _cut_largest("normalised"),
            _cut_largest("links"),
        )
        return cast(answers.ExtractAnswer, result)

    @tool("Read a page as markdown")
    @_answers_instead_of_raising
    def page_markdown(
        html_or_url: str,
        front_matter: bool = False,
        at: str | None = None,
        respect_tdm: bool = False,
        offset: int = 0,
        max_chars: int = DEFAULT_CHARS,
    ) -> answers.MarkdownAnswer:
        """Return a page's main content as markdown, without navigation or footer.

        html_or_url: an http(s) URL to fetch, or the HTML itself.
        front_matter: open the markdown with a YAML block of what the page
        declares about itself (title, author, dates, url...) and each
        answer's source.
        at: a date: read the URL as the Wayback Machine captured it then.
        respect_tdm: answer tdm_reserved when the site reserves its text and
        data mining rights (TDMRep).
        offset: where in the markdown this answer starts, 0 for the
        beginning; the answer before gives the next as next_offset.
        max_chars: the most characters this answer carries, 1 to 60,000;
        fewer when more would weigh over 75,000 bytes, as 60,000 characters
        of Chinese do.

        Returns {"ok", "markdown", "url", "length", "next_offset"}, and
        "fetch" for a URL: markdown is one slice, length the whole markdown's,
        next_offset where the next slice starts or null at the end. The
        markdown is always the page's own content: a failure is ok false with
        "error", never text that could be mistaken for the page.
        """
        html, url, fetched, headers = _page_of(html_or_url, at)
        if respect_tdm:
            _respect_tdm(html, url, fetched, headers)
        whole = to_markdown(html, url=url, front_matter=front_matter)
        part, following = _slice(whole, offset, max_chars)
        result: dict[str, Any] = {
            "ok": True,
            "markdown": part,
            "url": url,
            "length": len(whole),
            "next_offset": following,
        }
        if fetched is not None:
            result["fetch"] = fetched
        _slice_within_bound(result, "markdown", offset)
        return cast(answers.MarkdownAnswer, result)

    @tool("Fetch a page")
    @_answers_instead_of_raising
    def fetch_page(
        url: str, offset: int = 0, max_chars: int = DEFAULT_CHARS
    ) -> answers.PageAnswer:
        """Fetch a page's HTML, and say what it cost: plain HTTP or a browser.

        url: an http(s) URL. Literal HTML is refused, since nothing would be
        fetched.
        offset: where in the HTML this answer starts, 0 for the beginning;
        the answer before gives the next as next_offset.
        max_chars: the most characters this answer carries, 1 to 60,000;
        fewer when more would weigh over 75,000 bytes, as 60,000 characters
        of Chinese do.

        Returns {"ok", "html", "url", "fetch", "truncated", "length",
        "next_offset"}: html is one slice of the page, length the whole
        page's, and next_offset where the next slice starts, or null when
        this one reaches the end. Prefer extract_declared or page_markdown,
        which return what is in the page rather than all of it.
        """
        if not url.strip().lower().startswith(("http://", "https://")):
            # Refused rather than echoed back: a caller handed the string it
            # sent, with no way to tell nothing was fetched, is worse off.
            raise _BadInput(f"fetch_page needs an http:// or https:// URL, got {url!r}")
        html, landed, fetched = _html_of(url, error_page=True)
        part, following = _slice(html, offset, max_chars)
        page = {
            "ok": True,
            "html": part,
            "url": landed,
            "fetch": fetched,
            "truncated": following is not None,
            "length": len(html),
            "next_offset": following,
        }
        _slice_within_bound(page, "html", offset)
        return cast(answers.PageAnswer, page)

    @tool("Learn an extractor")
    @_answers_instead_of_raising
    def compile_extractor(
        pages: list[str],
        listing: bool | None = None,
        want: dict[str, str] | None = None,
        select: dict[str, str] | None = None,
        rows: str | None = None,
    ) -> answers.CompileAnswer:
        """Learn an extractor from pages of one template, to replay later for free.

        pages: http(s) URLs, or the HTML itself, of pages built from one
        template -- two or three pages of one listing, or of one kind of
        product page.
        listing: learn the rows the pages repeat; by default only where they
        declare nothing about a thing.
        want: example values one row of the listing holds, by the name each
        column is to have, as {"price": "41.90", "title": "Brake pad set"}:
        they choose the listing and the columns, and only those columns are
        kept. A value that no row holds is an error that names it.
        select: instead of want, each field by a CSS or XPath selector you
        write, as {"title": "h1", "price": "span.price::text"}; pages may
        then be empty. Where the fields are is not learnt; what the pages
        show of them is, and a run fails when a selector finds nothing. Try
        a selector first with select_values.
        rows: with select, the selector of a listing's rows ("li.product"),
        each field then read inside each row.

        Returns {"ok", "extractor"}: keep that object and hand it to
        run_extractor. It holds what the pages declared, the listing's place,
        its fields, and what every field looked like. An extractor heavier
        than one answer may be, 75,000 bytes, is too_large: sluicer compile
        writes it to a file.
        """
        if not pages and select is None:
            raise _BadInput("compile_extractor needs at least one page")
        if select is not None or rows is not None:
            try:
                # Every selector read before any page is fetched, and want
                # or listing beside them refused, as the command line does:
                # given both, want was dropped without a word.
                extractor_module.compile_extractor(
                    [], select=select, rows=rows, want=want, listing=listing
                )
            except ValueError as unread:
                raise _BadInput(str(unread)) from unread
        read = [_html_of(one)[:2] for one in pages]
        try:
            if select is not None:
                learnt = isolated(_written_from, read, select, rows)
            else:
                learnt = extractor_module.compile_extractor(
                    read, listing=listing, want=want
                )
        except (extractor_module.NothingToLearn, ValueError) as nothing:
            raise _BadInput(str(nothing)) from nothing
        return {"ok": True, "extractor": json.loads(learnt.to_json())}

    @tool("Run an extractor")
    @_answers_instead_of_raising
    def run_extractor(extractor: dict[str, Any], html_or_url: str) -> answers.RunAnswer:
        """Replay an extractor on one page, and check the page still keeps to it.

        extractor: the object compile_extractor returned.
        html_or_url: an http(s) URL to fetch, or the HTML itself.

        Returns {"ok", "rows", "fields", "summary", "failed"}; "fields" holds
        the page's own values an extractor learnt from examples. ok is false
        when the page drifted -- the listing moved, rows or a field vanished, a price no
        longer looks like a price -- and "failed" says which expectation broke.
        Never read rows from an answer whose ok is false as if nothing happened.
        Past 75,000 bytes the last rows are left out, counted in
        rows_left_out, then the heaviest summary and fields entries, named in
        summary_left_out and fields_left_out.
        """
        loaded = _extractor_from(extractor)
        html, url, _fetched = _html_of(html_or_url)
        if loaded.written is not None:
            run = isolated(extractor_module.run_extractor, loaded, html, url)
        else:
            run = extractor_module.run_extractor(loaded, html, url=url)
        answer = {
            "ok": run.ok,
            "rows": run.rows,
            "fields": run.fields,
            "summary": run.summary,
            "failed": [asdict(check) for check in run.checks if not check.ok],
        }
        _bounded(
            answer,
            _cut_list("rows"),
            _cut_largest("summary"),
            _cut_largest("fields"),
        )
        return cast(answers.RunAnswer, answer)

    @tool("Heal an extractor")
    @_answers_instead_of_raising
    def heal_extractor(
        extractor: dict[str, Any], pages: list[str]
    ) -> answers.HealAnswer:
        """Learn pages again after a redesign, and say what moved where.

        extractor: the object compile_extractor returned.
        pages: http(s) URLs, or the HTML itself, of the redesigned pages.

        Returns {"ok", "extractor", "changes", "lost"}. A field that moved
        keeps its old name, so rows read with the healed extractor keep their
        columns, and its change carries the evidence: how many of the values it
        was learnt with were found in the new place. "lost" is true when a
        change is data the page no longer has -- vanished, summary-lost,
        type-lost, listing-lost, or broken: a selector written by hand that
        the pages no longer bear out, which heal never rewrites -- and then
        ok is false: the old extractor,
        which keeps failing, is the safer one to keep until a person looks.
        A healed extractor heavier than 75,000 bytes is too_large.
        """
        loaded = _extractor_from(extractor)
        if not pages:
            raise _BadInput("heal_extractor needs at least one page")
        read = [_html_of(one)[:2] for one in pages]
        try:
            if loaded.written is not None:
                healed, changes = isolated(extractor_module.heal, loaded, read)
            else:
                healed, changes = extractor_module.heal(loaded, read)
        except extractor_module.NothingToLearn as nothing:
            raise _BadInput(str(nothing)) from nothing
        lost = any(c.kind in extractor_module.LOSSES for c in changes)
        answer = {
            "ok": not lost,
            "extractor": json.loads(healed.to_json()),
            "changes": [_change(change) for change in changes],
            "lost": lost,
        }
        return cast(answers.HealAnswer, answer)

    @tool("Audit a page's markup")
    @_answers_instead_of_raising
    def audit_page(html_or_url: str, site: bool = True) -> answers.AuditAnswer:
        """Check a page's structured data against what Google documents for it.

        html_or_url: an http(s) URL to fetch, or the HTML itself.
        site: for a URL, also read the site's robots.txt, llms.txt and
        llms-full.txt.

        Returns {"ok", "url", "records", "page", "not_checked", "errors",
        "warnings", "notes"}, and for a URL read with site "crawlers",
        "robots_txt", "other_agents", "llms_txt", "llms_full_txt" and "fetch".
        Every JSON-LD, microdata and RDFa record lists the rich-result features
        its type is documented for, each with requirements_met and the
        required and recommended properties it lacks, and findings that each
        name a severity, the record's source, the property path and the URL of
        the rule. crawlers says, per AI agent from its vendor's own page,
        whether robots.txt admits the page. ok is true whenever the audit ran:
        a page with errors is an answer; "not_checked" says what was not.
        errors, warnings and notes count everything found; past 75,000 bytes
        the last records, page findings and other_agents are left out,
        counted in records_left_out, page_left_out and other_agents_left_out.
        """
        html, url, fetched = _html_of(html_or_url, error_page=True)
        read = None
        if site and url is not None:
            from sluicer.fetch.site import read_site

            read = read_site(url, allow_private=_allow_private())
        audited = audit(html, url=url, site=read)
        if fetched is not None and not 200 <= fetched["status"] < 300:
            audited.not_checked.insert(0, answered_with(fetched["status"]))
        result: dict[str, Any] = {"ok": True, **asdict(audited)}
        if fetched is not None:
            result["fetch"] = fetched
        _bounded(
            result, _cut_list("records"), _cut_list("page"), _cut_list("other_agents")
        )
        return cast(answers.AuditAnswer, result)

    @tool("Read a feed")
    @_answers_instead_of_raising
    def read_feed(url_or_text: str, limit: int = 50) -> answers.FeedAnswer:
        """Read a feed's items: RSS, Atom or JSON Feed.

        url_or_text: an http(s) URL of a feed -- or of a page that declares
        one, which is followed to it -- or the feed itself.
        limit: the most items answered, 1 to 500; items_total says how many
        the feed holds.

        Returns {"ok", "url", "format", "title", "link", "description",
        "items", "items_total"}, each item {"title", "link", "id",
        "published", "updated", "summary", "content", "authors",
        "categories", "enclosures", "normalised"}, dates in normalised as ISO
        8601. What is not a feed, and declares none, is bad_input. Items that
        would make the answer weigh over 75,000 bytes are left out, counted in
        items_left_out; fetch_page reads the whole feed in slices.
        """
        from sluicer.declared.links import read_links
        from sluicer.document import load
        from sluicer.feeds import _read_feed as read

        _within("limit", limit, 1, FEED_ITEMS)
        html, url, fetched = _html_of(url_or_text, expect_html=False)
        feed = read(html, url=url)
        if feed is None and url is not None:
            declared = read_links(load(html, url=url)).get("feeds", [])
            if declared:
                html, url, fetched = _html_of(declared[0]["href"])
                feed = read(html, url=url)
        if feed is None:
            raise _BadInput(
                f"{url or 'the text'} is not RSS, Atom or JSON Feed, and declares none"
            )
        found = asdict(feed)
        answer: dict[str, Any] = {
            "ok": True,
            "url": url,
            **found,
            "items": found["items"][:limit],
            "items_total": len(feed.items),
        }
        if fetched is not None:
            answer["fetch"] = fetched
        _bounded(answer, _cut_list("items"))
        return cast(answers.FeedAnswer, answer)

    @tool("Map a site")
    @_answers_instead_of_raising
    def map_site(url: str, limit: int = 100) -> answers.MapAnswer:
        """List a site's addresses, from its sitemaps or its start page's links.

        url: an http(s) address on the site; its links stand in when the site
        has no sitemap.
        limit: the most addresses returned, 1 to 1,000.

        Returns {"ok", "url", "source", "urls", "sitemaps", "truncated"}.
        source is "sitemaps" or "links"; each of urls is {"url", "lastmod",
        "sitemap"}, only addresses on the site, in the order the sitemaps list
        them; sitemaps says what became of each one tried. At most ten
        sitemaps are read, politely, within a minute; truncated is true when a
        bound cut the map short, urls_left_out counting the addresses left out
        to keep the answer under 75,000 bytes. Hand the addresses worth
        reading to extract_declared, or crawl_site to follow links from one.
        """
        _within("limit", limit, 1, MAP_LIMIT)
        found = crawling.map_site(
            url,
            limit=limit,
            max_sitemaps=MAP_SITEMAPS,
            max_delay=CRAWL_MAX_DELAY_SECONDS,
            time_budget=TIME_BUDGET_SECONDS,
            allow_private=_allow_private(),
        )
        answer = {
            "ok": True,
            "url": found.url,
            "source": found.source,
            "urls": [asdict(address) for address in found.urls],
            "sitemaps": [asdict(read) for read in found.sitemaps],
            "truncated": found.truncated,
        }
        _bounded(answer, _cut_list("urls"))
        answer["truncated"] = found.truncated or "urls_left_out" in answer
        return cast(answers.MapAnswer, answer)

    @tool("Crawl a site")
    @_answers_instead_of_raising
    def crawl_site(
        url: str,
        max_pages: int = 10,
        max_depth: int = 2,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        respect_tdm: bool = False,
    ) -> answers.CrawlAnswer:
        """Crawl a site from url, following its links, and summarise every page.

        url: an http(s) address where the crawl starts; only links on its
        site are followed.
        max_pages: the most pages taken, 1 to 25.
        max_depth: the most links from url, 0 to 3; 0 reads url alone.
        respect_tdm: give a page whose site reserves its text and data mining
        rights (TDMRep) as a tdm_reserved error, never its summary.
        include: text an address must contain for its link to be followed
        (any one of them); plain text, not a pattern.
        exclude: text that stops a link being followed when its address
        contains it.

        Returns {"ok", "url", "pages", "stopped"}. Pages come breadth first,
        each {"ok", "url", "depth", "found_on", "landed", "fetch", "canonical",
        "summary", "sources", "types", "links"} -- the summary and the types
        declared, not the records; call extract_declared on a page for those
        -- or, when it has nothing, {"ok": false, "error"} with the page's
        reason. stopped is "done", "max_pages" (links were left unfollowed)
        or "time_budget" (a minute passed). One request at a time, a second
        apart or the site's Crawl-delay, robots.txt obeyed; a page asked again
        after a request that may succeed later says so in "retries". ok is
        false only
        when no page could be read, and error then says why. Past 75,000
        bytes the heaviest summary answers of any page go first, named in that
        page's summary_left_out, then the last pages, counted in
        pages_left_out.
        """
        _within("max_pages", max_pages, 1, CRAWL_PAGES)
        _within("max_depth", max_depth, 0, CRAWL_DEPTH)
        try:
            run = crawling.crawl(
                url,
                max_pages,
                max_depth,
                include=[re.escape(text) for text in include or ()],
                exclude=[re.escape(text) for text in exclude or ()],
                max_delay=CRAWL_MAX_DELAY_SECONDS,
                time_budget=TIME_BUDGET_SECONDS,
                allow_private=_allow_private(),
                respect_tdm=respect_tdm,
            )
        except ValueError as bad:
            raise _BadInput(str(bad)) from bad
        pages = [_crawled(page) for page in run]
        answer: dict[str, Any] = {
            "ok": any(page["ok"] for page in pages),
            "url": crawling.normalise(url),
            "pages": pages,
            "stopped": run.stopped,
        }
        if not answer["ok"] and pages:
            answer["error"] = pages[0]["error"]
        _bounded(answer, _cut_largest("summary", among="pages"), _cut_list("pages"))
        return cast(answers.CrawlAnswer, answer)

    @tool("Extract several pages")
    @_answers_instead_of_raising
    def extract_many(
        urls: list[str],
        records: bool = False,
        induce: bool = False,
        respect_tdm: bool = False,
    ) -> answers.ManyAnswer:
        """Read several pages' declared data, politely, in the order given.

        urls: 1 to 25 http(s) addresses, on one site or several; one given
        twice is read once.
        records: also return each page's records, not only its summary; the
        heaviest pages' records are left out first to keep the answer under
        75,000 bytes, each counted in that page's records_left_out.
        induce: also read repeated rows from a page that declares nothing
        about them; those fields say source "induced".
        respect_tdm: give a page whose site reserves its text and data mining
        rights (TDMRep) as a tdm_reserved error, never its data.

        Returns {"ok", "pages", "stopped"}. Pages come in the order given,
        each {"ok", "url", "landed", "fetch", "canonical", "summary",
        "sources", "types", "links"}, and "records" when asked -- or, when it
        has nothing, {"ok": false, "error"} with the page's reason. A page
        asked again after a request that may succeed later says so in
        "retries". Each site is asked one request at a time, a second apart
        or its Crawl-delay, robots.txt obeyed; several sites at once. stopped
        is "done", or "time_budget" when a minute passed first and the pages
        after are left out. ok is false only when no page could be read, and
        error then says why. Past 75,000 bytes the heaviest pages' records go
        first, then the heaviest summary answers, named in summary_left_out,
        then the last pages, counted in pages_left_out. For many more
        addresses, or a whole site, the command line's sluicer batch has no
        such bounds.
        """
        if not 1 <= len(urls) <= MANY_URLS:
            raise _BadInput(
                f"urls must hold 1 to {MANY_URLS} addresses, not {len(urls)}"
            )
        try:
            run = crawling.extract_many(
                urls,
                induce=induce,
                respect_tdm=respect_tdm,
                max_delay=CRAWL_MAX_DELAY_SECONDS,
                time_budget=TIME_BUDGET_SECONDS,
                allow_private=_allow_private(),
            )
        except ValueError as bad:
            raise _BadInput(str(bad)) from bad
        pages = [_crawled(page, records=records) for page in run]
        for page in pages:
            page.pop("depth", None)
            page.pop("found_on", None)
        answer: dict[str, Any] = {
            "ok": any(page["ok"] for page in pages),
            "pages": pages,
            "stopped": run.stopped,
        }
        if not answer["ok"] and pages:
            answer["error"] = pages[0]["error"]
        _bounded(
            answer,
            _cut_heaviest_lists("records", among="pages"),
            _cut_largest("summary", among="pages"),
            _cut_list("pages"),
        )
        return cast(answers.ManyAnswer, answer)

    @tool("Select values on a page")
    @_answers_instead_of_raising
    def select_values(
        html_or_url: str, selector: str, respect_tdm: bool = False
    ) -> answers.SelectAnswer:
        """Say what a CSS or XPath selector gives on a page, and where each value is.

        html_or_url: an http(s) URL to fetch, or the HTML itself.
        selector: CSS, with ::text for an element's own text and
        ::attr(name) for an attribute ("span.price::text", "a::attr(href)"),
        or XPath ("//h1", "//a/@href"), told apart by how it begins: an XPath
        begins with /, ./, ( or @, or is written after "xpath:".
        respect_tdm: answer tdm_reserved when the site reserves its text and
        data mining rights (TDMRep).

        Returns {"ok", "url", "values", "count"}, and "fetch" for a URL:
        values are {"value", "where"}, the text or attribute read, spaces
        collapsed, links resolved, and the XPath of its element; count is
        how many the selector gave. A selector that cannot be read is
        bad_input naming it; one that gives nothing is ok with no values.
        Past 75,000 bytes the last values are left out, counted in
        values_left_out. Use it to try the selectors compile_extractor's
        select takes.
        """
        try:
            read_selector(selector)
        except SelectorError as unread:
            raise _BadInput(str(unread)) from unread
        html, url, fetched, headers = _page_of(html_or_url)
        if respect_tdm:
            _respect_tdm(html, url, fetched, headers)
        try:
            found = isolated(_selected, html, url, headers, selector)
        except SelectorError as unanswered:
            # Read when written, a selector can still select a comment on
            # the page it is asked of.
            raise _BadInput(str(unanswered)) from unanswered
        answer: dict[str, Any] = {
            "ok": True,
            "url": url,
            "values": [{"value": value, "where": where} for value, where in found],
            "count": len(found),
        }
        if fetched is not None:
            answer["fetch"] = fetched
        _bounded(answer, _cut_list("values"))
        return cast(answers.SelectAnswer, answer)

    unknown = [name for name in wanted or () if name not in seen]
    if unknown:
        raise UnknownTool(
            f"no such tool: {', '.join(map(repr, unknown))}; "
            f"the tools are {', '.join(seen)}"
        )
    if wanted is not None and not wanted:
        # Until 0.9.1 `--tools ''` served no tool at all, and said nothing.
        raise UnknownTool(
            f"no tool named: name one or more of {', '.join(seen)}, or leave "
            "the list out for all twelve"
        )
    return server


def _parameter_notes(doc: str, names: Iterable[str]) -> dict[str, str]:
    """What a tool's docstring says of each parameter: the line that opens with
    its name and a colon, and the lines that continue it, up to a blank line
    or the next parameter's -- as ``scripts/reference.py`` reads them."""
    wanted = set(names)
    notes: dict[str, str] = {}
    current: str | None = None
    for line in inspect.cleandoc(doc).splitlines():
        opened = re.match(r"^(\w+): (.*)$", line)
        if opened and opened.group(1) in wanted and opened.group(1) not in notes:
            current = opened.group(1)
            notes[current] = opened.group(2).strip()
        elif current is not None and line.strip():
            notes[current] += " " + line.strip()
        else:
            current = None
    return notes


def _bytes_of(answer: Any) -> int:
    """What an answer, or a part of one, weighs as the JSON a client receives."""
    return len(json.dumps(answer, ensure_ascii=False, default=str).encode("utf-8"))


Cut = Callable[[dict[str, Any], int], None]
"""One way to make an answer lighter: given the answer and the most it may
weigh, it leaves something out and says so in the answer."""


def _bounded(answer: dict[str, Any], *cuts: Cut) -> dict[str, Any]:
    """``answer`` made to weigh at most ``MOST_ANSWER_BYTES``, by ``cuts`` in turn.

    Each cut runs only while the answer is still too heavy. What a cut writes
    to say what it left out weighs something too, so a pass that ends a few
    bytes over runs again aiming that much lower; an answer no cut can bring
    under the bound is left to ``_held_to_the_bound``.
    """
    most = MOST_ANSWER_BYTES
    for _ in range(3):
        for cut in cuts:
            if _bytes_of(answer) <= most:
                break
            cut(answer, most)
        over = _bytes_of(answer) - MOST_ANSWER_BYTES
        if over <= 0:
            break
        most -= over
    return answer


def _cut_list(key: str, within: str | None = None) -> Cut:
    """A cut that keeps the longest head of the list ``answer[key]`` -- or of
    ``answer[within][key]`` -- the bound allows, and adds how many items it
    left out to ``<key>_left_out`` beside the list."""

    def cut(answer: dict[str, Any], most: int) -> None:
        holder = answer if within is None else answer.get(within)
        if not isinstance(holder, dict) or not holder.get(key):
            return
        items = holder[key]
        holder[key] = []
        room = most - _bytes_of(answer)
        kept = used = 0
        for item in items:
            # ", " between two items, as json.dumps writes them.
            more = _bytes_of(item) + (2 if kept else 0)
            if used + more > room:
                break
            used += more
            kept += 1
        holder[key] = items[:kept]
        if kept < len(items):
            left_out = f"{key}_left_out"
            holder[left_out] = holder.get(left_out, 0) + len(items) - kept

    return cut


def _cut_largest(key: str, among: str | None = None) -> Cut:
    """A cut that takes entries out of the mapping ``answer[key]``, the heaviest
    first, until the answer fits, and names them in ``<key>_left_out``.

    With ``among``, the mappings are ``answer[among][i][key]`` -- each crawled
    page's summary -- and the heaviest entry of all of them goes first, so one
    page with a two-megabyte title costs that title, not the other pages.
    """

    def cut(answer: dict[str, Any], most: int) -> None:
        if among is None:
            holders = [answer]
        else:
            holders = [one for one in answer.get(among) or () if isinstance(one, dict)]
        entries = [
            (_bytes_of({name: value}) - 2, index, name)
            for index, holder in enumerate(holders)
            if isinstance(holder.get(key), dict)
            for name, value in holder[key].items()
        ]
        weight = _bytes_of(answer)
        for size, index, name in sorted(entries, key=lambda e: (-e[0], e[1], e[2])):
            if weight <= most:
                break
            mapping = holders[index][key]
            # The entry, and the ", " that joined it to another, if one is
            # left; the names written below are weighed by _bounded's next pass.
            weight -= size + (2 if len(mapping) > 1 else 0)
            del mapping[name]
            holders[index].setdefault(f"{key}_left_out", []).append(name)

    return cut


def _cut_heaviest_lists(key: str, among: str) -> Cut:
    """A cut that leaves the whole list ``answer[among][i][key]`` out of the
    heaviest entries first, counting each in that entry's ``<key>_left_out``:
    a page's records, which it carries all of or none of."""

    def cut(answer: dict[str, Any], most: int) -> None:
        holders = [one for one in answer.get(among) or () if isinstance(one, dict)]
        heaviest = sorted(
            (index for index, one in enumerate(holders) if key in one),
            key=lambda index: (-_bytes_of(holders[index][key]), index),
        )
        weight = _bytes_of(answer)
        for index in heaviest:
            if weight <= most:
                break
            weight -= _bytes_of(holders[index][key])
            holders[index][f"{key}_left_out"] = len(holders[index].pop(key))

    return cut


def _cut_leaving_all(key: str) -> Cut:
    """A cut that leaves the whole list ``answer[key]`` out and counts it in
    ``<key>_left_out``: ``extract_declared``'s records, which an answer
    carries all of or none of."""

    def cut(answer: dict[str, Any], most: int) -> None:
        if key in answer:
            answer[f"{key}_left_out"] = len(answer.pop(key))

    return cut


def _slice(text: str, offset: int, max_chars: int) -> tuple[str, int | None]:
    """The slice of ``text`` an answer carries, and where the next one starts,
    or None when this one reaches the end. The same text, offset and length
    always give the same slice."""
    _within("max_chars", max_chars, 1, MOST_CHARS)
    if offset < 0 or (offset and offset >= len(text)):
        raise _BadInput(
            f"offset {offset} is outside the text, which is {len(text):,} characters"
        )
    part = text[offset : offset + max_chars]
    end = offset + len(part)
    return part, end if end < len(text) else None


def _slice_within_bound(answer: dict[str, Any], key: str, offset: int) -> None:
    """Shorten the slice ``answer[key]``, which starts at ``offset``, until the
    answer weighs at most ``MOST_ANSWER_BYTES``; ``next_offset`` then says where
    the shortened slice ends, so the slices still join back to the whole.

    60,000 characters are 180,000 bytes of Chinese, and HTML's quotes each
    weigh two once escaped: the character bound alone let ``fetch_page``
    answer 180 KB.
    """
    if _bytes_of(answer) <= MOST_ANSWER_BYTES:
        return
    part: str = answer[key]
    answer[key] = ""
    # The rest of the answer, and room for next_offset turning from null into
    # a number and truncated from false into true.
    room = MOST_ANSWER_BYTES - _bytes_of(answer) - 16
    least, most = 0, len(part)
    while least < most:
        middle = (least + most + 1) // 2
        if _bytes_of(part[:middle]) - 2 <= room:
            least = middle
        else:
            most = middle - 1
    answer[key] = part[:least]
    answer["next_offset"] = offset + least
    if "truncated" in answer:
        answer["truncated"] = True


def _within(name: str, value: int, least: int, most: int) -> None:
    """Refuse a bound outside what a tool call may ask for, saying what may."""
    if not least <= value <= most:
        raise _BadInput(f"{name} must be from {least} to {most}, not {value}")


def _crawled(page: crawling.Page, records: bool = False) -> dict[str, Any]:
    """A crawled page as an agent gets it: the summary, and the records only
    when asked for."""
    line = page.to_json()
    if not page.ok:
        error = {**line["error"], "url": page.url}
        kept = ("ok", "url", "depth", "retries", "landed", "fetch")
        return {key: line[key] for key in kept if key in line} | {"error": error}
    read = line["records"] if records else line.pop("records")
    line["types"] = sorted({kind for record in read for kind in record["types"]})
    line["links"] = len(line["links"])
    return line


def _change(change: extractor_module.Change) -> Any:
    answer = asdict(change)
    return {
        key: value
        for key, value in answer.items()
        if value is not None or key in ("before", "after")
    }


# -- evaluated isolated: a caller's selectors, in a process of their own ------


def _selected(
    html: str, url: str | None, headers: dict[str, str] | None, selector: str
) -> list[tuple[str, str]]:
    """What ``selector`` gives on the page, each value and where it is."""
    return [
        (one.value, one.where)
        for one in parse_page(html, url, headers).select(selector)
    ]


def _written_from(
    pages: list[tuple[str, str | None]], select: dict[str, str], rows: str | None
) -> extractor_module.Extractor:
    """An extractor written by ``select`` and ``rows``, learnt from ``pages``."""
    return extractor_module.compile_extractor(pages, select=select, rows=rows)


def _extractor_from(given: dict[str, Any]) -> extractor_module.Extractor:
    try:
        return extractor_module.Extractor.from_json(json.dumps(given))
    except (ValueError, KeyError, TypeError) as invalid:
        raise _BadInput(
            f"not an extractor from compile_extractor: {invalid}"
        ) from invalid


TOOLS_ENV = "SLUICER_MCP_TOOLS"
"""Comma-separated tools to register, for a client that sets variables and not
a command line; ``sluicer mcp --tools`` says the same."""


SCRIPT_USAGE = (
    "Usage: sluicer-mcp\n\n"
    "  Run Sluicer's MCP server over stdio (needs sluicer[mcp]); it takes no\n"
    "  arguments. SLUICER_MCP_TOOLS=extract_declared,page_markdown registers\n"
    "  only those tools, as sluicer mcp --tools does."
)


def _refuse_script_arguments(argv: list[str]) -> None:
    """``sluicer-mcp --help`` prints its usage and exits 0; any other argument
    exits 2. Until 0.9.1 both started the server, which then sat waiting on
    stdin. ``sluicer mcp`` reads its own arguments, and is left alone."""
    if not argv or not os.path.basename(argv[0]).startswith("sluicer-mcp"):
        return
    given = argv[1:]
    if not given:
        return
    if given in (["--help"], ["-h"]):
        print(SCRIPT_USAGE)
        raise SystemExit(0)
    print(
        f"sluicer-mcp takes no arguments, not {' '.join(given)!r}.\n\n" + SCRIPT_USAGE,
        file=sys.stderr,
    )
    raise SystemExit(2)


def main(tools: Iterable[str] | None = None) -> None:
    """Run the server over stdio, or explain a missing ``mcp`` extra in one line.

    ``tools`` names the tools to register, or ``SLUICER_MCP_TOOLS`` does; all
    twelve when neither says. A name that is not a tool exits 2, as a wrong
    option does, with the list of the twelve. A missing ``mcp`` extra exits 2
    too, with the line that installs it: until 0.9.1 it exited 1, which the
    command line's codes keep for "read, and found nothing". A broken
    install, as opposed to a missing one, keeps its traceback.
    """
    from sluicer.fetch.browser import UnknownBrowser

    _refuse_script_arguments(sys.argv)
    if tools is None and os.environ.get(TOOLS_ENV, "").strip():
        tools = [n.strip() for n in os.environ[TOOLS_ENV].split(",") if n.strip()]
    try:
        server = build_server(tools=tools) if tools is not None else build_server()
    except McpExtraMissing as missing:
        # Flushed now: the exit that follows must not be what decides whether
        # the one line that says what to install is ever written.
        print(str(missing), file=sys.stderr, flush=True)
        raise SystemExit(2) from missing
    except (UnknownTool, UnusableProxy, UnknownBrowser) as unknown:
        print(str(unknown), file=sys.stderr, flush=True)
        raise SystemExit(2) from unknown
    # scrapling logs every request at INFO into the server's stderr, and sets
    # its level when first imported; a filter outlives that.
    logging.getLogger("scrapling").addFilter(
        lambda record: record.levelno >= logging.WARNING
    )
    server.run()
