import pytest

from sluicer import extract
from sluicer.normalise import ISO_4217, amount, currency, iso_date


@pytest.mark.parametrize(
    ("written", "meant"),
    [
        ("2024-11-07", "2024-11-07"),
        ("2026-03-06T09:00:00+01:00", "2026-03-06T09:00:00+01:00"),
        ("2025-10-29T00:00:00.000Z", "2025-10-29T00:00:00Z"),
        # Seen on pages as served, in the scoreboard's corpus:
        ("2023-05-17T17:30:55.140904-0400", "2023-05-17T17:30:55-04:00"),
        ("2026-03-09 16:00:22 +0000 UTC", "2026-03-09T16:00:22+00:00"),
        ("Jun 16, 2025", "2025-06-16"),
        ("April 8, 2019", "2019-04-08"),
        ("June 16th, 2025", "2025-06-16"),
        ("Sept 3, 2024", "2024-09-03"),
        ("16 June 2025", "2025-06-16"),
        ("Monday, 3 March 2025", "2025-03-03"),
        ("Tue, 03 Jun 2025 10:00:00 GMT", "2025-06-03T10:00:00+00:00"),
    ],
)
def test_a_date_is_read_into_iso_8601(written, meant):
    assert iso_date(written) == meant


@pytest.mark.parametrize(
    "written",
    [
        "03/04/2025",  # March in one country, April in another
        "240221",  # seen on a page as served; YYMMDD or DDMMYY
        "2025-02-30",
        "2026-01-01T25:00:00",
        "Jan 24, 2026T00:00:00-05:00",  # seen on a page as served
        "Mayo 3, 2025",
        "soon",
        "",
    ],
)
def test_a_date_that_could_mean_two_things_or_none_is_not_read(written):
    assert iso_date(written) is None


def test_a_date_keeps_the_offset_the_page_gave_it():
    """Moved to UTC, 2024-01-31T22:46:10-05:00 would become the first of February."""
    assert iso_date("2024-01-31T22:46:10-05:00") == "2024-01-31T22:46:10-05:00"


@pytest.mark.parametrize(
    ("written", "meant"),
    [
        ("41.90", "41.90"),
        ("42", "42"),
        ("£51.77", "51.77"),
        ("$19.99", "19.99"),
        ("EUR 49.90", "49.90"),
        ("49.90 EUR", "49.90"),
        ("1.299,00 €", "1299.00"),
        ("1,299.00", "1299.00"),
        ("1 299,00", "1299.00"),
        ("1\u00a0299,00", "1299.00"),
        ("1.299.000", "1299000"),
        ("12,5", "12.5"),
        ("0.999", "0.999"),
        ("007.50", "7.50"),
    ],
)
def test_an_amount_is_read_into_a_decimal_with_a_point(written, meant):
    assert amount(written) == meant


@pytest.mark.parametrize(
    "written", ["1,299", "1.299", "1.29.9", "free", "", "12.34.56,7", "1,2,3"]
)
def test_an_amount_that_could_mean_two_things_or_none_is_not_read(written):
    assert amount(written) is None


def test_a_currency_is_its_iso_4217_code_or_an_unambiguous_symbol():
    assert currency("eur") == "EUR"
    assert currency("€") == "EUR"
    assert currency("US$") == "USD"
    assert currency("zł") == "PLN"
    assert currency("$") is None  # a dozen currencies
    assert currency("XYZ") is None
    assert len(ISO_4217) == 178


def test_extract_says_what_the_summary_s_dates_and_price_mean():
    page = (
        '<script type="application/ld+json">{"@type": "Product", "name": "Pad",'
        ' "offers": {"@type": "Offer", "price": "1.299,00", "priceCurrency": "eur"}}'
        "</script>"
        '<meta property="article:published_time" content="Jun 16, 2025">'
    )

    result = extract(page)

    assert result.summary["price"].value == "1.299,00"
    assert result.normalised == {
        "published": "2025-06-16",
        "price": "1299.00",
        "currency": "EUR",
    }


def test_nothing_is_normalised_that_the_summary_does_not_answer():
    assert extract("<p>nothing declared</p>").normalised == {}
