from pathlib import Path

import lxml.html

from sluicer.structure.groups import repeating_groups

FIXTURES = Path(__file__).parent / "fixtures"


def tree_of(name):
    return lxml.html.fromstring((FIXTURES / name).read_text(encoding="utf-8"))


def test_a_listing_page_yields_its_rows():
    tree = tree_of("listing_no_declared_data.html")

    groups = repeating_groups(tree)

    assert groups, "a page that is one long list should yield a group"
    assert len(groups[0]) == 4


def test_two_of_a_kind_is_not_a_pattern():
    """The floor is the default, so the default is what this calls."""
    tree = lxml.html.fromstring(
        "<div><p class='x'><b>a</b></p><p class='x'><b>b</b></p></div>"
    )

    assert repeating_groups(tree) == []


def test_the_floor_is_the_callers_to_lower():
    """Two is not a pattern by default; a caller who says so gets the pair."""
    tree = lxml.html.fromstring(
        "<div><p class='x'><b>a</b></p><p class='x'><b>b</b></p></div>"
    )

    assert len(repeating_groups(tree, minimum=2)[0]) == 2


def test_the_richer_group_comes_first():
    tree = lxml.html.fromstring(
        "<body>"
        "<ul>" + "<li><a>x</a></li>" * 6 + "</ul>"
        "<div>" + "<article><h3>t</h3><p>b</p><span>s</span></article>" * 4 + "</div>"
        "</body>"
    )

    groups = repeating_groups(tree)

    assert len(groups[0]) == 4, "the four rich cards should beat the six thin links"


def test_richness_is_the_widest_member_not_the_narrowest():
    """One rich member says what the group can hold; the thinnest says nothing."""
    tree = lxml.html.fromstring(
        "<main>"
        "<div class='uneven'>"
        "<p class='x'><span>" + "word " * 30 + "</span></p>"
        "<p class='x'><span>i</span></p>"
        "<p class='x'><span>i</span></p>"
        "</div>"
        "<div class='even'>"
        + ("<p class='y'><span>" + "word " * 8 + "</span></p>")
        * 3
        + "</div>"
        "</main>"
    )

    groups = repeating_groups(tree)

    assert groups[0][0].getparent().get("class") == "uneven"


def test_the_order_is_stable_across_runs():
    html = "<div>" + "<li><a>x</a><b>y</b></li>" * 5 + "</div>"

    first = [len(g) for g in repeating_groups(lxml.html.fromstring(html))]
    second = [len(g) for g in repeating_groups(lxml.html.fromstring(html))]

    assert first == second


def test_two_groups_that_score_alike_are_ranked_by_document_order():
    """Nothing separates them but where they sit, so the first one wins."""
    rows = "<li class='r'><span>ab</span></li>" * 3
    tree = lxml.html.fromstring(
        f"<main><ul class='first'>{rows}</ul><ul class='second'>{rows}</ul></main>"
    )

    groups = repeating_groups(tree)

    assert groups[0][0].getparent().get("class") == "first"


def test_a_comment_is_not_a_member_and_does_not_break_a_group():
    """A comment is not an element: it cannot be a row, and it does not split one."""
    tree = lxml.html.fromstring(
        "<main><div>"
        + "<!-- a note about the row that follows -->" * 3
        + "<p class='x'><b>a text</b><!-- inline --></p>" * 3
        + "</div></main>"
    )

    groups = repeating_groups(tree)

    assert [member.tag for member in groups[0]] == ["p", "p", "p"]
    assert all(isinstance(member.tag, str) for group in groups for member in group), (
        "a group is made of elements, and a comment is not one"
    )


def test_the_head_is_not_a_listing():
    """Fourteen meta tags are a page's paperwork, not fourteen records."""
    groups = repeating_groups(tree_of("listing_under_a_crowded_head.html"))

    assert [member.tag for member in groups[0]] == ["li"] * 5


CONTENT = (
    "<main><div>" + "<article><h2>Real headline</h2></article>" * 3 + "</div></main>"
)


def test_a_head_full_of_links_is_still_the_head():
    """Twenty links in the head point at more than three articles do, and mean less."""
    links = "".join(f"<link rel='alternate' href='/page/{n}'>" for n in range(20))
    tree = lxml.html.fromstring(
        f"<html><head>{links}</head><body>{CONTENT}</body></html>"
    )

    groups = repeating_groups(tree)

    assert [member.tag for member in groups[0]] == ["article"] * 3


def test_a_repeat_inside_the_furniture_is_not_a_listing():
    """Eight long links in the chrome outweigh three articles, and are not records."""
    crowd = "".join(
        f"<li><a href='/l{n}'>A navigation label that is quite long</a></li>"
        for n in range(8)
    )
    for region in ("nav", "aside", "footer"):
        tree = lxml.html.fromstring(
            f"<body>{CONTENT}<{region}><ul>{crowd}</ul></{region}></body>"
        )

        groups = repeating_groups(tree)

        assert [member.tag for member in groups[0]] == ["article"] * 3, region


def test_a_script_is_not_a_row():
    """Three inline scripts carry more characters than any row, and no facts."""
    code = "<script>var config = {a: 1, b: 2, c: 3, d: 4, e: 5, f: 6};</script>" * 3
    tree = lxml.html.fromstring(f"<body><div>{code}</div>{CONTENT}</body>")

    groups = repeating_groups(tree)

    assert [member.tag for member in groups[0]] == ["article"] * 3


def test_the_sidebar_and_the_footer_do_not_outrank_the_content():
    """Eight widgets and twenty footer links are furniture; five articles are not."""
    groups = repeating_groups(tree_of("listing_between_sidebar_and_footer.html"))

    assert [member.get("class") for member in groups[0]] == ["post"] * 5


def test_many_empty_children_do_not_beat_fewer_full_ones():
    """A row that carries no text carries no record, however many parts it has."""
    tree = lxml.html.fromstring(
        "<main>"
        "<ul class='filters'>"
        + "<li><span></span><span></span><span></span><span></span></li>"
        * 6
        + "</ul>"
        "<div class='posts'>"
        + "<article><h2>A real headline</h2><p>Real body text here</p></article>"
        * 4
        + "</div>"
        "</main>"
    )

    groups = repeating_groups(tree)

    assert [member.tag for member in groups[0]] == ["article"] * 4


def test_a_row_that_only_points_somewhere_is_still_worth_something():
    """A grid of image links carries no text at all, and is still the content."""
    tree = lxml.html.fromstring(
        "<main>"
        "<div class='rules'>" + "<hr>" * 6 + "</div>"
        "<div class='grid'>"
        + "".join(f"<a href='/p/{n}'><img src='/i{n}.jpg'></a>" for n in range(4))
        + "</div>"
        "</main>"
    )

    groups = repeating_groups(tree)

    assert [member.tag for member in groups[0]] == ["a"] * 4


def test_a_rating_written_as_a_class_does_not_split_the_listing():
    """Every book on books.toscrape.com is one group, whatever its stars."""
    stars = ["One", "Three", "Five", "Two", "Three", "Four"]
    books = "".join(
        f"<li><article class='product_pod'><p class='star-rating {rating}'>"
        f"<i></i></p><h3><a href='/b{n}'>Book {n}</a></h3>"
        f"<p class='price_color'>{n}.00</p></article></li>"
        for n, rating in enumerate(stars)
    )
    tree = lxml.html.fromstring(f"<main><ol class='row'>{books}</ol></main>")

    groups = repeating_groups(tree)

    assert len(groups[0]) == 6


def test_a_varying_number_of_tags_does_not_split_the_listing():
    quotes = "".join(
        f"<div class='quote'><span class='text'>Quote {n}</span><div class='tags'>"
        + "<a class='tag' href='/t'>tag</a>" * (n + 1)
        + "</div></div>"
        for n in range(5)
    )
    tree = lxml.html.fromstring(f"<main><div class='col'>{quotes}</div></main>")

    groups = repeating_groups(tree)

    assert [member.get("class") for member in groups[0]] == ["quote"] * 5


def test_rows_of_another_class_between_the_rows_stay_out_of_the_group():
    """A news aggregator interleaves each story with a subtext row and a spacer."""
    rows = "".join(
        f"<tr class='athing'><td><span class='rank'>{n}.</span></td>"
        f"<td><span><a href='/s{n}'>Story {n}</a></span></td></tr>"
        f"<tr><td></td><td><span>{n} points</span><a href='/u'>user</a></td></tr>"
        "<tr class='spacer'></tr>"
        for n in range(4)
    )
    tree = lxml.html.fromstring(f"<body><table>{rows}</table></body>")

    groups = repeating_groups(tree)

    for group in groups:
        assert len({member.get("class") for member in group}) == 1, group
    stories = next(group for group in groups if group[0].get("class") == "athing")
    assert len(stories) == 4


def test_a_listing_under_two_thousand_wrappers_is_found_in_a_moment():
    """Found profiling why the bounded-output property was slow on deep pages.

    Whether an element sits in the page's furniture was decided by climbing
    from it to the root, once for every element: 3,000 rows under 2,000
    wrappers took 2.9 seconds of an 85 KB page.
    """
    import time

    from sluicer.document import load

    rows = "<li><a href=/p>x</a></li>" * 3000
    doc = load("<div>" * 2000 + "<ul>" + rows)

    started = time.perf_counter()
    groups = repeating_groups(doc.tree)

    assert time.perf_counter() - started < 0.5
    assert len(groups[0]) == 3000


def test_a_listing_deep_inside_the_furniture_is_still_furniture():
    from sluicer.document import load

    rows = "<li><a href=/p>x</a></li>" * 3
    doc = load("<body><nav>" + "<div>" * 300 + "<ul>" + rows + "</ul></nav></body>")

    assert repeating_groups(doc.tree) == []


def _stories(n, cls="story"):
    return "".join(
        f"<li class='{cls}'><a href='/s{i}'>Story {i} with a longer headline</a>"
        f"<span class='by'>by someone</span><time>2026-01-0{i % 9 + 1}</time></li>"
        for i in range(n)
    )


def test_a_menu_the_page_marks_with_its_role_is_furniture():
    """A trending page's language menu of 491 links, role "menu"."""
    menu = "".join(
        f"<a role='menuitem' href='/l{i}'>Language {i}</a>" for i in range(60)
    )
    tree = lxml.html.fromstring(
        f"<body><div role='menu'>{menu}</div><ol>{_stories(5)}</ol></body>"
    )

    groups = repeating_groups(tree)

    assert groups[0][0].get("class") == "story"
    assert all(group[0].get("role") != "menuitem" for group in groups)


def test_what_the_page_hides_is_furniture():
    hidden = "".join(f"<a href='/x{i}'>Hidden choice {i}</a>" for i in range(40))
    tree = lxml.html.fromstring(
        f"<body><div hidden>{hidden}</div><div aria-hidden='true'>{hidden}</div>"
        f"<ol>{_stories(4)}</ol></body>"
    )

    assert repeating_groups(tree)[0][0].get("class") == "story"


def test_sections_holding_listings_are_not_rows():
    """Two news sites: three page sections outweighed their stories."""
    sections = "".join(
        f"<section class='column'><h2>Column {c}</h2><ol>{_stories(6)}</ol></section>"
        for c in range(3)
    )
    tree = lxml.html.fromstring(f"<body><main>{sections}</main></body>")

    groups = repeating_groups(tree)

    assert groups[0][0].tag == "li"
    assert all(group[0].tag != "section" for group in groups)


def test_classes_that_name_one_item_or_a_position_do_not_split_a_listing():
    """A forum and WordPress: id-t3_…, odd/even, category-… on every row."""
    rows = "".join(
        f"<div class='thing link id-t3_a{i} {'odd' if i % 2 else 'even'} "
        f"category-c{i % 3}'><a href='/p{i}'>Post {i} with a title</a>"
        f"<span>{i} points</span></div>"
        for i in range(6)
    )
    tree = lxml.html.fromstring(f"<body><div id='siteTable'>{rows}</div></body>")

    assert len(repeating_groups(tree)[0]) == 6
