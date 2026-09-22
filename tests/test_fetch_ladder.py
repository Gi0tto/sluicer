import pytest

from sluicer.fetch.ladder import RobotsRefused, fetch
from sluicer.fetch.result import Fetched

RICH = (
    '<html><head><script type="application/ld+json">'
    '{"@type":"Product","name":"Brake pad set"}</script></head>'
    "<body>" + ("Real content. " * 40) + "</body></html>"
)
REFUSED = "<html><body>Forbidden</body></html>"


def rung(name, html, status=200):
    calls = []

    def go(url):
        calls.append(url)
        return Fetched(url=url, html=html, status=status, rung=name)

    go.calls = calls
    return go


def test_the_cheapest_rung_is_enough_and_the_others_never_run():
    http = rung("http", RICH)
    browser = rung("browser", RICH)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "http"
    assert result.climbs == []
    assert browser.calls == []


def test_a_refusal_climbs_once_and_records_why():
    http = rung("http", REFUSED, status=403)
    browser = rung("browser", RICH)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "browser"
    assert len(result.climbs) == 1
    assert result.climbs[0].from_rung == "http"
    assert result.climbs[0].to_rung == "browser"
    assert "403" in result.climbs[0].reason


def test_the_last_rung_is_returned_even_when_it_is_still_poor():
    http = rung("http", REFUSED, status=403)
    browser = rung("browser", REFUSED, status=403)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "browser"
    assert len(result.climbs) == 1


def test_an_empty_ladder_is_a_programming_error():
    with pytest.raises(ValueError):
        fetch("https://example.com", rungs=[])


def test_a_rung_that_raises_climbs_to_the_next():
    def http_raises(url):
        raise ConnectionError("connection refused")

    http_raises.calls = []
    browser = rung("browser", RICH)

    result = fetch("https://example.com", rungs=[("http", http_raises), ("browser", browser)])

    assert result.rung == "browser"
    assert len(result.climbs) == 1
    assert result.climbs[0].from_rung == "http"
    assert result.climbs[0].to_rung == "browser"
    assert "connection refused" in result.climbs[0].reason


def test_a_raising_last_rung_propagates():
    def last_rung_raises(url):
        raise TimeoutError("timed out")

    last_rung_raises.calls = []

    with pytest.raises(TimeoutError):
        fetch("https://example.com", rungs=[("single", last_rung_raises)])


def test_two_climbs_are_recorded_in_order():
    http = rung("http", REFUSED, status=403)
    browser = rung("browser", REFUSED, status=403)
    headless = rung("headless", RICH)

    result = fetch(
        "https://example.com",
        rungs=[("http", http), ("browser", browser), ("headless", headless)],
    )

    assert result.rung == "headless"
    assert len(result.climbs) == 2
    assert result.climbs[0].from_rung == "http"
    assert result.climbs[0].to_rung == "browser"
    assert result.climbs[1].from_rung == "browser"
    assert result.climbs[1].to_rung == "headless"


def test_a_refusal_stops_the_ladder_before_the_first_rung():
    http = rung("http", RICH)

    with pytest.raises(RobotsRefused):
        fetch(
            "https://example.com/private/p",
            rungs=[("http", http)],
            robots_reader=lambda url: "User-agent: Sluicer\nDisallow: /private/\n",
        )

    assert http.calls == []


def test_a_site_with_no_robots_is_fetched():
    http = rung("http", RICH)

    result = fetch(
        "https://example.com/p", rungs=[("http", http)], robots_reader=lambda url: None
    )

    assert result.rung == "http"


def test_robots_can_be_turned_off_deliberately():
    http = rung("http", RICH)

    result = fetch(
        "https://example.com/private/p",
        rungs=[("http", http)],
        obey_robots=False,
        robots_reader=lambda url: "User-agent: Sluicer\nDisallow: /private/\n",
    )

    assert result.rung == "http"


def test_the_default_reader_takes_the_text_out_of_the_markup():
    """The real rung wraps a plain-text robots.txt body in HTML.

    Measured against httpbin.org/robots.txt by the person reviewing this
    round: scrapling's ``Fetched.html`` for a plain-text response is not the
    bare directives, it is
    ``<html><body>User-agent: *\\nDisallow: /deny\\n</body></html>``. A
    reader that hands that straight to protego gets a first "line" of
    ``<html><body>User-agent: *``, which protego does not recognise as a
    directive, so it parses no rules at all and allows everything -- the
    exact defect this test is written to catch.
    """
    from sluicer.fetch.ladder import _default_robots_reader

    wrapped_rung = rung(
        "http", "<html><body>User-agent: *\nDisallow: /deny\n</body></html>"
    )
    read = _default_robots_reader(wrapped_rung)

    text = read("https://example.com/robots.txt")

    assert text == "User-agent: *\nDisallow: /deny\n"


def test_a_site_that_refuses_us_is_obeyed_through_the_real_reader_shape():
    """Drive ``fetch`` end to end with a robots response shaped like the real rung's.

    This is the test that would have caught the HTML-wrapping defect: every
    other robots test in this file hands ``robots_reader`` plain text
    directly, which is what a sensible fake returns but not what the real
    "http" rung actually produces. Here the fake rung returns HTML for both
    the robots file and the page, exactly as scrapling does, and only the
    default reader -- the one production actually uses -- stands between
    them.
    """
    calls: list[str] = []

    def http(url: str) -> Fetched:
        calls.append(url)
        if url.endswith("/robots.txt"):
            return Fetched(
                url=url,
                html="<html><body>User-agent: *\nDisallow: /deny\n</body></html>",
                status=200,
                rung="http",
            )
        return Fetched(url=url, html=RICH, status=200, rung="http")

    with pytest.raises(RobotsRefused):
        fetch("https://example.com/deny", rungs=[("http", http)])


def test_a_robots_file_that_answers_200_is_read_as_the_rules_it_publishes():
    """2xx is the only status whose body is a set of rules."""
    from sluicer.fetch.ladder import _default_robots_reader

    read = _default_robots_reader(rung("http", "User-agent: *\nDisallow: /deny\n"))

    assert read("https://example.com/robots.txt") == "User-agent: *\nDisallow: /deny\n"


def test_a_robots_file_that_404s_means_no_rules_were_published():
    """RFC 9309: 4xx means the site publishes no rules, so nothing is refused.

    The status used to be ignored entirely, which happened to give the right
    answer here and the wrong one for every other failing status.
    """
    from sluicer.fetch.ladder import _default_robots_reader

    read = _default_robots_reader(rung("http", "<html><body>Not found</body></html>", status=404))

    assert read("https://example.com/robots.txt") is None


def test_a_robots_file_that_5xxs_is_read_as_a_full_disallow():
    """RFC 9309: 5xx means the rules are unavailable, and that means stay out.

    This is the case the swallowed status got exactly backwards. A 503 body
    was read as "nothing to read", which this module treats as "no rules were
    published, so go ahead" -- and the cache then pinned that answer. A site
    under load was a site with no rules.

    Asserted by effect rather than by spelling: what matters is that the text
    the reader returns refuses everything when the real gate parses it.
    """
    from sluicer.fetch.identity import robots_allows
    from sluicer.fetch.ladder import _default_robots_reader

    read = _default_robots_reader(
        rung("http", "<html><body>Service unavailable</body></html>", status=503)
    )

    text = read("https://example.com/robots.txt")

    assert text is not None, "a 5xx was read as nothing to read"
    assert robots_allows("https://example.com/anything", read=lambda url: text) is False


def test_a_rung_that_raises_still_means_there_is_nothing_to_read():
    """A connection that never opened carries no status and refuses nothing.

    The site did not answer at all, so it did not tell us to stay out. That
    is the one case where swallowing really is right, and it has to survive
    the statuses being read.
    """
    from sluicer.fetch.ladder import _default_robots_reader

    def never_opened(url):
        raise ConnectionError("connection refused")

    read = _default_robots_reader(never_opened)

    assert read("https://example.com/robots.txt") is None


def test_a_site_whose_robots_is_unavailable_is_not_fetched():
    """End to end: a 503 on robots.txt stops the ladder before the page."""
    calls: list[str] = []

    def http(url: str) -> Fetched:
        calls.append(url)
        if url.endswith("/robots.txt"):
            return Fetched(
                url=url,
                html="<html><body>Service unavailable</body></html>",
                status=503,
                rung="http",
            )
        return Fetched(url=url, html=RICH, status=200, rung="http")

    with pytest.raises(RobotsRefused):
        fetch("https://example.com/p", rungs=[("http", http)])

    assert calls == ["https://example.com/robots.txt"]
