import lxml.html
import pytest

from sluicer.structure.records import records_from


def rows(html):
    """The children of ``html``, which is what a group is."""
    return list(lxml.html.fromstring(html))


LISTING = (
    "<ul>"
    + "".join(
        f"<li class='row'><a href='/p{n}'>Product name {n}</a>"
        f"<span class='price'>{n}.99</span></li>"
        for n in range(3)
    )
    + "</ul>"
)


def test_a_link_carries_its_text_as_well_as_its_address():
    """The commonest listing shape on the web puts the name inside the link."""
    record = records_from(rows(LISTING))[0]

    values = {field.value for field in record.fields.values()}
    assert "Product name 0" in values, "the product name is in no field"
    assert "/p0" in values


def test_the_text_and_the_address_are_named_as_a_pair():
    """One slot, two facts: the address is the text field's name plus @href."""
    record = records_from(rows(LISTING))[0]

    named = {name: field.value for name, field in record.fields.items()}
    text = [name for name, value in named.items() if value == "Product name 0"]
    assert text, f"no field holds the link text: {named}"
    assert named.get(text[0] + "@href") == "/p0", named


def test_an_image_carries_its_alt_text_as_well_as_its_source():
    """An image says two things too, and one of them is words."""
    group = rows(
        "<ul>"
        + "<li class='row'><img src='/i.jpg' alt='A photo of the part'></li>" * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    named = {name: field.value for name, field in record.fields.items()}
    text = [name for name, value in named.items() if value == "A photo of the part"]
    assert text, f"no field holds the alt text: {named}"
    assert named.get(text[0] + "@src") == "/i.jpg", named


OPTIONAL_EMPHASIS = (
    "<ul>"
    "<li class='row'><h3 class='name'>A</h3>"
    "<p class='blurb'><span><b>plain</b></span></p>"
    "<span>in stock</span></li>"
    "<li class='row'><h3 class='name'>B</h3>"
    "<p class='blurb'><span><b>with <em>one</em></b></span></p>"
    "<span>in stock</span></li>"
    "<li class='row'><h3 class='name'>C</h3>"
    "<p class='blurb'><span><b>with <em>one</em> and <em>two</em></b></span></p>"
    "<span>in stock</span></li>"
    "<li class='row'><h3 class='name'>D</h3>"
    "<p class='blurb'><span><b>plain</b></span></p>"
    "<span>in stock</span></li>"
    "</ul>"
)


def slot_holding(record, value):
    return next(name for name, field in record.fields.items() if field.value == value)


def test_the_same_slot_keeps_its_name_in_every_record():
    """Members differing below the compared depth are rows, not four shapes."""
    records = records_from(rows(OPTIONAL_EMPHASIS))

    names = {slot_holding(record, "in stock") for record in records}
    assert len(names) == 1, f"one slot came back under several names: {names}"


def test_a_slot_a_member_does_not_have_is_absent_and_not_renamed():
    """The first and last rows have no emphasis; the ones they share are unmoved."""
    first, second, _, last = records_from(rows(OPTIONAL_EMPHASIS))

    shared = set(first.fields) & set(second.fields)
    assert set(first.fields) == set(last.fields)
    assert set(first.fields) == shared, "the plain rows carry nothing extra"
    assert set(second.fields) - shared, "the emphasised row carries one slot more"


def test_three_badges_are_three_facts():
    """Same tag, same class, three of them: three values, none of them dropped."""
    group = rows(
        "<ul>"
        + (
            "<li class='row'><span class='tag'>new</span>"
            "<span class='tag'>sale</span><span class='tag'>last</span></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert {field.value for field in record.fields.values()} == {
        "new",
        "sale",
        "last",
    }, record.fields


def test_the_field_names_say_where_the_value_sat():
    """Positional naming is only usable if the names are stated somewhere."""
    record = records_from(rows(LISTING))[0]

    assert {name: field.value for name, field in record.fields.items()} == {
        "a": "Product name 0",
        "a@href": "/p0",
        "span.price": "0.99",
    }


def test_a_nested_slot_is_named_by_the_path_down_to_it():
    """A name that does not say which branch it came from is not a slot name.

    The wrapper here holds a label of its own, so both slots are facts and the
    deeper one has to say which branch it came from. A wrapper that held only
    the span would carry no fact at all -- see
    ``test_a_wrapper_does_not_repeat_its_child_s_text``.
    """
    group = rows(
        "<ul>"
        + (
            "<li class='row'><div class='meta'>Part: "
            "<span class='sku'>ABC</span></div></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert set(record.fields) == {"div.meta", "div.meta>span.sku"}
    assert record.fields["div.meta"].value == "Part: ABC"
    assert record.fields["div.meta>span.sku"].value == "ABC"


def test_a_comment_inside_a_row_is_not_a_slot():
    """A comment is not an element: it names no field and its words are not a value."""
    group = rows(
        "<ul>"
        + (
            "<li class='row'><!-- a note the shop left in --> "
            "<span class='sku'>ABC</span></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert {name: field.value for name, field in record.fields.items()} == {
        "span.sku": "ABC"
    }


def test_a_class_a_build_tool_generated_never_names_a_field():
    """CSS-in-JS hashes change with every deploy, and a name must not.

    A news site's front page names everything ``dcr-1t2r5md`` and the like, so
    every field came back under a name that would not survive the next release.
    A generated class is skipped and the next honest label is used: a class a
    person wrote, and failing that the tag.
    """
    group = rows(
        "<ul>"
        + (
            "<li class='dcr-1t2r5md'>"
            "<h3 class='dcr-7co5ks card-headline'>Headline</h3>"
            "<span class='css-1x2y3z'>kicker</span>"
            "<p class='sc-bdVaJa kPXmIq'>blurb</p>"
            "<div class='dcr-mmqaso'>standfirst</div>"
            "</li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert {name: field.value for name, field in record.fields.items()} == {
        "h3.card-headline": "Headline",
        "span": "kicker",
        "p": "blurb",
        "div": "standfirst",
    }


def test_a_css_module_keeps_the_name_a_person_wrote_and_loses_the_hash():
    group = rows(
        "<ul>"
        + (
            "<li class='row'><span class='Card_title__a1B2c'>T</span>"
            "<span class='card__price'>9</span></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert set(record.fields) == {"span.Card_title", "span.card__price"}


def test_a_class_that_only_looks_technical_still_names_its_field():
    """Tailwind, Bootstrap and BEM are written by people and change by hand."""
    group = rows(
        "<ul>"
        + (
            "<li class='row'><span class='col-md-6'>a</span>"
            "<span class='title1'>b</span><span class='h-full'>c</span>"
            "<span class='iPhone'>d</span></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert set(record.fields) == {
        "span.col-md-6",
        "span.title1",
        "span.h-full",
        "span.iPhone",
    }


def test_a_wrapper_around_several_children_repeats_none_of_them():
    """A news site's card list: a ``ul`` whose text is its items' run together.

    ``text_content`` joins children with no space, so the wrapper's "AB" never
    equalled its children's "A B" and the wrapper kept a value that was only
    theirs.
    """
    group = rows(
        "<ul>"
        + (
            "<li class='row'><div class='tags'><a href='/a'>alpha</a>"
            "<a href='/b'>beta</a></div></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert "div.tags" not in record.fields, record.fields
    assert {field.value for field in record.fields.values()} == {
        "alpha",
        "/a",
        "beta",
        "/b",
    }


def test_a_separator_between_children_is_not_text_of_the_wrapper_s_own():
    group = rows(
        "<ul>"
        + (
            "<li class='row'><span class='meta'><a href='/u'>user</a> | "
            "<a href='/c'>3 comments</a> · </span></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert "span.meta" not in record.fields, record.fields


def test_a_row_nested_a_thousand_deep_is_walked_not_a_recursion_error():
    """Found by the property that ``extract`` never raises.

    libxml2 nests elements up to 2,047 deep, and the walk over a row's parts
    recursed once per level: a row 1,000 deep was a ``RecursionError`` out of
    ``extract(html, induce=True)``.
    """
    from sluicer.document import load
    from sluicer.structure.records import _parts

    depth = 1000
    # Parsed by load, whose parser keeps what lxml's default drops past 256.
    row = load("<ul><li>" + "<b>x" * depth + "</li></ul>").tree.xpath("//li")[0]

    parts = list(_parts(row, ()))

    assert len(parts) == depth
    assert [len(path) for _, path in parts] == list(range(1, depth + 1))


def _listing_of(html):
    """The rows of the first list in ``html``, parsed the way sluicer parses."""
    from sluicer.document import load

    # load's parser keeps what lxml's default drops past 256 levels.
    return list(load(html).tree.xpath("//ul")[0])


_SHAPES_THAT_MULTIPLY = {
    "rows six hundred deep, with text at every level": (
        "<ul>" + ("<li>" + "<b>x" * 600 + "</li>") * 3 + "</ul>"
    ),
    "a long class over three hundred parts": (
        "<ul>"
        + (f'<li><div class="{"c" * 4000}">' + "<i>y</i>" * 300 + "</div></li>") * 3
        + "</ul>"
    ),
}


@pytest.mark.parametrize(
    "html", _SHAPES_THAT_MULTIPLY.values(), ids=_SHAPES_THAT_MULTIPLY
)
def test_what_induced_records_hold_is_bounded_by_their_rows(html):
    """Found by the property that what a page yields is bounded by its size.

    A field is named by the path down to it and a part with text of its own
    holds all the text below it: the first made 1.6 MB from a 7 KB page, the
    second 3.6 MB from 19 KB, and both grow with the square of the page.
    """
    import json

    records = records_from(_listing_of(html))

    assert records
    held = [{name: f.value for name, f in r.fields.items()} for r in records]
    assert len(json.dumps(held)) <= 11 * len(html)


def test_a_row_a_thousand_deep_is_named_in_a_moment():
    """Each part's name was spelt from its whole path, level by level, and a
    check at each level copied the path again: three rows a thousand deep took
    2.5 seconds, and the cost grew with the cube of the depth."""
    import time

    rows = _listing_of("<ul>" + ("<li>" + "<b>x" * 1000 + "</li>") * 3 + "</ul>")

    started = time.perf_counter()
    records_from(rows)

    assert time.perf_counter() - started < 0.5
