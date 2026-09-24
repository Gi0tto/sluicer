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
