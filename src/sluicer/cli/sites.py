"""The "Whole sites" commands: ``map``, ``crawl``, ``batch``, ``feed`` and ``warc``.

``crawl`` and ``batch`` share their options and their report: each page is a
line of the output as its turn comes, stderr says what became of it, a line
each or one bar to a terminal, and the exit code is the whole run's, pages
resumed from ``--out`` included. The crawling itself, and its politeness, is
``sluicer.crawl``'s.
"""

from __future__ import annotations

import contextlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import click

from sluicer.cli.exits import COULD_NOT_READ, INTERRUPTED, NOTHING_FOUND, _fail
from sluicer.cli.options import _sent, _with_fetch_options, _with_proxy
from sluicer.cli.source import _read_source
from sluicer.crawl import Crawl, crawl as crawl_site, extract_many
from sluicer.crawl.pages import MAX_DEPTH, MAX_PAGES
from sluicer.crawl.schedule import (
    CONCURRENCY,
    DEFAULT_DELAY_SECONDS,
    MAX_CONCURRENCY,
    MAX_RETRIES,
    RETRIES,
)
from sluicer.crawl.sitemaps import MAX_SITEMAP_URLS, map_site
from sluicer.crawl.table import (
    PAGE_COLUMNS,
    SITE_URL_COLUMNS,
    page_row,
    site_url_row,
    write_csv,
)
from sluicer.crawl.templates import TEMPLATES, shopify_products, sitemap_pages
from sluicer.declared.microformats import MicroformatsExtraMissing
from sluicer.fetch import AddressRefused, FetchFailed, RobotsRefused
from sluicer.fetch.result import ResponseTooLarge
from sluicer.fetch.rungs import FetchExtraMissing


@click.command("map")
@click.argument("url")
@click.option(
    "--limit",
    type=click.IntRange(min=1),
    default=MAX_SITEMAP_URLS,
    show_default=True,
    help="The most addresses listed.",
)
@click.option(
    "--plain", is_flag=True, help="One address a line, for `sluicer batch -`."
)
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "csv"]),
    default="json",
    show_default=True,
    help="json: the map as one object; csv: a row per address (url, lastmod, sitemap).",
)
@click.option(
    "--time-budget",
    type=click.FloatRange(min=0),
    metavar="SECONDS",
    help="Ask for no further sitemap once this many seconds have passed; the "
    "map is then cut short. None by default.",
)
@_with_proxy
def map_command(
    url: str, limit: int, plain: bool, output_format: str, time_budget: float | None
) -> None:
    """List a site's addresses, from its sitemaps or its start page's links.

    Each sitemap is asked politely, through robots.txt and after the site's
    delay, and stderr says what became of each one.
    """
    if plain and output_format != "json":
        raise click.UsageError("--plain is one address a line; --format is another")
    try:
        found = map_site(url, limit=limit, time_budget=time_budget, **_sent())
    except (
        FetchExtraMissing,
        RobotsRefused,
        AddressRefused,
        FetchFailed,
        ResponseTooLarge,
    ) as failure:
        _fail(str(failure), failure)
    for read in found.sitemaps:
        said = read.error or f"{read.entries} entries ({read.kind})"
        click.echo(f"sitemap {read.url}: {said}", err=True)
    where = "its sitemaps" if found.source == "sitemaps" else "the start page's links"
    cut = ", cut short by a bound" if found.truncated else ""
    click.echo(f"Found {len(found.urls)} addresses in {where}{cut}.", err=True)
    if plain:
        for address in found.urls:
            click.echo(address.url)
    elif output_format == "csv":
        write = write_csv(sys.stdout, SITE_URL_COLUMNS)
        for address in found.urls:
            write(site_url_row(asdict(address)))
    else:
        click.echo(json.dumps(asdict(found), indent=2, ensure_ascii=False))
    if not found.urls:
        raise SystemExit(NOTHING_FOUND)


_many_options = [
    click.option(
        "-o",
        "--out",
        metavar="FILE",
        help="Write one JSON line per page here, not to stdout; the file is the "
        "state --resume continues from.",
    ),
    click.option(
        "--format",
        "output_format",
        type=click.Choice(["jsonl", "csv"]),
        default="jsonl",
        show_default=True,
        help="jsonl: a JSON line per page; csv: a row per page, its summary "
        "flattened into a column a question (docs/crawling.md says which).",
    ),
    click.option(
        "--resume",
        is_flag=True,
        help="Continue what --out already holds, fetching none of it again.",
    ),
    click.option(
        "--delay",
        type=click.FloatRange(min=0),
        default=DEFAULT_DELAY_SECONDS,
        show_default=True,
        help="The least seconds between two requests to one site; its "
        "robots.txt Crawl-delay wins when longer.",
    ),
    click.option(
        "--retries",
        type=click.IntRange(min=0, max=MAX_RETRIES),
        default=RETRIES,
        show_default=True,
        help="Ask a page again this many times when it did not answer, or "
        "answered 429 or a 5xx, each time twice as late; never another 4xx.",
    ),
    click.option(
        "--jobs",
        type=click.IntRange(min=1, max=MAX_CONCURRENCY),
        default=CONCURRENCY,
        show_default=True,
        help="How many sites are asked at once, each still one request at a time.",
    ),
    click.option(
        "--induce",
        is_flag=True,
        help="Also read the rows a page repeats when it declares nothing about them.",
    ),
    click.option(
        "--respect",
        type=click.Choice(["tdm"]),
        multiple=True,
        help="Give a page whose rights are reserved as an error, not its data: "
        "tdm reads TDMRep's tdmrep.json, headers and meta tags.",
    ),
]


def _with_many_options(command: click.decorators.FC) -> click.decorators.FC:
    for option in reversed(_many_options):
        command = option(command)
    return command


@click.command("crawl")
@click.argument("url")
@click.option(
    "--max-pages",
    type=click.IntRange(min=1),
    default=MAX_PAGES,
    show_default=True,
    help="The most addresses taken, whatever becomes of them.",
)
@click.option(
    "--max-depth",
    type=click.IntRange(min=0),
    default=MAX_DEPTH,
    show_default=True,
    help="The most links from URL; 0 reads URL alone.",
)
@click.option(
    "--include",
    multiple=True,
    metavar="REGEX",
    help="Follow only links whose address this is found in; repeatable.",
)
@click.option(
    "--exclude",
    multiple=True,
    metavar="REGEX",
    help="Do not follow links whose address this is found in; repeatable.",
)
@click.option(
    "--any-site", is_flag=True, help="Follow links that leave URL's site too."
)
@click.option(
    "--template",
    type=click.Choice(TEMPLATES),
    help="A ready crawl: sitemap reads the pages URL's sitemaps list; shopify "
    "reads a Shopify shop's /products.json, a line per product.",
)
@_with_many_options
@_with_proxy
def crawl_command(
    url: str,
    max_pages: int,
    max_depth: int,
    include: tuple[str, ...],
    exclude: tuple[str, ...],
    any_site: bool,
    template: str | None,
    out: str | None,
    output_format: str,
    resume: bool,
    delay: float,
    retries: int,
    jobs: int,
    induce: bool,
    respect: tuple[str, ...],
) -> None:
    """Crawl a site from URL, politely, one JSON line per page.

    Breadth first, on URL's site unless --any-site, every page through
    robots.txt and one request at a time with the site's delay between. Run
    twice, it takes the same pages in the same order. --template sitemap
    reads the pages the site's sitemaps list instead, --include and
    --exclude choosing among them; --template shopify reads a Shopify shop's
    products from its /products.json, --max-pages of them at 250 a page.
    """
    table = output_format == "csv"
    if template is not None:
        _refuse_unused(template, include=include, induce=induce, respect=respect)
    _check_out(out, resume, table)
    state = None if table else out
    total: int | None = max_pages
    label = "Crawling"
    try:
        if template == "shopify":
            total, label = None, "Reading products"
            pages = shopify_products(
                url,
                max_pages,
                state=state,
                min_delay=delay,
                retries=retries,
                **_sent(),
            )
        elif template == "sitemap":
            label = "Reading"
            pages = sitemap_pages(
                url,
                max_pages,
                include=include,
                exclude=exclude,
                state=state,
                induce=induce,
                respect_tdm="tdm" in respect,
                min_delay=delay,
                retries=retries,
                concurrency=jobs,
                **_sent(),
            )
        else:
            pages = crawl_site(
                url,
                max_pages,
                max_depth,
                same_site=not any_site,
                include=include,
                exclude=exclude,
                state=state,
                induce=induce,
                respect_tdm="tdm" in respect,
                min_delay=delay,
                retries=retries,
                concurrency=jobs,
                **_sent(),
            )
    except (
        FetchExtraMissing,
        ValueError,
        RobotsRefused,
        AddressRefused,
        FetchFailed,
        ResponseTooLarge,
    ) as failure:
        _fail(str(failure), failure)
    _report(pages, out, table, total=total, label=label)


def _refuse_unused(template: str, **given: tuple[str, ...] | bool) -> None:
    """Refuse, before anything is asked, an option ``template`` would not use:
    ignored, it would read as obeyed."""
    context = click.get_current_context()
    unused = {
        "max_depth": "--max-depth",
        "any_site": "--any-site",
    }
    if template == "shopify":
        unused |= {
            "include": "--include",
            "exclude": "--exclude",
            "induce": "--induce",
            "respect": "--respect",
        }
    for name, option in unused.items():
        source = context.get_parameter_source(name)
        if source is not None and source.name not in ("DEFAULT", "DEFAULT_MAP"):
            raise click.UsageError(
                f"{option} does not apply to --template {template}: "
                + (
                    "a sitemap lists the pages, no link is followed"
                    if name in ("max_depth", "any_site")
                    else "a shop's products are read from its products.json, "
                    "not from pages"
                )
            )


@click.command("feed")
@click.argument("source")
@_with_fetch_options
def feed_command(
    source: str,
    stealth: bool,
    no_robots: bool,
    base_url: str | None,
    respect: tuple[str, ...],
    cache_dir: str | None,
    max_age: float | None,
    at: str | None,
) -> None:
    """Read a feed's items: RSS, Atom or JSON Feed, from a URL, a file or stdin.

    A page that is not a feed but declares one, with <link rel=alternate>, is
    followed to it. Prints the feed as JSON: what it says about itself and
    every item, dates also normalised. Exits 1 for a feed with no item, 2 for
    what is not a feed.
    """
    from sluicer.declared.links import read_links
    from sluicer.document import load
    from sluicer.feeds import read_feed

    html, url, fetched = _read_source(
        source, stealth, no_robots, base_url, at, respect, cache_dir, max_age
    )
    feed = read_feed(html, url=url)
    if feed is None:
        declared = read_links(load(html, url=url)).get("feeds", [])
        if not declared:
            _fail(f"{url or source} is not RSS, Atom or JSON Feed, and declares none.")
        followed = declared[0]["href"]
        click.echo(f"Reading the feed the page declares: {followed}", err=True)
        html, url, fetched = _read_source(
            followed, stealth, no_robots, None, at, respect, cache_dir, max_age
        )
        feed = read_feed(html, url=url)
        if feed is None:
            _fail(f"{followed}, which the page declares as a feed, is not one.")
    payload = {"url": url, **asdict(feed)}
    if fetched is not None:
        payload["fetch"] = {"rung": fetched.rung, "status": fetched.status}
    click.echo(json.dumps(payload, indent=2, ensure_ascii=False))
    if not feed.items:
        raise SystemExit(NOTHING_FOUND)


@click.command("warc")
@click.argument("files", nargs=-1, required=True)
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
def warc_command(files: tuple[str, ...], induce: bool, microformats: bool) -> None:
    """Read every page the WARC FILES hold, one JSON line per page.

    Plain or gzipped, as web archives and Common Crawl write them; - reads
    stdin. Each line is extract's answer, read with the headers the page was
    served with, and a "warc" object naming the file and the record. Nothing
    is fetched. Records that are not pages are passed over, and those left
    out -- revisits, non-HTML bodies, error answers -- are counted at the end.
    """
    from sluicer.warc import Skipped, WarcError, extract_warc

    read = 0
    for name in files:
        skipped = Skipped()
        count = 0
        try:
            for page, extraction in extract_warc(
                name, induce=induce, microformats=microformats, skipped=skipped
            ):
                count += 1
                payload = asdict(extraction)
                record = {
                    "file": "-" if name == "-" else name,
                    "record_id": page.record_id,
                    "date": page.date,
                    "digest": page.digest,
                    "status": page.status,
                }
                if page.truncated:
                    record["truncated"] = page.truncated
                click.echo(
                    json.dumps(
                        {"url": payload.pop("url"), "warc": record, **payload},
                        ensure_ascii=False,
                    )
                )
        except MicroformatsExtraMissing as missing:
            _fail(str(missing), missing)
        except (OSError, WarcError) as failure:
            _fail(f"{failure}; {count} pages were read before it.", failure)
        read += count
        said = f"; skipped {skipped}" if skipped else ""
        click.echo(f"{name}: {count} pages{said}.", err=True)
    if not read:
        raise SystemExit(NOTHING_FOUND)


@click.command("batch")
@click.argument("urls_file")
@_with_many_options
@_with_proxy
def batch_command(
    urls_file: str,
    out: str | None,
    output_format: str,
    resume: bool,
    delay: float,
    retries: int,
    jobs: int,
    induce: bool,
    respect: tuple[str, ...],
) -> None:
    """Read every address in URLS_FILE, politely, one JSON line per page.

    One address a line, blank lines and # comments skipped; - reads stdin,
    so `sluicer map URL --plain | sluicer batch -` reads a site's sitemap.
    No link is followed. Several sites are asked at once, each one request at
    a time, and the pages come out in the order the file lists them.
    """
    table = output_format == "csv"
    _check_out(out, resume, table)
    try:
        text = (
            sys.stdin.read()
            if urls_file == "-"
            else Path(urls_file).read_text(encoding="utf-8")
        )
    except (OSError, UnicodeDecodeError) as failure:
        _fail(f"Could not read {urls_file}: {failure}", failure)
    listed = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not listed:
        _fail(f"{urls_file} lists no address.")
    try:
        pages = extract_many(
            listed,
            state=None if table else out,
            induce=induce,
            respect_tdm="tdm" in respect,
            min_delay=delay,
            retries=retries,
            concurrency=jobs,
            **_sent(),
        )
    except (FetchExtraMissing, ValueError) as failure:
        _fail(str(failure), failure)
    _report(pages, out, table, total=len(listed), label="Reading")


def _check_out(out: str | None, resume: bool, table: bool = False) -> None:
    """Refuse to append to a file that holds pages unless asked to continue it.

    A crawl's file is hours of other people's servers' time; writing a second
    crawl onto its end would make both unusable. A table is not a state: it
    holds no page's links, so there is nothing to continue from.
    """
    if resume and out is None:
        _fail("--resume needs --out: the file is what the crawl continues from.")
    if resume and table:
        _fail(
            "--resume reads JSON Lines: a table holds no page's links to "
            "continue from. Write --format jsonl, and turn it into a table after."
        )
    if out is not None and not resume:
        path = Path(out)
        if path.is_file() and path.stat().st_size > 0:
            _fail(
                f"{out} already holds pages. Pass --resume to continue that "
                "crawl, or name another file."
            )


def _stderr_is_a_terminal() -> bool:
    """Whether a person is watching stderr, who is shown a bar, not a log."""
    try:
        return sys.stderr.isatty()
    except (AttributeError, ValueError):
        return False


def _report(
    pages: Crawl,
    out: str | None,
    table: bool = False,
    total: int | None = None,
    label: str = "Crawling",
) -> None:
    """Write each page as its turn comes, say how it went, and exit by it.

    Each page is a JSON line, or with ``table`` a row of ``PAGE_COLUMNS``, on
    stdout or in ``out``. stderr says what became of each page, a line each,
    or, to a terminal, on one bar of ``total`` pages. The verdict is the whole
    crawl's, pages resumed from the file included, so a crawl finished in two
    runs exits as it would have in one.
    """
    if pages.resumed:
        click.echo(f"Resuming after the {pages.resumed} pages {out} holds.", err=True)
    tally = _Tally()
    count = pages.resumed
    watched = _stderr_is_a_terminal()
    try:
        with contextlib.ExitStack() as held:
            write = None
            if table:
                sink = (
                    held.enter_context(
                        Path(out).open("w", encoding="utf-8", newline="")
                    )
                    if out is not None
                    else sys.stdout
                )
                write = write_csv(sink, PAGE_COLUMNS)
            bar = (
                held.enter_context(
                    click.progressbar(
                        length=max(total or 0, count, 1),
                        label=label,
                        file=sys.stderr,
                        show_pos=True,
                        item_show_func=lambda said: said,
                    )
                )
                if watched
                else None
            )
            if bar is not None and count:
                bar.update(count)
            for page in pages:
                count += 1
                line = page.to_json()
                if write is not None:
                    write(page_row(line))
                    tally.add(line)
                elif out is None:
                    click.echo(json.dumps(line, ensure_ascii=False))
                    tally.add(line)
                said = page.error.code if page.error else f"{page.status} {page.rung}"
                if page.retries:
                    said += f", asked {len(page.retries) + 1} times"
                if bar is not None:
                    if bar.length is not None and count > bar.length:
                        bar.length = count
                    bar.update(1, f"{said}  {page.url}")
                else:
                    click.echo(f"{count:>5}  {said}  {page.url}", err=True)
            if bar is not None:
                # A crawl that ran out of links ends short of its budget: the
                # bar ends full at what it took.
                bar.length = bar.pos = max(count, 1)
                bar.render_progress()
    except KeyboardInterrupt:
        kept = ""
        if out is not None:
            kept = f"; {out} holds them" + ("" if table else ", and --resume continues")
        click.echo(f"Stopped after {count} pages{kept}.", err=True)
        raise SystemExit(INTERRUPTED) from None
    except FetchExtraMissing as missing:
        _fail(str(missing), missing)
    except OSError as failure:
        _fail(f"Could not write {out}: {failure.strerror or failure}", failure)
    if out is not None and not table:
        with Path(out).open(encoding="utf-8") as written:
            for raw in written:
                if raw.strip():
                    tally.add(json.loads(raw))
    why = {
        "max_pages": "; the page budget left links unfollowed",
        "time_budget": "; the time ran out",
    }.get(pages.stopped or "", "")
    click.echo(f"{tally}{why}." + (f" Wrote {out}." if out else ""), err=True)
    if not tally.read:
        raise SystemExit(COULD_NOT_READ)
    if not tally.found:
        raise SystemExit(NOTHING_FOUND)


class _Tally:
    """What a run of pages came to, counted one line at a time."""

    def __init__(self) -> None:
        self.pages = self.read = self.found = 0
        self.failed: dict[str, int] = {}

    def add(self, line: dict[str, object]) -> None:
        self.pages += 1
        error = line.get("error")
        if isinstance(error, dict):
            code = str(error.get("code"))
            self.failed[code] = self.failed.get(code, 0) + 1
            return
        self.read += 1
        self.found += bool(line.get("records") or line.get("summary"))

    def __str__(self) -> str:
        said = f"{self.pages} pages: {self.read} read"
        if self.failed:
            codes = ", ".join(f"{n} {code}" for code, n in sorted(self.failed.items()))
            said += f", {self.pages - self.read} failed ({codes})"
        return said
