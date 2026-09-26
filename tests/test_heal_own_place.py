"""heal moves a page field only to the page's own places, on evidence.

Found by the 0.9.1 demo study: an extractor learnt with ``--want`` on three
books.toscrape.com product pages, healed with one redesigned page, moved
``price`` into the "Products you recently viewed" strip, which held one
other book whose price was a learnt one, £51.77. heal exited 0, wrote the
file, and the healed extractor read that book's price as the page's. The
fixtures under ``fixtures/books_redesign`` are those pages, trimmed: the
price moved from ``p.price_color`` to ``div.price-box>span.price-now``.
"""

from pathlib import Path

from click.testing import CliRunner

from sluicer.cli import main
from sluicer.extractor import (
    Extractor,
    compile_extractor,
    heal,
    run_extractor,
)

REDESIGN = Path(__file__).parent / "fixtures" / "books_redesign"
PRICES = {
    "a-light-in-the-attic_1000": "£51.77",
    "sapiens-a-brief-history-of-humankind_996": "£54.23",
    "tipping-the-velvet_999": "£53.74",
}


def learnt() -> Extractor:
    return Extractor.from_json((REDESIGN / "book-want.json").read_text("utf-8"))


def pages(folder: str) -> list[tuple[bytes, str]]:
    return [
        (
            path.read_bytes(),
            f"https://books.toscrape.com/catalogue/{path.stem}/index.html",
        )
        for path in sorted((REDESIGN / folder).glob("*.html"))
    ]


def test_one_redesigned_page_heals_its_own_price_not_a_related_books():
    [page] = pages("one")

    healed, changes = heal(learnt(), [page])

    price = next(c for c in changes if c.before == "price")
    assert price.kind == "moved"
    assert price.after is not None
    assert "product_pod" not in price.after
    assert price.after.endswith("span.price-now")
    assert price.evidence == {"seen": 1, "samples": 3, "runner_up": 0}
    run = run_extractor(healed, *page)
    assert run.ok
    assert run.fields["price"] == "£53.74"


def test_three_redesigned_pages_still_heal_every_price():
    three = pages("three")

    healed, changes = heal(learnt(), three)

    moved = {c.before: c for c in changes if c.kind == "moved"}
    assert moved["price"].after.endswith("span.price-now")
    assert moved["price"].evidence == {"seen": 3, "samples": 3, "runner_up": 0}
    assert moved["upc"].after == "after 'UPC'"
    assert not [c for c in changes if c.kind in ("ambiguous", "vanished")]
    for html, url in three:
        run = run_extractor(healed, html, url)
        assert run.ok
        assert run.fields["price"] == PRICES[url.split("/")[-2]]


def test_every_page_field_move_says_what_it_rests_on():
    for folder in ("one", "three"):
        _, changes = heal(learnt(), pages(folder))
        assert all(c.evidence is not None for c in changes if c.kind == "moved")


# A product page, and the same page redesigned, with a strip of related
# products of one item that is neither a list nor an article: only the old
# values say where the price went, and the related one is as good as the own.


def product(title: str, price: str, related: str = "", own: str = "p.price") -> str:
    tag, _, name = own.partition(".")
    return (
        f"<html><head><title>{title}</title></head><body><main>"
        f"<h1>{title}</h1><{tag} class='{name}'>{price}</{tag}>"
        f"<p class='blurb'>A part for the car.</p>{related}</main></body></html>"
    )


def card(title: str, price: str) -> str:
    return (
        "<section class='related'><h2>You might also like</h2>"
        f"<div class='card'><a href='/p/other'>{title}</a>"
        f"<div class='cost'>{price}</div></div></section>"
    )


def two_parts() -> Extractor:
    return compile_extractor(
        [
            (product("Brake pads", "£41.90"), "https://shop.example/p/brake-pads"),
            (product("Oil filter", "£8.99"), "https://shop.example/p/oil-filter"),
        ],
        want={"title": "Brake pads", "price": "£41.90"},
    )


def test_two_own_places_each_showing_an_old_value_are_left_for_a_person(tmp_path):
    moved = product("Oil filter", "£8.99", card("Brake pads", "£41.90"), own="span.now")

    _, changes = heal(two_parts(), [(moved, "https://shop.example/p/oil-filter")])

    price = next(c for c in changes if c.before == "price")
    assert price.kind == "ambiguous"
    assert price.evidence is not None
    assert price.evidence["seen"] == price.evidence["runner_up"] == 1

    extractor = tmp_path / "e.json"
    extractor.write_text(two_parts().to_json(), encoding="utf-8")
    page = tmp_path / "oil-filter.html"
    page.write_text(moved, encoding="utf-8")
    healed = tmp_path / "healed.json"
    result = CliRunner().invoke(
        main, ["heal", str(extractor), str(page), "-o", str(healed)]
    )
    assert result.exit_code == 3
    assert "ambiguous: price" in result.stderr
    assert "Did not write" in result.stderr
    assert not healed.exists()


def test_a_price_only_a_related_item_shows_is_no_move():
    for related in (
        "<ul class='strip'><li><a href='/p/brake-pads'>Brake pads</a>"
        "<span class='cost'>£41.90</span></li></ul>",
        "<article class='also'><a href='/p/brake-pads'>Brake pads</a>"
        "<span class='cost'>£41.90</span></article>",
    ):
        # The own price is now "Call us": no own place shows an old value.
        page = product("Oil filter", "Call us", related, own="span.ask")
        if "article" in related:
            page = page.replace("<main>", "<main><article>").replace(
                "</main>", "</article></main>"
            )

        _, changes = heal(two_parts(), [(page, "https://shop.example/p/oil-filter")])

        price = next(c for c in changes if c.before == "price")
        assert (price.kind, price.after) == ("vanished", None), related
