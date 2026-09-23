"""Find candidate pairs: fetch each candidate's snapshots and see what compiles.

Run once to choose the pairs committed in ``pairs.json``; the benchmark itself
only reads that file. Each candidate is a listing page and four dates: A and
A2, a week apart, to learn from; a short B a few weeks later, where the
template has usually not changed; a long B years later, across a redesign when
the site had one.
"""

from __future__ import annotations

import json
import sys

from wayback import snapshot

from sluicer.extractor import NothingToLearn, compile_extractor

CANDIDATES = [
    # url, A, A2, short B, long B
    ("https://books.toscrape.com/", "20200601", "20200615", "20200801", "20240601"),
    ("https://quotes.toscrape.com/", "20200601", "20200615", "20200801", "20240601"),
    ("https://news.ycombinator.com/", "20230110", "20230117", "20230215", "20250901"),
    (
        "https://news.ycombinator.com/newest",
        "20220110",
        "20220117",
        "20220215",
        "20250901",
    ),
    ("https://lobste.rs/", "20190110", "20190117", "20190215", "20250101"),
    ("https://github.com/trending", "20190110", "20190117", "20190215", "20250101"),
    (
        "https://stackoverflow.com/questions",
        "20190110",
        "20190117",
        "20190215",
        "20240601",
    ),
    (
        "https://old.reddit.com/r/programming/",
        "20190110",
        "20190117",
        "20190215",
        "20240601",
    ),
    (
        "https://sfbay.craigslist.org/search/sss",
        "20210110",
        "20210117",
        "20210215",
        "20240601",
    ),
    ("https://www.imdb.com/chart/top/", "20210110", "20210117", "20210215", "20240601"),
    ("https://www.python.org/jobs/", "20130110", "20130124", "20130301", "20240101"),
    (
        "https://arxiv.org/list/cs.CL/recent",
        "20220110",
        "20220117",
        "20220215",
        "20250101",
    ),
    ("https://slashdot.org/", "20120110", "20120117", "20120215", "20240101"),
    (
        "https://www.npr.org/sections/news/",
        "20180110",
        "20180117",
        "20180215",
        "20240601",
    ),
    (
        "https://weworkremotely.com/categories/remote-programming-jobs",
        "20190110",
        "20190117",
        "20190215",
        "20240601",
    ),
    ("https://metacpan.org/recent", "20190110", "20190117", "20190215", "20240601"),
    ("https://hackaday.com/blog/", "20160110", "20160117", "20160215", "20240601"),
    (
        "https://sourceforge.net/directory/",
        "20160110",
        "20160117",
        "20160215",
        "20240601",
    ),
    ("https://pinboard.in/popular/", "20190110", "20190117", "20190215", "20240601"),
    ("https://www.theverge.com/tech", "20210110", "20210117", "20210215", "20240601"),
    (
        "https://techcrunch.com/category/startups/",
        "20210110",
        "20210117",
        "20210215",
        "20240601",
    ),
    (
        "https://www.bbc.com/news/technology",
        "20210110",
        "20210117",
        "20210215",
        "20240601",
    ),
    (
        "https://arstechnica.com/gadgets/",
        "20210110",
        "20210117",
        "20210215",
        "20250301",
    ),
    ("https://www.producthunt.com/", "20190110", "20190117", "20190215", "20240601"),
    (
        "https://pypi.org/search/?q=scraping",
        "20210110",
        "20210117",
        "20210215",
        "20240601",
    ),
]


def main() -> None:
    wanted = set(sys.argv[1:])
    out = []
    for url, a, a2, short, long_ in CANDIDATES:
        if wanted and not any(w in url for w in wanted):
            continue
        shots, errors = {}, {}
        for name, when in (("A", a), ("A2", a2), ("B_short", short), ("B_long", long_)):
            try:
                shots[name] = snapshot(url, when)
            except RuntimeError as failure:
                # Not cached, so a rerun asks again; the pair is left out now.
                shots[name], errors[name] = None, str(failure)
        stamps = {k: (v.timestamp if v else None) for k, v in shots.items()}
        moved = {k: v.landed for k, v in shots.items() if v and _moved(url, v.landed)}
        learn = [s for s in (shots["A"], shots["A2"]) if s]
        learn = [
            s
            for n, s in enumerate(learn)
            if s.timestamp not in {x.timestamp for x in learn[:n]}
        ]
        verdict = "no A"
        listing = None
        if learn:
            try:
                ex = compile_extractor([(s.html, s.url) for s in learn], listing=True)
                listing = ex.listing
                verdict = "listing" if listing else "no listing"
            except NothingToLearn:
                verdict = "nothing"
        row = {
            "url": url,
            "stamps": stamps,
            "landed": moved,
            "verdict": verdict,
            "archive_errors": errors,
            "container": listing.container if listing else None,
            "member": listing.member if listing else None,
            "rows": listing.rows if listing else None,
            "fields": len(listing.fields) if listing else 0,
        }
        out.append(row)
        print(json.dumps(row), flush=True)


def _moved(url: str, landed: str) -> bool:
    """Whether the site redirected ``url`` somewhere else, not just to https."""

    def bare(address: str) -> str:
        return address.split("://", 1)[-1].removeprefix("www.").rstrip("/")

    return bare(url) != bare(landed)


if __name__ == "__main__":
    main()
