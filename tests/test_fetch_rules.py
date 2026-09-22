from sluicer.fetch.rules import why_climb

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
