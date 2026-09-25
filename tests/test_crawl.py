"""A polite crawl: in order, bounded, on its site, paced, and resumable."""

import json
import threading
import time

import pytest

from fake_site import FakeWeb, page
from sluicer.crawl import StateMismatch, crawl, extract_many
from sluicer.crawl.web import Web
from sluicer.fetch import RedirectRefused
from sluicer.fetch.result import Fetched

ROOT = "https://example.com"


def shop():
    """A small shop: a home page, two categories, products, and a loop."""
    return {
        f"{ROOT}/": page("Home", "/c/1", "/c/2", "/about", "https://other.example/"),
        f"{ROOT}/c/1": page("Cat 1", "/p/1", "/p/2", "/"),
        f"{ROOT}/c/2": page("Cat 2", "/p/3", "/p/1", "/c/1"),
        f"{ROOT}/about": page("About", "/"),
        f"{ROOT}/p/1": page("Pad 1", "/c/1"),
        f"{ROOT}/p/2": page("Pad 2", "/c/1"),
        f"{ROOT}/p/3": page("Pad 3", "/c/2"),
        "https://other.example/": page("Elsewhere"),
    }


def run(fake, start=f"{ROOT}/", **options):
    options.setdefault("min_delay", 1.0)
    options.setdefault("concurrency", 1)
    return crawl(
        start, web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep, **options
    )


def urls(pages):
    return [p.url for p in pages]


def test_a_crawl_goes_breadth_first_and_keeps_to_its_site():
    fake = FakeWeb(shop())

    pages = list(run(fake))

    assert urls(pages) == [
        f"{ROOT}/",
        f"{ROOT}/c/1",
        f"{ROOT}/c/2",
        f"{ROOT}/about",
        f"{ROOT}/p/1",
        f"{ROOT}/p/2",
        f"{ROOT}/p/3",
    ]
    assert [p.depth for p in pages] == [0, 1, 1, 1, 2, 2, 2]
    assert pages[4].found_on == f"{ROOT}/c/1"
    assert all(p.ok and p.found for p in pages)
    assert "https://other.example/" not in fake.asked()
    assert pages[0].extraction.summary["title"].value == "Home"


def test_the_same_site_crawled_twice_gives_the_same_pages_in_the_same_order():
    first = [p.to_json() for p in run(FakeWeb(shop()))]
    second = [p.to_json() for p in run(FakeWeb(shop()), concurrency=4)]

    assert first == second


def test_every_page_is_asked_once_a_loop_included():
    fake = FakeWeb(shop())

    list(run(fake))

    pages = [url for url in fake.asked() if not url.endswith("robots.txt")]
    assert len(pages) == len(set(pages)) == 7


def test_requests_to_a_site_are_spaced_by_its_delay_from_the_end_of_the_last():
    fake = FakeWeb(shop(), cost=0.4)

    list(run(fake, min_delay=1.5))

    assert fake.asked()[0] == f"{ROOT}/robots.txt"
    assert fake.gaps("example.com") == [1.5] * 7


def test_a_crawl_delay_longer_than_ours_is_honoured():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = "User-agent: *\nCrawl-delay: 4\n"
    fake = FakeWeb(pages)

    list(run(fake, max_pages=3))

    assert fake.gaps("example.com") == [4.0, 4.0, 4.0]


def test_a_site_saying_too_many_is_asked_again_only_after_its_retry_after():
    pages = shop()
    pages[f"{ROOT}/c/1"] = (429, page("Slow down"), {"Retry-After": "30"})
    fake = FakeWeb(pages)

    result = list(run(fake, max_pages=4))

    assert [p.status for p in result][:2] == [200, 429]
    assert fake.gaps("example.com")[:3] == [1.0, 1.0, 30.0]


def test_a_retry_after_date_is_counted_from_the_response_s_own_date():
    pages = shop()
    pages[f"{ROOT}/c/1"] = (
        503,
        page("Maintenance"),
        {
            "Date": "Wed, 23 Sep 2026 10:00:00 GMT",
            "Retry-After": "Wed, 23 Sep 2026 10:00:20 GMT",
        },
    )
    fake = FakeWeb(pages)

    list(run(fake, max_pages=4))

    assert fake.gaps("example.com")[:3] == [1.0, 1.0, 20.0]


def test_a_site_saying_too_many_without_a_retry_after_is_asked_half_as_often():
    pages = shop()
    pages[f"{ROOT}/c/1"] = (429, page("Slow down"), {})
    fake = FakeWeb(pages)

    result = list(run(fake, max_pages=5))

    # Each 429 doubles the delay, the two retries' included: 2, 4, then 8 s
    # for every page after.
    assert len(result[1].retries) == 2
    assert fake.gaps("example.com") == [1.0, 1.0, 2.0, 4.0, 8.0, 8.0, 8.0]


def test_a_retry_after_longer_than_the_crawl_waits_is_an_answer():
    pages = shop()
    pages[f"{ROOT}/c/1"] = (429, page("Slow down"), {"Retry-After": "3600"})
    fake = FakeWeb(pages)

    result = list(run(fake, max_pages=4, max_delay=60))

    assert [p.error.code if p.error else p.status for p in result] == [
        200,
        429,
        "rate_limited",
        "rate_limited",
    ]
    assert result[2].error.retryable
    assert "3600" in result[2].error.message or "3599" in result[2].error.message
    assert len([u for u in fake.asked() if not u.endswith("robots.txt")]) == 2


def test_a_delay_longer_than_the_crawl_waits_is_an_answer_not_a_week():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = "User-agent: *\nCrawl-delay: 86400\n"
    fake = FakeWeb(pages)

    result = list(run(fake, max_delay=60))

    assert [p.error.code for p in result] == ["crawl_delay_too_long"]
    assert "86400 s" in result[0].error.message
    assert fake.asked() == [f"{ROOT}/robots.txt"]


def test_a_page_robots_disallows_is_answered_and_never_asked():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = "User-agent: *\nDisallow: /p/\n"
    fake = FakeWeb(pages)

    result = {p.url: p for p in run(fake)}

    assert result[f"{ROOT}/p/1"].error.code == "refused_by_robots"
    assert not any("/p/" in url for url in fake.asked())
    assert result[f"{ROOT}/c/1"].ok


def test_a_robots_file_nobody_can_read_is_a_failure_worth_retrying():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = (503, "busy", {})
    fake = FakeWeb(pages)

    result = list(run(fake))

    assert result[0].error.code == "fetch_failed"
    assert result[0].error.retryable is True
    assert f"{ROOT}/" not in fake.asked()


def test_the_page_budget_is_a_bound_and_says_it_cut():
    crawled = run(FakeWeb(shop()), max_pages=3)

    assert urls(crawled) == [f"{ROOT}/", f"{ROOT}/c/1", f"{ROOT}/c/2"]
    assert crawled.stopped == "max_pages"


def test_a_crawl_that_ran_out_of_links_says_it_is_done():
    crawled = run(FakeWeb(shop()))
    list(crawled)

    assert crawled.stopped == "done"


def test_depth_zero_takes_the_start_alone():
    assert urls(run(FakeWeb(shop()), max_depth=0)) == [f"{ROOT}/"]
    assert len(list(run(FakeWeb(shop()), max_depth=1))) == 4


def test_leaving_the_site_is_allowed_when_asked_for():
    pages = list(run(FakeWeb(shop()), same_site=False, max_depth=1))

    assert "https://other.example/" in urls(pages)


def test_include_and_exclude_choose_which_links_are_followed():
    only_products = run(FakeWeb(shop()), include=[r"/p/", r"/c/1$"])
    no_categories = run(FakeWeb(shop()), exclude=[r"/c/"])

    assert urls(only_products) == [
        f"{ROOT}/",
        f"{ROOT}/c/1",
        f"{ROOT}/p/1",
        f"{ROOT}/p/2",
    ]
    assert urls(no_categories) == [f"{ROOT}/", f"{ROOT}/about"]


def test_a_pattern_that_is_not_one_says_so():
    with pytest.raises(ValueError, match="not a regular expression"):
        run(FakeWeb(shop()), include=["(unclosed"])


def test_a_start_that_is_not_an_address_says_so():
    with pytest.raises(ValueError, match="not an http"):
        run(FakeWeb({}), start="mailto:x@example.com")


def test_a_link_to_a_file_is_not_fetched():
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/manual.pdf", "/photo.JPG", "/next"),
            f"{ROOT}/next": page("Next"),
        }
    )

    assert urls(run(fake)) == [f"{ROOT}/", f"{ROOT}/next"]


def test_where_a_redirect_landed_is_not_fetched_again():
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/old"),
            f"{ROOT}/old": (301, "", {"Location": "/new"}),
            f"{ROOT}/new": page("New", "/new", "/old"),
        }
    )

    pages = list(run(fake))

    assert urls(pages) == [f"{ROOT}/", f"{ROOT}/old"]
    assert pages[1].landed == f"{ROOT}/new"
    assert fake.asked().count(f"{ROOT}/new") == 1


def test_a_canonical_on_the_site_is_marked_seen_and_one_elsewhere_is_not():
    canon = f'<link rel="canonical" href="{ROOT}/the-product">'
    away = '<link rel="canonical" href="https://mirror.example/p">'
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/p?ref=home", "/b"),
            f"{ROOT}/p?ref=home": page("P", "/the-product", extra=canon),
            f"{ROOT}/b": page("B", "https://mirror.example/p", extra=away),
            "https://mirror.example/p": page("Mirror"),
        }
    )

    pages = list(run(fake, same_site=False))

    assert urls(pages) == [
        f"{ROOT}/",
        f"{ROOT}/p?ref=home",
        f"{ROOT}/b",
        "https://mirror.example/p",
    ]
    assert pages[1].canonical == f"{ROOT}/the-product"
    assert f"{ROOT}/the-product" not in fake.asked()


def test_a_page_that_says_nofollow_ends_the_walk_there():
    fake = FakeWeb(
        {
            f"{ROOT}/": page(
                "Home", "/a", extra='<meta name="robots" content="nofollow">'
            ),
            f"{ROOT}/a": page("A"),
        }
    )

    assert urls(run(fake)) == [f"{ROOT}/"]


def test_a_redirect_off_the_site_is_answered_and_its_page_not_kept():
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/away"),
            f"{ROOT}/away": (302, "", {"Location": "https://other.example/landing"}),
            "https://other.example/landing": page("Landing", "/deeper"),
        }
    )

    pages = list(run(fake))

    assert pages[1].error.code == "redirected_off_site"
    assert pages[1].error.target == "https://other.example/landing"
    assert "other.example/deeper" not in " ".join(fake.asked())


def test_a_redirect_the_rung_refused_is_followed_as_a_link_when_sites_may_change():
    def refusing(url):
        if url == f"{ROOT}/away":
            raise RedirectRefused(url, "https://other.example/", "it leads off")
        return fake.rung(url)

    fake = FakeWeb({**shop(), f"{ROOT}/": page("Home", "/away")})
    web = Web(rungs=[("http", refusing)], read=fake.web().read, get=fake.get)

    kept = list(crawl(f"{ROOT}/", web=web, clock=fake.clock, sleep=fake.clock.sleep))
    left = list(
        crawl(
            f"{ROOT}/",
            same_site=False,
            max_depth=1,
            web=web,
            clock=fake.clock,
            sleep=fake.clock.sleep,
        )
    )

    assert kept[1].error.code == "redirected_off_site"
    assert "https://other.example/" not in urls(kept)
    assert urls(left)[-1] == "https://other.example/"
    assert left[-1].depth == 1 and left[-1].found_on == f"{ROOT}/away"


def test_a_failed_page_is_an_answer_and_the_crawl_goes_on():
    pages = shop()
    pages[f"{ROOT}/c/1"] = ConnectionError("connection reset")
    fake = FakeWeb(pages)

    result = list(run(fake))

    failed = [p for p in result if not p.ok]
    assert [p.url for p in failed] == [f"{ROOT}/c/1"]
    assert failed[0].error.code == "fetch_failed" and failed[0].error.retryable
    assert f"{ROOT}/p/3" in urls(result)


def test_the_time_budget_stops_the_crawl_and_says_so():
    crawled = run(FakeWeb(shop()), time_budget=2.0)
    taken = list(crawled)

    assert crawled.stopped == "time_budget"
    assert 1 <= len(taken) < 7
    assert urls(taken) == urls(run(FakeWeb(shop())))[: len(taken)]


def test_a_page_as_a_line_says_what_it_is_and_where_it_came_from():
    pages = list(run(FakeWeb(shop()), max_pages=2))

    line = pages[1].to_json()

    assert line["url"] == f"{ROOT}/c/1" and line["ok"] is True
    assert line["depth"] == 1 and line["found_on"] == f"{ROOT}/"
    assert line["landed"] == f"{ROOT}/c/1"
    assert line["fetch"]["rung"] == "http" and line["fetch"]["status"] == 200
    assert line["records"][0]["fields"]["name"]["value"] == "Cat 1"
    assert line["sources"] == ["jsonld"]
    assert line["links"] == [f"{ROOT}/p/1", f"{ROOT}/p/2", f"{ROOT}/"]
    json.dumps(line)


def test_a_failed_page_as_a_line_carries_its_error_and_nothing_else():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = "User-agent: *\nDisallow: /\n"

    line = next(iter(run(FakeWeb(pages)))).to_json()

    assert line == {
        "url": f"{ROOT}/",
        "ok": False,
        "depth": 0,
        "found_on": None,
        "error": {
            "code": "refused_by_robots",
            "message": f"{ROOT}/ is refused: its robots.txt disallows it",
            "retryable": False,
        },
    }


# -- resuming ------------------------------------------------------------------


def test_a_stopped_crawl_resumes_without_asking_again_and_ends_the_same(tmp_path):
    whole = tmp_path / "whole.jsonl"
    list(run(FakeWeb(shop()), state=whole))

    part = tmp_path / "part.jsonl"
    first = FakeWeb(shop())
    stopped = iter(run(first, state=part))
    for _ in range(3):
        next(stopped)
    stopped.close()
    second = FakeWeb(shop())
    resumed = run(second, state=part)
    rest = list(resumed)

    assert resumed.resumed == 3
    assert len(rest) == 4
    fetched_twice = set(first.asked()) & set(second.asked()) - {f"{ROOT}/robots.txt"}
    assert fetched_twice == set()
    assert _without_seconds(part) == _without_seconds(whole)


def test_a_finished_crawl_resumed_has_nothing_left_to_take(tmp_path):
    state = tmp_path / "crawl.jsonl"
    list(run(FakeWeb(shop()), state=state))
    fake = FakeWeb(shop())

    again = run(fake, state=state)

    assert list(again) == []
    assert again.stopped == "done"
    assert fake.requests == []


def test_a_bigger_budget_resumed_continues_where_the_smaller_stopped(tmp_path):
    state = tmp_path / "crawl.jsonl"
    list(run(FakeWeb(shop()), state=state, max_pages=3))

    more = list(run(FakeWeb(shop()), state=state, max_pages=5))

    assert urls(more) == [f"{ROOT}/about", f"{ROOT}/p/1"]


def test_a_line_cut_off_by_a_stop_mid_write_is_dropped_and_redone(tmp_path):
    state = tmp_path / "crawl.jsonl"
    list(run(FakeWeb(shop()), state=state, max_pages=2))
    with state.open("a", encoding="utf-8") as out:
        out.write('{"url": "https://example.com/c/2", "ok": tr')

    rest = list(run(FakeWeb(shop()), state=state))

    assert urls(rest)[0] == f"{ROOT}/c/2"
    assert all(
        json.loads(line) for line in state.read_text(encoding="utf-8").splitlines()
    )


def test_a_file_from_another_crawl_is_refused_not_mixed(tmp_path):
    state = tmp_path / "crawl.jsonl"
    list(run(FakeWeb(shop()), state=state, max_pages=2))

    with pytest.raises(StateMismatch, match="line 1"):
        run(FakeWeb(shop()), start=f"{ROOT}/about", state=state)
    with pytest.raises(StateMismatch, match="line 2"):
        run(FakeWeb(shop()), state=state, exclude=["/c/1"])


def test_a_file_that_is_not_a_crawls_output_is_refused(tmp_path):
    state = tmp_path / "notes.jsonl"
    state.write_text("these are my notes\n", encoding="utf-8")

    with pytest.raises(StateMismatch, match="not a page's JSON"):
        run(FakeWeb(shop()), state=state)


@pytest.mark.parametrize(
    "written",
    [
        "these are my notes\nand the last line has no newline",
        '{"url": "https://example.com/", "ok": true}\nsomething else entirely',
        "no newline at all",
    ],
)
def test_a_file_that_is_not_a_crawls_output_is_left_as_it_was(tmp_path, written):
    """--resume cut the last line off before it read the file: pointed at
    someone's notes, it destroyed their last line, then refused them."""
    state = tmp_path / "notes.txt"
    state.write_text(written, encoding="utf-8")

    with pytest.raises(StateMismatch):
        run(FakeWeb(shop()), state=state)
    with pytest.raises(StateMismatch):
        extract_many([f"{ROOT}/"], state=state)

    assert state.read_text(encoding="utf-8") == written


def test_another_crawls_file_is_refused_before_its_last_line_is_cut(tmp_path):
    state = tmp_path / "crawl.jsonl"
    list(run(FakeWeb(shop()), state=state, max_pages=2))
    with state.open("a", encoding="utf-8") as out:
        out.write('{"url": "https://example.com/c/2", "ok": tr')
    written = state.read_bytes()

    with pytest.raises(StateMismatch, match="line 1"):
        run(FakeWeb(shop()), start=f"{ROOT}/about", state=state)

    assert state.read_bytes() == written


def _without_seconds(path):
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    for line in lines:
        if "fetch" in line:
            line["fetch"]["seconds"] = 0
    return lines


# -- many sites at once ---------------------------------------------------------


class Slow:
    """A web whose every request takes real time, counting how many are in
    flight per site, so "one at a time per site" is measured, not assumed."""

    def __init__(self, seconds=0.03):
        self.seconds = seconds
        self.lock = threading.Lock()
        self.in_flight: dict[str, int] = {}
        self.most: dict[str, int] = {}
        self.most_at_once = 0

    def rung(self, url):
        from sluicer.crawl.urls import site_of

        site = site_of(url)
        with self.lock:
            self.in_flight[site] = self.in_flight.get(site, 0) + 1
            self.most[site] = max(self.most.get(site, 0), self.in_flight[site])
            self.most_at_once = max(self.most_at_once, sum(self.in_flight.values()))
        time.sleep(self.seconds)
        with self.lock:
            self.in_flight[site] -= 1
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="", status=404, rung="http")
        return Fetched(url=url, html=page(url), status=200, rung="http")

    def web(self):
        from sluicer.fetch import robots_reader_from

        return Web(
            rungs=[("http", self.rung)], read=robots_reader_from(self.rung), get=None
        )


def test_many_sites_are_asked_at_once_and_each_one_at_a_time():
    slow = Slow()
    listed = [f"https://site{n}.example/p{k}" for k in range(3) for n in range(4)]

    pages = list(extract_many(listed, web=slow.web(), min_delay=0.01, concurrency=4))

    assert [p.url for p in pages] == listed
    assert all(p.ok for p in pages)
    assert max(slow.most.values()) == 1
    assert slow.most_at_once > 1


def test_a_batch_keeps_its_order_reads_each_address_once_and_answers_bad_ones():
    fake = FakeWeb(shop())

    pages = list(
        extract_many(
            [f"{ROOT}/p/2", "not an address", f"{ROOT}/p/1", f"{ROOT}/p/2#again"],
            web=fake.web(),
            clock=fake.clock,
            sleep=fake.clock.sleep,
            concurrency=1,
        )
    )

    assert urls(pages) == [f"{ROOT}/p/2", "not an address", f"{ROOT}/p/1"]
    assert pages[1].error.code == "bad_input"
    assert pages[2].links == (f"{ROOT}/c/1",)
    assert fake.gaps("example.com") == [1.0, 1.0]


def paced(fake, **options):
    """Options that pace a crawl or a batch by ``fake``'s clock, its web left to
    ``as_default`` so the redirect rule is wired as in production."""
    return {"clock": fake.clock, "sleep": fake.clock.sleep, **options}


def test_a_batch_reads_a_redirect_to_another_site_in_that_sites_own_turn(
    monkeypatch,
):
    fake = FakeWeb(
        {
            f"{ROOT}/moved": (301, "", {"Location": "https://other.example/"}),
            f"{ROOT}/p/1": page("Pad 1"),
            "https://other.example/": page("Elsewhere"),
        }
    )
    fake.as_default(monkeypatch)

    pages = list(
        extract_many([f"{ROOT}/moved", f"{ROOT}/p/1"], concurrency=1, **paced(fake))
    )

    assert urls(pages) == [f"{ROOT}/moved", f"{ROOT}/p/1", "https://other.example/"]
    assert pages[0].error.code == "redirected_off_site"
    assert pages[0].error.target == "https://other.example/"
    assert pages[2].ok and pages[2].found_on == f"{ROOT}/moved"
    # Its own turn begins with its own robots.txt; followed inside /moved's
    # fetch, the page would have come first and the robots.txt after.
    asked = fake.asked()
    assert asked.index("https://other.example/robots.txt") < asked.index(
        "https://other.example/"
    )
    assert asked.index(f"{ROOT}/moved") + 1 == asked.index(
        "https://other.example/robots.txt"
    )


def test_every_hop_of_a_redirect_waits_the_sites_delay(monkeypatch):
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/old"),
            f"{ROOT}/old": (301, "", {"Location": "/mid"}),
            f"{ROOT}/mid": (302, "", {"Location": "/new"}),
            f"{ROOT}/new": page("New"),
            f"{ROOT}/robots.txt": "User-agent: *\nCrawl-delay: 2\n",
        }
    )
    fake.as_default(monkeypatch)

    pages = list(crawl(f"{ROOT}/", **paced(fake)))

    assert pages[1].landed == f"{ROOT}/new"
    assert fake.asked()[-3:] == [f"{ROOT}/old", f"{ROOT}/mid", f"{ROOT}/new"]
    assert fake.gaps("example.com") == [2.0, 2.0, 2.0, 2.0]


def test_a_redirect_off_the_site_is_refused_before_the_other_site_is_asked(
    monkeypatch,
):
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/away"),
            f"{ROOT}/away": (302, "", {"Location": "https://other.example/landing"}),
            "https://other.example/landing": page("Landing"),
        }
    )
    fake.as_default(monkeypatch)

    pages = list(crawl(f"{ROOT}/", **paced(fake)))

    assert pages[1].error.code == "redirected_off_site"
    assert not any("other.example" in url for url in fake.asked())


def test_a_batch_resumed_reads_a_redirects_target_it_had_not_reached(tmp_path):
    state = tmp_path / "batch.jsonl"
    line = {
        "url": f"{ROOT}/moved",
        "ok": False,
        "depth": 0,
        "found_on": None,
        "error": {
            "code": "redirected_off_site",
            "message": "moved",
            "retryable": False,
            "target": "https://other.example/",
        },
    }
    state.write_text(json.dumps(line) + "\n", encoding="utf-8")
    fake = FakeWeb(shop())

    rest = extract_many(
        [f"{ROOT}/moved"],
        state=state,
        web=fake.web(),
        clock=fake.clock,
        sleep=fake.clock.sleep,
    )

    assert urls(rest) == ["https://other.example/"]
    assert rest.resumed == 1


def test_a_batch_resumed_skips_what_its_file_holds(tmp_path):
    state = tmp_path / "batch.jsonl"
    listed = [f"{ROOT}/p/1", f"{ROOT}/p/2", f"{ROOT}/p/3"]
    first = extract_many(
        listed[:2], state=state, web=FakeWeb(shop()).web(), sleep=lambda s: None
    )
    list(first)
    fake = FakeWeb(shop())

    rest = extract_many(
        listed, state=state, web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep
    )

    assert urls(rest) == [f"{ROOT}/p/3"]
    assert rest.resumed == 2
    assert len(state.read_text(encoding="utf-8").splitlines()) == 3


def test_a_batch_out_of_time_hands_back_an_unbroken_prefix():
    fake = FakeWeb(shop())
    listed = [f"{ROOT}/p/1", f"{ROOT}/p/2", f"{ROOT}/p/3", f"{ROOT}/about"]

    batch = extract_many(
        listed,
        web=fake.web(),
        clock=fake.clock,
        sleep=fake.clock.sleep,
        time_budget=2.5,
        concurrency=1,
    )
    taken = urls(batch)

    assert batch.stopped == "time_budget"
    assert taken == listed[: len(taken)] and 1 <= len(taken) < 4


def test_a_crawl_can_be_stepped_one_page_at_a_time():
    crawled = run(FakeWeb(shop()))

    assert next(crawled).url == f"{ROOT}/"
    assert next(crawled).url == f"{ROOT}/c/1"


def test_a_budget_of_nothing_takes_nothing():
    fake = FakeWeb(shop())

    assert list(run(fake, max_pages=0)) == []
    assert fake.requests == []


def test_a_private_address_and_a_page_too_heavy_are_answers():
    heavy = FakeWeb({f"{ROOT}/": "<p>" + "x" * 5000 + "</p>"})

    private = list(run(FakeWeb({}), start="http://127.0.0.1/", allow_private=False))
    big = list(run(heavy, max_bytes=1000))

    assert private[0].error.code == "refused_address"
    assert big[0].error.code == "too_large"
    assert not any("127.0.0.1" in url for url in heavy.asked())


def test_an_off_site_redirect_as_a_line_names_where_it_pointed():
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/away"),
            f"{ROOT}/away": (302, "", {"Location": "https://other.example/"}),
        }
    )

    line = list(run(fake))[1].to_json()

    assert line["error"]["code"] == "redirected_off_site"
    assert line["error"]["target"] == "https://other.example/"


def test_blank_lines_in_a_state_file_are_nothing(tmp_path):
    state = tmp_path / "crawl.jsonl"
    list(run(FakeWeb(shop()), state=state, max_pages=2))
    state.write_text(
        state.read_text(encoding="utf-8").replace("\n", "\n\n", 1), encoding="utf-8"
    )

    assert urls(run(FakeWeb(shop()), state=state, max_pages=3)) == [f"{ROOT}/c/2"]


def test_a_redirect_into_a_private_address_is_an_answer():
    from sluicer.fetch import AddressRefused

    fake = FakeWeb(shop())

    def refusing(url):
        raise AddressRefused(
            "http://10.0.0.1/", "10.0.0.1 is not on the public internet"
        )

    web = Web(rungs=[("http", refusing)], read=fake.web().read, get=fake.get)
    pages = list(
        crawl(
            f"{ROOT}/",
            allow_private=False,
            resolve=lambda host: ["93.184.215.14"],
            web=web,
            clock=fake.clock,
            sleep=fake.clock.sleep,
        )
    )

    assert pages[0].error.code == "refused_address"


def test_a_climb_to_the_next_rung_waits_the_sites_delay():
    """The ladder asks the browser the moment plain HTTP came back with a shell."""
    shell = (
        "<html><body><div id='root'></div>"
        + "<script src='/app.js'></script>" * 80
        + "</body></html>"
    )
    fake = FakeWeb({f"{ROOT}/": shell})
    browser = FakeWeb({f"{ROOT}/": page("Rendered")}, clock=fake.clock)
    web = Web(
        rungs=[("http", fake.rung), ("browser", browser.rung)],
        read=fake.web().read,
        get=fake.get,
    )

    pages = list(
        crawl(
            f"{ROOT}/", min_delay=3.0, web=web, clock=fake.clock, sleep=fake.clock.sleep
        )
    )

    assert [climb.to_rung for climb in pages[0].climbs] == ["browser"]
    assert pages[0].extraction.summary["title"].value == "Rendered"
    http_ended = fake.requests[-1][2]
    browser_started = browser.requests[0][1]
    # Rounded as ``gaps`` rounds: the fake clock starts at the real monotonic
    # time, where a difference of two floats is not exactly 3.0.
    assert round(browser_started - http_ended, 6) == 3.0


def test_a_robots_file_read_after_a_redirect_waits_the_sites_delay(monkeypatch):
    """Measured on quotes.toscrape.com: a redirect to the other scheme had the
    ladder read that origin's robots.txt the moment the page landed."""
    fake = FakeWeb(
        {
            "http://example.com/": (301, "", {"Location": "https://example.com/"}),
            "https://example.com/": page("Home"),
        }
    )
    fake.as_default(monkeypatch)

    list(crawl("http://example.com/", min_delay=2.0, **paced(fake)))

    assert fake.asked() == [
        "http://example.com/robots.txt",
        "http://example.com/",
        "https://example.com/",
        "https://example.com/robots.txt",
    ]
    assert fake.gaps("example.com") == [2.0, 2.0, 2.0]


def test_a_second_crawl_of_a_site_in_one_process_waits_for_the_first():
    """Measured on scrapeme.live: a batch began 0.00 s after the map before it."""
    fake = FakeWeb(shop())

    list(run(fake, max_pages=2))
    list(run(fake, start=f"{ROOT}/about", max_pages=1))
    list(extract_many([f"{ROOT}/p/1"], **paced(fake, web=fake.web())))

    assert fake.gaps("example.com") == [1.0, 1.0, 1.0, 1.0]


def test_an_error_pages_links_and_canonical_are_not_the_sites():
    """A 404 naming a product as its canonical would mark the product seen."""
    canon = f'<link rel="canonical" href="{ROOT}/p/1">'
    fake = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/gone", "/p/1"),
            f"{ROOT}/gone": (404, page("Not found", "/nav/1", extra=canon), {}),
            f"{ROOT}/p/1": page("Pad 1"),
        }
    )

    pages = list(run(fake))

    assert urls(pages) == [f"{ROOT}/", f"{ROOT}/gone", f"{ROOT}/p/1"]
    assert pages[1].ok and pages[1].status == 404
    assert pages[1].links == () and pages[1].canonical is None


@pytest.mark.parametrize(
    ("headers", "seconds"),
    [
        ({"retry-after": "120"}, 120.0),
        ({"retry-after": " 0 "}, 0.0),
        (
            {
                "retry-after": "Wed, 23 Sep 2026 10:01:00 GMT",
                "date": "Wed, 23 Sep 2026 10:00:00 GMT",
            },
            60.0,
        ),
        # A moment already past asks for no wait.
        (
            {
                "retry-after": "Wed, 23 Sep 2026 09:00:00 GMT",
                "date": "Wed, 23 Sep 2026 10:00:00 GMT",
            },
            0.0,
        ),
        # A date with no Date to count from, and what is neither, say nothing.
        ({"retry-after": "Wed, 23 Sep 2026 10:01:00 GMT"}, None),
        ({"retry-after": "soon"}, None),
        ({"retry-after": "-5"}, None),
        ({}, None),
    ],
)
def test_a_retry_after_is_read_as_rfc_9110_writes_it(headers, seconds):
    from sluicer.crawl.schedule import retry_after

    assert retry_after(headers) == seconds


def test_a_challenge_page_is_a_page_the_site_refused():
    """The ladder's last rung used to hand a challenge back as the page, and a
    crawl read a waiting room's words as a page's summary."""
    challenge = (
        "<html><head><title>Just a moment...</title></head>"
        "<body>Checking your browser</body></html>"
    )
    fake = FakeWeb({f"{ROOT}/": challenge})

    (only,) = list(run(fake))

    assert only.error is not None and only.error.code == "refused_by_site"
    assert only.error.retryable is False
    assert "challenge page" in only.error.message


def test_a_page_that_asks_to_be_paid_says_so():
    fake = FakeWeb({f"{ROOT}/": (402, page("Pay first"), {})})

    (only,) = list(run(fake))

    assert only.error is not None and only.error.code == "payment_required"
    assert only.error.retryable is False
    assert only.extraction is None, "a 402's body is not the page"


def test_a_site_that_needed_the_browser_is_asked_of_it_from_its_second_page():
    """Measured on 0.7.0: a five-page JS site crawled at 3.22 s a page, every
    document asked twice, of plain HTTP and then of the browser."""
    from sluicer.fetch.ladder import RungMemory

    def shell(*links):
        anchors = "".join(f'<a href="{link}">{link}</a>' for link in links)
        return (
            "<html><body><div id='root'></div>"
            + "<script src='/app.js'></script>" * 80
            + anchors
            + "</body></html>"
        )

    fake = FakeWeb(
        {
            f"{ROOT}/": shell("/a", "/b"),
            f"{ROOT}/a": shell(),
            f"{ROOT}/b": shell(),
        }
    )
    browser = FakeWeb(
        {
            f"{ROOT}/": page("Home", "/a", "/b"),
            f"{ROOT}/a": page("A"),
            f"{ROOT}/b": page("B"),
        },
        clock=fake.clock,
    )
    web = Web(
        rungs=[("http", fake.rung), ("browser", browser.rung)],
        read=fake.web().read,
        get=fake.get,
        memory=RungMemory(),
    )

    pages = list(crawl(f"{ROOT}/", web=web, clock=fake.clock, sleep=fake.clock.sleep))

    # The fake's rungs both call their pages "http"; the climbs say which ran.
    assert [[c.to_rung for c in p.climbs] for p in pages] == [["browser"]] * 3
    assert [url for url in fake.asked() if not url.endswith("robots.txt")] == [
        f"{ROOT}/"
    ]
    assert browser.asked() == [f"{ROOT}/", f"{ROOT}/a", f"{ROOT}/b"]
    assert all(p.climbs[0].seconds == 0.0 for p in pages[1:])


def _two_rung_shop(listings, details):
    """A web whose plain HTTP serves ``listings`` whole and ``details`` as
    empty shells a browser fills, with a memory of its own."""
    from sluicer.fetch.ladder import RungMemory

    shell = (
        "<html><body><div id='root'></div>"
        + "<script src='/app.js'></script>" * 80
        + "</body></html>"
    )
    fake = FakeWeb({**listings, **{url: shell for url in details}})
    browser = FakeWeb({**listings, **details}, clock=fake.clock)
    memory = RungMemory()
    web = Web(
        rungs=[("http", fake.rung), ("browser", browser.rung)],
        read=fake.web().read,
        get=fake.get,
        memory=memory,
    )
    return fake, browser, web, memory


def test_listing_pages_stay_on_plain_http_after_a_detail_page_needed_the_browser():
    """Measured on a local shop before: after its first product needed the
    browser, three of its seven listing pages were rendered in the browser
    too, 0.7 s each where plain HTTP took 2 ms."""
    listings = {
        f"{ROOT}/": page("Home", "/c/1", "/p/1", "/c/2", "/p/2"),
        f"{ROOT}/c/1": page("Cat 1"),
        f"{ROOT}/c/2": page("Cat 2"),
    }
    details = {f"{ROOT}/p/1": page("Pad 1"), f"{ROOT}/p/2": page("Pad 2")}
    fake, browser, web, memory = _two_rung_shop(listings, details)

    pages = list(crawl(f"{ROOT}/", web=web, clock=fake.clock, sleep=fake.clock.sleep))

    assert all(p.ok and p.found for p in pages)
    assert [url for url in fake.asked() if not url.endswith("robots.txt")] == [
        f"{ROOT}/",
        f"{ROOT}/c/1",
        f"{ROOT}/p/1",
        f"{ROOT}/c/2",
    ]
    assert browser.asked() == [f"{ROOT}/p/1", f"{ROOT}/p/2"]
    second = {p.url: p for p in pages}[f"{ROOT}/p/2"]
    assert "an earlier page of /p/ on example.com needed it" in second.climbs[0].reason
    # What the site needed is still the process's, for the next crawl of it.
    assert memory.recall(f"{ROOT}/c/9").rung == "browser"


def test_a_part_of_the_site_not_yet_seen_starts_where_the_site_needed():
    listings = {
        f"{ROOT}/": page("Home", "/p/1", "/news/1"),
        f"{ROOT}/news/1": page("News"),
    }
    fake, browser, web, _ = _two_rung_shop(listings, {f"{ROOT}/p/1": page("Pad")})

    pages = list(crawl(f"{ROOT}/", web=web, clock=fake.clock, sleep=fake.clock.sleep))

    assert all(p.ok for p in pages)
    assert browser.asked() == [f"{ROOT}/p/1", f"{ROOT}/news/1"]
    news = pages[-1]
    assert "an earlier page of example.com needed it" in news.climbs[0].reason


def test_the_real_web_remembers_for_the_process(monkeypatch):
    from sluicer.crawl.web import default_web
    from sluicer.fetch.ladder import STICKY

    monkeypatch.setenv("SLUICER_BROWSER", "none")

    assert default_web().memory is STICKY


@pytest.mark.parametrize("how", ["crawl", "extract_many", "map_site"])
def test_the_callers_headers_and_cookies_go_into_the_web_every_page_is_asked_of(
    monkeypatch, how
):
    from sluicer.crawl import map_site

    fake = FakeWeb({f"{ROOT}/": page("Home")})
    built = {}

    def default_web(*args, **kwargs):
        built.update(kwargs)
        return fake.web(args[3] if len(args) > 3 else kwargs.get("redirects"))

    monkeypatch.setattr("sluicer.crawl.pages.default_web", default_web)
    monkeypatch.setattr("sluicer.crawl.sitemaps.default_web", default_web)
    sending = {"headers": {"Authorization": "Bearer t"}, "cookies": {"s": "1"}}
    timing = {"clock": fake.clock, "sleep": fake.clock.sleep}
    if how == "crawl":
        list(crawl(f"{ROOT}/", **sending, **timing))
    elif how == "extract_many":
        list(extract_many([f"{ROOT}/"], **sending, **timing))
    else:
        map_site(f"{ROOT}/", **sending, **timing)

    assert built["headers"] == {"Authorization": "Bearer t"}
    assert built["cookies"] == {"s": "1"}


def test_headers_for_a_web_of_ones_own_are_refused_rather_than_dropped():
    fake = FakeWeb({f"{ROOT}/": page("Home")})

    with pytest.raises(ValueError, match="a web of its own"):
        crawl(f"{ROOT}/", web=fake.web(), headers={"Authorization": "Bearer t"})


def test_a_crawl_refuses_a_user_agent_before_it_asks_anything(monkeypatch):
    with pytest.raises(ValueError, match="User-Agent"):
        crawl(f"{ROOT}/", headers={"User-Agent": "Mozilla/5.0"})


# -- retries -------------------------------------------------------------------


def requests_of(fake, url):
    """When each request for ``url`` started and ended, in order."""
    return [(start, end) for asked, start, end in fake.requests if asked == url]


def test_a_page_whose_connection_was_reset_is_asked_again_after_a_backoff():
    pages = shop()
    pages[f"{ROOT}/c/1"] = [ConnectionResetError("reset by peer"), pages[f"{ROOT}/c/1"]]
    fake = FakeWeb(pages)

    result = {p.url: p for p in run(fake)}

    again = result[f"{ROOT}/c/1"]
    assert again.ok and again.found
    assert [retry.after for retry in again.retries] == [2.0]
    assert "ConnectionResetError: reset by peer" in again.retries[0].reason
    failed, answered = requests_of(fake, f"{ROOT}/c/1")
    assert round(answered[0] - failed[1], 6) == 2.0
    assert result[f"{ROOT}/c/2"].retries == ()


def test_a_server_error_is_asked_again_each_time_twice_as_late():
    pages = shop()
    pages[f"{ROOT}/c/1"] = [
        (500, "oops", {}),
        (502, "gateway", {}),
        pages[f"{ROOT}/c/1"],
    ]
    fake = FakeWeb(pages)

    again = {p.url: p for p in run(fake)}[f"{ROOT}/c/1"]

    assert again.status == 200 and again.found
    assert [(r.reason, r.after) for r in again.retries] == [
        ("it answered 500", 2.0),
        ("it answered 502", 4.0),
    ]


def test_a_page_is_asked_three_times_at_most_and_is_then_what_it_last_was():
    pages = shop()
    pages[f"{ROOT}/c/1"] = (500, "oops", {})
    fake = FakeWeb(pages)

    again = {p.url: p for p in run(fake)}[f"{ROOT}/c/1"]

    assert again.status == 500 and len(again.retries) == 2
    assert len(requests_of(fake, f"{ROOT}/c/1")) == 3


def test_no_retries_asks_once():
    pages = shop()
    pages[f"{ROOT}/c/1"] = ConnectionError("connection reset")
    fake = FakeWeb(pages)

    again = {p.url: p for p in run(fake, retries=0)}[f"{ROOT}/c/1"]

    assert again.error.code == "fetch_failed" and again.retries == ()
    assert len(requests_of(fake, f"{ROOT}/c/1")) == 1


def test_a_client_error_is_the_page_s_answer_and_never_asked_again():
    pages = shop()
    pages[f"{ROOT}/c/1"] = (404, "gone", {})
    pages[f"{ROOT}/c/2"] = (403, "no", {})
    fake = FakeWeb(pages)

    result = {p.url: p for p in run(fake)}

    assert [result[f"{ROOT}/c/{n}"].status for n in (1, 2)] == [404, 403]
    assert result[f"{ROOT}/c/1"].retries == result[f"{ROOT}/c/2"].retries == ()
    assert len(requests_of(fake, f"{ROOT}/c/1")) == 1
    assert len(requests_of(fake, f"{ROOT}/c/2")) == 1


@pytest.mark.parametrize(
    "failure",
    [
        "TooManyRedirects",
        "UnreadableEncoding",
        "EmptyBody",
    ],
)
def test_a_failure_that_asking_again_cannot_change_is_asked_once(failure):
    """Measured on 0.8.0: a redirect loop was followed three times over, 33
    requests, and the site was then treated as failing; every failure was
    retried, whatever it was."""
    from sluicer.fetch.http_rung import TooManyRedirects
    from sluicer.fetch.result import EmptyBody
    from sluicer.fetch.wire import UnreadableEncoding

    raised = {
        "TooManyRedirects": TooManyRedirects("it redirected more than 10 times"),
        "UnreadableEncoding": UnreadableEncoding(f"{ROOT}/c/1", "br"),
        "EmptyBody": EmptyBody(f"{ROOT}/c/1", "http", 200),
    }[failure]
    pages = shop()
    pages[f"{ROOT}/c/1"] = raised
    fake = FakeWeb(pages)

    again = {p.url: p for p in run(fake)}[f"{ROOT}/c/1"]

    assert again.error.code == "fetch_failed"
    assert not again.error.retryable
    assert again.retries == ()
    assert len(requests_of(fake, f"{ROOT}/c/1")) == 1


def test_a_page_cut_short_or_timed_out_is_asked_again():
    from sluicer.fetch.http_rung import ProtocolError

    pages = shop()
    pages[f"{ROOT}/c/1"] = [ProtocolError("cut short"), pages[f"{ROOT}/c/1"]]
    pages[f"{ROOT}/c/2"] = [TimeoutError("took too long"), pages[f"{ROOT}/c/2"]]
    fake = FakeWeb(pages)

    result = {p.url: p for p in run(fake)}

    assert [len(result[f"{ROOT}/c/{n}"].retries) for n in (1, 2)] == [1, 1]
    assert result[f"{ROOT}/c/1"].ok and result[f"{ROOT}/c/2"].ok


def test_an_empty_404_is_the_page_s_answer_and_asked_once(monkeypatch):
    """Measured on 0.8.0: an empty 404 was the HTTP rung failing, not a 404;
    asked three times, it ended fetch_failed."""
    from fake_wire import fake_http

    monkeypatch.setenv("SLUICER_BROWSER", "none")
    seen = fake_http(monkeypatch, [(404, b"", {}), (404, b"", {})])

    pages = list(extract_many([f"{ROOT}/gone"], min_delay=0))

    assert [(p.status, p.error) for p in pages] == [(404, None)]
    assert [r.target for r in seen.requests] == ["/robots.txt", "/gone"]


def test_a_robots_file_that_did_not_answer_is_asked_again():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = [ConnectionError("no route"), "User-agent: *\n"]
    fake = FakeWeb(pages)

    first = next(iter(run(fake)))

    assert first.ok and len(first.retries) == 1
    assert "robots.txt" in first.retries[0].reason


def test_a_retry_waits_the_retry_after_the_site_named_when_it_is_longer():
    pages = shop()
    pages[f"{ROOT}/c/1"] = [(503, "busy", {"Retry-After": "7"}), pages[f"{ROOT}/c/1"]]
    fake = FakeWeb(pages)

    again = {p.url: p for p in run(fake)}[f"{ROOT}/c/1"]

    assert again.ok and [r.after for r in again.retries] == [7.0]
    failed, answered = requests_of(fake, f"{ROOT}/c/1")
    assert round(answered[0] - failed[1], 6) == 7.0


def test_a_site_that_failed_a_page_through_its_retries_is_asked_once_a_page():
    """A site that is down costs its retries once, not once a page; the first
    page it answers makes its failures worth retrying again."""
    pages = shop()
    pages[f"{ROOT}/c/1"] = ConnectionError("down")
    pages[f"{ROOT}/c/2"] = ConnectionError("down")
    pages[f"{ROOT}/p/1"] = [ConnectionError("blip"), pages[f"{ROOT}/p/1"]]
    fake = FakeWeb(pages)
    listed = [f"{ROOT}/c/1", f"{ROOT}/c/2", f"{ROOT}/about", f"{ROOT}/p/1"]

    result = list(
        extract_many(listed, web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep)
    )

    assert [len(p.retries) for p in result] == [2, 0, 0, 1]
    assert [p.ok for p in result] == [False, False, True, True]
    assert len(requests_of(fake, f"{ROOT}/c/2")) == 1


def test_a_retry_that_would_start_past_the_time_budget_is_not_made():
    pages = shop()
    pages[f"{ROOT}/c/1"] = ConnectionError("connection reset")
    fake = FakeWeb(pages)

    result = list(run(fake, time_budget=4.0))

    assert result[1].url == f"{ROOT}/c/1" and result[1].retries == ()
    assert len(requests_of(fake, f"{ROOT}/c/1")) == 1


def test_a_retried_page_says_so_in_its_line_and_another_says_nothing():
    pages = shop()
    pages[f"{ROOT}/c/1"] = [(503, "busy", {}), pages[f"{ROOT}/c/1"]]
    pages[f"{ROOT}/c/2"] = ConnectionError("down")

    lines = {p.url: p.to_json() for p in run(FakeWeb(pages), max_depth=1)}

    assert lines[f"{ROOT}/c/1"]["retries"] == [
        {"reason": "it answered 503", "after": 2.0}
    ]
    # The 503 doubled the site's delay to two seconds; the backoff doubles
    # the delay robots.txt and ours ask, and waits the longer of the two.
    assert [r["after"] for r in lines[f"{ROOT}/c/2"]["retries"]] == [2.0, 4.0]
    assert lines[f"{ROOT}/c/2"]["error"]["code"] == "fetch_failed"
    assert "retries" not in lines[f"{ROOT}/"]
    json.dumps(lines)


def test_a_batch_retries_as_a_crawl_does():
    pages = shop()
    pages[f"{ROOT}/p/1"] = [ConnectionResetError("reset"), pages[f"{ROOT}/p/1"]]
    fake = FakeWeb(pages)

    listed = [f"{ROOT}/p/1", f"{ROOT}/p/2"]
    result = list(
        extract_many(listed, web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep)
    )

    assert [p.ok for p in result] == [True, True]
    assert len(result[0].retries) == 1 and result[1].retries == ()


# -- a pace that follows the site ------------------------------------------------


def test_a_site_that_answers_slowly_is_asked_as_slowly():
    fake = FakeWeb(shop(), cost=3.0)

    list(run(fake, max_pages=4))

    assert fake.gaps("example.com") == [3.0] * 4


def test_a_slow_site_is_never_waited_for_longer_than_the_crawl_waits():
    fake = FakeWeb(shop(), cost=100.0)

    list(run(fake, max_pages=3, max_delay=10.0))

    assert fake.gaps("example.com") == [10.0] * 3


def test_a_fast_site_is_still_asked_no_sooner_than_its_crawl_delay():
    pages = shop()
    pages[f"{ROOT}/robots.txt"] = "User-agent: *\nCrawl-delay: 4\n"
    fake = FakeWeb(pages, cost=3.0)

    list(run(fake, max_pages=3))

    assert fake.gaps("example.com") == [4.0, 4.0, 4.0]


def test_a_crawls_login_goes_to_the_origin_it_started_at_and_no_other(monkeypatch):
    """Measured on 0.8.0: a crawl of https://site.test/ with a cookie followed
    an http:// link of the same site and sent the cookie in clear text. The
    site is its host with or without www., over http or https; a login is
    for the one origin the caller named."""
    from fake_wire import fake_http

    monkeypatch.setenv("SLUICER_BROWSER", "none")
    home = (
        b"<html><body>" + b"<p>words of the home page</p>" * 20 + b"<a href="
        b"'http://example.com/plain'>plain</a><a href='https://www.example.com/w'>"
        b"w</a><a href='/same'>same</a></body></html>"
    )
    leaf = b"<html><body>" + b"<p>words of a page</p>" * 20 + b"</body></html>"
    nothing = (404, b"", {})
    seen = fake_http(
        monkeypatch,
        [nothing, (200, home, {}), nothing, (200, leaf, {}), nothing]
        + [(200, leaf, {})] * 2,
    )

    pages = list(
        crawl(
            "https://example.com/",
            max_pages=4,
            min_delay=0,
            headers={"Authorization": "Bearer t"},
            cookies={"s": "1"},
        )
    )

    assert [p.error for p in pages] == [None] * 4
    asked = [
        (seen.targets[r.connection].scheme, seen.targets[r.connection].host, r.target)
        for r in seen.requests
    ]
    logged_in = [
        target
        for target, r in zip(asked, seen.requests, strict=True)
        if "authorization" in r.headers or "cookie" in r.headers
    ]
    assert sorted(logged_in) == [
        ("https", "example.com", "/"),
        ("https", "example.com", "/same"),
    ]
    assert len(asked) == 7


def test_a_batchs_login_does_not_follow_a_redirect_into_another_sites_turn(
    monkeypatch,
):
    """A redirect to another site is read in that site's own turn, as an
    address of its own; asked that way it was sent the login meant for the
    address given."""
    from fake_wire import fake_http

    monkeypatch.setenv("SLUICER_BROWSER", "none")
    leaf = b"<html><body>" + b"<p>words of a page</p>" * 20 + b"</body></html>"
    nothing = (404, b"", {})
    seen = fake_http(
        monkeypatch,
        [
            nothing,
            (302, b"", {"location": "https://other.example/q"}),
            nothing,
            (200, leaf, {}),
        ],
    )

    pages = list(
        extract_many(
            ["https://example.com/p"], min_delay=0, headers={"Authorization": "t"}
        )
    )

    assert [p.error.code if p.error else None for p in pages] == [
        "redirected_off_site",
        None,
    ]
    assert [r.target for r in seen.requests] == [
        "/robots.txt",
        "/p",
        "/robots.txt",
        "/q",
    ]
    assert ["authorization" in r.headers for r in seen.requests] == [
        False,
        True,
        False,
        False,
    ]
