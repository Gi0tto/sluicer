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
            "headline": "The diver who knits",
            "author": [{"@type": "Person", "name": "Mara Quill"}],
            "datePublished": "2026-09-22T14:00:02Z",
            "publisher": {"@type": "Organization", "name": "Example News"},
            "image": {"@type": "ImageObject", "url": "https://i.example/a.jpg"},
        },
        head='<meta property="og:title" content="The diver who knits | Example News">',
    )

    summary = _summary(html)

    assert summary["title"] == (
        "The diver who knits",
        "jsonld",
        "NewsArticle.headline",
    )
    assert summary["author"] == ("Mara Quill", "jsonld", "NewsArticle.author")
    assert summary["published"][0] == "2026-09-22T14:00:02Z"
    assert summary["publisher"][0] == "Example News"
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
        head='<meta name="author" content="Jane Doe">'
        '<meta property="article:author" content="https://x.example/profile/np">',
    )

    assert _summary(html)["author"] == ("Jane Doe", "html", "meta name=author")


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


def test_a_json_ld_address_keeps_a_query_that_spells_a_legacy_entity():
    """``&reg`` and ``&sect`` need no semicolon in HTML, but not before a letter.

    Read as ``html.unescape`` reads text, ``?id=1&region=us&section=a`` was
    ``?id=1\u00aeion=us\u00a7ion=a``: the HTML standard leaves such a
    reference alone in an attribute when a letter, a digit or ``=`` follows,
    which is how a browser reads the same address in an ``href``.
    """
    address = "https://shop.example/p?id=1&region=us&section=a&para=2&copy=3"
    html = _page(
        {
            "@type": "Product",
            "name": "Pad &amp; pen",
            "url": address,
            "image": address + "&not=4",
            "description": "Ben &amp; Jerry&#39;s &copy 2024 &lt;b&gt; &amp",
        }
    )

    summary = _summary(html)

    assert summary["url"][0] == address
    assert summary["image"][0] == address + "&not=4"
    assert summary["title"][0] == "Pad & pen"
    assert summary["description"][0] == "Ben & Jerry's \u00a9 2024 <b> &"


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
        '<html><head><meta name="author" content="Northside TV">'
        '<meta property="og:site_name" content="Northside TV"></head></html>'
    )

    assert "author" not in _summary(html)


def test_the_site_name_is_not_part_of_the_title():
    html = (
        '<html><head><meta property="og:title" '
        'content="Brief History of Coffee - Harbour Coffee Roasters">'
        '<meta property="og:site_name" content="Harbour Coffee Roasters">'
        "</head></html>"
    )

    assert _summary(html)["title"][0] == "Brief History of Coffee"


def test_a_blogger_who_publishes_their_own_posts_is_still_the_author():
    html = _page(
        {
            "@type": "BlogPosting",
            "headline": "H",
            "author": {"@type": "Person", "name": "Theo Marsh"},
            "publisher": {"@type": "Person", "name": "Theo Marsh"},
        }
    )

    assert _summary(html)["author"][0] == "Theo Marsh"


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
    """A shop on Zyte's product benchmark: a Product per colour, one name."""
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
    """A shop's product with an offer, and four related ones without."""
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
    """A bookshop's microdata price text '71,91 € 79,90 €', and a clean product: tag."""
    page = (
        '<div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">Book</span>'
        '<div itemprop="offers" itemscope itemtype="https://schema.org/Offer">'
        '<span itemprop="price">71,91 € 79,90 €</span></div></div>'
        '<meta property="product:price:amount" content="71.91">'
    )

    assert _summary(page)["price"] == ("71.91", "opengraph", "product:price:amount")


def test_a_product_id_answers_the_sku_when_no_sku_is_declared():
    summary = _summary(_page({"@type": "Product", "name": "Pads", "productID": "BP-9"}))

    assert summary["sku"] == ("BP-9", "jsonld", "Product.productID")


# -- a ProductGroup and its variants, as Google documents them ------------------


def _group(*variants, group_offers=None, extra=None, nested=True):
    import json

    group = {
        "@context": "https://schema.org/",
        "@type": "ProductGroup",
        "@id": "#coat",
        "name": "Wool winter coat",
        "brand": {"@type": "Brand", "name": "Good brand"},
        "productGroupID": "44E01",
        **(extra or {}),
    }
    if group_offers is not None:
        group["offers"] = group_offers
    if nested:
        group["hasVariant"] = list(variants) if len(variants) != 1 else variants[0]
        nodes = [group]
    else:
        nodes = [group, *variants]
    script = f'<script type="application/ld+json">{json.dumps(nodes)}</script>'
    return f"<html><head>{script}</head></html>"


def _variant(
    sku, price, currency="USD", availability="https://schema.org/InStock", **more
):
    offers = {"@type": "Offer", "price": price, "priceCurrency": currency}
    if availability:
        offers["availability"] = availability
    return {
        "@type": "Product",
        "sku": sku,
        "name": f"Coat {sku}",
        "offers": offers,
        **more,
    }


def _answers(html):
    from sluicer import extract

    summary = extract(html).summary
    return {name: (field.value, field.key) for name, field in summary.items()}


def test_variants_priced_apart_are_a_range_with_each_ends_own_key():
    """Google's own example: the summary gave only title, brand and type."""
    got = _answers(
        _group(_variant("S", 39.99), _variant("M", 39.99), _variant("L", 49.99))
    )
    assert got["price_low"] == ("39.99", "ProductGroup.hasVariant[0].offers.price")
    assert got["price_high"] == ("49.99", "ProductGroup.hasVariant[2].offers.price")
    assert got["currency"] == ("USD", "ProductGroup.hasVariant[0].offers.priceCurrency")
    assert got["availability"][0] == "InStock"
    assert got["brand"] == ("Good brand", "ProductGroup.brand")
    assert "price" not in got
    assert "sku" not in got, "a variant's SKU is not the group's"


def test_variants_priced_alike_answer_the_price():
    got = _answers(_group(_variant("S", 10), _variant("M", 10)))
    assert got["price"] == ("10", "ProductGroup.hasVariant[0].offers.price")
    assert "price_low" not in got and "price_high" not in got


def test_a_range_needs_one_currency_and_amounts_that_read():
    apart = _answers(_group(_variant("S", 10, "USD"), _variant("M", 12, "EUR")))
    assert not {"price", "price_low", "price_high", "currency"} & set(apart)
    unsure = _answers(_group(_variant("S", "1.299"), _variant("M", "12")))
    assert not {"price_low", "price_high"} & set(unsure)


def test_a_range_needs_two_variants_that_declare_a_price():
    """Google's page-per-variant shape: one variant described, the others
    only linked. The group's price is not known here, and no variant is picked."""
    got = _answers(_group(_variant("S", 39.99), {"url": "https://example.com/coat/l"}))
    assert not {"price", "price_low", "price_high", "currency"} & set(got)


def test_an_availability_the_variants_do_not_share_is_not_answered():
    got = _answers(
        _group(
            _variant("S", 10),
            _variant("M", 10, availability="https://schema.org/OutOfStock"),
        )
    )
    assert got["price"][0] == "10"
    assert "availability" not in got


def test_the_groups_own_offers_come_before_its_variants():
    got = _answers(
        _group(
            _variant("S", 10),
            _variant("M", 20),
            group_offers={
                "@type": "AggregateOffer",
                "lowPrice": 9,
                "highPrice": 25,
                "priceCurrency": "GBP",
            },
        )
    )
    assert got["price_low"] == ("9", "ProductGroup.offers.lowPrice")
    assert got["currency"][0] == "GBP"


def test_a_field_the_group_leaves_to_its_variants_is_answered_when_all_agree():
    same = _answers(_group(_variant("S", 10, mpn="C-1"), _variant("M", 10, mpn="C-1")))
    assert same["mpn"] == ("C-1", "ProductGroup.hasVariant[0].mpn")
    apart = _answers(_group(_variant("S", 10, mpn="C-1"), _variant("M", 10, mpn="C-2")))
    assert "mpn" not in apart


def test_one_variant_nested_alone_is_read_at_its_own_path():
    got = _answers(_group(_variant("S", 10)))
    assert got["price"] == ("10", "ProductGroup.hasVariant.offers.price")


def test_variants_declared_apart_are_found_by_what_they_point_at():
    """Google's second shape: each variant its own node, isVariantOf the group."""
    by_reference = [
        {**_variant("S", 39.99), "isVariantOf": {"@id": "#coat"}},
        {**_variant("M", 49.99), "isVariantOf": {"@id": "#coat"}},
    ]
    got = _answers(_group(*by_reference, nested=False))
    assert got["price_low"] == ("39.99", "Product.offers.price")
    assert got["price_high"] == ("49.99", "Product.offers.price")
    by_id = [
        {**_variant("S", 5), "inProductGroupWithID": "44E01"},
        {**_variant("M", 5), "inProductGroupWithID": "44E01"},
        {**_variant("X", 99), "inProductGroupWithID": "OTHER"},
    ]
    assert _answers(_group(*by_id, nested=False))["price"][0] == "5"


def test_a_variant_may_name_its_group_by_id_or_by_name():
    by_text = [
        {**_variant("S", 7), "isVariantOf": "44E01"},
        {**_variant("M", 7), "isVariantOf": "44E01"},
    ]
    assert _answers(_group(*by_text, nested=False))["price"][0] == "7"
    by_name = [
        {**_variant("S", 3), "isVariantOf": {"name": "Wool winter coat"}},
        {**_variant("M", 3), "isVariantOf": {"name": "Wool winter coat"}},
    ]
    html = _group(*by_name, nested=False).replace('"productGroupID": "44E01", ', "")
    assert _answers(html)["price"][0] == "3"
    stranger = [
        {**_variant("S", 3), "isVariantOf": {"name": "Another coat"}},
        {**_variant("M", 3), "isVariantOf": {"name": "Another coat"}},
    ]
    html = _group(*stranger, nested=False).replace('"productGroupID": "44E01", ', "")
    assert "price" not in _answers(html)


def test_a_hostile_group_of_variants_is_read_only_so_far():
    many = [_variant(str(i), 10) for i in range(500)] + [_variant("last", 99)]
    got = _answers(_group(*many))
    assert got["price"][0] == "10", "only the first hundred variants are read"


def test_a_variant_written_as_an_address_alone_is_no_variant_to_read():
    got = _answers(
        _group(_variant("S", 10), "https://example.com/coat/m", _variant("L", 10))
    )
    assert got["price"] == ("10", "ProductGroup.hasVariant[0].offers.price")


def test_an_address_that_cleans_to_nothing_lets_the_next_declaration_answer():
    """Found by the fuzz profile: a JSON-LD ``url`` of one control character,
    resolved against the page's base, was the empty answer ``""``."""
    page = (
        '<html><head><base href="">'
        '<script type="application/ld+json">'
        '{"@type": "Product", "name": "Pad", "url": "\\u001b"}</script>'
        '<meta property="og:url" content="https://shop.example/p">'
        "</head><body></body></html>"
    )
    url = extract(page, url="https://shop.example/").summary["url"]
    assert (url.value, url.source) == ("https://shop.example/p", "opengraph")


def _ld(*nodes: object) -> str:
    return "".join(
        '<script type="application/ld+json">'
        f"{json.dumps(node, ensure_ascii=False)}</script>"
        for node in nodes
    )


def test_the_journal_a_page_is_published_in_is_not_what_it_is_about():
    """Found on the news scoreboard: a journal declares its Periodical in
    the footer of every article, and its name was every article's title."""
    page = (
        '<html><head><meta property="og:title" content="How to fight climate change">'
        "</head><body><footer><div itemscope itemtype='https://schema.org/Periodical'>"
        "<span itemprop='name'>The Journal</span></div></footer></body></html>"
    )
    summary = extract(page).summary
    assert summary["title"].value == "How to fight climate change"
    assert "type" not in summary or summary["type"].value != "Periodical"


def test_beside_an_article_a_record_named_as_the_publisher_is_not_the_subject():
    """Found on the news scoreboard: a paper declares its own app, named as
    the paper is, ahead of the story, and the app was the page's title."""
    page = _ld(
        {"@type": "NewsMediaOrganization", "name": "Daily Paper"},
        {"@type": "MobileApplication", "name": "Daily Paper", "offers": {"price": "0"}},
        {"@type": "NewsArticle", "headline": "Police arrest two", "author": "Ada"},
    )
    summary = extract(page).summary
    assert summary["title"].value == "Police arrest two"
    assert summary["type"].value == "NewsArticle"
    assert "price" not in summary, "the app's price is not the story's"


def test_a_business_named_as_its_site_stays_the_subject_beside_its_reviews():
    """The rule above is for pages with an article: a landscaper's page declares
    the business, named as the site, and a review of it."""
    page = (
        '<html><head><meta property="og:site_name" content="Green Acre Landscaping">'
        + _ld(
            {"@type": "LocalBusiness", "name": "Green Acre Landscaping"},
            {"@type": "Review", "name": "Lawn Maintenance", "author": "Pat"},
        )
        + "</head></html>"
    )
    summary = extract(page).summary
    assert summary["type"].value == "LocalBusiness"
    assert "author" not in summary, "a review's author is not the page's"


def test_an_author_is_a_name_not_a_number_nor_the_site_s_own_address():
    """Found on the news scoreboard: one paper writes an id, 105092, where
    the author goes, and another writes its own domain."""
    numbered = '<html><head><meta name="author" content="105092"></head></html>'
    assert "author" not in extract(numbered).summary
    url = "https://www.news.example/p"
    domain = '<html><head><meta name="author" content="news.example"></head></html>'
    assert "author" not in extract(domain, url=url).summary
    person = '<html><head><meta name="author" content="John Doe"></head></html>'
    assert extract(person, url=url).summary["author"].value == "John Doe"


def test_a_person_s_own_site_bears_their_name_and_they_sign_it():
    """Found on the scoreboard as served: a blogger publishes their own site
    as a Person, so the author bearing the site's name is its owner."""

    def page(publisher_type: object, *extra: dict[str, object]) -> str:
        publisher = {"@type": publisher_type, "name": "Sam Rivera"}
        return (
            '<html><head><meta property="og:site_name" content="Sam Rivera">'
            + _ld(
                {
                    "@type": "BlogPosting",
                    "headline": "My fitness journey",
                    "author": {"name": "Sam Rivera"},
                    "publisher": publisher,
                },
                *extra,
            )
            + "</head></html>"
        )

    blog = extract(page(["Person", "Organization"])).summary
    assert blog["author"].value == "Sam Rivera"
    assert blog["author"].key == "BlogPosting.author"
    paper = extract(page("NewsMediaOrganization")).summary
    assert "author" not in paper, "a paper signing its own story names no one"
    # WordPress declares a Person for every user, a shared account named as
    # the site included: that alone does not make the site a person's.
    user = {"@type": "Person", "name": "Sam Rivera"}
    assert "author" not in extract(page("Organization", user)).summary


def test_a_title_ending_in_the_page_s_own_host_has_it_cut():
    """WCXB: "Volunteer with us | town.example", on town.example, is the first
    part alone."""
    page = "<html><head><title>Volunteer with us | town.example</title></head></html>"
    url = "https://www.town.example/volunteer"
    assert extract(page, url=url).summary["title"].value == "Volunteer with us"


def test_a_page_s_declared_main_entity_is_what_it_is_about():
    """Found on the news scoreboard: a news site declares a WebPage whose
    mainEntity is the NewsArticle, and its author went unread."""
    page = (
        "<html><head>"
        + _ld(
            {
                "@type": "WebPage",
                "name": "Example News",
                "mainEntity": {
                    "@type": "NewsArticle",
                    "headline": "Who inherits the mill?",
                    "datePublished": "2023-04-28T18:16:04+0200",
                    "author": {"@type": "Person", "name": "Greta Lindner"},
                },
            }
        )
        + "</head></html>"
    )
    summary = extract(page).summary
    assert summary["type"].value == "NewsArticle"
    assert summary["title"].value == "Who inherits the mill?"
    author = summary["author"]
    assert (author.value, author.key) == ("Greta Lindner", "NewsArticle.author")
    assert author.where == "/html/head/script[1]#/mainEntity/author"
    assert (
        summary["published"].where == "/html/head/script[1]#/mainEntity/datePublished"
    )


def test_a_main_entity_declared_in_microdata_is_placed_at_its_element():
    page = (
        '<html><body itemscope itemtype="https://schema.org/WebPage">'
        '<article itemprop="mainEntity" itemscope '
        'itemtype="https://schema.org/BlogPosting">'
        '<h1 itemprop="headline">Tube amp versus solid state</h1>'
        '<span itemprop="author">valvefan42</span></article></body></html>'
    )
    summary = extract(page).summary
    assert summary["type"].value == "BlogPosting"
    assert summary["author"].value == "valvefan42"
    assert summary["author"].where == "/html/body/article[1]/span[1]"


def test_a_main_entity_that_is_a_list_or_the_site_is_not_the_subject():
    """An FAQ page's questions are its parts, and an about page's organisation
    is the site: neither is what the summary is about."""
    faq = _ld(
        {
            "@type": "FAQPage",
            "name": "Shipping questions",
            "mainEntity": [
                {"@type": "Question", "name": "How long?"},
                {"@type": "Question", "name": "How much?"},
            ],
        }
    )
    summary = extract(f"<html><head>{faq}</head></html>").summary
    assert (summary["type"].value, summary["title"].value) == (
        "FAQPage",
        "Shipping questions",
    )
    about = _ld(
        {
            "@type": "AboutPage",
            "name": "About us",
            "mainEntity": {"@type": "Organization", "name": "Acme"},
        }
    )
    summary = extract(f"<html><head>{about}</head></html>").summary
    assert (summary["type"].value, summary["title"].value) == ("AboutPage", "About us")


def test_every_author_tag_is_read_and_the_site_s_own_is_passed_over():
    """Found on the news scoreboard: a paper's first author tag is the paper,
    its second the reporter, and the first alone was read."""
    paper = (
        '<html><head><meta property="og:site_name" content="Example Daily">'
        '<meta name="author" content="Example Daily">'
        '<meta name="author" content="Han Mi-rae">'
        "</head></html>"
    )
    author = extract(paper).summary["author"]
    assert (author.value, author.key) == ("Han Mi-rae", "meta name=author")
    assert author.where == "/html/head/meta[3]"
    two = (
        '<html><head><meta name="author" content="Lena Voss">'
        '<meta name="Author" content="Tobias Kern"></head></html>'
    )
    author = extract(two).summary["author"]
    assert (author.value, author.where) == ("Lena Voss, Tobias Kern", None)
    alone = (
        '<html><head><meta property="og:site_name" content="Example Daily">'
        '<meta name="author" content="Example Daily"></head></html>'
    )
    assert "author" not in extract(alone).summary


def test_the_names_content_systems_give_nobody_are_no_author():
    """Found on trafilatura's evaluation set: Blogger writes "Unknown" and
    Joomla "Super User" where the author goes, and WordPress "admin"."""
    for placeholder in ("admin", "Administrator", "Super User", "Unknown"):
        page = f'<html><head><meta name="author" content="{placeholder}"></head></html>'
        assert "author" not in extract(page).summary, placeholder
    named = '<html><head><meta name="author" content="Anna Admin"></head></html>'
    assert extract(named).summary["author"].value == "Anna Admin"
