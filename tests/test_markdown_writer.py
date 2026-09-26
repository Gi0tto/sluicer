"""sluicer.markdown_writer: any element of a page written as markdown, by lxml."""

from pathlib import Path

from sluicer.document import load
from sluicer.markdown_writer import (
    element_markdown,
    fragment_markdown,
    shown_words,
    text_markdown,
)

FIXTURES = Path(__file__).parent / "fixtures" / "markdown"
URL = "https://shop.example/guide/brakes/fitting.html"


def _body(html: str, url: str | None = URL, **options: bool) -> str:
    doc = load(html, url=url)
    return element_markdown(doc.tree.find("body"), doc.base, **options)


def test_the_whole_fixture_page_is_written_as_markdown():
    """Every kind of block the writer knows, on one page, in one answer."""
    page = (FIXTURES / "every_block.html").read_text(encoding="utf-8")

    assert _body(page) == (FIXTURES / "every_block.md").read_text(
        encoding="utf-8"
    ).rstrip("\n")


def test_the_same_page_always_gives_the_same_markdown():
    page = (FIXTURES / "every_block.html").read_text(encoding="utf-8")

    assert len({_body(page) for _ in range(3)}) == 1


def test_links_and_images_resolve_against_the_page_and_its_base():
    page = (
        '<html><head><base href="/docs/"></head><body><p><a href="a.html">A</a> '
        '<img src="i.png" alt="pic"></p></body></html>'
    )

    assert _body(page) == (
        "[A](https://shop.example/docs/a.html) ![pic](https://shop.example/docs/i.png)"
    )


def test_a_link_to_a_script_or_to_nowhere_keeps_only_its_words():
    page = (
        '<p><a href="#top">Back to top</a> and <a href="javascript:void(0)">'
        "open</a> and <a>no target</a>.</p>"
    )

    # A link within the page resolves against it, as the main text's links do.
    assert _body(page) == (f"[Back to top]({URL}#top) and open and no target.")


def test_what_a_reader_never_sees_is_left_out():
    page = (
        "<html><head><title>T</title><style>p{}</style></head><body>"
        "<script>var shown = 'no';</script><p>Shown.</p>"
        "<div hidden>Hidden.</div><p style='display: none'>Gone.</p>"
        "<form><input value='typed'><button>Send</button></form>"
        "<template><p>Later.</p></template></body></html>"
    )

    assert _body(page) == "Shown."


def test_noscript_is_shown_only_as_a_reader_without_scripts_sees_it():
    page = (
        "<body><p>Before.</p><noscript><p>The posts, for crawlers.</p>"
        '<img src="/pixel.gif" alt="pixel"></noscript></body>'
    )

    assert _body(page) == "Before."
    assert _body(page, noscript=True) == "Before.\n\nThe posts, for crawlers."


def test_text_that_looks_like_markdown_stays_text():
    page = (
        "<p># not a heading</p><p>1. not a list</p><p>- nor this</p>"
        "<p>a *star*, a [bracket] and a_snake_case name, _emphasis_</p>"
    )

    assert _body(page) == (
        "\\# not a heading\n\n1\\. not a list\n\n\\- nor this\n\n"
        "a \\*star\\*, a \\[bracket\\] and a_snake_case name, \\_emphasis\\_"
    )


def test_a_table_laying_out_the_page_is_written_as_its_blocks():
    page = (
        "<table><tr><td><table><tr><td>Menu</td></tr></table></td>"
        "<td><p>The article.</p></td></tr></table>"
    )

    assert _body(page) == "Menu\n\nThe article."


def test_a_fragment_and_plain_text_are_written_too():
    assert fragment_markdown(
        '<p>One <a href="/x">link</a>.</p><h2>Part</h2>Two.', "https://a.example/"
    ) == ("One [link](https://a.example/x).\n\n## Part\n\nTwo.")
    assert text_markdown("First line.\n\n# Second *line*\n") == (
        "First line.\n\n\\# Second \\*line\\*"
    )


def test_shown_words_name_the_element_holding_each():
    doc = load("<body><p>Two words</p><script>no</script><div>three</div></body>")

    assert [(w, e.tag) for w, e in shown_words(doc.tree.find("body"))] == [
        ("two", "p"),
        ("words", "p"),
        ("three", "div"),
    ]
