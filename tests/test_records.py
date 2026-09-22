import lxml.html

from sluicer.structure.records import records_from


def rows(html):
    """The children of ``html``, which is what a group is."""
    return list(lxml.html.fromstring(html))


LISTING = "<ul>" + "".join(
    f"<li class='row'><a href='/p{n}'>Product name {n}</a>"
    f"<span class='price'>{n}.99</span></li>"
    for n in range(3)
) + "</ul>"


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
    return next(
        name for name, field in record.fields.items() if field.value == value
    )


def test_the_same_slot_keeps_its_name_in_every_record():
    """Members differing below the signature's depth are rows, not four shapes."""
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
    """A name that does not say which branch it came from is not a slot name."""
    group = rows(
        "<ul>"
        + (
            "<li class='row'><div class='meta'>"
            "<span class='sku'>ABC</span></div></li>"
        )
        * 3
        + "</ul>"
    )

    record = records_from(group)[0]

    assert set(record.fields) == {"div.meta", "div.meta>span.sku"}


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
