"""``aextract`` and ``afetch``: the same answers, off the event loop, and a
site asked as politely by many coroutines as by many threads.

The politeness tests run on the real clock, as ``test_gate`` does, with the
process's gate a few hundredths of a second apart and the default rungs
replaced by a fake site that writes down when each request started and ended.
"""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import sluicer
from sluicer import aextract, extract
from sluicer.fetch import RobotsRefused, afetch, fetch
from sluicer.fetch.gate import GATE
from test_gate import DELAY, ROOT, TOLERANCE, Site

OTHER = "https://example.org"


@pytest.fixture
def site(monkeypatch):
    """The default rungs are this site's, paced by the process's gate."""
    fake = Site()
    monkeypatch.setattr(
        "sluicer.fetch.rungs.default_rungs",
        lambda *args, **kwargs: [("http", fake.rung)],
    )
    monkeypatch.setattr(GATE, "min_delay", DELAY)
    return fake


def _run(main, workers: int | None = None):
    """``asyncio.run(main())``, the loop's threads limited to ``workers``."""

    async def limited():
        if workers is not None:
            asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(workers))
        return await main()

    return asyncio.run(limited())


def test_they_take_what_the_sync_calls_take():
    assert inspect.iscoroutinefunction(aextract)
    assert inspect.iscoroutinefunction(afetch)
    assert list(inspect.signature(aextract).parameters.values()) == list(
        inspect.signature(extract).parameters.values()
    )
    assert list(inspect.signature(afetch).parameters.values()) == list(
        inspect.signature(fetch).parameters.values()
    )
    assert "aextract" in sluicer.__all__


def test_aextract_answers_what_extract_answers():
    page = (
        '<html><head><title>T</title><script type="application/ld+json">'
        '{"@type":"Product","name":"Pads","offers":{"price":"12.50",'
        '"priceCurrency":"EUR"}}</script></head></html>'
    )

    async def main():
        return await aextract(page, url="https://example.com/p", visible=True)

    assert _run(main) == extract(page, url="https://example.com/p", visible=True)


def test_aextract_reads_on_another_thread(monkeypatch):
    seen = []
    real = sluicer.api._extract_document

    def spy(*args, **kwargs):
        seen.append(threading.get_ident())
        return real(*args, **kwargs)

    monkeypatch.setattr(sluicer.api, "_extract_document", spy)

    async def main():
        await aextract("<title>T</title>")
        return threading.get_ident()

    assert _run(main) not in seen and len(seen) == 1


def test_parallel_afetch_calls_to_one_site_are_asked_one_after_another(site):
    """What six parallel fetches on threads do (``test_gate``), from one
    event loop: robots.txt once, never two requests in flight, the gate's
    delay between one fetch and the next."""

    async def main():
        return await asyncio.gather(*(afetch(f"{ROOT}/{n}") for n in range(6)))

    pages = _run(main)

    assert [page.url for page in pages] == [f"{ROOT}/{n}" for n in range(6)]
    asked = [url for url, _, _ in site.requests]
    assert asked.count(f"{ROOT}/robots.txt") == 1
    assert len(asked) == 7
    gaps = site.gaps()
    assert all(gap >= -TOLERANCE for gap in gaps), "two were never in flight at once"
    assert sorted(gaps)[1] >= DELAY - TOLERANCE, gaps


def test_coroutines_and_threads_share_one_site(site):
    """A thread's fetch and a coroutine's wait for each other: one gate."""
    thread = threading.Thread(
        target=lambda: [fetch(f"{ROOT}/{10 + n}") for n in range(3)]
    )

    async def main():
        thread.start()
        await asyncio.gather(*(afetch(f"{ROOT}/{n}") for n in range(3)))

    _run(main)
    thread.join()

    gaps = site.gaps()
    assert len(site.requests) == 7
    assert all(gap >= -TOLERANCE for gap in gaps), gaps
    assert len([gap for gap in gaps if gap < DELAY - TOLERANCE]) <= 1, (
        "only the first fetch's robots.txt and page follow each other"
    )


def test_a_site_s_queue_holds_one_thread_and_another_site_is_not_kept_waiting(
    site,
):
    """Coroutines waiting for one site wait on the loop, not each on a worker
    thread: with two workers and five fetches of one site queued, a fetch of
    another site starts at once rather than behind them."""

    async def main():
        busy = [afetch(f"{ROOT}/{n}") for n in range(5)]
        return await asyncio.gather(*busy, afetch(f"{OTHER}/0"))

    _run(main, workers=2)

    first_end = min(end for url, _, end in site.requests if url.startswith(ROOT))
    other = [start for url, start, _ in site.requests if url.startswith(OTHER)]
    assert other and min(other) < first_end + DELAY, (
        "the other site waited behind the first one's queue"
    )


def test_the_loop_runs_while_a_page_is_fetched(site):
    site.cost = 0.2
    ticks = []

    async def ticking():
        while True:
            ticks.append(time.monotonic())
            await asyncio.sleep(0.01)

    async def main():
        ticker = asyncio.create_task(ticking())
        await afetch(f"{OTHER}/1")
        ticker.cancel()

    _run(main)

    assert len(ticks) >= 20, "the event loop was blocked by the fetch"


def test_a_refusal_is_raised_as_fetch_raises_it(site):
    from sluicer.fetch.identity import _CACHE

    _CACHE[ROOT] = (time.monotonic(), "User-agent: *\nDisallow: /\n")

    async def main():
        await afetch(f"{ROOT}/1")

    with pytest.raises(RobotsRefused):
        _run(main)
    assert site.requests == []


def test_a_fetch_cancelled_while_it_waits_for_its_site_asks_nothing(site):
    site.cost = 0.1

    async def main():
        first = asyncio.create_task(afetch(f"{ROOT}/1"))
        second = asyncio.create_task(afetch(f"{ROOT}/2"))
        await asyncio.sleep(0.05)
        second.cancel()
        await first
        with pytest.raises(asyncio.CancelledError):
            await second

    _run(main)
    time.sleep(DELAY + 0.1)

    assert f"{ROOT}/2" not in [url for url, _, _ in site.requests]


def test_injected_rungs_are_the_caller_s_to_pace():
    """As for ``fetch``: a ladder handed in is not gated, from a coroutine
    either."""
    started = []

    def rung(url):
        started.append(time.monotonic())
        time.sleep(0.05)
        from sluicer.fetch import Fetched

        return Fetched(
            url=url, html="<title>x</title>" + "t " * 80, status=200, rung="own"
        )

    async def main():
        await asyncio.gather(
            *(
                afetch(f"{ROOT}/{n}", rungs=[("own", rung)], obey_robots=False)
                for n in range(3)
            )
        )

    _run(main)

    assert max(started) - min(started) < 0.05
