import json

from sluicer.fetch.rules import MARKUP_CEILING, why_climb

FULL_PAGE = "<html><body>" + ("Real sentences of real content. " * 40) + "</body></html>"


def test_a_good_page_does_not_climb():
    assert why_climb(200, FULL_PAGE, found_records=True) is None


def test_a_refusal_climbs_and_names_the_status():
    reason = why_climb(403, "<html><body>Forbidden</body></html>", found_records=False)

    assert reason is not None
    assert "403" in reason


def test_a_server_error_does_not_climb():
    assert why_climb(500, "<html><body>oops</body></html>", found_records=False) is None


def test_a_challenge_page_climbs_even_with_status_200():
    challenge = '<html><body><div id="cf-challenge-running"></div>Just a moment...</body></html>'

    reason = why_climb(200, challenge, found_records=False)

    assert reason is not None
    assert "challenge" in reason.lower()


def test_a_skeletal_body_climbs():
    skeleton = '<html><body><div id="app"></div>' + ('<script src="a.js"></script>' * 80) + "</body></html>"

    assert why_climb(200, skeleton, found_records=False) is not None


def test_a_thin_page_that_declared_records_stays_put():
    thin = "<html><body><p>Short.</p></body></html>"

    assert why_climb(200, thin, found_records=True) is None


def test_a_page_that_declared_nothing_and_says_little_climbs():
    thin = "<html><body><p>Short.</p></body></html>"

    reason = why_climb(200, thin, found_records=False)

    assert reason is not None
    assert "characters" in reason.lower()


def test_a_refusal_that_is_also_a_challenge_names_the_challenge():
    challenge_refusal = '<html><body><div id="cf-challenge-running"></div>Forbidden</body></html>'

    reason = why_climb(403, challenge_refusal, found_records=False)

    assert reason is not None
    assert "challenge" in reason.lower()
    assert "403" not in reason


# A page that says everything in JSON-LD and nothing to the eye: the markup is
# heavy, the visible text is empty, and the record is already complete.
DECLARED_ONLY_PAGE = (
    '<html><head><script type="application/ld+json">'
    + json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "Product",
            "name": "Brake pad set",
            "sku": "BP-1234",
            "description": "Front axle brake pads for a 2014 hatchback. " * 40,
            "offers": {"@type": "Offer", "price": "49.90", "priceCurrency": "EUR"},
        }
    )
    + '</script></head><body><div id="app"></div></body></html>'
)


def test_a_skeletal_page_that_declared_records_stays_put():
    """A page that already yielded records has delivered: climbing buys nothing."""
    assert len(DECLARED_ONLY_PAGE) > MARKUP_CEILING

    assert why_climb(200, DECLARED_ONLY_PAGE, found_records=True) is None


def test_the_same_skeletal_page_climbs_when_nothing_was_declared():
    reason = why_climb(200, DECLARED_ONLY_PAGE, found_records=False)

    assert reason is not None
    assert "skeletal" in reason
