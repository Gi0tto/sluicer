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


def test_the_default_reader_takes_the_text_out_of_a_browsers_markup():
    """A browser shows a plain-text robots.txt as an HTML document.

    Measured against httpbin.org/robots.txt when the cheapest rung was
    scrapling's: its ``Fetched.html`` for a plain-text response was
    ``<html><body>User-agent: *\\nDisallow: /deny\\n</body></html>``, and a
    reader handing that to protego got a first "line" of
    ``<html><body>User-agent: *``, parsed no rules and allowed everything.
    The cheapest rung is plain HTTP now; a ladder that starts at a browser
    still gets this shape, and only a whole document is read so.
    """
    from sluicer.fetch.ladder import robots_reader_from

    wrapped_rung = rung(
        "http", "<html><body>User-agent: *\nDisallow: /deny\n</body></html>"
    )
    read = robots_reader_from(wrapped_rung)

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


@pytest.mark.parametrize(
    "text",
    [
        "User-agent: *\nDisallow: /a<b\nDisallow: /private/\n",
        "# see <a href=x>\nUser-agent: *\nDisallow: /private/\n",
        "# <script>\nUser-agent: *\nDisallow: /private/\n",
        "User-agent: *\nDisallow: /q&amp;x\nDisallow: /private/\n",
        "\ufeffUser-agent: *\nDisallow: /private/\n",
    ],
)
def test_a_robots_txt_is_read_as_text_whatever_markup_its_lines_hold(text):
    """Read through the HTML parser, ``Disallow: /a<b`` opened a tag that
    swallowed every rule after it, and ``/private/`` was fetched; ``&amp;``
    became ``&``. A robots.txt is text, and only a BOM is taken off it."""
    from sluicer.fetch.identity import robots_refusal
    from sluicer.fetch.ladder import robots_reader_from

    read = robots_reader_from(rung("http", text))

    assert read("https://example.com/robots.txt") == text.lstrip("\ufeff")
    assert robots_refusal("https://example.com/private/x", read, cache={})


def test_a_robots_file_that_answers_200_is_read_as_the_rules_it_publishes():
    """2xx is the only status whose body is a set of rules."""
    from sluicer.fetch.ladder import robots_reader_from

    read = robots_reader_from(rung("http", "User-agent: *\nDisallow: /deny\n"))

    assert read("https://example.com/robots.txt") == "User-agent: *\nDisallow: /deny\n"


def test_a_robots_file_that_404s_means_no_rules_were_published():
    """RFC 9309: 4xx means the site publishes no rules, so nothing is refused.

    The status used to be ignored entirely, which happened to give the right
    answer here and the wrong one for every other failing status.
    """
    from sluicer.fetch.ladder import robots_reader_from

    read = robots_reader_from(
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
    from sluicer.fetch.ladder import robots_reader_from

    read = robots_reader_from(
        rung("http", "<html><body>Service unavailable</body></html>", status=503)
    )

    text = read("https://example.com/robots.txt")

    assert text is not None, "a 5xx was read as nothing to read"
    assert robots_allows("https://example.com/anything", read=lambda url: text) is False


def test_a_robots_file_that_cannot_be_reached_stops_the_fetch_and_says_so():
    """RFC 9309, 2.3.1.4: unreachable because of a network error is a complete
    disallow, so the page is never asked for. It used to be read as permission,
    so a robots.txt that timed out let the page be fetched. It is reported as
    the fetch failing, not as the site refusing us: a host that does not
    resolve has refused nothing."""
    calls = []

    def http(url):
        calls.append(url)
        if url.endswith("/robots.txt"):
            raise TimeoutError("timed out after 20 seconds")
        return Fetched(url=url, html=RICH, status=200, rung="http")

    with pytest.raises(FetchFailed) as raised:
        fetch("https://slow.example/p", rungs=[("http", http)])

    assert "robots.txt" in str(raised.value)
    assert "timed out" in str(raised.value)
    assert calls == ["https://slow.example/robots.txt"]


def test_an_unreachable_robots_file_is_asked_again_next_time():
    """One timeout must not keep a long-running server away for a day."""
    answers = iter([TimeoutError("timed out"), None])

    def http(url):
        if url.endswith("/robots.txt"):
            answer = next(answers)
            if isinstance(answer, Exception):
                raise answer
            return Fetched(url=url, html="", status=404, rung="http")
        return Fetched(url=url, html=RICH, status=200, rung="http")

    with pytest.raises(FetchFailed):
        fetch("https://flaky.example/p", rungs=[("http", http)])

    assert fetch("https://flaky.example/p", rungs=[("http", http)]).status == 200


def test_a_robots_file_that_answers_5xx_stops_the_fetch_and_says_so():
    """RFC 9309 puts a 5xx with a network error: unreadable, so nothing is
    fetched, and a 503 is a reason to try later rather than a rule."""

    def http(url):
        if url.endswith("/robots.txt"):
            return Fetched(url=url, html="busy", status=503, rung="http")
        return Fetched(url=url, html=RICH, status=200, rung="http")

    with pytest.raises(FetchFailed) as raised:
        fetch("https://busy.example/p", rungs=[("http", http)])

    assert "503" in str(raised.value)


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

    with pytest.raises(FetchFailed):
        fetch("https://example.com/p", rungs=[("http", http)])

    assert calls == ["https://example.com/robots.txt"]


def test_stealth_appends_the_stealth_rung_when_a_caller_asks(monkeypatch):
    """One of the branch's three promises, exercised at the seam that keeps it.

    ``stealth=True`` was implemented in ``fetch`` and tested nowhere: the rung
    itself has tests in ``test_stealth.py``, but nothing asserted that
    asking for it actually puts it on the end of the ladder. The rungs are
    injected, and ``stealth_rung`` is patched where ``fetch`` imports it from,
    so nothing here needs scrapling.
    """
    http = rung("http", REFUSED, status=403)
    stealth = rung("stealth", RICH)
    monkeypatch.setattr(
        "sluicer.fetch.stealth.stealth_rung",
        lambda *guarded: ("stealth", stealth),
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

    monkeypatch.setattr("sluicer.fetch.stealth.stealth_rung", must_not_be_built)
    http = rung("http", REFUSED, status=403)

    result = fetch(
        "https://example.com/p", rungs=[("http", http)], robots_reader=lambda url: None
    )

    assert result.rung == "http"
    assert result.climbs == []


CHALLENGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body>Checking your browser</body></html>"
)


def test_a_challenge_on_the_last_rung_is_the_site_refusing_not_a_page():
    """The ladder handed back its last rung's page whatever it was, and an MCP
    answer said ok: true about a waiting room."""
    from sluicer.fetch import SiteRefused

    http = rung("http", CHALLENGE)
    browser = rung("browser", CHALLENGE)

    with pytest.raises(SiteRefused, match="challenge page") as refused:
        fetch("https://example.com/p", rungs=[("http", http), ("browser", browser)])

    assert isinstance(refused.value, FetchFailed), "a caller of FetchFailed catches it"
    assert refused.value.url == "https://example.com/p"
    assert [(c.from_rung, c.to_rung) for c in refused.value.climbs] == [
        ("http", "browser")
    ]
    assert "'just a moment'" in refused.value.reason


def test_a_challenge_is_not_returned_when_the_rung_above_it_failed():
    """A fresh install has no browser: the cheaper page comes back, unless it
    is a challenge, which is not a page to come back with."""
    from sluicer.fetch import SiteRefused

    def no_browser(url):
        raise RuntimeError("no browser installed")

    http = rung("http", CHALLENGE)

    with pytest.raises(SiteRefused) as refused:
        fetch("https://example.com/p", rungs=[("http", http), ("browser", no_browser)])

    assert [(c.from_rung, c.to_rung) for c in refused.value.climbs] == [
        ("http", "browser"),
        ("browser", "http"),
    ]


def test_a_shell_on_the_last_rung_is_still_returned():
    """Only a challenge is a refusal: a small page is often simply small."""
    shell = "<html><body><div id=app></div><script src=a.js></script></body></html>"

    result = fetch(
        "https://example.com/p",
        rungs=[("http", rung("http", shell)), ("browser", rung("browser", shell))],
    )

    assert result.rung == "browser"


@pytest.mark.parametrize("body", [RICH, CHALLENGE])
def test_payment_required_is_an_answer_never_a_page_nor_a_reason_to_climb(body):
    """A 402 was read as the page: its body's records came back as the site's.
    Whatever the body looks like, no other rung is asked the same question,
    and nothing is paid."""
    from sluicer.fetch import PaymentRequired

    http = rung("http", body, status=402)
    browser = rung("browser", RICH)

    with pytest.raises(PaymentRequired, match="402") as refused:
        fetch("https://example.com/p", rungs=[("http", http), ("browser", browser)])

    assert isinstance(refused.value, FetchFailed)
    assert refused.value.url == "https://example.com/p"
    assert browser.calls == []


def test_payment_required_on_a_higher_rung_is_the_answer_too():
    from sluicer.fetch import PaymentRequired

    http = rung("http", REFUSED, status=403)
    browser = rung("browser", RICH, status=402)

    with pytest.raises(PaymentRequired) as refused:
        fetch("https://example.com/p", rungs=[("http", http), ("browser", browser)])

    assert [(c.from_rung, c.to_rung) for c in refused.value.climbs] == [
        ("http", "browser")
    ]


# -- the rung a site needed, remembered ------------------------------------------

SHELL = (
    '<html><head><script src="/app.js"></script></head>'
    '<body><div id="root"></div></body></html>'
)


def test_the_second_page_of_a_site_starts_at_the_rung_the_first_needed():
    """Measured on 0.7.0: a JS site crawled at 3.22 s a page, every document
    asked twice, once of plain HTTP to learn again what the last page taught."""
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    http = rung("http", SHELL)
    browser = rung("browser", RICH)
    ladder = [("http", http), ("browser", browser)]

    first = fetch(
        "https://shop.example/1", rungs=ladder, memory=memory, obey_robots=False
    )
    second = fetch(
        "https://www.shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert first.rung == second.rung == "browser"
    assert http.calls == ["https://shop.example/1"]
    assert browser.calls == ["https://shop.example/1", "https://www.shop.example/2"]
    assert [(c.from_rung, c.to_rung, c.seconds) for c in second.climbs] == [
        ("http", "browser", 0.0)
    ]
    assert "an earlier page of shop.example needed it" in second.climbs[0].reason
    assert first.climbs[0].reason in second.climbs[0].reason


def test_another_site_starts_at_the_bottom():
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    http = rung("http", SHELL)
    ladder = [("http", http), ("browser", rung("browser", RICH))]

    fetch("https://shop.example/1", rungs=ladder, memory=memory, obey_robots=False)
    fetch("https://other.example/1", rungs=ladder, memory=memory, obey_robots=False)

    assert http.calls == ["https://shop.example/1", "https://other.example/1"]


def test_a_rung_that_failed_teaches_nothing_about_the_site():
    """A timeout is the moment's, not the site's: only a page that needed more
    is remembered."""
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    tries = []

    def flaky(url):
        tries.append(url)
        if len(tries) == 1:
            raise ConnectionError("connection reset")
        return Fetched(url=url, html=RICH, status=200, rung="http")

    ladder = [("http", flaky), ("browser", rung("browser", RICH))]
    fetch("https://shop.example/1", rungs=ladder, memory=memory, obey_robots=False)
    second = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert second.rung == "http" and second.climbs == []


def test_a_remembered_rung_that_fails_is_forgotten_and_the_ladder_starts_again():
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    pages = {"https://shop.example/1": SHELL, "https://shop.example/2": RICH}

    def http(url):
        return Fetched(url=url, html=pages[url], status=200, rung="http")

    loads = []

    def browser(url):
        loads.append(url)
        if url.endswith("/2"):
            raise RuntimeError("the browser crashed")
        return Fetched(url=url, html=RICH, status=200, rung="browser")

    ladder = [("http", http), ("browser", browser)]
    fetch("https://shop.example/1", rungs=ladder, memory=memory, obey_robots=False)
    second = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )
    third = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert second.rung == "http"
    assert [(c.from_rung, c.to_rung) for c in second.climbs] == [
        ("http", "browser"),
        ("browser", "http"),
    ]
    assert "the browser crashed" in second.climbs[1].reason
    assert third.rung == "http" and third.climbs == []


def test_the_stealth_rung_is_never_remembered():
    """Disguise is asked for page by page; no memory makes a page go stealth."""
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    ladder = [
        ("http", rung("http", SHELL)),
        ("browser", rung("browser", SHELL)),
        ("stealth", rung("stealth", RICH)),
    ]
    fetch("https://shop.example/1", rungs=ladder, memory=memory, obey_robots=False)

    assert memory.recall("https://shop.example/2") is None


def test_a_remembered_rung_the_ladder_does_not_have_is_no_start():
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    memory.learn("https://shop.example/1", "browser", "it was a shell")
    http = rung("http", RICH)

    page = fetch(
        "https://shop.example/2",
        rungs=[("http", http)],
        memory=memory,
        obey_robots=False,
    )

    assert page.rung == "http" and page.climbs == []


def test_what_a_site_needed_is_forgotten_after_a_day_and_past_a_bound():
    from sluicer.fetch.ladder import RungMemory

    now = [0.0]
    memory = RungMemory(limit=2, clock=lambda: now[0])
    for site in ("a", "b", "c"):
        memory.learn(f"https://{site}.example/", "browser", "a shell")

    assert memory.recall("https://a.example/") is None
    assert memory.recall("https://c.example/") is not None
    now[0] = 24 * 60 * 60 + 1
    assert memory.recall("https://c.example/") is None


def test_the_default_ladder_remembers_for_the_process(monkeypatch):
    """Without injected rungs, the process's memory; with them, none unless
    handed one, so a test's sites never teach another's."""
    from sluicer.fetch.gate import GATE
    from sluicer.fetch.ladder import STICKY

    http = rung("http", SHELL)
    browser = rung("browser", RICH)
    monkeypatch.setattr(
        "sluicer.fetch.rungs.default_rungs",
        lambda *a, **k: [("http", http), ("browser", browser)],
    )
    monkeypatch.setattr(GATE, "min_delay", 0.0)

    fetch("https://shop.example/1", robots_reader=lambda url: None)
    fetch("https://shop.example/2", robots_reader=lambda url: None)

    assert http.calls == ["https://shop.example/1"]
    assert STICKY.recall("https://shop.example/3") is not None
    injected = rung("http", SHELL)
    fetch(
        "https://shop.example/4",
        rungs=[("http", injected), ("browser", rung("browser", RICH))],
        obey_robots=False,
    )
    assert injected.calls == ["https://shop.example/4"]


# -- the caller's headers and cookies -------------------------------------------


def test_the_callers_headers_and_cookies_reach_the_default_rungs(monkeypatch):
    from sluicer.fetch.gate import GATE

    built = {}

    def default_rungs(*args, **kwargs):
        built.update(kwargs)
        return [("http", rung("http", RICH))]

    monkeypatch.setattr("sluicer.fetch.rungs.default_rungs", default_rungs)
    monkeypatch.setattr(GATE, "min_delay", 0.0)

    fetch(
        "https://example.com/account",
        headers={"Authorization": "Bearer t"},
        cookies={"session": "abc"},
        robots_reader=lambda url: None,
    )

    assert built["headers"] == {"Authorization": "Bearer t"}
    assert built["cookies"] == {"session": "abc"}


def test_a_user_agent_of_the_callers_is_refused_before_anything_is_asked():
    http = rung("http", RICH)

    with pytest.raises(ValueError, match="User-Agent is not replaced"):
        fetch("https://example.com/p", headers={"User-Agent": "Mozilla/5.0"})
    assert http.calls == []


def test_headers_for_injected_rungs_are_refused_rather_than_dropped():
    """Injected rungs are built by their caller, with whatever they send; a
    header handed to fetch() beside them would reach no request."""
    with pytest.raises(ValueError, match="injected rungs"):
        fetch(
            "https://example.com/p",
            rungs=[("http", rung("http", RICH))],
            headers={"Authorization": "Bearer t"},
        )


def test_the_stealth_rung_is_not_asked_to_carry_a_login():
    """It does not say who is asking; a cookie or a token would."""
    with pytest.raises(ValueError, match="stealth rung"):
        fetch("https://example.com/p", stealth=True, cookies={"session": "abc"})


# -- a remembered rung whose page is worse ------------------------------------------


def _remembering_the_browser(memory, http, browser):
    """``memory`` taught that shop.example needs the browser, by a page whose
    plain HTTP answer was a shell."""
    learnt = {"http": rung("http", SHELL), "browser": rung("browser", RICH)}
    fetch(
        "https://shop.example/1",
        rungs=[("http", learnt["http"]), ("browser", learnt["browser"])],
        memory=memory,
        obey_robots=False,
    )
    assert memory.recall("https://shop.example/2").rung == "browser"
    return [("http", http), ("browser", browser)]


def test_a_remembered_rung_whose_page_is_refused_is_forgotten_for_plain_http():
    """Measured on 0.8.0 with a real browser: once a site's script-drawn page
    had taught it the browser, its articles, which plain HTTP read whole and
    the browser was refused (403), came back as the 403, and so did every
    later article: the memory was dropped only when the browser raised."""
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    http = rung("http", RICH)
    browser = rung("browser", REFUSED, status=403)
    ladder = _remembering_the_browser(memory, http, browser)

    second = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )
    third = fetch(
        "https://shop.example/3", rungs=ladder, memory=memory, obey_robots=False
    )

    assert (second.rung, second.status) == ("http", 200)
    assert [(c.from_rung, c.to_rung) for c in second.climbs] == [
        ("http", "browser"),
        ("browser", "http"),
    ]
    assert "status 403; starting again from http" in second.climbs[1].reason
    assert memory.recall("https://shop.example/4") is None
    assert (third.rung, third.climbs) == ("http", [])
    assert browser.calls == ["https://shop.example/2"]


def test_a_remembered_rung_whose_page_is_a_shell_is_forgotten_too():
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    ladder = _remembering_the_browser(
        memory, rung("http", RICH), rung("browser", SHELL)
    )

    page = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert (page.rung, page.html) == ("http", RICH)
    assert memory.recall("https://shop.example/2") is None


def test_a_remembered_challenge_is_not_the_last_word_when_plain_http_reads_the_page():
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    challenge = "<html><head><title>Just a moment...</title></head></html>"
    ladder = _remembering_the_browser(
        memory, rung("http", RICH), rung("browser", challenge)
    )

    page = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert page.rung == "http"


def test_the_remembered_rungs_page_is_kept_and_not_asked_for_twice():
    """Plain HTTP no better than the browser was: the ladder would climb to
    the browser, whose page it already has, and gives that back."""
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    http = rung("http", SHELL)
    browser = rung("browser", REFUSED, status=403)
    ladder = _remembering_the_browser(memory, http, browser)

    page = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert (page.rung, page.status) == ("browser", 403)
    assert browser.calls == ["https://shop.example/2"]
    assert http.calls == ["https://shop.example/2"]
    assert [(c.from_rung, c.to_rung) for c in page.climbs] == [
        ("http", "browser"),
        ("browser", "http"),
        ("http", "browser"),
    ]


def test_past_the_remembered_rung_the_ladder_climbs_on_without_asking_it_again():
    from sluicer.fetch.ladder import RungMemory

    memory = RungMemory()
    browser = rung("browser", REFUSED, status=403)
    stealth = rung("stealth", RICH)
    ladder = [
        *_remembering_the_browser(memory, rung("http", SHELL), browser),
        ("stealth", stealth),
    ]

    page = fetch(
        "https://shop.example/2", rungs=ladder, memory=memory, obey_robots=False
    )

    assert page.rung == "stealth"
    assert browser.calls == ["https://shop.example/2"]


def test_a_crawls_part_forgets_a_rung_whose_page_is_refused():
    from sluicer.crawl.web import Parts
    from sluicer.fetch.ladder import RungMemory

    site = RungMemory()
    parts = Parts(site)
    http = rung("http", RICH)
    browser = rung("browser", REFUSED, status=403)
    ladder = _remembering_the_browser(parts, http, browser)

    page = fetch(
        "https://shop.example/2", rungs=ladder, memory=parts, obey_robots=False
    )

    assert page.rung == "http"
    assert parts.recall("https://shop.example/3") is None
    assert site.recall("https://shop.example/3") is None


# -- whether a failure may be different later ---------------------------------------


def _failing(error):
    def go(url):
        raise error

    return go


@pytest.mark.parametrize(
    ("error", "transient"),
    [
        (ConnectionResetError("reset"), True),
        (TimeoutError("took too long"), True),
        (ValueError("the browser rung returned no HTML"), False),
        (RuntimeError("redirected more than 10 times"), False),
    ],
)
def test_a_failure_says_whether_asking_again_may_bring_something_else(error, transient):
    with pytest.raises(FetchFailed) as failed:
        fetch(
            "https://example.com/p",
            rungs=[("http", _failing(error))],
            obey_robots=False,
        )

    assert failed.value.transient is transient


_NETWORK = ["EHOSTUNREACH", "ENETUNREACH", "ENETDOWN", "EHOSTDOWN", "ENETRESET"]
_NETWORK += ["ECONNABORTED", "EPIPE"]


@pytest.mark.parametrize("name", _NETWORK)
def test_a_network_that_failed_for_now_is_transient(name):
    """A route that went away, a network down, a connection aborted: the
    network flapped, and a crawl asked a page no more when it did. Measured,
    one EHOSTUNREACH ended a page fetch_failed with retryable false."""
    import errno

    number = getattr(errno, name, None)
    if number is None:
        pytest.skip(f"{name} is not an errno on this platform")
    with pytest.raises(FetchFailed) as failed:
        fetch(
            "https://example.com/p",
            rungs=[("http", _failing(OSError(number, name)))],
            obey_robots=False,
        )

    assert failed.value.transient


def test_a_host_with_no_address_to_connect_to_is_transient():
    import time

    from sluicer.fetch import wire

    with pytest.raises(OSError) as none:
        wire._connect([], 443, time.monotonic() + 5)

    assert wire.passing(none.value)


def test_a_browser_that_found_no_route_is_transient():
    from sluicer.fetch.ladder import transient

    assert transient(RuntimeError("net::ERR_ADDRESS_UNREACHABLE at http://x/"))


def test_one_rung_that_may_answer_later_makes_the_failure_transient():
    ladder = [
        ("http", _failing(ConnectionRefusedError("refused"))),
        ("browser", _failing(ValueError("the browser rung returned no HTML"))),
    ]

    with pytest.raises(FetchFailed) as failed:
        fetch("https://example.com/p", rungs=ladder, obey_robots=False)

    assert failed.value.transient


def test_a_robots_txt_that_did_not_answer_is_transient():
    """Whatever the rung that read it raised: RFC 9309 counts every way of
    not reaching it as one event, and it may answer later."""
    ladder = [("http", _failing(ValueError("the browser rung returned no HTML")))]

    with pytest.raises(FetchFailed, match=r"robots\.txt") as failed:
        fetch("https://example.com/p", rungs=ladder)

    assert failed.value.transient
