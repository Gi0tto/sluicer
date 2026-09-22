from pathlib import Path

import lxml.html

from sluicer.induce.groups import repeating_groups

FIXTURES = Path(__file__).parent / "fixtures"


def test_a_listing_page_yields_its_rows():
    tree = lxml.html.fromstring(
        (FIXTURES / "listing_no_declared_data.html").read_text()
    )

    groups = repeating_groups(tree)

    assert groups, "a page that is one long list should yield a group"
    assert len(groups[0]) == 4


def test_two_of_a_kind_is_not_a_pattern():
    tree = lxml.html.fromstring(
        "<div><p class='x'><b>a</b></p><p class='x'><b>b</b></p></div>"
    )

    assert repeating_groups(tree, minimum=3) == []


def test_the_richer_group_comes_first():
    tree = lxml.html.fromstring(
        "<body>"
        "<ul>" + "<li><a>x</a></li>" * 6 + "</ul>"
        "<div>" + "<article><h3>t</h3><p>b</p><span>s</span></article>" * 4 + "</div>"
        "</body>"
    )

    groups = repeating_groups(tree)

    assert len(groups[0]) == 4, "the four rich cards should beat the six thin links"


def test_the_order_is_stable_across_runs():
    html = "<div>" + "<li><a>x</a><b>y</b></li>" * 5 + "</div>"

    first = [len(g) for g in repeating_groups(lxml.html.fromstring(html))]
    second = [len(g) for g in repeating_groups(lxml.html.fromstring(html))]

    assert first == second


def test_a_comment_is_not_an_element_and_does_not_break_a_group():
    """A comment has no tag name, and a group of three is still a group."""
    tree = lxml.html.fromstring(
        "<div><!-- a note -->"
        + "<p class='x'><b>a</b><!-- inline --></p>" * 3
        + "</div>"
    )

    groups = repeating_groups(tree)

    assert len(groups[0]) == 3
