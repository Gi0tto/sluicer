"""A page a fetch kept parsed is let go wherever no extraction follows.

0.10 hands the tree a fetch parsed to the extraction of that page, and keeps
it per thread until then. A page fetched and never extracted -- turned into
markdown, dropped by a crawl, refused by its TDM reservation -- stayed parsed
for as long as its thread: sixteen threads that fetched a 10 MB page each
held 1.4 to 1.9 GB where 0.9.1 held 0.25 to 0.3 GB.
"""

from __future__ import annotations

import pytest

from fake_site import FakeWeb, page
from sluicer import document
from sluicer.document import load_and_keep, load_kept

PAGE = "<html><head><title>Pads</title></head><body><p>Brake pads.</p></body></html>"


def _kept() -> object:
    return getattr(document._KEPT, "page", None)


@pytest.fixture(autouse=True)
def _nothing_kept_before():
    document._KEPT.page = None
    yield
    document._KEPT.page = None


def test_a_page_over_the_cap_is_not_kept_and_lets_go_of_the_last(monkeypatch):
    small = load_and_keep(PAGE)
    assert _kept() is not None
    monkeypatch.setattr(document, "KEEP_AT_MOST", len(PAGE) - 1)
    big = PAGE.replace("Pads", "Discs")

    load_and_keep(big)

    assert _kept() is None
    assert load_kept(PAGE) is not small


def test_the_whole_page_as_markdown_does_not_parse_a_kept_page_again(monkeypatch):
    from sluicer.markdown import read_markdown

    load_and_keep(PAGE, url="https://a.example/p")
    parsed = []
    real = document.load
    monkeypatch.setattr(
        document, "load", lambda *a, **k: parsed.append(1) or real(*a, **k)
    )

    found = read_markdown(PAGE, url="https://a.example/p", full=True)

    assert "Brake pads." in found.markdown
    assert parsed == []
    assert _kept() is None


def test_the_main_text_as_markdown_lets_the_kept_page_go():
    pytest.importorskip("trafilatura")
    from sluicer.markdown import read_markdown

    load_and_keep(PAGE, url="https://a.example/p")

    read_markdown(PAGE, url="https://a.example/p")

    assert _kept() is None


def test_an_mcp_call_lets_go_of_what_it_kept_even_when_it_refuses(monkeypatch):
    from test_mcp_server import fake_mcp

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    reserved = '<meta name="tdm-reservation" content="1">'
    html = f"<html><head>{reserved}<title>T</title></head></html>"

    answer = registered["extract_declared"](html, respect_tdm=True)

    assert answer["error"]["code"] == "tdm_reserved"
    assert _kept() is None


def test_a_page_a_crawl_drops_is_let_go():
    from sluicer.crawl import crawl

    root = "https://shop.example"
    fake = FakeWeb(
        {
            f"{root}/": page("Home", "/away"),
            f"{root}/away": (302, "", {"Location": "https://other.example/landing"}),
            "https://other.example/landing": page("Landing"),
        }
    )

    # One site at a time: the pages are read in this thread, which outlives
    # the crawl, where a pool's workers end with it.
    pages = list(
        crawl(
            f"{root}/",
            web=fake.web(),
            clock=fake.clock,
            sleep=fake.clock.sleep,
            concurrency=1,
        )
    )

    assert pages[-1].error.code == "redirected_off_site"
    assert _kept() is None
