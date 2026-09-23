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
        # PubMed's citation_publication_date, seen on pages as served:
        ("2023 Jan 7", "2023-01-07"),
        ("2024 Jun 30", "2024-06-30"),
        # JavaScript's Date.toString(), seen in a page's JSON-LD:
        ("Fri Oct 24 2025 03:22:33 GMT+0000 (GMT)", "2025-10-24T03:22:33+00:00"),
        (
            "Fri Oct 24 2025 05:22:33 GMT+0200 (Central European Summer Time)",
            "2025-10-24T05:22:33+02:00",
        ),
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
        "2023 Jan 32",
        "Thu, 08/21/2025 - 13:40",  # seen on a page as served; all numbers
        "Fri Oct 24 2025 03:22:33",  # no offset, so no moment
        "Fri Oct 24 2025 03:22:33 GMT+2500",
        "Fri Feb 30 2025 03:22:33 GMT+0000",
        "Fri Okt 24 2025 03:22:33 GMT+0000",
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


@pytest.mark.parametrize(
    ("written", "meant"),
    [
        ("4001234567891", "4001234567891"),
        ("036000291452", "036000291452"),
        ("96385074", "96385074"),
        ("978-0-306-40615-7", "9780306406157"),
        ("00012345600012", "00012345600012"),
    ],
)
def test_a_gtin_with_a_right_check_digit_is_normalised(written, meant):
    from sluicer.normalise import gtin

    assert gtin(written) == meant


@pytest.mark.parametrize("written", ["4001234567890", "12345", "BP-2210", ""])
def test_a_gtin_with_a_wrong_check_digit_or_length_is_not(written):
    from sluicer.normalise import gtin

    assert gtin(written) is None
