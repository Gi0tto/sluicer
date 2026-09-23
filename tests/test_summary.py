"""The summary: one answer per question, each saying where it came from."""

import json

from sluicer import extract
from sluicer.summary import FIELDS


def _page(*blocks: object, head: str = "", attrs: str = "") -> str:
    scripts = "".join(
        f'<script type="application/ld+json">{json.dumps(block)}</script>'
        for block in blocks
    )
    return f"<html{attrs}><head>{head}{scripts}</head><body></body></html>"


def _summary(html: str, url: str | None = None) -> dict[str, tuple[str, str, str]]:
    found = extract(html, url=url).summary
    return {name: (f.value, f.source, f.key) for name, f in found.items()}


def test_an_article_answers_from_the_article():
    html = _page(
        {"@type": "BreadcrumbList", "name": "Home > News"},
        {
            "@type": "NewsArticle",
            "headline": "Tom Daley on knitting",
            "author": [{"@type": "Person", "name": "Lily Smith"}],
            "datePublished": "2026-09-22T14:00:02Z",
            "publisher": {"@type": "Organization", "name": "The Guardian"},
            "image": {"@type": "ImageObject", "url": "https://i.example/a.jpg"},
        },
        head='<meta property="og:title" content="Tom Daley | The Guardian">',
    )

    summary = _summary(html)

    assert summary["title"] == (
        "Tom Daley on knitting",
        "jsonld",
        "NewsArticle.headline",
    )
    assert summary["author"] == ("Lily Smith", "jsonld", "NewsArticle.author")
    assert summary["published"][0] == "2026-09-22T14:00:02Z"
    assert summary["publisher"][0] == "The Guardian"
    assert summary["image"][0] == "https://i.example/a.jpg"
    assert summary["type"][0] == "NewsArticle"


def test_a_recipe_is_the_subject_of_a_page_that_also_carries_its_video():
    html = _page(
        {"@type": "VideoObject", "name": "Watch the cake", "uploadDate": "2020-01-01"},
        {
            "@type": "Recipe",
            "name": "Easy chocolate cake",
            "datePublished": "2017-10-08",
        },
    )

    summary = _summary(html)

    assert summary["title"][0] == "Easy chocolate cake"
    assert summary["published"][0] == "2017-10-08"


def test_a_page_about_its_own_site_is_titled_by_the_page():
    html = _page(
        {"@type": "WebSite", "name": "Yoast"},
        {"@type": ["Organization", "Brand"], "name": "Yoast"},
        head='<meta property="og:title" content="SEO for everyone"><title>x</title>',
    )

    summary = _summary(html)

    assert summary["title"] == ("SEO for everyone", "opengraph", "og:title")
    assert summary["publisher"] == ("Yoast", "jsonld", "Organization.name")
    assert summary["site_name"] == ("Yoast", "jsonld", "WebSite.name")


def test_a_page_that_declares_only_its_title_still_has_one():
    summary = _summary("<html lang='de'><head><title> Bremsöl  </title></head></html>")

    assert summary == {
        "title": ("Bremsöl", "html", "<title>"),
        "language": ("de", "html", "<html lang>"),
    }


def test_a_page_with_nothing_at_all_has_an_empty_summary():
    assert extract("<p>hi</p>").summary == {}


def test_an_author_meta_fills_what_json_ld_did_not_say():
    html = _page(
        {"@type": "Article", "headline": "H"},
        head='<meta name="author" content="Nancy Peyer">'
        '<meta property="article:author" content="https://x.example/profile/np">',
    )

    assert _summary(html)["author"] == ("Nancy Peyer", "html", "meta name=author")


def test_a_profile_address_is_not_an_author():
    html = _page(
        {"@type": "Article", "headline": "H"},
        head='<meta property="article:author" content="https://x.example/profile/np">',
    )

    assert "author" not in _summary(html)


def test_several_authors_are_named_once_each_in_order():
    html = _page(
        {
            "@type": "Article",
            "headline": "H",
            "author": [
                {"@type": "Person", "name": "A. One"},
                {"@type": "Person", "givenName": "Bea", "familyName": "Two"},
                {"@type": "Person", "name": "A. One"},
            ],
        }
    )

    assert _summary(html)["author"][0] == "A. One, Bea Two"


def test_a_product_answers_its_price_from_inside_its_offers():
    html = _page(
        {
            "@type": "Product",
            "name": "Brake pad set",
            "sku": "BP-1",
            "brand": {"@type": "Brand", "name": "Textar"},
            "offers": [
                {
                    "@type": "Offer",
                    "price": "41.90",
                    "priceCurrency": "EUR",
                    "availability": "https://schema.org/InStock",
                }
            ],
        }
    )

    summary = _summary(html)

    assert summary["price"][0] == "41.90"
    assert summary["currency"][0] == "EUR"
    assert summary["availability"][0] == "InStock"
    assert summary["brand"][0] == "Textar"
    assert summary["sku"][0] == "BP-1"


def test_an_aggregate_offer_answers_with_its_lowest_price_as_the_lowest():
    """A plain price would be a claim the page never made: "from 19" is not 19."""
    html = _page(
        {
            "@type": "Product",
            "name": "Pads",
            "offers": {
                "@type": "AggregateOffer",
                "lowPrice": "19",
                "priceCurrency": "EUR",
            },
        }
    )

    summary = _summary(html)

    assert summary["price_low"][0] == "19"
    assert "price" not in summary
    assert summary["currency"][0] == "EUR"


def test_a_price_in_a_price_specification_is_found():
    html = _page(
        {
            "@type": "Product",
            "name": "Pads",
            "offers": {
                "@type": "Offer",
                "priceSpecification": {"price": "7.50", "priceCurrency": "GBP"},
            },
        }
    )

    summary = _summary(html)

    assert summary["price"][0] == "7.50"
    assert summary["currency"][0] == "GBP"


def test_addresses_resolve_against_the_page():
    html = _page(
        {"@type": "Product", "name": "Pad", "image": "/i/pad.jpg"},
        head='<link rel="canonical" href="/p/pad">',
    )

    summary = _summary(html, url="https://shop.example/c/pads?page=2")

    assert summary["url"] == (
        "https://shop.example/p/pad",
        "html",
        "<link rel=canonical>",
    )
    assert summary["image"][0] == "https://shop.example/i/pad.jpg"


def test_html_entities_written_into_json_ld_are_read_as_characters():
    html = _page({"@type": "Article", "headline": "Guide &#8226; Yoast &amp; you"})

    assert _summary(html)["title"][0] == "Guide • Yoast & you"


def test_a_locale_becomes_a_language_tag_when_the_page_has_no_lang():
    html = _page(head='<meta property="og:locale" content="en_US">')

    assert _summary(html)["language"] == ("en-US", "opengraph", "og:locale")


def test_an_opengraph_value_folded_onto_a_record_keeps_its_own_key():
    html = _page(
        {"@type": "CollectionPage", "name": "Men's Shoes"},
        head='<meta property="og:image" content="https://x.example/og.jpg">',
    )

    assert _summary(html)["image"] == (
        "https://x.example/og.jpg",
        "opengraph",
        "og:image",
    )


def test_induced_rows_are_never_the_subject():
    rows = "".join(
        f"<li class='r'><a href='/p{n}'>Product {n}</a>"
        f"<span class='p'>{n}.99</span></li>"
        for n in range(5)
    )
    html = (
        f"<html><head><title>Brakes</title></head><body><ul>{rows}</ul></body></html>"
    )

    assert extract(html, induce=True).summary["title"].value == "Brakes"


def test_answers_come_in_the_stated_order():
    html = _page(
        {
            "@type": "Product",
            "sku": "S",
            "name": "N",
            "offers": {"@type": "Offer", "price": "1", "priceCurrency": "EUR"},
        },
        head="<title>T</title>",
        attrs=" lang='en'",
    )

    names = list(extract(html).summary)

    assert names == [name for name in FIELDS if name in names]


def test_one_of_many_items_of_a_type_is_not_what_the_page_is_about():
    """A forum thread's ten Comment items made the title "Post #1"."""
    comments = "".join(
        '<div itemscope itemtype="https://schema.org/Comment">'
        f'<span itemprop="name">Post #{n}</span></div>'
        for n in range(3)
    )
    html = (
        '<html><head><meta property="og:title" content="Thread"></head>'
        f"<body>{comments}</body></html>"
    )

    assert _summary(html)["title"] == ("Thread", "opengraph", "og:title")


def test_a_product_with_one_related_product_is_still_the_subject():
    html = _page(
        {"@type": "Product", "name": "Main pad", "sku": "M1"},
        {"@type": "Product", "name": "Related pad", "sku": "R1"},
    )

    assert _summary(html)["sku"][0] == "M1"


def test_a_meta_itemprop_in_the_head_is_read_for_the_summary():
    """Outside any item, so not microdata, and on 14 of 511 WCXB pages."""
    html = (
        '<html><head><meta itemprop="datePublished" content="2026-03-11">'
        '<meta itemprop="dateModified" content="2026-03-12">'
        "</head></html>"
    )

    summary = _summary(html)

    assert summary["published"] == (
        "2026-03-11",
        "html",
        "<meta itemprop=datePublished>",
    )
    assert summary["modified"][0] == "2026-03-12"


def test_scholarly_citation_tags_answer_title_author_and_date():
    html = (
        '<html><head><meta name="citation_title" content="On sluices">'
        '<meta name="citation_author" content="A. One">'
        '<meta name="citation_author" content="B. Two">'
        '<meta name="citation_publication_date" content="2021/05/04">'
        "</head></html>"
    )

    summary = _summary(html)

    assert summary["title"][0] == "On sluices"
    assert summary["author"] == ("A. One, B. Two", "html", "meta name=citation_author")
    assert summary["published"][0] == "2021/05/04"


def test_the_common_date_and_byline_meta_names_are_read():
    html = (
        '<html><head><meta name="parsely-pub-date" content="2026-01-02T10:00:00Z">'
        '<meta name="byl" content="By Ann Smith and Bo Li">'
        "</head></html>"
    )

    summary = _summary(html)

    assert summary["published"][0] == "2026-01-02T10:00:00Z"
    assert summary["author"][0] == "Ann Smith and Bo Li"


def test_the_site_is_not_the_author():
    html = (
        '<html><head><meta name="author" content="WRAL">'
        '<meta property="og:site_name" content="WRAL"></head></html>'
    )

    assert "author" not in _summary(html)


def test_the_site_name_is_not_part_of_the_title():
    html = (
        '<html><head><meta property="og:title" '
        'content="Brief History of Coffee - Charleston Coffee Roasters">'
        '<meta property="og:site_name" content="Charleston Coffee Roasters">'
        "</head></html>"
    )

    assert _summary(html)["title"][0] == "Brief History of Coffee"


def test_a_blogger_who_publishes_their_own_posts_is_still_the_author():
    html = _page(
        {
            "@type": "BlogPosting",
            "headline": "H",
            "author": {"@type": "Person", "name": "Edwin Toonen"},
            "publisher": {"@type": "Person", "name": "Edwin Toonen"},
        }
    )

    assert _summary(html)["author"][0] == "Edwin Toonen"


def test_an_availability_that_is_only_the_vocabulary_is_no_answer():
    """Found by the property that every answer is a value.

    ``https://schema.org/`` shortened to its term is the empty string, and it
    was reported as the availability -- an empty answer, which also kept the
    page's ``og:availability`` from being asked.
    """
    html = (
        '<meta property="og:availability" content="in stock">'
        '<script type="application/ld+json">{"@type": "Product", "name": "P",'
        '"offers": {"price": "1", "availability": "https://schema.org/"}}</script>'
    )

    availability = extract(html).summary["availability"]

    assert (availability.value, availability.source) == ("in stock", "opengraph")


def _offers(offers):
    return _summary(_page({"@type": "Product", "name": "Pads", "offers": offers}))


def test_a_strikethrough_price_listed_first_is_the_regular_price_not_the_price():
    """Google's merchant listing: an active price has no priceType."""
    summary = _offers(
        {
            "@type": "Offer",
            "priceSpecification": [
                {
                    "price": "15.00",
                    "priceCurrency": "EUR",
                    "priceType": "https://schema.org/StrikethroughPrice",
                },
                {"price": "10.00", "priceCurrency": "EUR"},
            ],
        }
    )

    assert summary["price"][0] == "10.00"
    assert summary["price"][2] == "Product.offers.priceSpecification[1].price"
    assert summary["price_regular"][0] == "15.00"


def test_a_member_price_listed_first_is_not_the_price():
    summary = _offers(
        {
            "@type": "Offer",
            "priceSpecification": [
                {"price": "8.00", "validForMemberTier": {"name": "Gold"}},
                {"price": "10.00", "priceCurrency": "EUR"},
            ],
        }
    )

    assert summary["price"][0] == "10.00"
    assert "price_regular" not in summary


def test_the_offers_inside_an_aggregate_offer_are_read():
    summary = _offers(
        {
            "@type": "AggregateOffer",
            "offerCount": 2,
            "offers": [
                {"@type": "Offer", "price": "12.50", "priceCurrency": "GBP"},
                {"@type": "Offer", "price": "13", "priceCurrency": "USD"},
            ],
        }
    )

    assert summary["price"] == ("12.50", "jsonld", "Product.offers.offers[0].price")
    assert summary["currency"][0] == "GBP"


def test_price_and_currency_always_come_from_one_offer():
    summary = _offers(
        [
            {
                "@type": "Offer",
                "price": "5",
                "priceType": "ListPrice",
                "priceCurrency": "USD",
            },
            {"@type": "Offer", "price": "6", "priceCurrency": "EUR"},
        ]
    )

    assert summary["price"][0] == "6"
    assert summary["currency"] == ("EUR", "jsonld", "Product.offers[1].priceCurrency")


def test_facebook_s_product_tags_answer_a_page_with_no_offer():
    html = (
        '<meta property="og:type" content="product">'
        '<meta property="product:price:amount" content="24.95">'
        '<meta property="product:price:currency" content="EUR">'
        '<meta property="product:availability" content="in stock">'
        '<meta property="product:retailer_item_id" content="BP-1187">'
    )

    summary = _summary(html)

    assert summary["price"] == ("24.95", "opengraph", "product:price:amount")
    assert summary["currency"][0] == "EUR"
    assert summary["sku"] == ("BP-1187", "opengraph", "product:retailer_item_id")


def test_identifiers_and_the_rating_are_answered_as_declared():
    summary = _summary(
        _page(
            {
                "@type": "Product",
                "name": "Pads",
                "gtin13": "4001234567891",
                "mpn": "BP-2210",
                "aggregateRating": {
                    "@type": "AggregateRating",
                    "ratingValue": "8",
                    "bestRating": "10",
                    "reviewCount": "112",
                },
            }
        )
    )

    assert summary["gtin"] == ("4001234567891", "jsonld", "Product.gtin13")
    assert summary["mpn"][0] == "BP-2210"
    # Never rescaled: 8 of 10 is 8, with the best beside it.
    assert summary["rating"] == ("8", "jsonld", "Product.aggregateRating.ratingValue")
    assert summary["rating_best"][0] == "10"
    assert summary["rating_count"] == (
        "112",
        "jsonld",
        "Product.aggregateRating.reviewCount",
    )


def test_the_breadcrumb_is_the_last_list_in_the_order_of_its_positions():
    html = (
        _page(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "Elsewhere"}
                ],
            }
        )
        + _page(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 3, "name": "Brake pads"},
                    {
                        "@type": "ListItem",
                        "position": 1,
                        "item": {"@id": "/", "name": "Home"},
                    },
                    {"@type": "ListItem", "position": 2, "name": "Brakes"},
                ],
            }
        )
        + _page({"@type": "Product", "name": "Pads"})
    )

    assert _summary(html)["breadcrumb"] == (
        "Home > Brakes > Brake pads",
        "jsonld",
        "BreadcrumbList.itemListElement",
    )


def test_a_gtin_with_a_wrong_check_digit_is_answered_but_not_normalised():
    """The page's value is kept; the normalised one would name another product."""
    from sluicer import extract

    page = _page({"@type": "Product", "name": "Pads", "gtin13": "4001234567890"})
    result = extract(page)

    assert result.summary["gtin"].value == "4001234567890"
    assert "gtin" not in result.normalised


def _product(name, **fields):
    return _page({"@type": "Product", "name": name, **fields})


def test_one_product_declared_once_per_colour_is_one_product():
    """Zara, on Zyte's product benchmark: a Product per colour, one name."""
    colours = "".join(
        _product(
            "Boots",
            sku=f"BOOT-{n}",
            offers={
                "price": "69.95",
                "priceCurrency": "EUR",
                "availability": "InStock" if n % 2 else "OutOfStock",
            },
        )
        for n in range(4)
    )

    summary = _summary(colours)

    assert summary["title"][0] == "Boots"
    assert summary["price"][0] == "69.95"
    # What the colours disagree on belongs to one colour, not to the product.
    assert "sku" not in summary
    assert "availability" not in summary


def test_the_one_product_with_an_offer_among_related_ones_is_the_subject():
    """Argos: its product with an offer, and four related ones without."""
    page = _product(
        "Kettle", sku="4667999", offers={"price": "34.99", "priceCurrency": "GBP"}
    )
    page += "".join(_product(f"Related {n}") for n in range(4))

    summary = _summary(page)

    assert summary["title"][0] == "Kettle"
    assert summary["price"][0] == "34.99"


def test_a_category_page_is_still_a_listing():
    page = "".join(
        _product(f"Item {n}", offers={"price": f"{n}.00", "priceCurrency": "EUR"})
        for n in range(4)
    )

    assert "price" not in _summary(page)


def test_a_price_that_holds_two_numbers_gives_way_to_the_next_declaration():
    """Almedina: microdata price text '71,91 € 79,90 €', and a clean product: tag."""
    page = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Book</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">71,91 € 79,90 €</span></div></div>'
        '<meta property="product:price:amount" content="71.91">'
    )

    assert _summary(page)["price"] == ("71.91", "opengraph", "product:price:amount")
