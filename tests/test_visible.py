"""--visible: what a page shows and does not declare, each answer a guess."""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

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


def test_extract_guesses_only_when_asked_and_never_in_the_summary() -> None:
    assert sluicer.extract(_SHOWN).visible == {}
    read = sluicer.extract(_SHOWN, visible=True)
    assert read.visible["author"].value == "Ada Lovelace"
    assert read.visible["published"].value == "2025-06-03"
    assert read.summary == {}


def test_the_command_line_shows_guesses_as_guesses(tmp_path) -> None:
    page = tmp_path / "page.html"
    page.write_text(_SHOWN, encoding="utf-8")

    plain = CliRunner().invoke(main, ["extract", str(page)])
    assert plain.exit_code == 1
    asked = CliRunner().invoke(main, ["extract", "--visible", str(page)])
    assert asked.exit_code == 0
    assert json.loads(asked.output)["visible"]["title"]["rule"] == "h1"
    shown = CliRunner().invoke(main, ["inspect", "--visible", str(page)])
    assert "from what the page shows, not declared" in shown.output
    assert "[guess: by-line]" in shown.output
