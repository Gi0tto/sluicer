"""What a site serves beside a page: the AI agents robots.txt admits, llms.txt.

protego is the autouse fake of ``conftest.py``, the standard library's parser
behind protego's call, so Allow and Disallow are really decided; the real
protego is asked the same questions by the with-extras CI job.
"""

import pytest

from sluicer.audit import Site, SiteFile, audit, crawlers, llmstxt
from sluicer.fetch.address import AddressRefused
from sluicer.fetch.result import Fetched, ResponseTooLarge
from sluicer.fetch.site import read_site
from test_fetch_guards import fake_curl

URL = "https://example.com/blog/post"

ROBOTS = """# A site that has an opinion
User-agent: GPTBot
Disallow: /

User-agent: anthropic-ai
Disallow: /

User-agent: Perplexity-User
Disallow: /blog/

User-agent: *
Allow: /
"""


def site(robots=ROBOTS, status=200, llms=None, llms_status=404, full_status=404):
    return Site(
        SiteFile("https://example.com/robots.txt", status=status, text=robots),
        SiteFile("https://example.com/llms.txt", status=llms_status, text=llms),
        SiteFile("https://example.com/llms-full.txt", status=full_status),
    )


def by_agent(result):
    return {verdict.agent: verdict for verdict in result.crawlers}


def test_each_agent_is_judged_by_the_group_that_applies_to_it():
    verdicts = by_agent(audit("<html></html>", url=URL, site=site()))

    assert verdicts["GPTBot"].allowed is False
    assert verdicts["GPTBot"].group == "gptbot"
    assert verdicts["ClaudeBot"].allowed is True
    assert verdicts["ClaudeBot"].group == "*"
    assert verdicts["Perplexity-User"].allowed is False
    assert verdicts["Perplexity-User"].honours_robots is False
    assert verdicts["OAI-SearchBot"].allowed is True


def test_a_name_no_vendor_documents_is_reported_as_one():
    result = audit("<html></html>", url=URL, site=site())

    assert result.other_agents == ["anthropic-ai"]


def test_every_agent_comes_from_its_vendors_page_with_a_use():
    for agent in crawlers.AGENTS:
        assert agent.doc in {url for _vendor, url in crawlers.VENDOR_PAGES}, agent.token
        assert agent.use in crawlers.USES, agent.token
        assert agent.note.endswith("."), agent.token
    tokens = [agent.token.lower() for agent in crawlers.AGENTS]
    assert len(tokens) == len(set(tokens))
    for undocumented in ("anthropic-ai", "cohere-ai", "bytespider"):
        assert undocumented not in tokens


def test_a_site_that_publishes_no_robots_txt_allows_everyone():
    result = audit("<html></html>", url=URL, site=site(robots=None, status=404))

    assert {verdict.allowed for verdict in result.crawlers} == {True}
    assert {verdict.group for verdict in result.crawlers} == {None}
    assert result.robots_txt.status == 404
    assert result.robots_txt.text is None


@pytest.mark.parametrize("status", [503, None])
def test_a_robots_txt_that_could_not_be_read_decides_nothing(status):
    result = audit("<html></html>", url=URL, site=site(robots=None, status=status))

    assert {verdict.allowed for verdict in result.crawlers} == {None}


def test_an_empty_robots_txt_allows_everyone():
    result = audit("<html></html>", url=URL, site=site(robots=""))

    assert {verdict.allowed for verdict in result.crawlers} == {True}


def test_the_deciding_group_is_protegos_longest_match_at_a_boundary():
    names = ["*", "google", "google-extended", "bot"]

    assert crawlers.deciding_group("Google-Extended", names) == "google-extended"
    assert crawlers.deciding_group("Google-Agent", names) == "google"
    # "bot" sits inside "gptbot" but not at a boundary: the catch-all decides.
    assert crawlers.deciding_group("GPTBot", names) == "*"
    assert crawlers.deciding_group("GPTBot", ["bot"]) is None


def test_user_agent_lines_are_read_as_robots_txt_writes_them():
    text = (
        "user-agent: A # first\nUSER-AGENT:b\nUser-agent:\nDisallow: /\nuser-agent: a"
    )

    assert crawlers.user_agents(text) == ["a", "b"]


def test_verdicts_need_protego(absent):
    absent("protego")
    from sluicer.fetch.scrapling_rungs import FetchExtraMissing

    with pytest.raises(FetchExtraMissing, match=r"sluicer\[fetch\]"):
        audit("<html></html>", url=URL, site=site())


# -- llms.txt -------------------------------------------------------------------

GOOD = """\ufeff# FastHTML

> FastHTML is a python library for server-rendered hypermedia applications.

Important notes:

- It is *not* compatible with FastAPI syntax.

```
# not a heading, inside a fence
```

## Docs

- [Quick start](https://fastht.ml/docs/quickstart.html.md): A brief overview
- [HTMX reference](https://github.com/bigskysoftware/htmx/blob/master/www/content/reference.md)
  continued on a second line

## Optional

- [Starlette docs](https://example.com/starlette.md)
"""


def read(text, status=200):
    return llmstxt.read_llms_txt(SiteFile("https://e.com/llms.txt", status, text))


def test_an_llms_txt_that_keeps_to_the_format_has_nothing_wrong():
    report = read(GOOD)

    assert report.present is True
    assert report.name == "FastHTML"
    assert report.summary.startswith("FastHTML is a python library")
    assert [(s.name, s.links) for s in report.sections] == [
        ("Docs", 2),
        ("Optional", 1),
    ]
    assert report.links == 3
    assert report.findings == []


def test_an_llms_txt_without_its_name_is_an_error():
    report = read("> A summary\n\n## Docs\n- [a](https://a)\n")

    first = report.findings[0]
    assert (first.code, first.severity) == ("llms-no-name", "error")
    assert report.findings[0].rule == "https://llmstxt.org/"


def test_a_setext_heading_names_it_too():
    report = read("FastHTML\n========\n\n> Summary\n")

    assert report.name == "FastHTML"
    assert [f.code for f in report.findings] == ["llms-no-file-list"]
    assert report.findings[0].severity == "info"


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("# Name\n\nNo quote.\n", "llms-no-summary"),
        ("# Name\n> S\n### Deep\n", "llms-heading"),
        ("# Name\n> S\n# Again\n", "llms-second-h1"),
        (
            "# Name\n> S\n## Docs\n- a page, no link\n- [b](https://b)\n",
            "llms-not-a-link",
        ),
        ("# Name\n> S\n## Docs\nprose where a list belongs\n", "llms-not-a-list"),
        ("# Name\n> S\n## Docs\n\n## More\n- [b](https://b)\n", "llms-empty-section"),
    ],
)
def test_each_departure_from_the_format_is_named(text, code):
    report = read(text)

    found = [f for f in report.findings if f.severity != "info"]
    assert [f.code for f in found] == [code]
    assert found[0].severity == "warning"


def test_an_html_page_served_as_llms_txt_is_not_one():
    report = read("<!DOCTYPE html><html><body>Not found</body></html>")

    assert [(f.code, f.severity) for f in report.findings] == [("llms-html", "error")]


def test_an_absent_llms_txt_is_absent_not_wrong():
    report = read(None, status=404)

    assert (report.present, report.status, report.findings) == (False, 404, [])


def test_llms_full_txt_is_reported_by_presence_and_length():
    served = llmstxt.read_llms_full_txt(SiteFile("https://e.com/f", 200, "# All\n" * 3))
    html = llmstxt.read_llms_full_txt(
        SiteFile("https://e.com/f", 200, "<html>x</html>")
    )
    missing = llmstxt.read_llms_full_txt(SiteFile("https://e.com/f", error="refused"))

    assert (served.present, served.length, served.findings) == (True, 18, [])
    assert [f.code for f in html.findings] == ["llms-html"]
    assert (missing.present, missing.status) == (False, None)


def test_the_site_findings_count_in_the_audit():
    result = audit(
        "<html></html>", url=URL, site=site(llms="no heading", llms_status=200)
    )

    assert result.llms_txt.findings[0].code == "llms-no-name"
    assert result.errors == 1
    assert result.llms_full_txt.present is False


# -- Reading the site -----------------------------------------------------------


class Rung:
    """A rung that answers from a table, and remembers what it was asked."""

    def __init__(self, answers):
        self.answers = answers
        self.asked = []

    def __call__(self, url):
        self.asked.append(url)
        answer = self.answers.get(url, (404, ""))
        if isinstance(answer, Exception):
            raise answer
        status, body = answer
        return Fetched(url=url, html=body, status=status, rung="http")


def test_the_three_files_are_read_from_the_sites_root():
    rung = Rung(
        {
            "https://example.com/robots.txt": (200, "User-agent: *\nAllow: /\n"),
            "https://example.com/llms.txt": (200, "# Example\n"),
        }
    )

    read_back = read_site(URL, rung=rung)

    assert rung.asked == [
        "https://example.com/robots.txt",
        "https://example.com/llms.txt",
        "https://example.com/llms-full.txt",
    ]
    assert read_back.robots.text == "User-agent: *\nAllow: /\n"
    assert read_back.llms_txt.found and read_back.llms_txt.text == "# Example\n"
    assert (read_back.llms_full_txt.status, read_back.llms_full_txt.text) == (404, None)


def test_an_llms_file_robots_txt_refuses_to_sluicer_is_not_fetched():
    robots = "User-agent: Sluicer\nDisallow: /llms-full.txt\n"
    rung = Rung({"https://example.com/robots.txt": (200, robots)})

    read_back = read_site(URL, rung=rung)

    assert "https://example.com/llms-full.txt" not in rung.asked
    assert read_back.llms_full_txt.error == (
        "not fetched: the site's robots.txt disallows it"
    )
    assert read_back.llms_txt.status == 404


def test_without_robots_obedience_everything_is_fetched():
    robots = "User-agent: *\nDisallow: /\n"
    rung = Rung({"https://example.com/robots.txt": (200, robots)})

    read_site(URL, rung=rung, obey_robots=False)

    assert len(rung.asked) == 3


def test_an_unreadable_robots_txt_keeps_the_llms_files_unfetched():
    rung = Rung({"https://example.com/robots.txt": OSError("no route to host")})

    read_back = read_site(URL, rung=rung)

    assert rung.asked == ["https://example.com/robots.txt"]
    assert read_back.robots.error == "OSError: no route to host"
    assert "RFC 9309" in read_back.llms_txt.error


def test_a_file_too_heavy_is_one_that_could_not_be_read():
    rung = Rung(
        {
            "https://example.com/llms-full.txt": ResponseTooLarge(
                "https://example.com/llms-full.txt", 10
            )
        }
    )

    read_back = read_site(URL, rung=rung)

    assert "larger than 10 bytes" in read_back.llms_full_txt.error


def test_a_private_address_is_refused_not_reported():
    rung = Rung({"https://example.com/robots.txt": AddressRefused("x", "private")})

    with pytest.raises(AddressRefused):
        read_site(URL, rung=rung)


def test_the_default_rung_answers_an_empty_file_rather_than_failing(monkeypatch):
    """An empty robots.txt is an answer, allow-all; the ladder's rung refuses
    an empty page, and the site reader asks it not to."""
    fake_curl(monkeypatch, [(200, b"", {}), (200, b"# Example\n", {}), (404, b"", {})])

    read_back = read_site(URL)

    assert (read_back.robots.status, read_back.robots.text) == (200, "")
    assert read_back.llms_txt.text == "# Example\n"
    assert read_back.llms_full_txt.status == 404


def test_an_empty_llms_txt_has_no_name():
    report = read("")

    assert [f.code for f in report.findings] == [
        "llms-no-name",
        "llms-no-summary",
        "llms-no-file-list",
    ]
