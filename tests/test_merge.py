from sluicer.declared.merge import Field, merge


def test_jsonld_wins_and_provenance_is_kept():
    records = merge(
        jsonld=[{"@type": "Product", "name": "From JSON-LD"}],
        microdata=[{"@type": "Product", "name": "From microdata", "sku": "X1"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={"title": "From OpenGraph"},
        twitter={},
    )

    assert len(records) == 1
    assert records[0].type == "Product"
    assert records[0].fields["name"].value == "From JSON-LD"
    assert records[0].fields["name"].source == "jsonld"
    assert records[0].fields["sku"].source == "microdata"


def test_opengraph_alone_still_produces_one_record():
    records = merge(
        jsonld=[],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={"title": "Only OG"},
        twitter={},
    )

    assert records[0].fields["title"].source == "opengraph"
    assert records[0].type is None


def test_nothing_declared_gives_no_records():
    assert (
        merge(
            jsonld=[],
            microdata=[],
            microformats=[],
        rdfa=[],
            dublincore={},
            opengraph={},
            twitter={},
        )
        == []
    )


def test_two_jsonld_objects_of_one_type_stay_two_records():
    records = merge(
        jsonld=[
            {"@type": "Product", "name": "First"},
            {"@type": "Product", "sku": "X9"},
        ],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 2
    assert records[0].type == "Product"
    assert "name" in records[0].fields
    assert "sku" not in records[0].fields
    assert records[1].type == "Product"
    assert "sku" in records[1].fields
    assert "name" not in records[1].fields


def test_microdata_folds_into_the_first_record_of_its_type():
    records = merge(
        jsonld=[
            {"@type": "Product", "name": "First"},
            {"@type": "Product", "sku": "X9"},
        ],
        microdata=[{"@type": "Product", "colour": "red"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 2
    assert "colour" in records[0].fields
    assert "colour" not in records[1].fields


def test_opengraph_fills_only_the_first_record():
    records = merge(
        jsonld=[
            {"@type": "Product", "name": "First"},
            {"@type": "Product", "sku": "X9"},
        ],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={"title": "Page title"},
        twitter={},
    )

    assert len(records) == 2
    assert "title" in records[0].fields
    assert "title" not in records[1].fields


def test_a_list_valued_type_keeps_every_type_and_names_the_first():
    records = merge(
        jsonld=[{"@type": ["Person", "Organization"], "name": "Yoast style"}],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 1
    assert records[0].type == "Person"
    assert records[0].types == ("Person", "Organization")


def test_records_fold_when_they_share_any_type():
    records = merge(
        jsonld=[{"@type": ["Product", "Thing"], "name": "From JSON-LD"}],
        microdata=[{"@type": "Thing", "sku": "X1"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 1
    assert records[0].fields["name"].source == "jsonld"
    assert records[0].fields["sku"].source == "microdata"


def test_records_sharing_no_type_stay_apart():
    records = merge(
        jsonld=[{"@type": ["Product", "Thing"], "name": "From JSON-LD"}],
        microdata=[{"@type": "Offer", "price": "41.99"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 2
    assert "price" not in records[0].fields


def test_untyped_records_never_fold_into_each_other():
    records = merge(
        jsonld=[{"name": "An untyped JSON-LD entry"}],
        microdata=[{"sku": "An unrelated untyped scope"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 2
    assert records[0].fields["name"].source == "jsonld"
    assert "sku" not in records[0].fields
    assert records[1].fields["sku"].source == "microdata"


def test_a_json_null_is_an_absence_not_the_text_none():
    records = merge(
        jsonld=[{"@type": "Product", "name": "Brake pad set", "gtin": None}],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert "gtin" not in records[0].fields


def test_a_null_does_not_shadow_a_real_value_from_a_later_reader():
    records = merge(
        jsonld=[{"@type": "Product", "gtin": None}],
        microdata=[{"@type": "Product", "gtin": "4001234567890"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert records[0].fields["gtin"].value == "4001234567890"
    assert records[0].fields["gtin"].source == "microdata"


def test_a_boolean_is_recorded_the_way_the_page_declared_it():
    records = merge(
        jsonld=[
            {
                "@type": "Product",
                "isAccessibleForFree": True,
                "isFamilyFriendly": False,
            }
        ],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert records[0].fields["isAccessibleForFree"].value == "true"
    assert records[0].fields["isFamilyFriendly"].value == "false"


def test_an_empty_value_does_not_shadow_a_real_one_from_a_later_reader():
    records = merge(
        jsonld=[{"@type": "Product", "name": "", "sku": "   "}],
        microdata=[{"@type": "Product", "name": "Brake pad set", "sku": "BP-1187"}],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 1
    assert records[0].fields["name"].value == "Brake pad set"
    assert records[0].fields["name"].source == "microdata"
    assert records[0].fields["sku"].value == "BP-1187"
    assert records[0].fields["sku"].source == "microdata"


def test_six_readers_disagreeing_resolve_in_the_stated_order():
    """The whole precedence, on one field each reader also declares.

    Every reader here names ``title`` or a field only it carries, so the
    record shows both halves of the rule at once: who wins a collision, and
    that a later reader still fills what the earlier ones left empty."""
    records = merge(
        jsonld=[{"@type": "Product", "name": "From JSON-LD"}],
        microdata=[{"@type": "Product", "name": "From microdata", "mpn": "GDB1330"}],
        microformats=[],
        rdfa=[{"@type": "Product", "mpn": "From RDFa", "gtin": "4001234567890"}],
        dublincore={"title": "From Dublin Core", "creator": "A cataloguer"},
        opengraph={"title": "From OpenGraph", "image": "https://example.com/i.jpg"},
        twitter={"title": "From the Twitter card", "card": "summary"},
    )

    assert len(records) == 1
    fields = records[0].fields
    assert fields["name"] == Field(value="From JSON-LD", source="jsonld")
    assert fields["mpn"] == Field(value="GDB1330", source="microdata")
    assert fields["gtin"] == Field(value="4001234567890", source="rdfa")
    assert fields["title"] == Field(value="From Dublin Core", source="dublincore")
    assert fields["creator"] == Field(value="A cataloguer", source="dublincore")
    assert fields["image"] == Field(
        value="https://example.com/i.jpg", source="opengraph"
    )
    assert fields["card"] == Field(value="summary", source="twitter")


def test_rdfa_folds_into_a_record_of_its_type_and_keeps_its_source():
    records = merge(
        jsonld=[{"@type": "Product", "name": "From JSON-LD"}],
        microdata=[],
        microformats=[],
        rdfa=[{"@type": "Product", "gtin": "4001234567890"}],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 1
    assert records[0].fields["gtin"] == Field(value="4001234567890", source="rdfa")


def test_an_rdfa_subject_of_another_type_stays_its_own_record():
    records = merge(
        jsonld=[{"@type": "Product", "name": "From JSON-LD"}],
        microdata=[],
        microformats=[],
        rdfa=[{"@type": "Offer", "price": "41.99"}],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 2
    assert "price" not in records[0].fields
    assert records[1].fields["price"].source == "rdfa"


def test_opengraph_wins_a_key_the_twitter_card_also_declares():
    records = merge(
        jsonld=[],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={"title": "From OpenGraph"},
        twitter={"title": "From the Twitter card"},
    )

    assert records[0].fields["title"] == Field(
        value="From OpenGraph", source="opengraph"
    )


def test_the_twitter_card_fills_what_opengraph_left_empty():
    records = merge(
        jsonld=[],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={"title": "From OpenGraph"},
        twitter={"card": "summary_large_image"},
    )

    assert records[0].fields["card"] == Field(
        value="summary_large_image", source="twitter"
    )


def test_a_twitter_card_alone_still_produces_one_record():
    records = merge(
        jsonld=[],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={},
        opengraph={},
        twitter={"title": "Only the card"},
    )

    assert len(records) == 1
    assert records[0].fields["title"].source == "twitter"
    assert records[0].type is None


def test_an_empty_document_level_value_does_not_shadow_a_later_reader():
    """The rule that holds for JSON-LD holds down the document chain too.

    Three readers now fill the same record in turn, so a blank ``DC.title``
    can stand between an ``og:title`` and the record it belongs in. It does
    not: an empty value is not a value, in any reader."""
    records = merge(
        jsonld=[],
        microdata=[],
        microformats=[],
        rdfa=[],
        dublincore={"title": "   "},
        opengraph={"title": "From OpenGraph"},
        twitter={},
    )

    assert records[0].fields["title"] == Field(
        value="From OpenGraph", source="opengraph"
    )


def test_microformats_sits_between_microdata_and_rdfa():
    """The fourth vocabulary that describes a thing, and it folds like the others.

    Microdata keeps the key the two share, microformats fills the one microdata
    left, and RDFa only gets what neither of them claimed."""
    records = merge(
        jsonld=[],
        microdata=[{"@type": "Product", "name": "From microdata"}],
        microformats=[{"@type": "Product", "name": "From microformats", "sku": "MF-1"}],
        rdfa=[{"@type": "Product", "sku": "RD-1", "colour": "From RDFa"}],
        dublincore={},
        opengraph={},
        twitter={},
    )

    assert len(records) == 1
    assert records[0].fields["name"] == Field(
        value="From microdata", source="microdata"
    )
    assert records[0].fields["sku"] == Field(value="MF-1", source="microformats")
    assert records[0].fields["colour"] == Field(value="From RDFa", source="rdfa")
