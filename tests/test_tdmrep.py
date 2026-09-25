"""TDMRep: a page's text and data mining reservation, and respecting it."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

import sluicer
from fake_site import FakeWeb, page
from sluicer.cli import main
from sluicer.crawl import crawl, extract_many
from sluicer.declared.tdmrep import (
    Reservation,
    TdmRule,
    read_tdmrep,
    reservation,
    rule_for,
)
from sluicer.fetch.result import Fetched
from sluicer.fetch.site import read_tdmrep_file

ROOT = "https://example.com"
RESERVED = '<meta name="tdm-reservation" content="1">'


def rights(html: str, headers: dict[str, str] | None = None):
    return sluicer.extract(html, url=f"{ROOT}/p", headers=headers).rights


# -- the file --------------------------------------------------------------------


def test_the_file_is_read_as_the_report_writes_it():
    """The report's own example: a reservation on everything, no policy."""
    assert read_tdmrep('[{"location": "/", "tdm-reservation": 1}]') == [
        TdmRule("/", "1")
    ]
    assert read_tdmrep(
        json.dumps(
            [
                {
                    "location": "/policies/*",
                    "tdm-reservation": 1,
                    "tdm-policy": "https://example.com/policy.json",
                },
                {"location": "/", "tdm-reservation": "0"},
            ]
        )
    ) == [
        TdmRule("/policies/*", "1", "https://example.com/policy.json"),
        TdmRule("/", "0"),
    ]


@pytest.mark.parametrize(
    "text",
    [
        None,
        "",
        "not json",
        '{"location": "/", "tdm-reservation": 1}',
        '[{"tdm-reservation": 1}]',
        '[{"location": "/"}]',
        '[{"location": "/", "tdm-reservation": 2}]',
        '[{"location": "/", "tdm-reservation": true}]',
        '[{"location": "", "tdm-reservation": 1}]',
        "[1, 2]",
        "[" * 5000 + "]" * 5000,
    ],
)
def test_what_is_no_rule_is_passed_over(text):
    assert read_tdmrep(text) == []


def test_a_hostile_file_is_read_only_so_far():
    many = json.dumps(
        [{"location": f"/{n}", "tdm-reservation": 1} for n in range(5000)]
    )
    assert len(read_tdmrep(many)) == 1000


def test_the_first_rule_that_matches_is_the_one_as_the_report_says():
    """Unlike robots.txt: the first in sequence, not the longest pattern."""
    rules = [TdmRule("/", "0"), TdmRule("/private/*", "1")]
    assert rule_for(rules, f"{ROOT}/private/a") == TdmRule("/", "0")
    rules = [TdmRule("/*.pdf$", "1"), TdmRule("/", "0")]
    assert rule_for(rules, f"{ROOT}/a.pdf").reservation == "1"
    assert rule_for(rules, f"{ROOT}/a.pdf?x=1").reservation == "0"
    assert rule_for([TdmRule("/x", "1")], f"{ROOT}/y") is None


# -- the page's reservation, from all three -----------------------------------------


def test_the_header_supersedes_the_file_and_the_meta_tag_both():
    file_ = [TdmRule("/", "1", "https://example.com/file-policy")]
    plain = rights("<html></html>")
    assert reservation(file_, f"{ROOT}/p", plain) == Reservation(
        True, "https://example.com/file-policy", "/.well-known/tdmrep.json"
    )
    header = rights("<html></html>", {"TDM-Reservation": "0"})
    assert reservation(file_, f"{ROOT}/p", header) == Reservation(
        False, "https://example.com/file-policy", "header"
    )
    meta = rights(f"<html><head>{RESERVED}</head></html>", {"TDM-Reservation": "0"})
    assert reservation(file_, f"{ROOT}/p", meta) == Reservation(
        True, "https://example.com/file-policy", "meta"
    )


def test_an_absent_value_resets_nothing_and_a_policy_alone_reserves_nothing():
    file_ = [TdmRule("/", "1")]
    policy_only = rights(
        '<html><head><meta name="tdm-policy" content="https://e.com/p"></head></html>'
    )
    found = reservation(file_, f"{ROOT}/p", policy_only)
    assert found == Reservation(True, "https://e.com/p", "/.well-known/tdmrep.json")
    assert reservation([], f"{ROOT}/p", policy_only) is None
    assert reservation([], f"{ROOT}/p", rights("<html></html>")) is None
    assert reservation([], None, rights(f"<html><head>{RESERVED}</head></html>")) == (
        Reservation(True, None, "meta")
    )


def test_a_value_that_is_not_zero_or_one_reserves_nothing_either_way():
    odd = rights(
        '<html><head><meta name="tdm-reservation" content="yes"></head></html>'
    )
    assert reservation([TdmRule("/", "0")], f"{ROOT}/p", odd).reserved is False


# -- reading the file from the site --------------------------------------------------


def test_the_file_is_read_from_the_well_known_place():
    def rung(url):
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="", status=404, rung="http")
        body = '[{"location": "/", "tdm-reservation": 1}]'
        return Fetched(url=url, html=body, status=200, rung="http")

    read = read_tdmrep_file(f"{ROOT}/deep/page", rung=rung)
    assert read.url == f"{ROOT}/.well-known/tdmrep.json"
    assert read_tdmrep(read.text) == [TdmRule("/", "1")]


def test_the_file_is_left_alone_where_robots_txt_refuses_it():
    def rung(url):
        if url.endswith("/robots.txt"):
            text = "User-agent: *\nDisallow: /.well-known/"
            return Fetched(url=url, html=text, status=200, rung="http")
        raise AssertionError("the file should not be asked for")

    read = read_tdmrep_file(f"{ROOT}/p", rung=rung)
    assert read.text is None and "disallows" in read.error
    asked = read_tdmrep_file(f"{ROOT}/p", rung=rung, obey_robots=False)
    assert "should not be asked for" in asked.error, "without robots, it is asked for"


# -- respecting it on the command line ----------------------------------------


def test_respect_tdm_refuses_a_page_that_reserves_its_rights(tmp_path):
    reserved = tmp_path / "reserved.html"
    reserved.write_text(
        f"<html><head>{RESERVED}<title>T</title></head></html>", encoding="utf-8"
    )
    refused = CliRunner().invoke(main, ["extract", str(reserved), "--respect", "tdm"])
    assert refused.exit_code == 2
    assert "reserves its text and data mining rights (TDMRep, by its meta)" in (
        refused.stderr
    )
    read = CliRunner().invoke(main, ["extract", str(reserved)])
    assert read.exit_code == 0, "without --respect, the page is read"


def test_respect_tdm_reads_the_sites_file_for_a_fetched_page(monkeypatch):
    def fetch_url(url, **kwargs):
        return Fetched(
            url=url,
            html="<html><head><title>T</title></head></html>",
            status=200,
            rung="http",
        )

    def the_file(url, obey_robots=True, **kwargs):
        from sluicer.audit.report import SiteFile

        return SiteFile(
            f"{ROOT}/.well-known/tdmrep.json",
            status=200,
            text=json.dumps(
                [
                    {
                        "location": "/p",
                        "tdm-reservation": 1,
                        "tdm-policy": "https://e.com/x",
                    }
                ]
            ),
        )

    monkeypatch.setattr("sluicer.cli.source.fetch_url", fetch_url)
    monkeypatch.setattr("sluicer.fetch.site.read_tdmrep_file", the_file)
    refused = CliRunner().invoke(main, ["extract", f"{ROOT}/p", "--respect", "tdm"])
    assert refused.exit_code == 2
    assert "by its /.well-known/tdmrep.json, policy https://e.com/x" in refused.stderr
    other = CliRunner().invoke(main, ["extract", f"{ROOT}/q", "--respect", "tdm"])
    assert other.exit_code == 0


# -- respecting it in a crawl -------------------------------------------------------


def _site():
    return FakeWeb(
        {
            f"{ROOT}/": page("Home", "/open", "/private/a", "/said"),
            f"{ROOT}/open": page("Open"),
            f"{ROOT}/private/a": page("Private"),
            f"{ROOT}/said": page("Said", extra=RESERVED),
            f"{ROOT}/.well-known/tdmrep.json": (
                200,
                '[{"location": "/private/*", "tdm-reservation": 1}]',
                {"content-type": "application/json"},
            ),
        }
    )


def test_a_crawl_that_respects_tdm_gives_reserved_pages_as_errors():
    fake = _site()
    pages = list(
        crawl(
            f"{ROOT}/",
            web=fake.web(),
            clock=fake.clock,
            sleep=fake.clock.sleep,
            min_delay=0.5,
            concurrency=1,
            respect_tdm=True,
        )
    )
    verdicts = {p.url: (p.error.code if p.error else "ok") for p in pages}
    assert verdicts == {
        f"{ROOT}/": "ok",
        f"{ROOT}/open": "ok",
        f"{ROOT}/private/a": "tdm_reserved",
        f"{ROOT}/said": "tdm_reserved",
    }
    assert fake.asked().count(f"{ROOT}/.well-known/tdmrep.json") == 1, "once a site"
    reserved = next(p for p in pages if p.url == f"{ROOT}/private/a")
    assert reserved.extraction is None and "by its /.well-known/tdmrep.json" in (
        reserved.error.message
    )


def test_a_crawl_that_does_not_respect_tdm_reads_everything_and_asks_for_no_file():
    fake = _site()
    pages = list(
        crawl(
            f"{ROOT}/",
            web=fake.web(),
            clock=fake.clock,
            sleep=fake.clock.sleep,
            min_delay=0.5,
            concurrency=1,
        )
    )
    assert all(p.ok for p in pages)
    assert f"{ROOT}/.well-known/tdmrep.json" not in fake.asked()


def test_a_batch_respects_it_too_and_a_file_that_fails_holds_no_rules():
    fake = _site()
    pages = list(
        extract_many(
            [f"{ROOT}/private/a", f"{ROOT}/open"],
            web=fake.web(),
            clock=fake.clock,
            sleep=fake.clock.sleep,
            min_delay=0.5,
            respect_tdm=True,
        )
    )
    assert [p.error.code if p.error else "ok" for p in pages] == ["tdm_reserved", "ok"]
    broken = FakeWeb(
        {
            f"{ROOT}/open": page("Open"),
            f"{ROOT}/.well-known/tdmrep.json": (500, "oops", {}),
        }
    )
    [only] = list(
        extract_many(
            [f"{ROOT}/open"],
            web=broken.web(),
            clock=broken.clock,
            sleep=broken.clock.sleep,
            respect_tdm=True,
        )
    )
    assert only.ok


def test_sluicer_crawl_takes_respect_on_the_command_line(monkeypatch):
    seen = {}

    def crawl_site(*args, **kwargs):
        seen.update(kwargs)
        raise ValueError("stop here")

    monkeypatch.setattr("sluicer.cli.crawl_site", crawl_site)
    CliRunner().invoke(main, ["crawl", f"{ROOT}/", "--respect", "tdm"])
    assert seen["respect_tdm"] is True


# -- for an agent ---------------------------------------------------------------------


def test_an_agent_that_respects_tdm_is_told_the_page_is_reserved(monkeypatch):
    from test_mcp_server import fake_mcp

    registered = fake_mcp(monkeypatch)
    from sluicer.mcp_server import build_server

    build_server()
    html = f"<html><head>{RESERVED}<title>T</title></head></html>"
    reserved = registered["extract_declared"](html, respect_tdm=True)
    assert reserved["ok"] is False
    assert reserved["error"]["code"] == "tdm_reserved"
    assert reserved["error"]["retryable"] is False
    assert registered["extract_declared"](html)["ok"] is True
    text = registered["page_markdown"](html, respect_tdm=True)
    assert text["error"]["code"] == "tdm_reserved"


def test_the_audit_says_whether_a_page_reserves_its_rights():
    from sluicer.audit import Site, SiteFile, audit

    site = Site(
        SiteFile(f"{ROOT}/robots.txt", status=404),
        SiteFile(f"{ROOT}/llms.txt", status=404),
        SiteFile(f"{ROOT}/llms-full.txt", status=404),
        SiteFile(
            f"{ROOT}/.well-known/tdmrep.json",
            status=200,
            text='[{"location": "/", "tdm-reservation": 1}]',
        ),
    )
    audited = audit("<html></html>", url=f"{ROOT}/p", site=site)
    assert audited.tdm == Reservation(True, None, "/.well-known/tdmrep.json")
    assert audit(f"<html><head>{RESERVED}</head></html>").tdm == Reservation(
        True, None, "meta"
    )
    assert audit("<html></html>").tdm is None
    from sluicer.cli.audit import _audit_report

    report = _audit_report(f"{ROOT}/p", audited, None, True, False)
    assert (
        "tdm       text and data mining reserved (TDMRep, by its "
        "/.well-known/tdmrep.json)"
    ) in report
    extracted = sluicer.extract(f"<html><head>{RESERVED}</head></html>")
    assert audit(extracted).tdm == Reservation(True, None, "meta")


def test_a_crawl_asks_for_no_file_robots_txt_refuses_and_survives_a_failing_one():
    fake = _site()
    fake.pages[f"{ROOT}/robots.txt"] = "User-agent: *\nDisallow: /.well-known/"
    pages = list(
        extract_many(
            [f"{ROOT}/private/a"],
            web=fake.web(),
            clock=fake.clock,
            sleep=fake.clock.sleep,
            respect_tdm=True,
        )
    )
    assert pages[0].ok, "the file was refused, and holds no rules"
    assert f"{ROOT}/.well-known/tdmrep.json" not in fake.asked()

    failing = _site()
    web = failing.web()

    def get(url, redirects=None):
        if url.endswith("tdmrep.json"):
            raise OSError("connection reset")
        return failing.get(url, redirects)

    web = type(web)(rungs=web.rungs, read=web.read, get=get)
    [only] = list(
        extract_many(
            [f"{ROOT}/open"],
            web=web,
            clock=failing.clock,
            sleep=failing.clock.sleep,
            respect_tdm=True,
        )
    )
    assert only.ok


def test_the_file_is_read_over_the_http_rung_by_default(monkeypatch):
    built = {}

    def http_rung(allow_private, resolve, max_bytes, error=None, allow_empty=False):
        built.update(allow_private=allow_private, allow_empty=allow_empty)

        def rung(url):
            return Fetched(url=url, html="", status=404, rung="http")

        return rung

    monkeypatch.setattr("sluicer.fetch.site.http_rung", http_rung)
    read = read_tdmrep_file(f"{ROOT}/p", allow_private=False)
    assert read.status == 404
    assert built == {"allow_private": False, "allow_empty": True}


def test_an_agent_is_refused_by_the_sites_file_for_a_fetched_page(monkeypatch):
    from sluicer.audit.report import SiteFile
    from test_mcp_server import fake_fetch, fake_mcp

    registered = fake_mcp(monkeypatch)
    fake_fetch(monkeypatch, landed_on=f"{ROOT}/p", html="<html><title>T</title></html>")
    monkeypatch.setattr(
        "sluicer.fetch.site.read_tdmrep_file",
        lambda url, **kwargs: SiteFile(
            f"{ROOT}/.well-known/tdmrep.json",
            status=200,
            text='[{"location": "/", "tdm-reservation": 1}]',
        ),
    )
    from sluicer.mcp_server import build_server

    build_server()
    refused = registered["extract_declared"](f"{ROOT}/p", respect_tdm=True)
    assert refused["error"]["code"] == "tdm_reserved"
    assert refused["error"]["url"] == f"{ROOT}/p"
