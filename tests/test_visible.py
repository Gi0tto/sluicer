"""--visible: what a page shows and does not declare, each answer a guess."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from click.testing import CliRunner
from hypothesis import given, strategies as st

import sluicer
from sluicer.cli import main
from sluicer.visible import Guess, read_visible


def _page(body: str, head: str = "") -> str:
    return f"<html><head>{head}</head><body>{body}</body></html>"


def test_a_page_that_shows_nothing_gives_no_guess() -> None:
    assert read_visible(_page("<p>Nothing here.</p>")) == {}


def test_the_one_heading_is_the_shown_title() -> None:
    guesses = read_visible(_page("<nav><h1>Menu</h1></nav><h1>Brake pads, tested</h1>"))
    assert guesses["title"] == Guess("Brake pads, tested", "/html/body/h1", "h1")


def test_two_headings_give_no_title() -> None:
    assert "title" not in read_visible(_page("<h1>One</h1><h1>Two</h1>"))


def test_a_link_marked_rel_author() -> None:
    guess = read_visible(_page('<a rel="author" href="/ada">Ada Lovelace</a>'))[
        "author"
    ]
    assert (guess.value, guess.rule) == ("Ada Lovelace", "rel-author")


def test_a_byline_box_and_the_name_after_its_label() -> None:
    body = '<div class="byline"><span>Written by</span> <a>Grace Hopper</a></div>'
    guess = read_visible(_page(body))["author"]
    assert (guess.value, guess.rule) == ("Grace Hopper", "byline")


def test_a_role_glued_after_the_name_is_cut() -> None:
    body = '<div class="author-card"><b>Jeff Hoyt</b><i>Co-founder</i></div>'
    assert read_visible(_page(body))["author"].value == "Jeff Hoyt"


def test_a_by_line() -> None:
    body = "<h1>Title</h1><p>By Lisa Jennings on Dec. 19, 2025</p>"
    guesses = read_visible(_page(body))
    assert (guesses["author"].value, guesses["author"].rule) == (
        "Lisa Jennings",
        "by-line",
    )
    assert guesses["published"].value == "2025-12-19"


def test_a_label_and_a_name_in_two_texts() -> None:
    body = "<p><span>Written by</span><span>Edzel Tabing</span></p>"
    assert read_visible(_page(body))["author"].value == "Edzel Tabing"


def test_a_reviewer_is_not_the_author() -> None:
    body = "<p>Medically reviewed <span>by</span> <a>Kim Rose</a></p>"
    assert "author" not in read_visible(_page(body))


@pytest.mark.parametrize(
    "text", ["Staff Writer", "About the Author", "Skip to Content", "from the desk"]
)
def test_labels_are_not_names(text: str) -> None:
    assert "author" not in read_visible(_page(f'<div class="byline">{text}</div>'))


def test_a_team_is_an_author() -> None:
    body = '<div class="byline">Podium Staff</div>'
    assert read_visible(_page(body))["author"].value == "Podium Staff"


def test_many_by_lines_are_a_listing_and_give_no_author() -> None:
    cards = "".join(f"<article><p>By Writer Number{n}</p></article>" for n in "ABCD")
    assert "author" not in read_visible(_page(cards))


def test_a_time_marked_published() -> None:
    body = (
        '<h1>T</h1><time class="updated" datetime="2025-03-01">March 1, 2025</time>'
        '<time class="published" datetime="2024-01-02">Jan 2, 2024</time>'
    )
    guesses = read_visible(_page(body))
    assert (guesses["published"].value, guesses["published"].rule) == (
        "2024-01-02",
        "time",
    )
    assert guesses["modified"].value == "2025-03-01"


def test_an_update_date_is_never_the_publication_date() -> None:
    body = "<h1>T</h1><p>Last updated on <span>March 12, 2026</span></p>"
    guesses = read_visible(_page(body))
    assert "published" not in guesses
    assert guesses["modified"].value == "2026-03-12"


def test_an_update_inside_a_by_line() -> None:
    body = "<h1>T</h1><p>By Mirel ZamanUpdated on June 18, 2025 at 12:35 PM</p>"
    guesses = read_visible(_page(body))
    assert "published" not in guesses
    assert guesses["modified"].value == "2025-06-18"


def test_a_date_class_text_and_a_date_by_the_heading() -> None:
    named = read_visible(_page('<h1>T</h1><span class="post-date">16 June 2025</span>'))
    assert (named["published"].value, named["published"].rule) == (
        "2025-06-16",
        "date-text",
    )
    near = read_visible(_page("<header><h1>T</h1><span>June 16, 2025</span></header>"))
    assert (near["published"].value, near["published"].rule) == (
        "2025-06-16",
        "near-heading",
    )


def test_an_all_number_date_is_not_read() -> None:
    assert "published" not in read_visible(_page("<h1>T</h1><span>03/04/2025</span>"))


def test_a_hidden_date_and_another_pages_card_are_passed_over() -> None:
    body = (
        '<h1>T</h1><time style="display: none" datetime="2025-01-01">x</time>'
        '<a href="/other"><time datetime="2025-02-02">Feb 2, 2025</time></a>'
    )
    assert "published" not in read_visible(_page(body), url="https://example.com/here")


def test_the_permalink_round_a_date_is_the_page_itself() -> None:
    body = '<h1>T</h1><a href="/here/"><time datetime="2025-02-02">Feb 2</time></a>'
    guess = read_visible(_page(body), url="https://example.com/here")["published"]
    assert guess.value == "2025-02-02"


@pytest.mark.parametrize(
    "href", ["https://[domain]/story", "http://[::1", "http://[x/"]
)
@pytest.mark.parametrize(
    "url", ["https://news.example/a/story", "https://[domain]/a/story", "http://[::1"]
)
def test_a_link_or_an_address_that_is_not_a_url_is_read(href: str, url: str) -> None:
    # An unfilled template's "https://[domain]/..." round a date: urlsplit
    # refuses it with a ValueError, and --visible raised it.
    body = (
        "<h1>Brake pads, tested</h1>"
        f'<a href="{href}"><time datetime="2024-05-01">May 1, 2024</time></a>'
    )
    assert "published" not in read_visible(_page(body), url=url)
    shown = sluicer.extract(_page(body), url=url, visible=True).visible
    assert shown["title"].value == "Brake pads, tested"


def test_an_address_that_is_not_a_url_gives_no_date() -> None:
    assert read_visible(_page("<p>x</p>"), url="http://[::1/2024/05/06/story") == {}


def test_a_listing_s_dates_are_read_only_by_its_heading() -> None:
    cards = "".join(
        f'<article><time datetime="2025-0{n}-01">x</time></article>'
        for n in range(1, 6)
    )
    assert "published" not in read_visible(
        _page("<h1>News</h1><main>" + cards + "</main>")
    )


def test_the_address_s_date_last() -> None:
    guess = read_visible(_page("<p>x</p>"), url="https://example.com/2024/05/06/story")
    assert (guess["published"].value, guess["published"].where) == ("2024-05-06", "url")


def test_chrome_and_comments_are_not_the_article_s() -> None:
    body = (
        "<footer><p>By Someone Else</p></footer>"
        '<div class="comments"><p>By Another Person</p></div>'
    )
    assert "author" not in read_visible(_page(body))


def test_the_same_page_gives_the_same_guesses() -> None:
    body = (
        '<h1>T</h1><div class="byline">By Ada Lovelace</div>'
        '<time datetime="2025-01-01">x</time>'
    )
    assert read_visible(_page(body)) == read_visible(_page(body))


_SHOWN = (
    "<html><body><h1>Brake pads</h1>"
    "<p>By Ada Lovelace on June 3, 2025</p></body></html>"
)


def test_extract_guesses_by_default_and_never_in_the_summary() -> None:
    assert sluicer.extract(_SHOWN, visible=False).visible == {}
    read = sluicer.extract(_SHOWN)
    assert read.visible["author"].value == "Ada Lovelace"
    assert read.visible["published"].value == "2025-06-03"
    assert read.summary == {}
    # visible=True, the spelling before 0.10, still asks for the same.
    assert sluicer.extract(_SHOWN, visible=True) == read


async def _awaited() -> sluicer.Extraction:
    return await sluicer.aextract(_SHOWN)


def test_aextract_guesses_by_default_too() -> None:
    import asyncio

    assert asyncio.run(_awaited()).visible["author"].value == "Ada Lovelace"


def test_the_command_line_shows_guesses_as_guesses(tmp_path) -> None:
    page = tmp_path / "page.html"
    page.write_text(_SHOWN, encoding="utf-8")

    declared = CliRunner().invoke(main, ["extract", "--no-visible", str(page)])
    assert declared.exit_code == 1
    plain = CliRunner().invoke(main, ["extract", str(page)])
    assert plain.exit_code == 0
    assert json.loads(plain.output)["visible"]["title"]["rule"] == "h1"
    asked = CliRunner().invoke(main, ["extract", "--visible", str(page)])
    assert asked.output == plain.output
    shown = CliRunner().invoke(main, ["inspect", str(page)])
    assert "from what the page shows, not declared" in shown.output
    assert "[guess: by-line]" in shown.output
    hidden = CliRunner().invoke(main, ["inspect", "--no-visible", str(page)])
    assert "[guess:" not in hidden.output


_FIXTURES = Path(__file__).parent / "fixtures"
# A trimmed copy of the page as served on 2026-09-26 (its robots.txt allows
# all). Framer writes the site's build time in a comment before <html>.
_TYPESAFE = _FIXTURES / "typesafe_byline_under_heading.html"
_TYPESAFE_URL = "https://typesafe.ai/blog/introducing-system-one-models-and-jev"


def test_a_name_and_role_under_the_heading_with_no_byline_mark_is_not_read() -> None:
    """0.10's development read "Diogo Almeida, founder, TypeSafe" under this
    page's heading as its byline. The hostile review of 0.10 showed that
    nothing in such a line tells it from a deck, a team's list or a job's
    department (the cases below), so it is not read: silence here, as in
    0.9, rather than a wrong author on other pages."""
    read = sluicer.extract(_TYPESAFE.read_bytes(), url=_TYPESAFE_URL, visible=True)
    assert "author" not in read.visible
    assert "author" not in read.summary


@pytest.mark.parametrize(
    "body",
    [
        # No role after the comma: a place.
        "<h1>Brake pads</h1><p>Porto Alegre, Brazil</p>",
        # Not the first line under the heading.
        "<h1>Brake pads</h1><p>A short intro.</p><p>Diogo Almeida, founder</p>",
        # A sentence, not a name.
        "<h1>Brake pads</h1><p>We asked the founder, who said no.</p>",
        "<h1>Brake pads</h1><p>Then Diogo Almeida left. Later, founder</p>",
        # One word, or words in lowercase.
        "<h1>Brake pads</h1><p>Almeida, founder, TypeSafe</p>",
        "<h1>Brake pads</h1><p>diogo almeida, founder, TypeSafe</p>",
        # Two headings: no page's heading to be under.
        "<h1>One</h1><h1>Two</h1><p>Diogo Almeida, founder</p>",
        # Found by the hostile review of 0.10: roles, organisations and a
        # team's list read as a byline's name.
        "<h1>Brake pads</h1><p>Managing Editor, Senior Writer</p>",
        "<h1>Brake pads</h1><p>The Daily Planet, Editor</p>",
        "<h1>Brake pads</h1><p>A Better Team, founder</p>",
        "<h1>Brake pads</h1><p>NASA JPL, Director</p>",
        "<h1>Brake pads</h1><p>, founder</p>",
        "<h1>Leadership</h1><ul><li>Jane Doe, CEO</li><li>John Roe, CTO</li></ul>",
        "<h1>Leadership</h1><p><b>Jane Doe, CEO</b></p><p>John Roe, CTO</p>",
        # Found by the second pass of that review: an organisation, a deck,
        # a job's department and a board's list, each read as a byline.
        "<h1>Hello</h1><p>Acme Widgets, Chief Executive Officer office</p>",
        "<h1>Hello</h1><p>Apple Inc, CEO Tim Cook said</p>",
        "<h1>Hello</h1><p>Prime Minister, President meet in Paris</p>",
        "<h1>Engineer</h1><p>Product Engineering, Senior Engineer, Remote</p>",
        "<h1>Minutes</h1><p>Jane Doe, Chair, John Roe, Treasurer</p>",
        "<h1>Keynote</h1><p>Ada Lovelace, Chief Scientist, Engines</p>",
        "<h1>Interview</h1><p><em>Mary Jones, Head of Marketing, Acme</em></p>",
    ],
)
def test_what_is_not_a_name_and_role_under_the_heading(body: str) -> None:
    assert "author" not in read_visible(_page(body))


def test_a_date_in_an_html_comment_is_never_read() -> None:
    read = sluicer.extract(_TYPESAFE.read_bytes(), url=_TYPESAFE_URL, visible=True)
    assert read.visible["published"].value == "2026-09-15"
    assert read.visible["published"].rule == "near-heading"
    assert "published" not in read.summary
    assert "modified" not in read.summary
    assert "modified" not in read.visible


def test_no_reader_or_guess_takes_a_date_from_a_comment() -> None:
    comment = "<!-- Published Sep 26, 2026, 7:01 AM UTC -->"
    page = (
        f"<!doctype html>{comment}<html><head>{comment}"
        '<meta name="date" content="2025-03-04">'
        '<!--[if IE]><meta name="dcterms.modified" content="2026-09-26"><![endif]-->'
        f"</head><body>{comment}"
        f'<h1>Brake pads</h1>{comment}<p class="date">{comment}</p>'
        f'<div itemscope itemtype="https://schema.org/Article">'
        f'<span itemprop="dateModified">{comment}</span></div>'
        f'<span property="dc:date">{comment}</span>'
        f"<time>{comment}</time><p>{comment} Published: {comment}</p>"
        f'<p class="byline">By Ada Lovelace {comment}</p></body></html>'
    )
    read = sluicer.extract(page, url="https://example.com/brake-pads", visible=True)
    answers = [a.value for a in read.summary.values()]
    answers += [g.value for g in read.visible.values()]
    answers += [str(f.value) for r in read.records for f in r.fields.values()]
    assert not [a for a in answers if "2026" in str(a) or "Sep 26" in str(a)]
    assert read.summary["published"].value == "2025-03-04"


def test_a_box_that_says_there_is_no_byline_is_none() -> None:
    body = (
        '<h1>Cybersecurity</h1><div class="post-meta-detail no-byline">'
        "Home » Consulting Services</div>"
    )
    assert "author" not in read_visible(_page(body))


@pytest.mark.parametrize("tag", ["main", "article"])
def test_a_box_holding_the_whole_article_is_no_byline(tag: str) -> None:
    body = (
        f'<{tag} class="author-archive"><h1>Store Policies</h1><p>Read on.</p></{tag}>'
    )
    assert "author" not in read_visible(_page(body))


def test_a_by_line_on_another_article_s_card_is_not_the_author() -> None:
    body = (
        "<h1>Tips from a first time visitor</h1>"
        '<a href="/articles/sports"><div>8 places to go all-in on sports this year'
        "</div><div>From baseball games in Tokyo to F1 races.</div>"
        "<div>By Noah Cortez</div></a>"
    )
    assert "author" not in read_visible(_page(body), url="https://example.com/topic/1")


def test_a_by_line_linked_to_its_author_s_page_is_the_author() -> None:
    body = '<h1>Costs</h1><a href="/authors/scott"><div>By Scott Kasun</div></a>'
    guess = read_visible(_page(body), url="https://example.com/costs")["author"]
    assert (guess.value, guess.rule) == ("Scott Kasun", "by-line")


def test_sluicer_s_own_callers_guess_by_default_as_extract_does() -> None:
    from sluicer.api import _extract

    assert _extract(_SHOWN).visible == sluicer.extract(_SHOWN).visible != {}


_TEXTS = st.text(alphabet=" \t\n\r\N{NO-BREAK SPACE}ab", max_size=6)


@given(st.lists(_TEXTS, min_size=1, max_size=8))
def test_the_texts_read_are_those_of_more_than_one_character(pieces):
    """What XPath's string-length(normalize-space()) > 1 kept, and nothing
    measured by rewriting each text node: that was a third of the time."""
    from sluicer import visible
    from sluicer.document import load

    body = "".join(f"<p>{piece}<b>x</b>{piece}</p>" for piece in pieces)
    page = visible._Page(load(f"<html><body>{body}</body></html>"))
    spaces = re.compile(r"[ \t\n\r]+")
    expected = [
        text
        for text in page.tree.xpath("//text()")
        if len(spaces.sub(" ", text).strip(" ")) > 1
    ]
    assert page.texts == expected


class _Counted:
    def __init__(self, pattern):
        self.pattern = pattern
        self.asked = 0

    def search(self, *args, **kwargs):
        self.asked += 1
        return self.pattern.search(*args, **kwargs)

    def sub(self, *args, **kwargs):
        self.asked += 1
        return self.pattern.sub(*args, **kwargs)


def test_each_element_s_names_are_asked_once_whether_they_are_a_byline_s(
    monkeypatch,
):
    from sluicer import visible

    counted = _Counted(visible._BYLINE)
    monkeypatch.setattr(visible, "_BYLINE", counted)
    rewritten = _Counted(re.compile(r"[ \t\n\r]+"))
    monkeypatch.setattr(visible, "_XML_SPACES", rewritten, raising=False)
    page = (
        "<html><body><h1>Pads</h1>"
        '<div class="byline"><span class="author">By Ann Lee</span></div>'
        '<p class="intro">text</p><p id="x">more</p></body></html>'
    )
    read_visible(page)
    # The four elements a class or an id names, once each, and the two it
    # names as a byline's once more, their no-/hide- words left out.
    assert counted.asked == 6
    assert rewritten.asked == 0
