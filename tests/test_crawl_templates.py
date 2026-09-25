"""Ready crawls: a site's sitemaps read page by page, and a Shopify shop's
products from its products.json. Local fixtures only; no shop is asked."""

import json
from pathlib import Path

import pytest

from fake_site import FakeWeb, page
from sluicer.crawl import StateMismatch
from sluicer.crawl.templates import MOST_NESTING, shopify_products, sitemap_pages
from sluicer.summary import FIELDS

SHOP = "https://shop.example"
PRODUCTS = (Path(__file__).parent / "fixtures" / "shopify_products.json").read_text(
    encoding="utf-8"
)
NS = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def json_page(products):
    return (
        200,
        json.dumps({"products": products}),
        {"content-type": "application/json"},
    )


def fixture_products():
    return json.loads(PRODUCTS)["products"]


def listing(n, start=0):
    """``n`` products named Item start..start+n-1."""
    return [
        {
            "id": start + i,
            "title": f"Item {start + i}",
            "handle": f"item-{start + i}",
            "variants": [{"price": "1.00", "sku": f"I{start + i}", "available": True}],
        }
        for i in range(n)
    ]


def products_url(page_number, per_page=2):
    return f"{SHOP}/products.json?limit={per_page}&page={page_number}"


def shop(fake, **options):
    options.setdefault("per_page", 2)
    return shopify_products(
        f"{SHOP}/", web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep, **options
    )


# -- Shopify ----------------------------------------------------------------------


def test_a_shop_s_products_are_read_page_by_page_until_a_page_is_short():
    fake = FakeWeb(
        {
            products_url(1): json_page(fixture_products()),
            products_url(2): json_page(listing(1, start=10)),
        }
    )

    run = shop(fake)
    products = list(run)

    assert [p.url for p in products] == [
        f"{SHOP}/products/brake-pad-set-front",
        f"{SHOP}/products/wiper-blade",
        f"{SHOP}/products/item-10",
    ]
    assert [p.found_on for p in products] == [products_url(1)] * 2 + [products_url(2)]
    assert fake.asked() == [f"{SHOP}/robots.txt", products_url(1), products_url(2)]
    assert run.stopped == "done"


def test_a_product_is_a_record_of_shopify_s_own_fields_and_a_summary():
    fake = FakeWeb({products_url(1, 3): json_page(fixture_products())})

    pads, wiper = list(shop(fake, per_page=3))

    record = pads.extraction.records[0]
    assert record.type == "Product" and record.source == "shopify"
    assert record.where == "/products/0"
    assert record.fields["title"].value == "Brake pad set, front"
    assert record.fields["title"].where == "/products/0/title"
    assert record.fields["variants"].value[0]["price"] == "49.90"
    assert record.fields["variants"].value[0]["available"] == "true"
    said = {name: field.value for name, field in pads.extraction.summary.items()}
    assert said == {
        "title": "Brake pad set, front",
        "description": "Ceramic pads for quiet braking.",
        "url": f"{SHOP}/products/brake-pad-set-front",
        "image": "https://cdn.shop.example/files/bp-100.jpg",
        "published": "2026-05-02T10:00:00+02:00",
        "modified": "2026-09-01T12:30:00+02:00",
        "type": "Product",
        "price": "49.90",
        "price_regular": "59.90",
        "availability": "InStock",
        "brand": "Acme Parts",
        "sku": "BP-100",
    }
    assert pads.extraction.summary["price"].key == "variants/price"
    assert pads.extraction.summary["price"].where == "/products/0/variants/0/price"
    assert list(pads.extraction.summary) == [
        name for name in FIELDS if name in pads.extraction.summary
    ]
    wiper_said = {name: f.value for name, f in wiper.extraction.summary.items()}
    assert wiper_said["price_low"] == "12.00" and wiper_said["price_high"] == "15.50"
    assert "price" not in wiper_said and "sku" not in wiper_said
    assert "description" not in wiper_said
    assert wiper_said["availability"] == "InStock"
    assert pads.found and pads.status == 200 and pads.rung == "http"


def test_a_product_line_is_a_page_line():
    fake = FakeWeb({products_url(1): json_page(fixture_products()[:1])})

    [line] = [p.to_json() for p in shop(fake)]

    assert line["ok"] is True and line["depth"] == 1
    assert line["summary"]["title"]["source"] == "shopify"
    assert line["records"][0]["fields"]["vendor"]["value"] == "Acme Parts"
    assert line["sources"] == ["shopify"] and line["links"] == []
    json.dumps(line)


def test_the_page_budget_bounds_the_json_pages_asked_and_says_it_cut():
    fake = FakeWeb({products_url(n): json_page(listing(2, 2 * n)) for n in (1, 2, 3)})

    run = shop(fake, max_pages=2)
    products = list(run)

    assert len(products) == 4 and run.stopped == "max_pages"
    assert products_url(3) not in fake.asked()


def test_each_json_page_waits_the_site_s_delay():
    pages = {products_url(n): json_page(listing(2, 2 * n)) for n in (1, 2)}
    pages[f"{SHOP}/robots.txt"] = "User-agent: *\nCrawl-delay: 3\n"
    fake = FakeWeb(pages)

    list(shop(fake))

    assert fake.gaps("shop.example") == [3.0, 3.0, 3.0]


def test_a_shop_whose_robots_refuses_its_products_json_is_not_asked():
    fake = FakeWeb(
        {
            f"{SHOP}/robots.txt": "User-agent: *\nDisallow: /products.json\n",
            products_url(1): json_page(fixture_products()),
        }
    )

    [refused] = list(shop(fake))

    assert refused.url == products_url(1)
    assert refused.error.code == "refused_by_robots"
    assert fake.asked() == [f"{SHOP}/robots.txt"]


def test_a_site_that_is_not_a_shop_says_so():
    fake = FakeWeb({products_url(1): (404, "<html>Not found</html>", {})})

    [answer] = list(shop(fake))

    assert answer.error.code == "bad_input"
    assert "answered 404" in answer.error.message
    assert "Shopify" in answer.error.message


def test_what_is_not_products_json_says_so():
    fake = FakeWeb({products_url(1): "<html><body>A shop, not JSON</body></html>"})

    [answer] = list(shop(fake))

    assert answer.error.code == "bad_input"
    assert "not a Shopify products.json" in answer.error.message


@pytest.mark.parametrize("depth", [200, 5_000, 100_000])
def test_a_products_json_nested_past_any_shop_is_read_without_recursion(depth):
    """Measured on 0.8.0: a product whose tags nested 5,000 lists deep raised
    RecursionError out of the crawl, and 100,000 did so from the parser. And
    how deep the parser goes depends on the Python: CI's 3.10 to 3.13 refused
    5,000 and its 3.14 read 100,000, so the depth is judged before parsing,
    the same on every Python."""
    deep = "[" * depth + "]" * depth
    body = (
        '{"products": [{"id": 1, "handle": "ok", "title": "Fine", "tags": '
        + deep
        + "}]}"
    )
    fake = FakeWeb({products_url(1): (200, body, {"content-type": "application/json"})})

    [answer] = list(shop(fake))

    if depth <= MOST_NESTING:
        assert answer.ok and answer.url == f"{SHOP}/products/ok"
        json.dumps(answer.to_json())
    else:
        assert answer.error.code == "bad_input"
        assert "not a Shopify products.json" in answer.error.message


def test_a_json_page_that_fails_is_asked_again_as_a_page_is():
    fake = FakeWeb(
        {products_url(1): [ConnectionResetError("reset"), json_page(listing(1))]}
    )

    [product] = list(shop(fake))

    assert product.ok and len(product.retries) == 1


def test_a_shop_read_to_a_file_resumes_where_it_stopped(tmp_path):
    out = tmp_path / "products.jsonl"
    pages = {products_url(n): json_page(listing(2, 2 * n)) for n in (1, 2, 3)}
    pages[products_url(4)] = json_page([])

    first = list(shop(FakeWeb(pages), max_pages=2, state=out))
    fake = FakeWeb(pages)
    resumed = shop(fake, state=out)
    rest = list(resumed)

    assert len(first) == 4 and len(rest) == 2
    assert resumed.resumed == 4
    # The last page the file holds is asked again, for a product it might
    # have been stopped before; what it holds is not written twice.
    assert [u for u in fake.asked() if "robots" not in u] == [
        products_url(2),
        products_url(3),
        products_url(4),
    ]
    written = [
        json.loads(line)["url"] for line in out.read_text(encoding="utf-8").splitlines()
    ]
    assert len(written) == len(set(written)) == 6


def test_another_shop_s_file_is_refused(tmp_path):
    out = tmp_path / "products.jsonl"
    out.write_text(
        json.dumps(
            {
                "url": "https://other.example/products/x",
                "ok": True,
                "found_on": "https://other.example/products.json?limit=2&page=1",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(StateMismatch):
        list(shop(FakeWeb({}), state=out))


# -- sitemaps -----------------------------------------------------------------------


def sitemap_site():
    return {
        f"{SHOP}/sitemap.xml": (
            f"<urlset {NS}>"
            + "".join(
                f"<url><loc>{SHOP}/{path}</loc></url>"
                for path in ("p/1", "p/2", "blog/1", "p/3")
            )
            + "</urlset>"
        ),
        f"{SHOP}/p/1": page("Pad 1"),
        f"{SHOP}/p/2": page("Pad 2"),
        f"{SHOP}/p/3": page("Pad 3"),
        f"{SHOP}/blog/1": page("Post"),
    }


def sitemaps(fake, **options):
    return sitemap_pages(
        f"{SHOP}/", web=fake.web(), clock=fake.clock, sleep=fake.clock.sleep, **options
    )


def test_a_sitemap_crawl_reads_every_address_its_sitemaps_list():
    fake = FakeWeb(sitemap_site())

    run = sitemaps(fake)
    pages = list(run)

    assert [p.url for p in pages] == [
        f"{SHOP}/p/1",
        f"{SHOP}/p/2",
        f"{SHOP}/blog/1",
        f"{SHOP}/p/3",
    ]
    assert all(p.ok and p.found for p in pages)
    assert run.stopped == "done"
    assert fake.gaps("shop.example") == [1.0] * 5


def test_a_sitemap_crawl_keeps_what_include_and_exclude_choose_up_to_its_budget():
    fake = FakeWeb(sitemap_site())

    run = sitemaps(fake, include=["/p/"], exclude=["/p/2"], max_pages=1)
    pages = list(run)

    assert [p.url for p in pages] == [f"{SHOP}/p/1"]
    assert run.stopped == "max_pages"


def test_a_sitemap_crawl_resumes_as_a_batch_does(tmp_path):
    out = tmp_path / "pages.jsonl"
    list(sitemaps(FakeWeb(sitemap_site()), max_pages=2, state=out))
    fake = FakeWeb(sitemap_site())

    resumed = sitemaps(fake, state=out)
    rest = list(resumed)

    assert [p.url for p in rest] == [f"{SHOP}/blog/1", f"{SHOP}/p/3"]
    assert resumed.resumed == 2
    assert f"{SHOP}/p/1" not in fake.asked()
