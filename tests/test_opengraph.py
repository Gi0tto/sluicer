import pytest

from sluicer.declared.opengraph import read_opengraph
from sluicer.document import load


def test_reads_the_og_tags_and_nothing_else():
    """``card`` used to come back from here, and that was the defect.

    One reader returned both vocabularies and labelled every value
    ``source="opengraph"``, so a field the Twitter card declared reported a
    reader that had not won it. The assertion below is the corrected one:
    ``twitter:card`` belongs to ``read_twitter``.
    """
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="Brake pad set">'
        '<meta property="og:type" content="product">'
        '<meta name="twitter:card" content="summary">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {
        "title": "Brake pad set",
        "type": "product",
    }


def test_a_page_declaring_nothing_returns_an_empty_mapping():
    assert read_opengraph(load("<html><body>hi</body></html>")) == {}


def test_a_page_carrying_only_a_twitter_card_returns_an_empty_mapping():
    doc = load(
        '<html><head><meta name="twitter:title" content="Brake pad set">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {}


def test_an_empty_content_is_not_a_value():
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="  ">'
        '<meta property="og:description" content="">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {}


def test_the_first_declaration_of_a_key_wins():
    doc = load(
        "<html><head>"
        '<meta property="og:title" content="First">'
        '<meta property="og:title" content="Second">'
        "</head><body></body></html>"
    )

    assert read_opengraph(doc) == {"title": "First"}


def test_the_protocol_s_vertical_namespaces_are_opengraph_too():
    """article:published_time is how a third of real pages state a date."""
    doc = load(
        "<html><head>"
        '<meta property="og:type" content="article">'
        '<meta property="article:published_time" content="2018-07-10T09:00:00Z">'
        '<meta property="article:author" content="Ines Varga">'
        '<meta property="article:section" content="Laptops">'
        "</head></html>"
    )

    got = read_opengraph(doc)

    assert got["type"] == "article"
    assert got["article:published_time"] == "2018-07-10T09:00:00Z"
    assert got["article:author"] == "Ines Varga"
    assert got["article:section"] == "Laptops"


def test_a_vertical_that_is_not_the_protocol_s_is_left_alone():
    """Only the namespaces the OpenGraph protocol defines; not every colon."""
    doc = load('<html><head><meta property="fb:app_id" content="1234"></head></html>')

    assert read_opengraph(doc) == {}


def test_a_tag_written_in_capitals_or_with_padding_is_still_read():
    doc = load(
        '<meta property="OG:Title" content="Shouted">'
        '<meta property=" og:description " content="Padded">'
    )

    found = read_opengraph(doc)

    assert found["title"] == "Shouted"
    assert found["description"] == "Padded"


def test_a_name_attribute_is_read_when_property_holds_something_else():
    doc = load('<meta property="description" name="og:title" content="From name">')

    assert read_opengraph(doc)["title"] == "From name"


@pytest.mark.parametrize("between", [" ", "  ", "\n\t"])
def test_a_property_naming_two_terms_is_read_by_the_one_opengraph_owns(between):
    """Found by the property that the spacing between the tokens of a token list
    does not change the answer.

    RDFa, which OpenGraph is written in, makes ``property`` a list of terms:
    ``<meta property="og:title name">`` is ``og:title`` and ``name``. The tag
    was read as one name, a field called "title name", spelt with whatever
    whitespace the page put between the two terms.
    """
    doc = load(f'<meta property="og:title{between}name" content="Pad">')

    assert read_opengraph(doc) == {"title": "Pad"}


# -- arrays and structured properties, as ogp.me reads them --------------------


def _og(*tags: tuple[str, str]):
    from sluicer.declared.opengraph import read_opengraph_declared

    doc = load(
        "<html><head>"
        + "".join(f'<meta property="{k}" content="{v}">' for k, v in tags)
        + "</head></html>"
    )
    return read_opengraph_declared(doc), read_opengraph(doc)


def test_ogp_me_s_own_example_of_three_images_reads_as_it_says():
    """ "There are 3 images on this page, the first image is 300x300, the
    middle one has unspecified dimensions, and the last one is 1000px tall."
    openGraphScraper pairs these by index and gets the last two wrong."""
    declared, flat = _og(
        ("og:image", "https://example.com/rock.jpg"),
        ("og:image:width", "300"),
        ("og:image:height", "300"),
        ("og:image", "https://example.com/rock2.jpg"),
        ("og:image", "https://example.com/rock3.jpg"),
        ("og:image:height", "1000"),
    )
    assert declared == {
        "image": [
            {"url": "https://example.com/rock.jpg", "width": "300", "height": "300"},
            {"url": "https://example.com/rock2.jpg"},
            {"url": "https://example.com/rock3.jpg", "height": "1000"},
        ]
    }
    assert flat == {
        "image": "https://example.com/rock.jpg",
        "image:width": "300",
        "image:height": "300",
    }


def test_a_later_images_size_is_never_the_first_ones():
    """The flat reading gave the second image's height to the first."""
    _declared, flat = _og(
        ("og:image", "https://example.com/a.jpg"),
        ("og:image", "https://example.com/b.jpg"),
        ("og:image:height", "1000"),
    )
    assert flat == {"image": "https://example.com/a.jpg"}


def test_one_image_with_its_size_reads_as_it_always_did():
    declared, flat = _og(
        ("og:image", "https://example.com/a.jpg"),
        ("og:image:width", "1200"),
        ("og:image:alt", "A pad"),
    )
    assert (
        declared
        == flat
        == {
            "image": "https://example.com/a.jpg",
            "image:width": "1200",
            "image:alt": "A pad",
        }
    )


def test_a_structured_property_before_any_image_is_the_first_images():
    """As two cached pages write it: alt and type ahead of the image."""
    declared, flat = _og(
        ("og:image:type", "image/jpeg"),
        ("og:image:alt", "A pad"),
        ("og:image", "https://example.com/a.jpg"),
        ("og:image:width", "600"),
        ("og:image", "https://example.com/b.jpg"),
        ("og:image:width", "300"),
    )
    assert declared["image"] == [
        {
            "url": "https://example.com/a.jpg",
            "type": "image/jpeg",
            "alt": "A pad",
            "width": "600",
        },
        {"url": "https://example.com/b.jpg", "width": "300"},
    ]
    assert flat["image:alt"] == "A pad"


def test_sizes_of_an_image_the_page_never_names_are_kept_as_written():
    declared, flat = _og(("og:image:width", "1200"), ("og:image:height", "630"))
    assert declared == flat == {"image:width": "1200", "image:height": "630"}


def test_an_image_named_only_by_its_url_property_is_called_that():
    """Found by the provenance property: the answer must name a tag the page
    wrote, and this page wrote og:image:url, not og:image."""
    declared, flat = _og(("og:image:url", "https://example.com/a.jpg"))
    assert declared == flat == {"image:url": "https://example.com/a.jpg"}


def test_og_image_url_after_og_image_restates_it():
    declared, flat = _og(
        ("og:image", "https://example.com/a.jpg"),
        ("og:image:url", "https://example.com/a.jpg"),
        ("og:image:secure_url", "https://example.com/a.jpg"),
    )
    assert (
        declared
        == flat
        == {
            "image": "https://example.com/a.jpg",
            "image:url": "https://example.com/a.jpg",
            "image:secure_url": "https://example.com/a.jpg",
        }
    )


def test_url_property_then_the_root_naming_the_same_address_is_one_image():
    declared, _flat = _og(
        ("og:image:url", "https://example.com/a.jpg"),
        ("og:image", "https://example.com/a.jpg"),
        ("og:image:width", "10"),
    )
    assert declared == {
        "image:url": "https://example.com/a.jpg",
        "image": "https://example.com/a.jpg",
        "image:width": "10",
    }


def test_the_same_image_twice_in_a_row_is_one_image():
    declared, _flat = _og(
        ("og:image", "https://example.com/a.jpg"),
        ("og:image:width", "10"),
        ("og:image", "https://example.com/a.jpg"),
        ("og:image:height", "20"),
    )
    assert declared == {
        "image": "https://example.com/a.jpg",
        "image:width": "10",
        "image:height": "20",
    }


def test_an_array_property_is_a_list_in_order_and_each_value_once():
    declared, flat = _og(
        ("article:tag", "brakes"),
        ("article:tag", "pads"),
        ("article:tag", "brakes"),
        ("og:locale", "en_GB"),
        ("og:locale:alternate", "de_DE"),
        ("og:locale:alternate", "fr_FR"),
    )
    assert declared == {
        "locale": "en_GB",
        "locale:alternate": ["de_DE", "fr_FR"],
        "article:tag": ["brakes", "pads"],
    }
    assert flat["article:tag"] == "brakes"


def test_a_single_valued_property_declared_twice_keeps_its_first():
    """As ogp.me says: the first tag is given preference during conflicts."""
    declared, flat = _og(("og:title", "First"), ("og:title", "Second"))
    assert declared == flat == {"title": "First"}


def test_a_verticals_structured_array_keeps_each_ones_parts():
    declared, _flat = _og(
        ("video:actor", "https://example.com/a"),
        ("video:actor:role", "Hero"),
        ("video:actor", "https://example.com/b"),
        ("music:song", "https://example.com/s1"),
        ("music:song:track", "1"),
    )
    assert declared == {
        "video:actor": [
            {"url": "https://example.com/a", "role": "Hero"},
            {"url": "https://example.com/b"},
        ],
        "music:song": "https://example.com/s1",
        "music:song:track": "1",
    }


def test_a_hostile_page_of_images_is_bounded():
    declared, _flat = _og(
        *[("og:image", f"https://example.com/{i}.jpg") for i in range(500)]
    )
    assert len(declared["image"]) == 100


def test_an_extraction_carries_the_arrays_and_answers_with_the_first():
    import sluicer

    result = sluicer.extract(
        "<html><head>"
        '<meta property="og:image" content="https://example.com/a.jpg">'
        '<meta property="og:image" content="https://example.com/b.jpg">'
        '<meta property="og:image:width" content="300">'
        '<meta property="article:tag" content="brakes">'
        '<meta property="article:tag" content="pads">'
        "</head></html>"
    )
    [record] = result.records
    assert record.fields["image"].value == [
        {"url": "https://example.com/a.jpg"},
        {"url": "https://example.com/b.jpg", "width": "300"},
    ]
    assert record.fields["article:tag"].value == ["brakes", "pads"]
    assert result.summary["image"].value == "https://example.com/a.jpg"
