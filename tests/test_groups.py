from pathlib import Path

import lxml.html

from sluicer.structure.groups import repeating_groups

FIXTURES = Path(__file__).parent / "fixtures"


def tree_of(name):
    return lxml.html.fromstring((FIXTURES / name).read_text())


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
        + ("<p class='y'><span>" + "word " * 8 + "</span></p>") * 3
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
    assert all(
        isinstance(member.tag, str) for group in groups for member in group
    ), "a group is made of elements, and a comment is not one"


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
        + "<li><span></span><span></span><span></span><span></span></li>" * 6
        + "</ul>"
        "<div class='posts'>"
        + "<article><h2>A real headline</h2><p>Real body text here</p></article>" * 4
        + "</div>"
        "</main>"
    )

    groups = repeating_groups(tree)

    assert [member.tag for member in groups[0]] == ["article"] * 4
