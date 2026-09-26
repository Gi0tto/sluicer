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


# -- what the 0.10 review found the whole page leaked or broke on ----------------


def _page(body: str) -> str:
    return f"<html><body>{body}</body></html>"


def test_a_hidden_cell_row_body_or_caption_of_a_table_is_left_out():
    head = "<tr><th>Part</th><th>Price</th></tr>"
    tables = [
        f"<table>{head}<tr><td>Pads</td><td hidden>SECRET</td></tr></table>",
        f'<table>{head}<tr style="display:none"><td>SECRET</td><td>1</td></tr></table>',
        f"<table><thead>{head}</thead><tbody hidden><tr><td>SECRET</td><td>1</td>"
        "</tr></tbody></table>",
        f'<table><caption style="display: none">SECRET</caption>{head}'
        "<tr><td>Pads</td><td>9</td></tr></table>",
        # A table that lays the page out, its cells written as blocks.
        "<table><tr><td><div>Pads</div></td><td hidden><div>SECRET</div></td></tr>"
        "</table>",
    ]
    for table in tables:
        written = _body(_page(table))
        assert "SECRET" not in written, table
        assert "Pads" in written or "Part" in written, table


def test_display_none_hides_whatever_white_space_it_is_written_with():
    for style in ("display:\tnone", "display:\nnone", "DISPLAY :  NONE"):
        written = _body(_page(f'<div style="{style}">SECRET</div><p>Shown</p>'))
        assert written == "Shown", style


def test_a_script_inside_code_is_not_written():
    written = _body(_page("<p>Run <code>make<script>SECRET()</script></code></p>"))

    assert written == "Run `make`"


def test_a_page_nested_deeper_than_python_recurses_is_still_written():
    deep = "<div>" * 600 + "Deep <b>words</b>" + "</div>" * 600
    spans = "<p>" + "<span>" * 600 + "Inner" + "</span>" * 600 + "</p>"

    assert _body(_page(deep + "<p>After</p>")) == "Deep words\n\nAfter"
    assert _body(_page(spans)) == "Inner"
    assert _body(_page("<pre>" + "<span>" * 900 + "x = 1" + "</span>" * 900)) == (
        "```\nx = 1\n```"
    )


def test_a_script_link_is_refused_however_its_scheme_is_split():
    for href in (
        "java&#9;script:alert(1)",
        "java&#10;script:alert(1)",
        " JavaScript:x",
    ):
        written = _body(_page(f'<p><a href="{href}">Click</a></p>'))
        assert written == "Click", href


def test_a_code_block_s_language_cannot_break_its_fence():
    written = _body(
        _page('<pre class="language-```x">code here</pre><p>After</p>'), url=None
    )

    assert written == "```\ncode here\n```\n\nAfter"
    assert _body(_page('<pre><code class="language-c++">x++;</code></pre>')) == (
        "```c++\nx++;\n```"
    )
    fenced = _body(_page("<pre>a\n````\nb</pre>"))
    assert fenced.startswith("`````\n") and fenced.endswith("\n`````")


def test_shown_words_walk_a_deep_page_in_order():
    doc = load(_page("<p>One " + "<span>" * 1500 + "two" + "</span>" * 1500 + " three"))

    assert [word for word, _ in shown_words(doc.tree.find("body"))] == [
        "one",
        "two",
        "three",
    ]
