"""Ready crawls for two kinds of site that say where their pages are.

``sitemap_pages`` reads every address a site's sitemaps list, page by page:
``sluicer map --plain | sluicer batch -`` in one process, so the delay
between the map's last request and the batch's first is kept, and with the
crawl's page budget and patterns.

``shopify_products`` reads a Shopify shop's products from the file every
Shopify shop serves, ``/products.json``, a page of products at a time, and
hands back each product as a page of its own: a record of Shopify's own
fields and a summary answering the questions a product page's does. The
file is asked like any page: through robots.txt, after the site's delay,
asked again when it did not answer, and never past the page budget.

Both hand back a ``Crawl`` of ``Page``s, written to ``state`` as a crawl's
are, and resumed from it.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit

from sluicer.api import Extraction
from sluicer.crawl.pages import (
    MAX_PAGES,
    Crawl,
    Page,
    PageError,
    StateMismatch,
    _appending,
    _check_retries,
    _cut_unfinished,
    _extract_listed,
    _lines,
    _patterns,
    _reach,
    _sendable,
    _write,
    asking_again,
)
from sluicer.crawl.schedule import (
    CONCURRENCY,
    DEFAULT_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    RETRIES,
    Politeness,
)
from sluicer.crawl.sitemaps import MAX_SITEMAP_URLS, map_site
from sluicer.crawl.urls import normalise
from sluicer.crawl.web import Web
from sluicer.declared.merge import MAX_DEPTH, Field, JsonValue, Record
from sluicer.document import load
from sluicer.fetch import AddressRefused, Fetched, ResponseTooLarge
from sluicer.fetch.address import _resolve, why_not_public
from sluicer.fetch.identity import RobotsUnreachable, robots_refusal
from sluicer.fetch.result import MAX_RESPONSE_BYTES
from sluicer.fetch.wire import passing
from sluicer.summary import FIELDS, SummaryField

TEMPLATES = ("sitemap", "shopify")
"""The ready crawls ``sluicer crawl --template`` knows."""

SHOPIFY_PAGE_SIZE = 250
"""How many products one ``/products.json`` page is asked for: the most
Shopify serves in one."""

SHOPIFY = "shopify"
"""The reader name a product's fields and summary answers carry."""


def sitemap_pages(
    url: str,
    max_pages: int = MAX_PAGES,
    include: Sequence[str] = (),
    exclude: Sequence[str] = (),
    *,
    state: str | Path | None = None,
    induce: bool = False,
    respect_tdm: bool = False,
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    concurrency: int = CONCURRENCY,
    retries: int = RETRIES,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Crawl:
    """Read the pages ``url``'s site lists in its sitemaps, in their order.

    The sitemaps are read as ``map_site`` reads them, their addresses kept
    when one of ``include`` is found in them (any, when none is given) and no
    ``exclude`` is, and the first ``max_pages`` read as ``extract_many``
    reads a list. ``stopped`` is ``max_pages`` when the sitemaps listed more.
    A site with no sitemap gives the links of the page at ``url``, as a map
    does. The other arguments are ``crawl``'s; the time budget covers the
    sitemaps and the pages both.

    Raises:
        ValueError: a pattern is not a regular expression.
        FetchFailed, AddressRefused, RobotsRefused, ResponseTooLarge: the
            site could not be mapped, as ``map_site`` raises them.
        StateMismatch: ``state`` holds something else.
    """
    wanted, unwanted = _patterns(include), _patterns(exclude)
    started = clock()
    found = map_site(
        url,
        limit=MAX_SITEMAP_URLS,
        min_delay=min_delay,
        max_delay=max_delay,
        time_budget=time_budget,
        allow_private=allow_private,
        resolve=resolve,
        max_bytes=max_bytes,
        web=web,
        clock=clock,
        sleep=sleep,
        headers=headers,
        cookies=cookies,
    )
    chosen = [
        address.url
        for address in found.urls
        if (not wanted or any(p.search(address.url) for p in wanted))
        and not any(p.search(address.url) for p in unwanted)
    ]
    left = None if time_budget is None else time_budget - (clock() - started)
    # The login goes to the origin the caller named, not to every address of
    # the site a sitemap lists: its www. twin, its pages over plain http.
    inner = _extract_listed(
        [normalise(address) or address for address in chosen[:max_pages]],
        [url],
        state=state,
        induce=induce,
        respect_tdm=respect_tdm,
        min_delay=min_delay,
        max_delay=max_delay,
        concurrency=concurrency,
        retries=retries,
        time_budget=left,
        allow_private=allow_private,
        resolve=resolve,
        max_bytes=max_bytes,
        web=web,
        clock=clock,
        sleep=sleep,
        headers=headers,
        cookies=cookies,
    )

    def pages(run: Crawl) -> Iterator[Page]:
        yield from inner
        cut = len(chosen) > max_pages or found.truncated
        run.stopped = "max_pages" if cut and inner.stopped == "done" else inner.stopped

    return Crawl(pages, resumed=inner.resumed)


def shopify_products(
    url: str,
    max_pages: int = MAX_PAGES,
    *,
    state: str | Path | None = None,
    per_page: int = SHOPIFY_PAGE_SIZE,
    min_delay: float = DEFAULT_DELAY_SECONDS,
    max_delay: float = MAX_DELAY_SECONDS,
    retries: int = RETRIES,
    time_budget: float | None = None,
    allow_private: bool = True,
    resolve: Callable[[str], Iterable[str]] = _resolve,
    max_bytes: int = MAX_RESPONSE_BYTES,
    web: Web | None = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    headers: Mapping[str, str] | None = None,
    cookies: Mapping[str, str] | None = None,
) -> Crawl:
    """Read the products of the Shopify shop at ``url``, a page each.

    ``/products.json?limit=250&page=1`` is asked, then page 2, and so on,
    until a page holds fewer than ``per_page`` products or ``max_pages``
    pages were asked. Each product is a ``Page`` whose ``url`` is its own
    page, ``/products/<handle>``, and whose ``found_on`` is the products.json
    page it was listed on; its extraction holds one ``Product`` record of the
    fields Shopify wrote, each with its JSON pointer in that page, and a
    summary of them -- title, description, image, dates, brand, price or the
    range of its variants' prices, the regular price, availability and, for
    a product of one variant, its SKU. Shopify's file names no currency.

    A products.json page that could not be read is a ``Page`` with its error
    at that page's address, and the reading stops there: ``bad_input`` when
    it answered with another status or with what is not a products.json --
    not a Shopify shop, or one that serves none -- and the codes a crawl's
    pages have otherwise. ``state`` resumes as a crawl's does: the last
    products.json page the file holds is asked again, and the products it
    already holds are not written twice. The other arguments are
    ``crawl``'s.

    Raises:
        ValueError: ``url`` is not an http(s) address, ``per_page`` is not
            positive, or ``retries`` is past ``MAX_RETRIES``.
        StateMismatch: ``state`` holds another shop's products, or not a
            crawl's output.
    """
    start = normalise(url)
    if start is None:
        raise ValueError(f"{url!r} is not an http(s) address a crawl can start at")
    if per_page < 1:
        raise ValueError(f"per_page must be 1 or more, not {per_page}")
    _check_retries(retries)
    _sendable(web, headers, cookies)
    parts = urlsplit(start)
    origin = f"{parts.scheme}://{parts.netloc}"
    listing = f"{origin}/products.json"
    written: set[str] = set()
    first = 1
    held = 0
    if state is not None:
        lines = _lines(Path(state))
        for number, line in enumerate(lines, 1):
            page_url = line.get("found_on") if line.get("ok") else line.get("url")
            if not isinstance(page_url, str) or not page_url.startswith(listing):
                raise StateMismatch(
                    str(state),
                    f"line {number} is not a product of {listing}; it was "
                    "written by a crawl of another shop, or of pages",
                )
            written.add(line["url"])
            first = _page_number(page_url)
        held = len(lines)
        _cut_unfinished(Path(state))
    polite, web = _reach(
        web,
        min_delay,
        clock,
        sleep,
        allow_private,
        resolve,
        max_bytes,
        headers,
        cookies,
        max_delay,
        [start],
    )
    deadline = None if time_budget is None else clock() + time_budget
    reader = _Listing(web, polite, allow_private, resolve, max_delay)

    def pages(run: Crawl) -> Iterator[Page]:
        run.stopped = "done"
        with _appending(state) as out:
            for asked, number in enumerate(range(first, first + max_pages)):
                if deadline is not None and clock() >= deadline and asked:
                    run.stopped = "time_budget"
                    return
                address = f"{listing}?limit={per_page}&page={number}"
                answer, made = asking_again(
                    polite,
                    address,
                    retries,
                    deadline,
                    lambda address=address: reader.take(address),  # type: ignore[misc]
                    lambda answer: answer.again,
                )
                if answer.error is not None or answer.products is None:
                    failed = Page(address, error=answer.error, retries=made)
                    _write(out, failed)
                    yield failed
                    return
                for index, product in enumerate(answer.products):
                    page = _product_page(origin, address, index, product, answer)
                    if page.url in written:
                        continue
                    written.add(page.url)
                    page = replace(page, retries=made) if made else page
                    _write(out, page)
                    yield page
                if len(answer.products) < per_page:
                    return
            run.stopped = "max_pages"

    return Crawl(pages, resumed=held)


@dataclass(frozen=True)
class _Answer:
    """What one products.json page came to: its products, or its error, and
    ``again`` when asking again later may bring back more."""

    products: list[dict[str, Any]] | None = None
    error: PageError | None = None
    again: str | None = None
    status: int | None = None
    seconds: float = 0.0


class _Listing:
    """Asks a shop for one products.json page at a time, politely."""

    def __init__(
        self,
        web: Web,
        polite: Politeness,
        allow_private: bool,
        resolve: Callable[[str], Iterable[str]],
        max_delay: float,
    ) -> None:
        self.web = web
        self.polite = polite
        self.allow_private = allow_private
        self.resolve = resolve
        self.max_delay = max_delay

    def take(self, address: str) -> _Answer:
        def failed(code: str, message: str, again: str | None = None) -> _Answer:
            error = PageError(code, message, retryable=again is not None)
            return _Answer(error=error, again=again)

        refused = None if self.allow_private else why_not_public(address, self.resolve)
        if refused is not None:
            return failed("refused_address", str(AddressRefused(address, refused)))
        try:
            refusal = robots_refusal(address, self.polite.reader, now=self.polite.clock)
            if refusal is not None:
                return failed("refused_by_robots", f"{address} is refused: {refusal}")
            delay = self.polite.delay_for(address)
        except RobotsUnreachable as unreachable:
            return failed("fetch_failed", str(unreachable), again=str(unreachable))
        if delay > self.max_delay:
            return failed(
                "crawl_delay_too_long",
                f"its robots.txt asks for {delay:g} s between requests, longer "
                f"than the {self.max_delay:g} s this crawl waits",
            )
        refused_for = self.polite.refused_for(address)
        if refused_for > 0:
            return failed(
                "rate_limited",
                f"it asked, by Retry-After, not to be asked for {refused_for:g} s "
                f"more, longer than the {self.max_delay:g} s this crawl waits",
            )
        began = self.polite.clock()
        try:
            with self.polite.turn(address, delay):
                response = self.web.get(address)
        except ResponseTooLarge as heavy:
            return failed("too_large", str(heavy))
        except AddressRefused as refused_address:
            return failed("refused_address", str(refused_address))
        # Deliberately blind, as the ladder is about its rungs: every way a
        # transport can fail to bring the page back is one event, and the
        # sentence says which; asked again only when it may pass.
        except Exception as failure:  # noqa: BLE001
            said = f"Could not fetch {address}: {type(failure).__name__}: {failure}"
            again = said if passing(failure) else None
            return failed("fetch_failed", said, again=again)
        seconds = self.polite.clock() - began
        self.polite.slow_down(
            address,
            Fetched(address, "", response.status, "http", headers=response.headers),
            self.max_delay,
        )
        if response.status == 429 or response.status >= 500:
            said = f"it answered {response.status}"
            return failed("fetch_failed", f"{address}: {said}", again=said)
        if response.status != 200:
            return failed(
                "bad_input",
                f"{address} answered {response.status}: not a Shopify shop, or "
                "one that serves no products.json",
            )
        try:
            if _nested_past(response.body, MOST_NESTING):
                raise ValueError("nested deeper than a shop writes")
            products = json.loads(response.body)["products"]
        # RecursionError: the parser's own limit, which the check above keeps
        # it from reaching on any Python.
        except (ValueError, KeyError, TypeError, RecursionError):
            products = None
        if not isinstance(products, list):
            return failed("bad_input", f"{address} is not a Shopify products.json")
        return _Answer(
            products=[one for one in products if isinstance(one, dict)],
            status=response.status,
            seconds=seconds,
        )


def _page_number(address: str) -> int:
    try:
        return max(1, int(parse_qs(urlsplit(address).query)["page"][0]))
    except (KeyError, ValueError, IndexError):
        return 1


def _product_page(
    origin: str, listed_on: str, index: int, product: dict[str, Any], answer: _Answer
) -> Page:
    """One product of a products.json page, as a crawled page."""
    at = f"/products/{index}"
    handle = str(product.get("handle") or product.get("id") or index)
    url = normalise(f"{origin}/products/{quote(handle, safe='')}") or listed_on
    record = Record(
        type="Product",
        types=("Product",),
        fields={
            name: Field(text, SHOPIFY, f"{at}/{_escaped(name)}")
            for name, value in product.items()
            if (text := _as_text(value)) is not None
        },
        source=SHOPIFY,
        where=at,
    )
    summary = _summary(product, at, url)
    return Page(
        url,
        depth=1,
        found_on=listed_on,
        rung="http",
        status=answer.status,
        seconds=answer.seconds,
        extraction=Extraction(
            url=url, summary=summary, records=[record], sources=[SHOPIFY]
        ),
    )


def _summary(product: dict[str, Any], at: str, url: str) -> dict[str, SummaryField]:
    """The summary's answers a product's own fields give, in ``FIELDS`` order."""
    found: dict[str, SummaryField] = {}

    def said(name: str, value: Any, key: str, where: str | None) -> None:
        text = _text(value)
        if text:
            found[name] = SummaryField(text, SHOPIFY, key, where)

    said("title", product.get("title"), "title", f"{at}/title")
    body = product.get("body_html")
    if isinstance(body, str) and body.strip():
        text = " ".join(str(load(body).tree.text_content()).split())
        said("description", text, "body_html", f"{at}/body_html")
    said("url", url, "handle", f"{at}/handle")
    images = product.get("images")
    if isinstance(images, list) and images and isinstance(images[0], dict):
        said("image", images[0].get("src"), "images/src", f"{at}/images/0/src")
    said("published", product.get("published_at"), "published_at", f"{at}/published_at")
    said("modified", product.get("updated_at"), "updated_at", f"{at}/updated_at")
    found["type"] = SummaryField("Product", SHOPIFY, "products.json", at)
    variants = [
        (index, variant)
        for index, variant in enumerate(product.get("variants") or ())
        if isinstance(variant, dict)
    ]
    priced = [
        (index, variant, amount)
        for index, variant in variants
        if (amount := _amount(variant.get("price"))) is not None
    ]
    if priced:
        low = min(priced, key=lambda one: one[2])
        high = max(priced, key=lambda one: one[2])
        if low[2] == high[2]:
            index, variant, _ = low
            said(
                "price", variant.get("price"), "variants/price", _in(at, index, "price")
            )
            regular = _amount(variant.get("compare_at_price"))
            if regular is not None and regular > low[2]:
                said(
                    "price_regular",
                    variant.get("compare_at_price"),
                    "variants/compare_at_price",
                    _in(at, index, "compare_at_price"),
                )
        else:
            for name, (index, variant, _) in (("price_low", low), ("price_high", high)):
                said(
                    name,
                    variant.get("price"),
                    "variants/price",
                    _in(at, index, "price"),
                )
    stock = [variant.get("available") for _, variant in variants]
    if any(isinstance(one, bool) for one in stock):
        said(
            "availability",
            "InStock" if any(one is True for one in stock) else "OutOfStock",
            "variants/available",
            f"{at}/variants",
        )
    said("brand", product.get("vendor"), "vendor", f"{at}/vendor")
    if len(variants) == 1:
        index, variant = variants[0]
        said("sku", variant.get("sku"), "variants/sku", _in(at, index, "sku"))
    return {name: found[name] for name in FIELDS if name in found}


def _in(at: str, index: int, key: str) -> str:
    return f"{at}/variants/{index}/{key}"


def _amount(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return None
    return amount if amount.is_finite() else None


def _text(value: Any) -> str | None:
    if value is None or isinstance(value, (dict, list)):
        return None
    text = _as_text(value)
    return text.strip() if isinstance(text, str) and text.strip() else None


MOST_NESTING = 256
"""The deepest a products.json may nest its arrays and objects. How deep the
json module parses before RecursionError depends on the Python and the
platform -- 5,000 was a page on one and an error on another -- so the same
page gave two answers: past this, it is no products.json, on every Python."""


def _nested_past(text: str | bytes, most: int) -> bool:
    """Whether ``text``, as JSON, nests arrays and objects deeper than ``most``.

    One pass, strings skipped, so what a string holds never counts.
    """
    if isinstance(text, bytes):
        text = text.decode("utf-8", "replace")
    depth = 0
    in_string = escaped = False
    for character in text:
        if in_string:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == '"':
                in_string = False
        elif character == '"':
            in_string = True
        elif character in "[{":
            depth += 1
            if depth > most:
                return True
        elif character in "]}":
            depth -= 1
    return False


def _as_text(value: Any, depth: int = 0) -> JsonValue | None:
    """``value`` with every leaf as text, as a record's fields hold them, and
    every null left out, as a page's JSON-LD nulls are.

    What nests deeper than ``MAX_DEPTH`` is left out, as a page's JSON-LD is:
    no shop nests so far, and a product 5,000 lists deep raised
    ``RecursionError`` out of the crawl."""
    if depth > MAX_DEPTH:
        return None
    if isinstance(value, dict):
        kept = {str(key): _as_text(one, depth + 1) for key, one in value.items()}
        return {key: one for key, one in kept.items() if one is not None}
    if isinstance(value, list):
        items = (_as_text(one, depth + 1) for one in value)
        return [one for one in items if one is not None]
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return None
    return str(value)


def _escaped(name: str) -> str:
    """A key as a JSON pointer writes it (RFC 6901)."""
    return name.replace("~", "~0").replace("/", "~1")
