import pytest

from sluicer.fetch.ladder import AddressRefused, FetchFailed, RobotsRefused, fetch
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

    result = fetch(
        "https://example.com",
        rungs=[("http", http_raises), ("browser", browser)],
        obey_robots=False,
    )

    assert result.rung == "browser"
    assert len(result.climbs) == 1
    assert result.climbs[0].from_rung == "http"
    assert result.climbs[0].to_rung == "browser"
    assert "connection refused" in result.climbs[0].reason


def test_a_ladder_where_every_rung_raised_fails_with_what_each_one_said():
    def last_rung_raises(url):
        raise TimeoutError("timed out")

    with pytest.raises(FetchFailed) as raised:
        fetch(
            "https://example.com",
            rungs=[("single", last_rung_raises)],
            obey_robots=False,
        )

    assert "timed out" in str(raised.value)
    assert isinstance(raised.value.__cause__, TimeoutError)


def test_a_failed_climb_keeps_the_page_the_cheaper_rung_brought_back():
    """A fresh install has no browser: climbing then failed, and the good page
    the http rung already had was thrown away for a traceback."""
    shell = (
        '<html><body><div id="root"></div><script src="/app.js"></script></body></html>'
    )
    http = rung("http", shell)

    def browser(url):
        raise RuntimeError("Executable doesn't exist at /ms-playwright/chromium")

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "http"
    assert result.html == shell
    assert [(c.from_rung, c.to_rung) for c in result.climbs] == [
        ("http", "browser"),
        ("browser", "http"),
    ]
    assert "Executable doesn't exist" in result.climbs[1].reason


def test_chrome_in_the_head_does_not_pass_for_a_page_that_declared_something():
    """A React shell whose only tag is theme-color used to count as a page that
    had delivered its data, and so never climbed."""
    shell = (
        '<html><head><meta name="theme-color" content="#fff"></head><body>'
        '<div id="root"></div>'
        + '<script src="/a.js"></script>' * 80
        + "</body></html>"
    )
    http = rung("http", shell)
    browser = rung("browser", RICH)

    result = fetch("https://example.com", rungs=[("http", http), ("browser", browser)])

    assert result.rung == "browser"


def test_a_redirect_to_another_host_asks_that_host_s_robots_too():
    def http(url):
        if url.endswith("/robots.txt"):
            refusing = "User-agent: *\nDisallow: /" if "other" in url else ""
            return Fetched(url=url, html=refusing, status=200, rung="http")
        return Fetched(
            url="https://other.example/landing", html=RICH, status=200, rung="http"
        )

    with pytest.raises(RobotsRefused) as raised:
        fetch("https://example.com/p", rungs=[("http", http)])

    assert raised.value.url == "https://other.example/landing"


def test_a_private_address_is_refused_when_the_caller_says_so():
    http = rung("http", RICH)

    for url in (
        "http://127.0.0.1:8080/admin",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.7/",
        "http://[::1]/",
        "file:///etc/passwd",
    ):
        with pytest.raises(AddressRefused):
            fetch(url, rungs=[("http", http)], obey_robots=False, allow_private=False)
    assert http.calls == []


def test_a_redirect_into_a_private_address_is_not_returned_when_refused():
    def http(url):
        return Fetched(
            url="http://127.0.0.1/secret", html=RICH, status=200, rung="http"
        )

    with pytest.raises(AddressRefused):
        fetch(
            "https://example.com/p",
            rungs=[("http", http)],
            obey_robots=False,
            allow_private=False,
            resolve=lambda host: ["93.184.215.14"],
        )


def test_a_name_that_resolves_to_this_machine_is_refused_too():
    http = rung("http", RICH)

    with pytest.raises(AddressRefused) as raised:
        fetch(
            "https://rebind.example/p",
            rungs=[("http", http)],
            obey_robots=False,
            allow_private=False,
            resolve=lambda host: ["93.184.215.14", "127.0.0.1"],
        )

    assert "127.0.0.1" in str(raised.value)
    assert http.calls == []


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

    # The whole point of the test: the robots file was read once and the page
    # the site refused was never asked for. ``calls`` was collected here and
    # never asserted, which left "we obeyed" and "we fetched it anyway and
    # then raised" indistinguishable.
    assert calls == ["https://example.com/robots.txt"]


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

    read = _default_robots_reader(
        rung("http", "<html><body>Not found</body></html>", status=404)
    )

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


def test_a_robots_file_that_cannot_be_reached_is_a_refusal_that_says_why():
    """RFC 9309, 2.3.1.4: unreachable because of a network error is a complete
    disallow. It used to be read as permission, so a robots.txt that timed out
    let the page be fetched."""

    def http(url):
        if url.endswith("/robots.txt"):
            raise TimeoutError("timed out after 20 seconds")
        return Fetched(url=url, html=RICH, status=200, rung="http")

    with pytest.raises(RobotsRefused) as raised:
        fetch("https://slow.example/p", rungs=[("http", http)])

    assert "could not be read" in str(raised.value)
    assert "timed out" in str(raised.value)


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


def test_stealth_appends_the_stealth_rung_when_a_caller_asks(monkeypatch):
    """One of the branch's three promises, exercised at the seam that keeps it.

    ``stealth=True`` was implemented in ``fetch`` and tested nowhere: the rung
    itself has tests in ``test_scrapling_rungs.py``, but nothing asserted that
    asking for it actually puts it on the end of the ladder. The rungs are
    injected, and ``stealth_rung`` is patched where ``fetch`` imports it from,
    so nothing here needs scrapling.
    """
    http = rung("http", REFUSED, status=403)
    stealth = rung("stealth", RICH)
    monkeypatch.setattr(
        "sluicer.fetch.scrapling_rungs.stealth_rung", lambda: ("stealth", stealth)
    )

    result = fetch(
        "https://example.com/p",
        rungs=[("http", http)],
        stealth=True,
        robots_reader=lambda url: None,
    )

    assert result.rung == "stealth"
    assert stealth.calls == ["https://example.com/p"]
    assert [climb.to_rung for climb in result.climbs] == ["stealth"]


def test_without_the_flag_the_stealth_rung_is_never_even_built(monkeypatch):
    """Climbing from announcing ourselves to hiding is a decision, not a fallback.

    Asserted by making ``stealth_rung()`` raise: a ladder that ends at the
    last declared rung must never reach for it, not even to build it.
    """

    def must_not_be_built():
        raise AssertionError("stealth_rung() was built for a caller who never asked")

    monkeypatch.setattr("sluicer.fetch.scrapling_rungs.stealth_rung", must_not_be_built)
    http = rung("http", REFUSED, status=403)

    result = fetch(
        "https://example.com/p", rungs=[("http", http)], robots_reader=lambda url: None
    )

    assert result.rung == "http"
    assert result.climbs == []
