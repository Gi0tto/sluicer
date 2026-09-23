"""How the audit reads a page: which records, from where, and what it compares."""

import json
from dataclasses import asdict

import pytest

from sluicer import extract
from sluicer.audit import audit, google, records
from test_audit_features import VALID, page


def findings(result, code=None):
    found = [finding for record in result.records for finding in record.findings]
    found += result.page
    return [finding for finding in found if code is None or finding.code == code]


MICRODATA_PRODUCT = """<html><head><title>Pads</title></head><body>
<div itemscope itemtype="https://schema.org/Product">
  <span itemprop="name">Brake pad set</span>
  <img itemprop="image" src="/pads.jpg">
  <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
    <meta itemprop="price" content="41,90">
    <meta itemprop="priceCurrency" content="EUR">
    <link itemprop="availability" href="https://schema.org/InStock">
    <meta itemprop="url" content="/pads">
  </div>
</div>
</body></html>"""


def test_microdata_is_audited_under_its_own_name():
    result = audit(MICRODATA_PRODUCT, url="https://example.com/p")

    record = result.records[0]
    assert (record.source, record.index, record.types) == ("microdata", 0, ["Product"])
    price = next(f for f in record.findings if f.path == "offers.price")
    assert price.source == "microdata"
    assert price.value == "41,90"
    # The <img src> was resolved against the page by the reader; the <meta
    # content> was not, since the standard gives it verbatim.
    urls = [
        f.path for f in record.findings if f.rule == google._DOCS + "local-business"
    ]
    assert urls == ["offers.url"]


def test_microdata_urls_are_not_judged_without_the_pages_address():
    result = audit(MICRODATA_PRODUCT)

    record = result.records[0]
    assert not [f for f in record.findings if f.path in ("image", "offers.url")]
    assert any("microdata and RDFa URLs" in note for note in result.not_checked)


def test_json_ld_urls_are_judged_with_or_without_an_address():
    node = {**VALID["product"], "image": "/pads.jpg"}

    result = audit(page(node))

    relative = [f for f in findings(result, "invalid-value") if f.path == "image"]
    assert [f.severity for f in relative] == ["warning"]


def test_rdfa_is_audited_under_its_own_name():
    html = """<html><body vocab="https://schema.org/">
    <div typeof="Event"><span property="name">Concert</span>
    <span property="startDate" content="21/07/2026"></span></div></body></html>"""

    result = audit(html, url="https://example.com/e")

    record = result.records[0]
    assert record.source == "rdfa"
    assert [f.name for f in record.features] == ["Event"]
    assert record.features[0].missing_required == ["location"]
    bad = next(f for f in record.findings if f.path == "startDate")
    assert bad.source == "rdfa"


YOAST = {
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "Article",
            "@id": "https://example.com/p/#article",
            "headline": "A post",
            "datePublished": "2026-09-01T08:00:00+00:00",
            "author": {"@id": "https://example.com/#/person/1"},
            "publisher": {"@id": "https://example.com/#organization"},
            "image": {"@id": "https://example.com/p/#primaryimage"},
        },
        {
            "@type": "Person",
            "@id": "https://example.com/#/person/1",
            "name": "Jane",
            "url": "/author/jane",
        },
        {
            "@type": "Organization",
            "@id": "https://example.com/#organization",
            "name": "Example",
            "logo": {"@id": "https://example.com/#logo"},
        },
    ],
}


def test_a_graph_is_followed_through_its_references():
    html = '<script type="application/ld+json">' + json.dumps(YOAST) + "</script>"

    result = audit(html, url="https://example.com/p/")

    article = result.records[0]
    assert article.types == ["Article"]
    # author.name is found by following the reference to the Person node.
    assert "author.name" not in article.features[0].missing_recommended
    # The Person's relative url is reported once, on the Person, not again
    # inside the Article that points at it.
    relative = [(f.record, f.type, f.path) for f in findings(result, "invalid-value")]
    assert relative == [(1, "Person", "url")]


def test_a_reference_the_page_never_defines_is_noted_not_guessed():
    node = {
        "@type": "Article",
        "headline": "Pie",
        "author": {"@id": "https://example.com/#nobody"},
    }

    result = audit(page(node))

    notes = findings(result, "reference-not-followed")
    assert [f.path for f in notes] == ["author"]
    assert notes[0].severity == "info"
    # What lies behind it is not reported missing: it is not known.
    assert "author.name" not in result.records[0].features[0].missing_recommended


def test_a_feature_walk_that_would_never_end_stops_and_says_so(monkeypatch):
    monkeypatch.setattr(records, "MAX_NODES", 3)
    comments = [
        {"@type": "Comment", "text": f"c{n}", "datePublished": "2026-01-01"}
        for n in range(5)
    ]
    node = {**VALID["discussion-forum"], "comment": comments}

    result = audit(page(node))

    stopped = findings(result, "walk-stopped")
    assert len(stopped) == 1
    assert "stopped after 3 nodes" in stopped[0].message


def test_references_that_loop_end():
    graph = {
        "@graph": [
            {
                "@type": "DiscussionForumPosting",
                "@id": "#a",
                "author": {"@type": "Person", "name": "A"},
                "datePublished": "2026-01-01",
                "text": "a",
                "comment": [{"@id": "#b"}],
            },
            {
                "@type": "Comment",
                "@id": "#b",
                "author": {"@type": "Person", "name": "B"},
                "datePublished": "2026-01-01",
                "text": "b",
                "comment": [{"@id": "#a"}, {"@id": "#b"}],
            },
        ]
    }
    html = '<script type="application/ld+json">' + json.dumps(graph) + "</script>"

    result = audit(html)

    assert result.records[0].features[0].requirements_met is True


def test_a_node_that_declares_only_a_type_is_still_held_to_its_rule():
    node = {**VALID["product"], "offers": {"@type": "Offer"}}
    del node["aggregateRating"]

    result = audit(page(node))

    snippet = result.records[0].features[0]
    assert snippet.missing_required == ["offers.price|offers.priceSpecification.price"]


def test_an_aggregate_offer_suits_a_snippet_and_not_a_merchant_listing():
    offers = {
        "@type": "AggregateOffer",
        "lowPrice": "10",
        "highPrice": "20",
        "priceCurrency": "EUR",
    }
    node = {**VALID["product"], "offers": offers}

    snippet, merchant = audit(page(node)).records[0].features

    assert snippet.requirements_met is True
    assert merchant.requirements_met is False
    assert merchant.missing_required == []


def test_a_value_of_another_type_gets_no_rule_it_was_not_written_for():
    node = {**VALID["product"], "subjectOf": {"@type": "VideoObject", "name": "x"}}

    merchant = audit(page(node)).records[0].features[1]

    assert not any(path.startswith("subjectOf.") for path in merchant.missing_required)


def test_a_condition_on_a_property_is_honoured():
    dentist = {**VALID["local-business"], "@type": "Dentist"}
    del dentist["menu"]
    rescheduled = {**VALID["event"], "eventStatus": "EventRescheduled"}

    dentist_verdict = audit(page(dentist)).records[0].features[1]
    restaurant = {k: v for k, v in VALID["local-business"].items() if k != "menu"}
    restaurant_verdict = audit(page(restaurant)).records[0].features[1]
    event_verdict = audit(page(rescheduled)).records[0].features[0]

    assert "menu" not in dentist_verdict.missing_recommended
    assert "menu" in restaurant_verdict.missing_recommended
    assert "previousStartDate" in event_verdict.missing_recommended
    assert "previousStartDate" not in (
        audit(page(VALID["event"])).records[0].features[0].missing_recommended
    )


def test_a_subtype_counts_only_where_the_documentation_says():
    car = audit(page({"@type": "Car", "name": "Model T", "offers": {"price": "1"}}))
    both = audit(page({"@type": ["Product", "Car"], "name": "Model T"}))
    game = audit(page({"@type": "VideoGame", "name": "Chess"}))
    report = audit(page({"@type": "Report", "headline": "Q3"}))

    assert [f.name for f in car.records[0].features] == ["Vehicle listing"]
    assert [f.name for f in both.records[0].features] == [
        "Product snippet",
        "Merchant listing",
    ]
    assert "Software app" not in [f.name for f in game.records[0].features]
    assert [f.name for f in report.records[0].features] == ["Article"]


@pytest.mark.parametrize(
    ("node", "feature"),
    [
        ({"@type": "FAQPage", "mainEntity": []}, "FAQ"),
        ({"@type": "HowTo", "name": "Tie a tie"}, "How-to"),
        ({"@type": "ClaimReview", "claimReviewed": "x"}, "Fact check"),
        ({"@type": "SpecialAnnouncement", "name": "x"}, "Special announcement"),
    ],
)
def test_a_retired_feature_is_said_to_be_retired(node, feature):
    record = audit(page(node)).records[0]

    assert [f.name for f in record.features] == [feature]
    assert record.features[0].status == "retired"
    assert record.features[0].requirements_met is None
    note = next(f for f in record.findings if f.code == "retired-feature")
    assert note.severity == "info"
    assert note.rule.startswith("https://developers.google.com/search/")


def test_a_site_with_a_search_box_is_told_the_box_is_gone():
    node = {
        **VALID["site-name"],
        "potentialAction": {"@type": "SearchAction", "target": "https://x/?q={q}"},
    }

    names = [f.name for f in audit(page(node)).records[0].features]

    assert names == ["Site name", "Sitelinks search box"]


def test_a_type_whose_feature_is_not_checked_says_so():
    record = audit(page({"@type": "Movie", "name": "Up"})).records[0]

    assert record.not_checked == [
        "Movie carousel (https://developers.google.com/search/docs/appearance/"
        "structured-data/movie)"
    ]


def test_a_record_with_no_type_is_audited_for_its_values():
    result = audit(page({"price": "1,5"}))

    record = result.records[0]
    assert record.types == []
    assert record.features == []
    assert [f.path for f in record.findings] == ["price"]


def test_the_same_page_gets_the_same_audit():
    html = page(VALID["product"], {**VALID["article"], "datePublished": "x"})

    assert asdict(audit(html, url="https://e.com/p")) == asdict(
        audit(html, url="https://e.com/p")
    )


def test_the_counts_add_up():
    result = audit(page({**VALID["product"], "offers": {"price": "x"}}))

    everything = result.findings()
    assert result.errors == sum(f.severity == "error" for f in everything)
    assert result.warnings == sum(f.severity == "warning" for f in everything)
    assert result.notes == sum(f.severity == "info" for f in everything)
    assert result.errors >= 1


# -- Conflicts ------------------------------------------------------------------

BOTH = """<html><head><script type="application/ld+json">
{"@type":"Product","name":"Pads","sku":"BP-1187","offers":{"@type":"Offer",
"price":"41.90","priceCurrency":"eur","availability":"https://schema.org/InStock"}}
</script></head><body>
<div itemscope itemtype="https://schema.org/Product">
 <span itemprop="name">Brake pads</span><span itemprop="sku">BP 1187</span>
 <div itemprop="offers" itemscope itemtype="https://schema.org/Offer">
  <meta itemprop="price" content="{price}"><meta itemprop="priceCurrency" content="EUR">
  <link itemprop="availability" href="http://schema.org/InStock">
 </div></div></body></html>"""


def test_two_vocabularies_that_disagree_on_a_price_are_a_conflict():
    result = audit(BOTH.replace("{price}", "39.90"))

    conflicts = [f for f in result.page if f.code == "conflict"]
    assert [f.path for f in conflicts] == ["offers.price"]
    assert conflicts[0].source == "jsonld and microdata"
    assert "41.90 in jsonld" in conflicts[0].message
    assert "39.90 in microdata" in conflicts[0].message


def test_the_same_fact_written_two_ways_is_no_conflict():
    """41.9 is 41.90, EUR is eur, a SKU keeps its meaning with a space for a
    hyphen, and InStock is InStock at either address."""
    result = audit(BOTH.replace("{price}", "41.9"))

    assert [f for f in result.page if f.code == "conflict"] == []


def test_two_products_against_one_are_not_guessed_at():
    html = BOTH.replace("{price}", "39.90").replace(
        "</script>",
        '</script><script type="application/ld+json">'
        '{"@type":"Product","name":"Other","offers":{"price":"5"}}</script>',
    )

    result = audit(html)

    assert [f for f in result.page if f.code == "conflict"] == []


def test_dates_are_compared_as_moments():
    jsonld = {"@type": "Article", "datePublished": "2026-09-01T10:00:00Z"}
    rdfa = (
        '<div vocab="https://schema.org/" typeof="Article">'
        '<meta property="datePublished" content="{date}"></div>'
    )

    same = audit(page(jsonld) + rdfa.replace("{date}", "2026-09-01T12:00:00+02:00"))
    other = audit(page(jsonld) + rdfa.replace("{date}", "2026-09-02"))

    assert [f for f in same.page if f.code == "conflict"] == []
    assert [f.path for f in other.page if f.code == "conflict"] == ["datePublished"]


# -- The page as a whole --------------------------------------------------------

COMPLETE_HEAD = """<html><head><title>Pads</title>
<meta name="description" content="Front axle brake pads.">
<link rel="canonical" href="https://example.com/pads">
<meta property="og:title" content="Pads"><meta property="og:type" content="product">
<meta property="og:image" content="https://example.com/pads.jpg">
<meta property="og:url" content="https://example.com/pads">
</head><body></body></html>"""


def test_a_complete_head_has_no_page_findings():
    assert audit(COMPLETE_HEAD).page == []


@pytest.mark.parametrize(
    ("cut", "code", "path"),
    [
        ("<title>Pads</title>", "missing-title", ""),
        (
            '<meta name="description" content="Front axle brake pads.">',
            "missing-description",
            "",
        ),
        (
            '<link rel="canonical" href="https://example.com/pads">',
            "missing-canonical",
            "",
        ),
        (
            '<meta property="og:image" content="https://example.com/pads.jpg">',
            "missing-opengraph",
            "og:image",
        ),
        ('<meta property="og:type" content="product">', "missing-opengraph", "og:type"),
    ],
)
def test_each_thing_the_head_lacks_is_named(cut, code, path):
    result = audit(COMPLETE_HEAD.replace(cut, ""))

    assert [(f.code, f.path, f.severity) for f in result.page] == [
        (code, path, "warning")
    ]
    assert result.page[0].rule.startswith("https://")


def test_canonicals_that_disagree_or_are_relative_are_named():
    head = COMPLETE_HEAD.replace(
        "</head>", '<link rel="canonical" href="/pads?ref=x"></head>'
    )

    codes = [f.code for f in audit(head).page]

    assert codes == ["canonicals-disagree", "canonical-relative"]


def test_an_image_under_another_opengraph_key_counts():
    head = COMPLETE_HEAD.replace(
        'property="og:image"', 'property="og:image:secure_url"'
    )

    assert audit(head).page == []


# -- An extraction instead of a page --------------------------------------------


def test_an_extraction_is_audited_as_merged_naming_each_propertys_reader():
    extraction = extract(BOTH.replace("{price}", "39.90"), url="https://e.com/p")
    extraction.records[0].fields["offers"].value["price"] = "41,90"

    result = audit(extraction)

    assert result.url == "https://e.com/p"
    assert [r.source for r in result.records] == ["jsonld"]
    bad = next(f for f in result.records[0].findings if f.path == "offers.price")
    assert bad.source == "jsonld"
    assert result.page == []
    assert any(
        "an Extraction holds the merged records" in n for n in result.not_checked
    )


def test_an_extraction_keeps_only_what_describes_a_thing():
    html = COMPLETE_HEAD.replace(
        "</head>",
        '<script type="application/ld+json">{"@type":"Product","name":"P"}</script>'
        "</head>",
    )

    result = audit(extract(html))

    merchant = result.records[0].features[1]
    # og:image folded onto the record by extract() is not the product's image.
    assert "image" in merchant.missing_required


def test_an_extraction_of_a_page_that_declares_nothing_has_no_records():
    assert audit(extract(COMPLETE_HEAD)).records == []


# -- Arguments ------------------------------------------------------------------


def test_a_need_that_is_not_written_in_the_short_form_is_refused():
    with pytest.raises(ValueError, match="not a need"):
        google.need("name @")


def test_every_feature_names_a_rule_that_exists_and_a_page_it_comes_from():
    for feature in google.FEATURES:
        assert feature.rule is None or feature.rule in google.RULES, feature.name
        assert (feature.rule is None) == (feature.status == "retired"), feature.name
        assert feature.url.startswith("https://developers.google.com/search/")
        assert feature.updated[:2] == "20"
    for rule in google.RULES.values():
        for _prop, choices in rule.nested:
            for _kind, name in choices:
                assert name is None or name in google.RULES, (rule.name, name)
    assert {source.url for source in google.SOURCES} >= {
        google._DOCS + "product-snippet",
        google._DOCS + "merchant-listing",
    }


# -- The edges of the walk ------------------------------------------------------


def test_a_value_object_is_its_value_and_a_deep_page_costs_a_bound():
    deep = {"name": "x"}
    for _ in range(60):
        deep = {"@type": "Thing", "about": deep}
    node = {**VALID["product"], "offers": {"price": {"@value": "41,90"}}, "x": deep}

    result = audit(page(node))

    assert [f.value for f in findings(result, "invalid-value")] == ["41,90"]


def test_a_chain_of_references_longer_than_any_page_nests_ends():
    nodes = [
        {
            "@type": "Comment",
            "@id": f"#c{n}",
            "author": {"@type": "Person", "name": "A"},
            "datePublished": "2026-01-01",
            "text": "t",
            "comment": {"@id": f"#c{n + 1}"},
        }
        for n in range(1, 60)
    ]
    post = {**VALID["discussion-forum"], "@id": "#c0", "comment": {"@id": "#c1"}}
    html = (
        '<script type="application/ld+json">'
        + json.dumps({"@graph": [post, *nodes]})
        + "</script>"
    )

    result = audit(html)

    assert result.records[0].features[0].requirements_met is True


def test_text_where_an_object_belongs_breaks_the_chain_and_gets_no_rule():
    node = {**VALID["event"], "location": "Berlin", "offers": "30 USD"}

    event = audit(page(node)).records[0].features[0]
    product = audit(page({**VALID["product"], "offers": "41.90"})).records[0]

    assert event.missing_required == ["location.address"]
    assert "offers.price" in event.missing_recommended
    # A product whose offers are text meets "offers" and gets no Offer rule.
    assert product.features[0].requirements_met is True


@pytest.mark.parametrize(
    ("reviewed", "said"),
    [
        ("Dune", "text, where Google asks for a typed item"),
        ({"name": "Dune"}, "an item that declares no type"),
    ],
)
def test_what_a_review_is_about_must_be_a_typed_item(reviewed, said):
    node = {**VALID["review"], "itemReviewed": reviewed}

    refused = findings(audit(page(node)), "refused-by-feature")

    assert [f.message.split(" is ", 1)[1] for f in refused] == [said]


def test_a_reviewer_named_in_text_is_held_to_the_same_length():
    node = {**VALID["review"], "author": "A" * 120}

    refused = findings(audit(page(node)), "refused-by-feature")

    assert [f.path for f in refused] == ["author"]


def test_a_subtype_of_a_documented_type_gets_its_rule():
    offer = {"@type": "OfferForPurchase", "price": "1", "priceCurrency": "EUR"}
    node = {**VALID["product"], "offers": offer}

    snippet = audit(page(node)).records[0].features[0]

    assert snippet.requirements_met is True
    assert "offers.availability" in snippet.missing_recommended


def test_a_list_inside_a_list_is_walked_past():
    node = {**VALID["product"], "image": [["https://example.com/a.jpg"]]}

    assert findings(audit(page(node)), "invalid-value") == []


def test_conflicts_read_a_list_of_one_and_follow_a_reference():
    jsonld = {
        "@graph": [
            {
                "@type": "Product",
                "name": "P",
                "offers": [{"@id": "#offer"}],
                "aggregateRating": [{"ratingValue": "4", "reviewCount": "3"}],
            },
            {"@type": "Offer", "@id": "#offer", "price": "10", "priceCurrency": "EUR"},
        ]
    }
    microdata = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">P</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="12"></div>'
        '<div itemprop="aggregateRating" itemscope '
        'itemtype="https://schema.org/AggregateRating">'
        '<meta itemprop="ratingValue" content="four"></div></div>'
    )
    html = (
        '<script type="application/ld+json">'
        + json.dumps(jsonld)
        + "</script>"
        + microdata
    )

    conflicts = [f.path for f in audit(html).page if f.code == "conflict"]

    assert conflicts == ["offers.price", "aggregateRating.ratingValue"]


def test_two_offers_are_not_one_fact():
    jsonld = {
        "@type": "Product",
        "name": "P",
        "offers": [{"price": "10"}, {"price": "11"}],
    }
    microdata = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<meta itemprop="price" content="12"></div></div>'
    )

    result = audit(page(jsonld) + microdata)

    assert [f for f in result.page if f.code == "conflict"] == []
