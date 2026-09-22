from sluicer.fetch.result import Climb, Fetched


def test_a_fetch_that_never_climbed_says_so():
    result = Fetched(
        url="https://example.com", html="<html></html>", status=200, rung="http"
    )

    assert result.climbs == []
    assert result.rung == "http"


def test_climbs_are_compared_by_value():
    one = Climb(
        from_rung="http", to_rung="browser", reason="the server refused: status 403"
    )
    same = Climb(
        from_rung="http", to_rung="browser", reason="the server refused: status 403"
    )

    assert one == same
