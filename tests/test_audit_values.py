"""The checks one value gets, each on values that pass and values that do not."""

import pytest

from sluicer.audit import google, values


@pytest.mark.parametrize("text", ["0", "41.90", "1234567.5"])
def test_a_price_is_digits_and_a_full_stop(text):
    assert values.price(text) is None


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("41,90", "comma"),
        ("€41.90", "currency symbol"),
        ("41.90 EUR", "not a number"),
        ("1,234.00", "not a number"),
        ("٤١", "not a number"),
        ("Free", "not a number"),
        ("-5", "not a number"),
    ],
)
def test_a_price_in_another_form_says_which(text, said):
    assert said in values.price(text)


def test_a_merchant_listing_price_is_above_zero():
    assert values.positive("0.01") is None
    assert "greater than zero" in values.positive("0")
    assert "greater than zero" in values.positive("0.00")
    assert values.positive("41,90") is None, "the form is price's to report"


def test_a_currency_is_a_code_of_iso_4217_list_one():
    assert values.currency("EUR") is None
    assert "upper case: EUR" in values.currency("eur")
    assert "symbol" in values.currency("€")
    assert "ISO 4217" in values.currency("HRK"), "the kuna left list one in 2023"
    assert "ISO 4217" in values.currency("BTC")


@pytest.mark.parametrize(
    "text",
    [
        "2026-09-23",
        "2026-09-23T10:00",
        "2026-09-23T10:00:05",
        "2026-09-23T10:00:05.123Z",
        "2026-09-23T10:00:05+02:00",
        "2026-09-23T10:00:05-0500",
        "2026-09-23T10:00+01",
    ],
)
def test_iso_8601_dates_and_times_pass(text):
    assert values.instant(text) is None


@pytest.mark.parametrize(
    ("text", "said"),
    [
        ("2026-09-23 10:00:00", "space where ISO 8601 puts a T"),
        ("23/09/2026", "not an ISO 8601 date"),
        ("2026-9-23", "not an ISO 8601 date"),
        ("2026-02-30", "not a day the calendar has"),
        ("2026-09-23T25:00", "not a time the clock has"),
        ("2026-09-23T10:00+25:00", "not a time zone offset"),
        ("2026-09-23T10", "not an ISO 8601 date"),
        ("September 23, 2026", "not an ISO 8601 date"),
    ],
)
def test_other_dates_say_why(text, said):
    assert said in values.instant(text)


def test_an_instant_is_a_moment_only_with_a_time_and_a_zone():
    day = values.parse_instant("2026-09-23")
    local = values.parse_instant("2026-09-23T10:00")
    zoned = values.parse_instant("2026-09-23T10:00Z")

    assert day.aware() is None
    assert local.aware() is None
    assert zoned.aware().isoformat() == "2026-09-23T10:00:00+00:00"


def test_dates_out_of_order_are_compared_as_far_as_they_say():
    assert values.before("2026-09-02", "2026-09-01")
    assert not values.before("2026-09-01", "2026-09-02")
    # The same moment, written in two zones: not out of order.
    assert not values.before("2026-09-01T23:30-02:00", "2026-09-02T01:30Z")
    assert values.before("2026-09-02T01:30Z", "2026-09-01T23:00-02:00")
    # A day against a moment: only the days are compared.
    assert not values.before("2026-09-01T23:00", "2026-09-01")
    assert not values.before("not a date", "2026-09-01")


@pytest.mark.parametrize(
    "text", ["PT1H", "PT1H30M", "P1DT2H", "PT0.5S", "P2W", "P1Y2M"]
)
def test_iso_8601_durations_pass(text):
    assert values.duration(text) is None


@pytest.mark.parametrize("text", ["1 hour", "PT", "P", "P1DT", "30 min", "PT1H30"])
def test_other_durations_do_not(text):
    assert values.duration(text) == "not an ISO 8601 duration such as PT1H30M"


def test_a_url_is_absolute_http_or_https():
    assert values.url("https://example.com/p") is None
    assert "relative" in values.url("/p")
    assert "relative" in values.url("//example.com/p")
    assert "data: address" in values.url("data:image/png;base64,AAAA")
    assert values.url("http://[::1") == "not a URL"


def test_an_enumeration_term_is_read_with_or_without_the_vocabulary():
    availability = values.enumeration("ItemAvailability")

    for written in (
        "InStock",
        "https://schema.org/InStock",
        "http://schema.org/InStock",
        "http://www.schema.org/InStock",
        "schema:InStock",
    ):
        assert availability(written) is None, written
    assert availability("instock") == "schema.org spells the term InStock"
    assert availability("Available") == "not a term of schema.org's ItemAvailability"


def test_counts_positions_and_coordinates():
    assert values.count("0") is None
    assert "whole number" in values.count("1,204")
    assert values.position("1") is None
    assert "from 1" in values.position("0")
    assert values.latitude("-90") is None
    assert "beyond 90" in values.latitude("90.5")
    assert values.longitude("-179.99") is None
    assert "decimal degrees" in values.longitude("73°W")


def test_a_gtin_has_its_length_and_its_check_digit():
    any_gtin = values.gtin((8, 12, 13, 14))

    assert any_gtin("4006381333931") is None
    assert any_gtin("96385074") is None
    assert "check digit" in any_gtin("4006381333932")
    assert "8 or 12 or 13 or 14 digits" in any_gtin("40063813339")
    assert "13 digits" in values.gtin((13,))("96385074")


def test_an_isbn_is_13_or_10_with_its_check_digit():
    assert values.isbn("978-0-306-40615-7") is None
    assert values.isbn("0-306-40615-2") is None
    assert values.isbn("080442957X") is None
    assert "ISBN-13 check digit" in values.isbn("9780306406158")
    assert "ISBN-10 check digit" in values.isbn("0306406153")
    assert "not an ISBN" in values.isbn("12345")


def test_times_booleans_and_googles_lists():
    assert values.clock_time("09:00") is None
    assert values.clock_time("09:00:00+01:00") is None
    assert "00 to 23" in values.clock_time("24:00")
    assert "hh:mm" in values.clock_time("9am")
    assert values.boolean("True") is None
    assert values.boolean("https://schema.org/False") is None
    assert values.boolean("yes") == "not true or false"
    assert values.employment_type("PART_TIME") is None
    assert "employment types" in values.employment_type("Part time")
    assert values.salary_unit("YEAR") is None
    assert values.job_location_type("TELECOMMUTE") is None
    assert "TELECOMMUTE" in values.job_location_type("remote")
    assert values.app_category("https://schema.org/GameApplication") is None
    assert "app types" in values.app_category("Games")
    assert values.under_100("x" * 99) is None
    assert values.under_100("x" * 100) == "100 characters or longer"
    assert values.dataset_description("x" * 50) is None
    assert "5001 characters" in values.dataset_description("x" * 5001)
    assert values.number("4.5") is None
    assert values.number("four") == "not a number"


@pytest.mark.parametrize(
    ("value", "best", "worst", "said"),
    [
        ("4.5", None, None, None),
        ("5", None, None, None),
        ("6", None, None, "outside the scale 1 to 5"),
        ("0", None, None, "outside the scale 1 to 5"),
        ("88", "100", None, None),
        ("88", "100", "90", "outside the scale 90 to 100"),
        ("3", "1", "5", "bestRating 1 is not above worstRating 5"),
        ("6 / 10", None, None, None),
        ("11/10", None, None, "not a fraction between 0 and 1"),
        ("60%", None, None, None),
        ("120%", None, None, "above 100%"),
        ("4,5", None, None, "comma"),
        ("four stars", None, None, "not a number, a fraction or a percentage"),
        ("4", "five", None, None),
    ],
)
def test_a_rating_is_on_its_scale(value, best, worst, said):
    reason = values.rating(value, best, worst)

    assert reason is None if said is None else said in reason


def test_every_check_names_where_its_rule_is_written():
    for check in (*values.PROPERTY_CHECKS.values(), *values.FEATURE_CHECKS.values()):
        assert check.source.startswith("https://"), check.name
        assert check.severity in ("error", "warning"), check.name
    assert values.PROPERTY_CHECKS["url"].severity == "warning"


def test_every_check_a_feature_names_exists():
    objects = {"review-target", "not-aggregate-offer"}
    for rule in google.RULES.values():
        for _path, check in rule.checks:
            assert check in values.FEATURE_CHECKS or check in objects, (
                rule.name,
                check,
            )
