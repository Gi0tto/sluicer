import lxml.html

from sluicer.induce.records import records_from


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
