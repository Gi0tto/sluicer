"""The drifts an independent review found passing, and the pages it failed.

Each test is one way a page changes in the wild. The rule they hold the code
to: a page that drifted never passes, and a page of the same template that did
not drift is never failed.
"""

import json
from pathlib import Path

import pytest

from sluicer.extractor import (
    Extractor,
    compile_extractor,
    heal,
    run_extractor,
)

DRIFT = Path(__file__).parent / "fixtures" / "drift"
TITLES = [
    "A Light in the Attic",
    "Tipping the Velvet",
    "Soumission",
    "Sharp Objects",
    "Sapiens",
    "The Requiem Red",
    "The Dirty Little Secrets",
    "The Coming Woman",
    "The Boys in the Boat",
    "Olio",
]


def li(title, href, price, extra="", cls="product"):
    price_span = f'<span class="price">{price}</span>' if price else ""
    return (
        f'<li class="{cls}"><a class="title" href="{href}">{title}</a>'
        f"{price_span}{extra}</li>"
    )


def shop_page(items, before=""):
    return (
        '<!doctype html><html lang="en"><head><title>Books | Example Shop</title>'
        "</head><body><div class='page'><h1>Books</h1>"
        f"{before}<ol class='row'>{''.join(items)}</ol></div></body></html>"
    )


def books(n=10, stock=lambda i: '<span class="stock">In stock</span>', **kw):
    return [
        li(
            TITLES[i % len(TITLES)] + ("" if i < len(TITLES) else f" {i}"),
            f"/book/{i}",
            f"£{10 + i}.99",
            stock(i),
            **kw,
        )
        for i in range(n)
    ]


def learn(*pages):
    return compile_extractor(
        [(html, f"https://shop.example/c?page={n}") for n, html in enumerate(pages, 1)]
    )


def failed(run):
    return [c.name for c in run.checks if not c.ok]


# -- silent passes --------------------------------------------------------------


def test_a_second_listing_of_the_same_kind_before_the_real_one_fails():
    extractor = learn(shop_page(books(10)), shop_page(books(8)))
    ads = "<ol class='row'>" + "".join(
        li(f"Ad {n}", f"/ad/{n}", "£1.00") for n in range(5)
    )
    ads += "</ol>"

    run = run_extractor(extractor, shop_page(books(10), before=ads), "https://s/3")

    assert not run.ok
    assert "listing" in failed(run)


def test_rows_that_gain_a_state_class_are_still_rows():
    extractor = learn(shop_page(books(12)), shop_page(books(10)))
    on_sale = [
        row.replace('class="product"', 'class="product on-sale"', 1) if n % 2 else row
        for n, row in enumerate(books(12))
    ]

    run = run_extractor(extractor, shop_page(on_sale), "https://s/3")

    assert run.ok, failed(run)
    assert len(run.rows) == 12


def test_a_field_most_rows_carried_cannot_vanish_from_all_of_them():
    with_gap = books(
        10, stock=lambda i: "" if i == 3 else '<span class="stock">In stock</span>'
    )
    extractor = learn(shop_page(with_gap))

    run = run_extractor(
        extractor, shop_page(books(10, stock=lambda i: "")), "https://s/2"
    )

    assert not run.ok
    assert "field" in failed(run)


def test_placeholder_rows_that_all_say_the_same_thing_fail():
    extractor = learn(shop_page(books(10)), shop_page(books(8)))
    skeleton = [li("Loading", "#", "£0.00", '<span class="stock">In stock</span>')] * 6

    run = run_extractor(extractor, shop_page(skeleton), "https://s/x")

    assert not run.ok
    assert "values" in failed(run)


SHELL = '<li class="product"><div class="skeleton"></div></li>'


def test_rows_that_became_empty_shells_fail():
    """Found by the drift benchmark's review: skeletons waiting for a script
    are members with nothing in them, and passed as a short page."""
    extractor = learn(shop_page(books(10)), shop_page(books(8)))

    run = run_extractor(extractor, shop_page(books(2) + [SHELL] * 8), "https://s/x")

    assert not run.ok
    assert "rows" in failed(run)
    shells = next(c for c in run.checks if c.name == "rows" and not c.ok)
    assert shells.got == "8 of 10 empty"


def test_a_listing_that_always_had_a_spacer_row_passes_with_it():
    with_spacer = [*books(9), SHELL]
    extractor = learn(shop_page(with_spacer), shop_page(with_spacer))

    run = run_extractor(extractor, shop_page([*books(7), SHELL]), "https://s/x")

    assert extractor.listing is not None and extractor.listing.empty == 0.1
    assert run.ok, failed(run)


def test_three_rows_that_say_the_same_thing_by_chance_are_no_placeholder():
    """The drift benchmark's one false alarm: three day-tables headed alike."""
    extractor = learn(shop_page(books(10)), shop_page(books(8)))
    alike = [li("River stage zero", f"/book/{i}", f"£1{i}.99") for i in range(3)]

    run = run_extractor(extractor, shop_page(alike), "https://s/x")

    assert "values" not in failed(run)


def test_an_extractor_file_from_0_2_without_the_empty_share_still_loads():
    extractor = learn(shop_page(books(10)))
    body = json.loads(extractor.to_json())
    del body["listing"]["empty"]

    loaded = Extractor.from_json(json.dumps(body))

    assert loaded.listing is not None and loaded.listing.empty == 0.0


def test_a_listing_page_with_a_breadcrumb_still_learns_its_listing():
    breadcrumb = (
        '<script type="application/ld+json">{"@type":"BreadcrumbList",'
        '"itemListElement":[{"@type":"ListItem","position":1,"name":"Home"}]}</script>'
    )
    page = shop_page(books(10)).replace("</head>", breadcrumb + "</head>")

    extractor = learn(page)

    assert extractor.listing is not None


def test_an_extractor_that_checks_nothing_is_a_failed_run():
    empty = Extractor(learnt_from=("x",), summary={}, types=(), listing=None)

    run = run_extractor(empty, "<p>anything</p>")

    assert not run.ok
    assert failed(run) == ["extractor"]


# -- false failures -------------------------------------------------------------


def test_a_short_page_of_the_same_template_passes():
    extractor = learn(shop_page(books(20)), shop_page(books(20)))

    run = run_extractor(extractor, shop_page(books(4)), "https://s/last")

    assert run.ok, failed(run)


def test_one_row_with_a_second_tag_does_not_rename_every_row():
    def tagged(extra_on=()):
        return books(
            10,
            stock=lambda i: (
                '<span class="tag">Paperback</span>'
                + ('<span class="tag">Bestseller</span>' if i in extra_on else "")
            ),
        )

    extractor = learn(shop_page(tagged()), shop_page(tagged()))
    run = run_extractor(extractor, shop_page(tagged(extra_on={4})), "https://s/3")

    assert run.ok, failed(run)
    assert run.rows[0]["span.tag"] == "Paperback"


def test_one_row_with_a_second_badge_does_not_rename_what_is_in_every_badge():
    # Found by the drift benchmark: a question site and a news site a month
    # apart, same markup. One user with a second kind of badge, or one story with a
    # second author, numbered the step for every row, and the field under it
    # was not found in any.
    gold = '<span><b class="count">3</b> gold</span>'
    silver = '<span><b class="count">7</b> silver</span>'

    def badged(extra_on=()):
        def flair(i):
            return f'<div class="flair">{gold}{silver if i in extra_on else ""}</div>'

        return books(10, stock=flair)

    extractor = learn(shop_page(badged()), shop_page(badged()))
    run = run_extractor(extractor, shop_page(badged(extra_on={4})), "https://s/3")

    assert run.ok, failed(run)
    assert run.rows[0]["div.flair>span>b.count"] == "3"


def test_a_rare_optional_field_is_not_held_to_a_shape():
    extractor = learn(
        shop_page(
            books(
                10, stock=lambda i: '<span class="note">Signed</span>' if i == 1 else ""
            )
        )
    )

    run = run_extractor(
        extractor,
        shop_page(
            books(
                10,
                stock=lambda i: '<span class="note">grown-ups</span>' if i == 2 else "",
            )
        ),
        "https://s/2",
    )

    assert run.ok, failed(run)


def test_a_whole_price_where_decimals_were_learnt_is_still_a_price():
    template = (
        '<html><head><script type="application/ld+json">{{"@type":"Product",'
        '"name":"Pad","offers":{{"price":"{p}","priceCurrency":"EUR"}}}}</script>'
        "</head></html>"
    )
    extractor = compile_extractor(
        [(template.format(p="41.90"), None), (template.format(p="9.50"), None)]
    )

    assert run_extractor(extractor, template.format(p="42")).ok
    assert not run_extractor(extractor, template.format(p="Call us")).ok


@pytest.mark.parametrize(
    "wrapper", ["mx-auto max-w-[1200px]", "[&>li]:mt-2 grid", "container md:w-1/2"]
)
def test_utility_classes_neither_crash_a_run_nor_pin_a_path(wrapper):
    page = (
        shop_page(books(6))
        .replace("<ol class='row'>", f"<div class='{wrapper}'><ol class='row'>")
        .replace("</ol>", "</ol></div>")
    )
    extractor = learn(page)

    run = run_extractor(extractor, page, "https://s/1")

    assert run.ok, failed(run)
    assert "[" not in extractor.listing.container


def test_an_at_sign_in_a_class_does_not_turn_text_into_an_address():
    page = shop_page(books(6)).replace('class="price"', 'class="@container price"')

    extractor = learn(page)

    names = [f.name for f in extractor.listing.fields]
    assert "span.price" in names
    assert all("@container" not in name for name in names)


# -- healing --------------------------------------------------------------------


def test_healing_onto_a_page_whose_listing_is_gone_is_a_loss():
    extractor = learn(shop_page(books(10)), shop_page(books(8)))
    product = (DRIFT / "product.html").read_bytes()

    _healed, changes = heal(extractor, [(product, "https://s/p")])

    assert "listing-lost" in [c.kind for c in changes]


def test_a_field_whose_values_are_new_is_vanished_and_new_not_moved():
    extractor = learn(shop_page(books(6)), shop_page(books(6)))
    authors = [
        "Shel Silverstein",
        "Sarah Waters",
        "Michel Houellebecq",
        "Gillian Flynn",
        "Yuval Harari",
        "Michelle Frances",
    ]
    page = shop_page(
        [
            li(
                TITLES[i],
                f"/book/{i}",
                f"£{10 + i}.99",
                f'<span class="author">{authors[i]}</span>',
            )
            for i in range(6)
        ]
    )

    _healed, changes = heal(extractor, [(page, "https://s/x")])

    kinds = {(c.kind, c.before or c.after) for c in changes}
    assert ("vanished", "span.stock") in kinds
    assert ("new", "span.author") in kinds


def test_values_that_swapped_places_are_moves_not_keeps():
    def page(swap):
        rows = []
        for i in range(6):
            a, b = (f"£{10 + i}.99", "In stock")
            if swap:
                a, b = b, a
            rows.append(
                f'<li class="product"><a href="/book/{i}">{TITLES[i]}</a>'
                f"<span>{a}</span><span>{b}</span></li>"
            )
        return shop_page(rows)

    extractor = learn(page(False))

    _healed, changes = heal(extractor, [(page(True), "https://s/1")])

    moved = {c.before: c.after for c in changes if c.kind == "moved"}
    assert moved == {"span1": "span2", "span2": "span1"}


def test_a_relative_address_learnt_from_a_file_still_matches_the_site():
    def rows():
        return [
            li(TITLES[i], f"catalogue/book-{i}/index.html", f"£{10 + i}.99")
            for i in range(6)
        ]

    extractor = compile_extractor([(shop_page(rows()), None)])
    redesigned = shop_page(rows()).replace('class="title"', 'class="name"')

    _healed, changes = heal(extractor, [(redesigned, "https://books.example/")])

    moved = {c.before: c.after for c in changes if c.kind == "moved"}
    assert moved["a.title@href"] == "a.name@href"


def test_a_field_found_in_two_new_places_moves_to_the_one_in_every_row():
    # Found by the drift benchmark: a software directory's 2024 redesign shows a
    # project's name as its heading in every row and as its icon's alt text in
    # rows that have an icon. The two held the old names equally, and heal took
    # the icon, first in the alphabet, which a quarter of the rows lack.
    def card(i):
        icon = f'<a class="icon"><img alt="{TITLES[i]}" src="/i/{i}.png"></a>'
        return (
            f'<li class="card">{icon if i < 5 or i == 7 else ""}'
            f'<h3 class="name">{TITLES[i]}</h3><a class="go" href="/book/{i}">Go</a>'
            f'<span class="cost">£{10 + i}.99</span>{STOCK}</li>'
        )

    extractor = learn(shop_page(books(10)), shop_page(books(10)))
    page = shop_page([card(i) for i in range(10)])

    _healed, changes = heal(extractor, [(page, "https://shop.example/")])

    moved = {c.before: c.after for c in changes if c.kind == "moved"}
    assert moved["a.title"] == "h3.name"


def test_a_link_that_gained_a_tracking_parameter_is_the_same_link():
    # Found by the drift benchmark: a film chart before and after its 2023
    # redesign tags every link with ?ref_=chttp_t_1, and heal called the title
    # links of the same films vanished.
    extractor = learn(shop_page(books(6)), shop_page(books(6)))
    redesigned = [
        li(TITLES[i], f"/book/{i}?ref_=list_{i}", f"£{10 + i}.99", STOCK, cls="card")
        for i in range(6)
    ]
    page = shop_page(redesigned).replace('class="title"', 'class="name"')

    _healed, changes = heal(extractor, [(page, "https://shop.example/")])

    moved = {c.before: c.after for c in changes if c.kind == "moved"}
    assert moved["a.title@href"] == "a.name@href"


def test_a_link_whose_parameter_changed_is_another_link():
    def page(edition, cls):
        rows = [
            li(TITLES[i], f"/book?id={i + edition}", f"£{10 + i}.99", STOCK)
            for i in range(6)
        ]
        return shop_page(rows).replace('class="title"', f'class="{cls}"')

    extractor = learn(page(0, "title"))

    _healed, changes = heal(extractor, [(page(10, "name"), "https://shop.example/")])

    assert ("vanished", "a.title@href") in {(c.kind, c.before) for c in changes}


def test_healing_learns_hrefs_against_their_own_page():
    extractor = compile_extractor(
        [
            (
                b"<html><body><p>no listing here</p><title>x</title></body></html>",
                "https://a/",
            ),
            (shop_page(books(6)).encode(), "https://b/c/"),
        ],
        listing=True,
    )

    href = next(f for f in extractor.listing.fields if f.name == "a.title@href")
    assert href.samples[0].startswith("https://b/")


STOCK = '<span class="stock">In stock</span>'


def test_a_field_where_it_was_with_new_items_in_it_is_kept():
    # Found by the drift benchmark: two link aggregators and a preprint listing
    # a month apart, same markup, and heal called every title and link vanished.
    extractor = learn(shop_page(books(6)), shop_page(books(6)))
    today = [
        li(title, f"/book/{100 + i}", f"£{40 + i}.50", STOCK)
        for i, title in enumerate(["Dune", "Emma", "Beloved", "Ulysses", "Rebecca"])
    ]

    _healed, changes = heal(extractor, [(shop_page(today), "https://shop.example/")])

    assert {c.kind for c in changes} == {"kept"}, changes


def test_a_place_that_now_holds_another_kind_of_value_is_not_kept():
    extractor = learn(shop_page(books(6)), shop_page(books(6)))
    today = [li(TITLES[i], f"/book/{i}", "Call us", STOCK) for i in range(6)]

    _healed, changes = heal(extractor, [(shop_page(today), "https://shop.example/")])

    assert ("vanished", "span.price") in {(c.kind, c.before) for c in changes}


def test_tags_from_one_vocabulary_that_change_rows_are_not_moves():
    # Found by the drift benchmark: a bookmarking site a month apart, and
    # heal moved its first tag to the fourth place and its fourth to the fifth.
    words = ["python", "rust", "web", "data", "security", "design", "career"]

    def tagged(offset):
        def tags(i):
            picked = [words[(i + n + offset) % len(words)] for n in range(3)]
            return "".join(f'<a class="tag" href="/t/{w}">{w}</a>' for w in picked)

        return shop_page(books(6, stock=tags))

    extractor = learn(tagged(0))

    _healed, changes = heal(extractor, [(tagged(1), "https://shop.example/")])

    assert [c for c in changes if c.kind == "moved"] == []


def test_an_author_who_turns_up_first_does_not_move_the_first_author():
    # Found by the drift benchmark: a preprint listing a month apart; one ninth
    # author of January was a first author in February, and heal moved the
    # ninth-author column onto the first and called the first vanished.
    def by(names):
        return "".join(f'<a class="by" href="/a/{n}">{n}</a>' for n in names)

    january = [["Ada", "Bo", "Cy"], ["Di", "Ed"], ["Flo", "Gus"], ["Hal", "Ivy"]]
    february = [["Cy", "Jo"], ["Kit", "Lu"], ["Mo", "Ned", "Oz"], ["Pia", "Quin"]]

    def page(rows):
        return shop_page(books(len(rows), stock=lambda i: by(rows[i])))

    extractor = learn(page(january))

    _healed, changes = heal(extractor, [(page(february), "https://shop.example/")])

    kinds = {c.before: c.kind for c in changes if c.before and "a.by" in c.before}
    assert set(kinds.values()) == {"kept"}, kinds


# -- the file -------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"format": 1},
        {
            "format": True,
            "learnt_from": [],
            "summary": {},
            "types": [],
            "listing": None,
        },
        {"format": 1, "learnt_from": [], "summary": {}, "types": [], "listing": {}},
        {
            "format": 1,
            "learnt_from": [],
            "summary": {},
            "types": [],
            "listing": {
                "container": "html>body",
                "member": "li",
                "rows": [1],
                "fields": [],
            },
        },
    ],
)
def test_a_file_that_is_not_a_whole_extractor_is_refused(body):
    with pytest.raises(ValueError):
        Extractor.from_json(json.dumps(body))


def test_a_page_s_base_address_is_worked_out_once_not_once_per_link(monkeypatch):
    """At 3,200 rows, looking up <base> for every address was 70% of the time."""
    from sluicer import document

    calls = []
    real = document._base_of

    def counting(tree, url):
        calls.append(1)
        return real(tree, url)

    monkeypatch.setattr(document, "_base_of", counting)

    learn(shop_page(books(400)))

    assert len(calls) < 10


# -- the command line -----------------------------------------------------------


def _cli(*args):
    from click.testing import CliRunner

    from sluicer.cli import main

    return CliRunner().invoke(main, list(args))


def test_heal_does_not_overwrite_the_extractor_when_it_lost_a_field(tmp_path):
    out = tmp_path / "shop.json"
    before = learn(shop_page(books(10))).to_json()
    out.write_text(before, encoding="utf-8")
    gone = tmp_path / "gone.html"
    gone.write_text(
        shop_page([li(TITLES[i], f"/book/{i}", "") for i in range(10)]),
        encoding="utf-8",
    )

    result = _cli("heal", str(out), str(gone), "-o", str(out))

    assert result.exit_code == 3
    assert out.read_text(encoding="utf-8") == before
    assert "--force" in result.stderr


def test_heal_writes_a_lossy_extractor_when_forced(tmp_path):
    out = tmp_path / "shop.json"
    out.write_text(learn(shop_page(books(10))).to_json(), encoding="utf-8")
    gone = tmp_path / "gone.html"
    gone.write_text(
        shop_page([li(TITLES[i], f"/b/{i}", "") for i in range(10)]), encoding="utf-8"
    )

    result = _cli("heal", str(out), str(gone), "-o", str(out), "--force")

    assert result.exit_code == 3
    assert "span.price" not in out.read_text(encoding="utf-8")


def test_compile_into_a_folder_that_does_not_exist_is_a_message(tmp_path):
    page = tmp_path / "p.html"
    page.write_text(shop_page(books(6)), encoding="utf-8")

    result = _cli("compile", str(page), "-o", str(tmp_path / "missing" / "x.json"))

    assert result.exit_code == 2
    assert "Could not write" in result.stderr


def test_asking_for_a_listing_that_is_not_there_says_so(tmp_path):
    out = tmp_path / "p.json"

    result = _cli("compile", str(DRIFT / "product.html"), "-o", str(out), "--listing")

    assert result.exit_code == 0
    assert "no listing" in result.stderr.lower()


def test_cards_that_carry_fewer_tags_than_before_have_not_drifted():
    def tagged(counts):
        return books(
            10,
            stock=lambda i: "".join(
                f'<span class="tag">t{n}</span>' for n in range(counts[i])
            ),
        )

    extractor = learn(shop_page(tagged([1, 2, 3, 3, 2, 2, 3, 1, 2, 3])))

    run = run_extractor(
        extractor, shop_page(tagged([1, 1, 2, 1, 1, 1, 1, 1, 1, 1])), "x"
    )

    assert run.ok, failed(run)


def test_a_numbered_slot_in_the_middle_of_a_path_is_a_count_not_a_column():
    """A code host's trending rows: language, stars, forks, each a span. On a page
    where half the repositories have no language, the stars take the first
    span and the forks the second: the same template, not a drift."""

    def repo(i, language=True):
        spans = (
            (f"<span class='meta'>Lang {i}</span>" if language else "")
            + f"<span class='meta'><a href='/r{i}/stars'>{i}</a></span>"
            + f"<span class='meta'><a href='/r{i}/forks'>{i * 2}</a></span>"
        )
        return (
            f"<li class='repo'><h3><a href='/r{i}'>repo {i}</a></h3>"
            f"<div class='f6'>{spans}</div></li>"
        )

    learnt = learn(shop_page([repo(i) for i in range(8)]))
    run = run_extractor(
        learnt,
        shop_page([repo(i, language=i % 2 == 0) for i in range(8)]),
        "https://s/x",
    )

    assert run.ok, failed(run)


def test_a_numbered_group_that_vanished_from_every_row_still_fails():
    """The first slot is held to some rows, so the group cannot go unnoticed."""

    def repo(i, meta=True):
        spans = (
            f"<div class='f6'><span class='meta'>Lang {i}</span>"
            f"<span class='meta'><a href='/r{i}/stars'>{i}</a></span></div>"
            if meta
            else ""
        )
        return f"<li class='repo'><h3><a href='/r{i}'>repo {i}</a></h3>{spans}</li>"

    learnt = learn(shop_page([repo(i) for i in range(8)]))
    run = run_extractor(
        learnt, shop_page([repo(i, meta=False) for i in range(8)]), "https://s/x"
    )

    assert not run.ok
    assert "field" in failed(run)


def test_a_price_column_that_now_holds_dates_fails_though_its_shape_is_kept():
    """12.99 and 2025-01-02 are both digits and punctuation: the shape check
    cannot tell a price from a date, and two columns that swap them kept their
    shapes. What each learnt value read as can."""

    def row(i, price, date):
        return (
            f"<li class='item'><a href='/p{i}'>Item {i}</a>"
            f"<span class='price'>{price}</span><span class='date'>{date}</span></li>"
        )

    learnt = learn(
        shop_page([row(i, f"{10 + i}.99", f"2025-01-0{i + 1}") for i in range(8)])
    )
    swapped = shop_page([row(i, f"2025-02-0{i + 1}", f"{20 + i}.50") for i in range(8)])

    run = run_extractor(learnt, swapped, "https://s/x")

    fields = {f.name: f.reads for f in learnt.listing.fields}
    assert fields["span.price"] == "amount" and fields["span.date"] == "date"
    assert not run.ok
    assert "reads" in failed(run)


def test_a_file_from_0_3_that_learnt_no_reading_still_loads():
    extractor = learn(shop_page(books(10)))
    body = json.loads(extractor.to_json())
    for f in body["listing"]["fields"]:
        del f["reads"]

    assert Extractor.from_json(json.dumps(body)).listing is not None


# -- 0.7.1: the review of the learnt extractors -----------------------------------


def _product(price, title="Brake pad set"):
    return (
        f"<html><body><main><h1 class='name'>{title}</h1>"
        f"<p class='cost'><span class='price'>{price}</span></p></main></body></html>",
        "https://shop.example/p/1",
    )


def test_an_example_is_the_same_amount_however_many_zeros_it_is_written_with():
    """``8`` and ``8.00`` are one amount; compared as the strings amount()
    gives back, they were two, and an example written without its cents was
    found nowhere -- on the page, in a listing, or after a label."""
    [price] = compile_extractor([_product("£8.00")], want={"price": "8"}).fields
    assert price.path.endswith("span.price")
    listed = shop_page(books(6)).replace("£10.99", "£8.00")
    learnt = compile_extractor([(listed, "https://s/1")], want={"price": "8"})
    assert [f.path for f in learnt.listing.fields] == ["span.price"]
    labelled = [
        (f"<html><body><ul><li><b>Price:</b> {price}</li></ul></body></html>", None)
        for price in ("$12.00", "$8.50")
    ]
    learnt = compile_extractor(labelled, listing=False, want={"price": "12"})
    [price] = learnt.fields
    assert price.anchor is not None and price.anchor.label == "Price:"


def _specs(brand, price, sku, weight, order=("brand", "price", "sku", "weight")):
    """A product page that declares nothing, its facts one to a row of a table."""
    facts = {"brand": brand, "price": price, "sku": sku, "weight": weight}
    labels = {"brand": "Brand", "price": "Price", "sku": "SKU", "weight": "Weight"}
    rows = "".join(f"<tr><th>{labels[k]}</th><td>{facts[k]}</td></tr>" for k in order)
    return (
        "<html><head><title>Shop</title></head><body><main>"
        f"<h1>Pads {sku}</h1><table class='specs'>{rows}</table></main></body></html>",
        f"https://shop.example/p/{sku}",
    )


SPECS = [
    _specs("Bosch", "41.90", "BP-1", "1 kg"),
    _specs("ATE", "39.00", "BP-2", "2 kg"),
]


def test_two_examples_in_one_column_are_no_listing():
    """A product's table holds its price and its SKU in two rows, both in the
    row's ``td``: learnt as a listing, both columns were that ``td``, and a
    new page's rows read price "Textar", sku "Textar" and passed."""
    learnt = compile_extractor(SPECS, want={"price": "41.90", "sku": "BP-1"})
    assert learnt.listing is None
    assert [f.name for f in learnt.fields] == ["price", "sku"]
    run = run_extractor(learnt, *_specs("Textar", "12.50", "BP-3", "3 kg"))
    assert run.ok, failed(run)
    assert run.rows == []
    assert run.fields == {"price": "12.50", "sku": "BP-3"}


def test_an_example_gives_up_a_column_another_example_needs():
    """A title said twice in a row, as the cover's alt text and as the link,
    and an alt text that says something else once: the alt is the only place
    that holds it, so the title is the link."""
    rows = "".join(
        f"<li class='book'><img class='cover' alt='{'Cover' if n == 6 else t}'>"
        f"<a class='title'>{t}</a><span class='price'>£{n}.00</span></li>"
        for n, t in enumerate(TITLES[:6], 1)
    )
    html = f"<html><body><ol class='books'>{rows}</ol></body></html>"
    learnt = compile_extractor(
        [(html, None)], want={"title": TITLES[0], "alt": "Cover"}
    )
    assert [(f.name, f.path) for f in learnt.listing.fields] == [
        ("title", "a.title"),
        ("alt", "img.cover"),
    ]
    assert learnt.notes == (
        "title='A Light in the Attic' was in 2 places in a row; a.title, the "
        "first no other example needs, was taken",
    )


def test_a_row_that_moved_under_another_label_fails():
    """The pages given agreed on the SKU's row, the third, so it was learnt by
    its place; a page that puts the weight third read sku "3 kg" and passed.
    Every page given said "SKU" right before it, once: a page that says it
    once before something else has moved the row."""
    learnt = compile_extractor(SPECS, want={"price": "41.90", "sku": "BP-1"})
    assert [f.label for f in learnt.fields] == ["Price", "SKU"]
    assert Extractor.from_json(learnt.to_json()) == learnt
    order = ("brand", "price", "weight", "sku")
    run = run_extractor(learnt, *_specs("Textar", "12.50", "BP-3", "3 kg", order))
    assert not run.ok
    assert failed(run) == ["field"]
    [check] = [c for c in run.checks if not c.ok]
    assert check.expected == "sku right after 'SKU', as on the pages learnt"
    assert check.got == "'SKU' is now before 'BP-3', and the place holds '3 kg'"


def test_a_label_the_page_does_not_say_once_is_no_verdict():
    """Renamed, or said twice, the label says nothing about the place: the
    place is read, as it was learnt."""
    learnt = compile_extractor(SPECS, listing=False, want={"sku": "BP-1"})
    html, url = _specs("Textar", "12.50", "BP-3", "3 kg")
    for page in (
        html.replace("SKU", "Art. no."),
        html.replace("<h1>", "<p>SKU</p><h1>"),
    ):
        run = run_extractor(learnt, page, url)
        assert run.ok, failed(run)
        assert run.fields == {"sku": "BP-3"}


def test_one_page_cannot_tell_its_labels_and_learns_none():
    learnt = compile_extractor(SPECS[:1], listing=False, want={"sku": "BP-1"})
    assert [f.label for f in learnt.fields] == [None]


def test_heal_reads_a_row_that_moved_after_its_label():
    learnt = compile_extractor(SPECS, listing=False, want={"sku": "BP-1"})
    order = ("brand", "price", "weight", "sku")
    moved = [
        _specs("Textar", "12.50", "BP-3", "3 kg", order),
        _specs("Brembo", "20.00", "BP-4", "4 kg", order),
    ]
    healed, changes = heal(learnt, moved)
    assert [(c.kind, c.before, c.after) for c in changes] == [
        ("moved", "sku", "after 'SKU'")
    ]
    run = run_extractor(healed, *_specs("Ferodo", "9.00", "BP-5", "5 kg", order))
    assert run.ok, failed(run)
    assert run.fields == {"sku": "BP-5"}


def _sections(*boxes):
    """A page of boxes of one kind, each a heading and a list of products."""
    html = "".join(
        f"<section class='box'><h2>{title}</h2><ul class='items'>"
        + "".join(
            f"<li class='item'><a class='name' href='/{title[0]}/{n}'>{title} {n}</a>"
            f"<span class='price'>£{n}.99</span></li>"
            for n in range(1, rows + 1)
        )
        + "</ul></section>"
        for title, rows in boxes
    )
    return f"<html><body><main>{html}</main></body></html>", "https://shop.example/c"


def test_a_box_of_the_same_kind_inserted_before_a_numbered_listing_fails():
    """The listing was the second box, section.box[2]; a sponsored box put
    before it made the pick of the week the second, and the run read its one
    row and passed. The page now has three boxes where it had two."""
    learnt = compile_extractor([_sections(("Pick", 1), ("All", 12))], listing=True)
    assert learnt.listing.container == "html>body>main>section.box[2]>ul.items"
    run = run_extractor(learnt, *_sections(("Sponsored", 4), ("Pick", 1), ("All", 12)))
    assert not run.ok
    assert failed(run) == ["listing"]
    [check] = [c for c in run.checks if not c.ok]
    assert check.got == "3 places that match section.box, where there were 2"
    assert run_extractor(learnt, *_sections(("Pick", 1), ("All", 9))).ok
    wanted = compile_extractor(
        [_sections(("Pick", 1), ("All", 12))], want={"n": "All 3"}
    )
    run = run_extractor(wanted, *_sections(("Sponsored", 4), ("Pick", 1), ("All", 12)))
    assert failed(run) == ["listing"]


def test_pages_that_number_a_step_differently_do_not_hold_it_to_a_count():
    learnt = compile_extractor(
        [
            _sections(("Pick", 1), ("All", 12)),
            _sections(("Pick", 1), ("All", 10), ("Recently viewed", 2)),
        ],
        want={"n": "All 3"},
    )
    assert learnt.listing.siblings[-2:] == (None, 1)
    run = run_extractor(learnt, *_sections(("Pick", 1), ("All", 8), ("Seen", 1)))
    assert run.ok, failed(run)
    assert Extractor.from_json(learnt.to_json()) == learnt


def _item(price, related=(), cls="price", extra=""):
    """A product page that declares nothing, and a strip of related products."""
    strip = "".join(
        f"<li class='rel'><a class='t' href='/p/{n}'>Disc {n}</a>"
        f"<span class='cost'>{cost}</span></li>"
        for n, cost in enumerate(related, 1)
    )
    return (
        "<html><body><main><div class='item'><h1 class='name'>Brake pad set</h1>"
        f"<p><span class='{cls}'>{price}</span>{extra}</p></div>"
        f"<h2>Related products</h2><ul class='related'>{strip}</ul>"
        "</main></body></html>",
        "https://shop.example/p/1",
    )


def test_heal_never_moves_a_page_field_into_another_product_s_place():
    """After a redesign the product costs £44.50, and a related product costs
    what it used to: heal moved the price to the related product's, and the
    healed extractor read another product's price and passed."""
    learnt = compile_extractor(
        [_item("£41.90", ("£12.00", "£13.00", "£14.00"))], want={"price": "41.90"}
    )
    new = _item("£44.50", ("£41.90", "£13.00", "£14.00"), cls="amount")
    healed, changes = heal(learnt, [new])
    assert [(c.kind, c.before) for c in changes] == [("vanished", "price")]
    assert healed.fields == ()
    _moved, changes = heal(learnt, [_item("£41.90", ("£41.90",), cls="amount")])
    assert [(c.kind, c.after) for c in changes] == [
        ("moved", "html>body>main>div.item>p>span.amount")
    ]


def test_heal_leaves_a_page_field_two_own_places_claim_to_a_person():
    learnt = compile_extractor([_item("£41.90")], want={"price": "41.90"})
    both = "<span class='rrp'>{}</span>"
    new = [
        _item("£41.90", cls="amount", extra=both.format("£41.90")),
        (_item("£20.00", cls="amount", extra=both.format("£25.00"))[0], "https://s/2"),
    ]
    healed, changes = heal(learnt, new)
    assert [(c.kind, c.before) for c in changes] == [("ambiguous", "price")]
    assert healed.fields == ()


def _catalogue(titles, sidebar):
    """A catalogue page, and a long bestsellers sidebar before it that also
    lists some of its books."""
    side = "".join(
        f"<li class='top'><a class='t' href='/b/{t}'>{t}</a></li>" for t in sidebar
    )
    rows = "".join(
        f"<li class='book'><a class='title' href='/b/{t}'>{t}</a>"
        f"<span class='price'>£{n}.00</span></li>"
        for n, t in enumerate(titles, 1)
    )
    return (
        "<html><head><meta property='og:title' content='Shop'></head><body>"
        f"<aside><h2>Bestsellers</h2><ul class='best'>{side}</ul></aside>"
        f"<main><ol class='books'>{rows}</ol></main></body></html>",
        "https://shop.example/c",
    )


BESTSELLERS = TITLES[:5] + [f"Other {n}" for n in range(15)]


def test_heal_keeps_a_chosen_listing_where_it_still_is():
    """Healing a page that had not changed moved the listing to a sidebar
    that lists the same books, and wrote it: it was a move, not a loss."""
    page_ = _catalogue(TITLES, BESTSELLERS)
    learnt = compile_extractor([page_], want={"title": "Olio"})
    assert learnt.listing.member == "li.book"
    healed, changes = heal(learnt, [page_])
    assert [(c.kind, c.before, c.after) for c in changes] == [
        ("kept", "title", "a.title")
    ]
    assert healed.listing.container == learnt.listing.container


def test_heal_keeps_a_chosen_listing_whose_items_all_changed():
    """The same template a day later, every book new: the listing was lost."""
    learnt = compile_extractor(
        [_catalogue(TITLES, BESTSELLERS)], want={"title": "Olio"}
    )
    tomorrow = _catalogue(["Alpha", "Beta", "Gamma", "Delta", "Epsilon"], ["Zeta"])
    assert run_extractor(learnt, *tomorrow).ok
    healed, changes = heal(learnt, [tomorrow])
    assert [c.kind for c in changes] == ["kept"]
    assert run_extractor(healed, *tomorrow).ok


def test_a_listing_heal_lost_is_kept_so_a_forced_extractor_still_fails():
    """Forced, heal wrote an extractor without the listing, which then passed
    every page it was run on, those without a single row among them."""
    learnt = compile_extractor(
        [_catalogue(TITLES, BESTSELLERS)], want={"title": "Olio"}
    )
    gone = _catalogue([], ["Zeta"])
    healed, changes = heal(learnt, [gone])
    assert [c.kind for c in changes] == ["listing-lost"]
    assert healed.listing == learnt.listing
    assert not run_extractor(healed, *gone).ok
    plain = learn(shop_page(books(10)))
    healed, changes = heal(plain, [(shop_page([]), "https://s/x")])
    assert "listing-lost" in [c.kind for c in changes]
    assert healed.listing == plain.listing


def test_heal_never_moves_a_chosen_listing_on_one_coincidence():
    """Redesigned, with every book new, the catalogue held none of its old
    prices, and one related product cost what a book used to: heal moved the
    listing of prices there, a move and no loss, so it was written."""

    def page_(books_, related, wrap="ol"):
        rows = "".join(
            f"<li class='book'><a class='title' href='/b/{n}'>{t}</a>"
            f"<span class='price'>{p}</span></li>"
            for n, (t, p) in enumerate(books_, 1)
        )
        strip = "".join(
            f"<li class='rel'><a class='t' href='/r/{n}'>{t}</a>"
            f"<span class='cost'>{p}</span></li>"
            for n, (t, p) in enumerate(related, 1)
        )
        return (
            f"<html><head><title>Shop</title></head><body><main><{wrap} class='b'>"
            f"{rows}</{wrap}><h2>Related</h2><ul class='related'>{strip}</ul>"
            "</main></body></html>",
            "https://shop.example/c",
        )

    others = [("Y", "£98.00"), ("Z", "£97.00")]
    learnt = compile_extractor(
        [
            page_(
                [(f"Book {n}", f"£{n}.50") for n in range(1, 8)],
                [("X", "£99.00"), *others],
            )
        ],
        want={"price": "1.50"},
    )
    new = page_(
        [(f"New {n}", f"£{n + 20}.00") for n in range(1, 8)],
        [("X", "£1.50"), *others],
        wrap="div",
    )
    healed, changes = heal(learnt, [new])
    assert [c.kind for c in changes] == ["listing-lost"]
    assert healed.listing == learnt.listing
    redesigned = page_(
        [(f"Book {n}", f"£{n}.50") for n in range(1, 8)],
        [("X", "£1.50"), *others],
        "div",
    )
    healed, changes = heal(learnt, [redesigned])
    assert healed.listing.container == "html>body>main>div.b"


def _file(**change):
    """An extractor's file, with one part of it changed by hand."""
    body = json.loads(learn(shop_page(books(10))).to_json())
    for where, value in change.items():
        *parents, key = where.split("__")
        node = body
        for part in parents:
            node = node[int(part)] if part.isdigit() else node[part]
        node[key] = value
    return json.dumps(body)


@pytest.mark.parametrize(
    ("change", "said"),
    [
        ({"listing__fields__0__missing": "nan"}, "missing is a share from 0 to 1"),
        ({"listing__fields__0__missing": float("nan")}, "missing is a share"),
        ({"listing__fields__0__missing": True}, "missing is a share"),
        ({"listing__fields__0__missing": "0"}, "missing is a share"),
        ({"listing__fields__0__missing": 1.5}, "missing is a share"),
        ({"listing__fields__0__missing": -0.1}, "missing is a share"),
        ({"listing__empty": 5}, "empty is a share from 0 to 1"),
        ({"listing__empty": "0.0"}, "empty is a share"),
        ({"listing__rows": ["5", "6"]}, "rows are the fewest and the most"),
        ({"listing__rows": [6, 5]}, "rows are the fewest and the most"),
        ({"listing__rows": [1.5, 6]}, "rows are the fewest and the most"),
        ({"listing__fields__0__shape": "XYZ"}, "a shape is made of L, N, P and S"),
        ({"listing__fields__1__name": "a.title"}, "two fields named 'a.title'"),
        ({"listing__chosen": "yes"}, "chosen is true or false"),
        ({"listing__siblings": [1, "1", 1]}, "siblings"),
        ({"listing__siblings": [1, 0, 1]}, "siblings"),
        ({"listing__siblings": [1, 1]}, "siblings"),
        ({"listing__container": "html>body>div[x]>ol.row"}, "not a path"),
        ({"listing__container": "html>body>div[0]>ol.row"}, "not a path"),
        ({"listing__member": "li>a"}, "not a row's kind"),
        ({"learnt_from": "page 1"}, "learnt_from is a list"),
        ({"types": "Product"}, "types is a list"),
        ({"summary": {"price": "money"}}, "a shape is made of L, N, P and S"),
        ({"listing__fields__0__samples": "abc"}, "samples is a list"),
    ],
)
def test_a_file_edited_into_one_that_checks_less_is_refused(change, said):
    """``"missing": "nan"`` read as a float that no comparison is true of: the
    field's presence was never checked again, and the run passed a page with
    none of it. Every value is checked as it is read, not only its key."""
    with pytest.raises(ValueError, match=said):
        Extractor.from_json(_file(**change))


def test_every_file_this_version_writes_is_read_back_the_same():
    for extractor in (
        learn(shop_page(books(10)), shop_page(books(8))),
        compile_extractor(SPECS, want={"price": "41.90", "sku": "BP-1"}),
        compile_extractor([_sections(("Pick", 1), ("All", 12))], want={"n": "All 3"}),
    ):
        assert Extractor.from_json(extractor.to_json()) == extractor


def test_run_refuses_a_file_whose_check_was_edited_away(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(_file(listing__fields__0__missing="nan"), encoding="utf-8")
    page_ = tmp_path / "p.html"
    page_.write_text(shop_page(books(10)), encoding="utf-8")
    result = _cli("run", str(bad), str(page_))
    assert result.exit_code == 2
    assert "not an extractor" in result.stderr
    assert "missing is a share from 0 to 1" in result.stderr


def test_a_column_of_no_letter_digit_or_sign_learns_no_shape():
    """A combining accent alone has none of the classes a shape is made of:
    learnt as the empty shape, the file to_json wrote was one from_json
    refused."""
    marked = books(6, stock=lambda i: '<span class="mark">́</span>')
    learnt = learn(shop_page(marked))
    fields = {f.name: f for f in learnt.listing.fields}
    assert fields["span.mark"].shape is None
    assert Extractor.from_json(learnt.to_json()) == learnt


# -- the cost -------------------------------------------------------------------


def test_compile_run_and_heal_parse_each_page_once(monkeypatch):
    """Each read the page twice or more: once to walk it, and once more for
    what it declares, and heal once for every part it healed."""
    from sluicer import document

    parsed = []
    real = document.lxml.html.document_fromstring

    def counting(*args, **kwargs):
        parsed.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(document.lxml.html, "document_fromstring", counting)
    pages = [
        (shop_page(books(10)), "https://s/1"),
        (shop_page(books(8)), "https://s/2"),
    ]
    learnt = compile_extractor(pages)
    assert len(parsed) == 2
    run_extractor(learnt, *pages[0])
    assert len(parsed) == 3
    heal(learnt, pages)
    assert len(parsed) == 5
    wanted = compile_extractor(pages, want={"title": TITLES[3]})
    heal(wanted, pages)
    assert len(parsed) == 9


def test_labels_are_looked_up_not_searched_for_on_every_candidate(monkeypatch):
    """A page of labelled rows that all say "Yes" has a candidate label for
    every row, and each candidate read every page again: 4,000 rows took two
    seconds, twice as many four times as long."""
    from sluicer import extractor

    scans = []
    real = extractor._value_after

    def counting(nodes, anchor, index=None):
        if index is None:
            scans.append(1)
        return real(nodes, anchor, index)

    monkeypatch.setattr(extractor, "_value_after", counting)
    rows = "".join(f"<li><b>Label {n}:</b> Yes</li>" for n in range(2000))
    html = f"<html><body><ul>{rows}</ul></body></html>"
    pages = [(html, "https://a.example/1"), (html, "https://a.example/2")]
    learnt = compile_extractor(pages, listing=False, want={"flag": "Yes"})
    assert learnt.fields[0].anchor is not None
    assert len(scans) <= len(pages)
