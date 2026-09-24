"""A page that answers one question in two ways says so, and only then."""

from __future__ import annotations

import json
from dataclasses import asdict

from sluicer import extract


def _page(ld: dict, *metas: tuple[str, str]) -> str:
    tags = "".join(f'<meta property="{p}" content="{c}">' for p, c in metas)
    return (
        f'<html><head>{tags}<script type="application/ld+json">'
        f"{json.dumps(ld)}</script></head></html>"
    )


PRODUCT = {
    "@type": "Product",
    "name": "Pads",
    "offers": {"@type": "Offer", "price": "41.90", "priceCurrency": "EUR"},
}


def test_two_prices_are_a_conflict_the_summary_s_answer_first():
    """Measured on Zyte's product pages: 4 of 13 that declare a price twice
    declare two prices -- 150 and 200, 997.00 and 1148.00."""
    result = extract(_page(PRODUCT, ("product:price:amount", "39.90")))
    [conflict] = result.conflicts
    assert conflict.question == "price"
    first, other = conflict.answers
    assert (first.value, first.source, first.key) == (
        "41.90",
        "jsonld",
        "Product.offers.price",
    )
    assert first.where == "/html/head/script[1]#/offers/price"
    assert (other.value, other.source, other.key) == (
        "39.90",
        "opengraph",
        "product:price:amount",
    )
    assert result.summary["price"].value == first.value


def test_one_value_written_two_ways_is_no_conflict():
    assert extract(_page(PRODUCT, ("product:price:amount", "41.9"))).conflicts == []
    assert extract(_page(PRODUCT, ("product:price:currency", "eur"))).conflicts == []


def test_two_currencies_are_a_conflict():
    [conflict] = extract(_page(PRODUCT, ("product:price:currency", "USD"))).conflicts
    assert conflict.question == "currency"
    assert [a.value for a in conflict.answers] == ["EUR", "USD"]


def test_dates_conflict_when_they_name_two_days():
    article = {
        "@type": "NewsArticle",
        "headline": "H",
        "datePublished": "2026-01-12T19:45:38-06:00",
    }
    # One instant at two offsets, across midnight in UTC: one date.
    same = _page(article, ("article:published_time", "2026-01-13T01:45:38+00:00"))
    assert extract(same).conflicts == []
    # One day, the time truncated or its offset written wrong: a reader's
    # question is the day, and every tag answers it alike.
    for time in ("2026-01-12T19:45:00-06:00", "2026-01-12T19:45:38+00:00"):
        assert extract(_page(article, ("article:published_time", time))).conflicts == []
    # Two days.
    other = _page(article, ("article:published_time", "2023-05-17T17:30:55Z"))
    [conflict] = extract(other).conflicts
    assert conflict.question == "published"
    assert [a.key for a in conflict.answers] == [
        "NewsArticle.datePublished",
        "article:published_time",
    ]


def test_only_declarations_of_the_same_fact_are_compared():
    """An upload or creation date is not a publication date."""
    video = {"@type": "VideoObject", "name": "V", "uploadDate": "2020-01-01"}
    page = _page(video, ("article:published_time", "2024-06-01T10:00:00Z"))
    assert extract(page).summary["published"].key == "VideoObject.uploadDate"
    assert extract(page).conflicts == []


def test_a_value_no_rule_can_read_is_no_disagreement():
    assert extract(_page(PRODUCT, ("product:price:amount", "call us"))).conflicts == []
    unread = {**PRODUCT, "offers": {"@type": "Offer", "price": "on request"}}
    assert extract(_page(unread, ("product:price:amount", "39.90"))).conflicts == []


def test_conflicts_reach_the_json_answer():
    result = extract(_page(PRODUCT, ("product:price:amount", "39.90")))
    [conflict] = asdict(result)["conflicts"]
    assert conflict["question"] == "price"
    assert [a["value"] for a in conflict["answers"]] == ["41.90", "39.90"]


def test_another_fact_among_the_candidates_is_passed_over():
    article = {
        "@type": "NewsArticle",
        "headline": "H",
        "datePublished": "2024-06-01T10:00:00Z",
        "uploadDate": "2020-01-01",
    }
    page = _page(article, ("article:published_time", "2024-06-01T10:00:00Z"))
    assert extract(page).conflicts == [], "the upload date is not compared"


def test_summarise_is_read_summary_without_its_conflicts():
    from sluicer.document import load
    from sluicer.summary import read_summary, summarise

    records = extract(_page(PRODUCT)).records
    doc = load(_page(PRODUCT, ("product:price:amount", "39.90")))
    alone = summarise(doc, records, {}, {"product:price:amount": "39.90"}, {}, {})
    both = read_summary(doc, records, {}, {"product:price:amount": "39.90"}, {}, {})
    assert alone == both[0]
    assert [c.question for c in both[1]] == ["price"]


def test_a_date_whose_time_cannot_be_read_is_compared_by_its_day(monkeypatch):
    from sluicer import summary

    monkeypatch.setattr(summary, "iso_date", lambda text: "2024-01-01T99:00:00")
    assert summary._moment("anything") == ("2024-01-01", None)


def test_inspect_shows_a_conflict_under_the_summary(tmp_path):
    from click.testing import CliRunner

    from sluicer.cli import main

    page = tmp_path / "page.html"
    page.write_text(_page(PRODUCT, ("product:price:amount", "39.90")), encoding="utf-8")
    output = CliRunner().invoke(main, ["inspect", str(page)]).output
    assert "conflict: price is declared two ways" in output
    assert "39.90  [opengraph product:price:amount]" in output
