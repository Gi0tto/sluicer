from sluicer.declared.merge import merge


def test_jsonld_wins_and_provenance_is_kept():
    records = merge(
        jsonld=[{"@type": "Product", "name": "From JSON-LD"}],
        microdata=[{"@type": "Product", "name": "From microdata", "sku": "X1"}],
        opengraph={"title": "From OpenGraph"},
    )

    assert len(records) == 1
    assert records[0].type == "Product"
    assert records[0].fields["name"].value == "From JSON-LD"
    assert records[0].fields["name"].source == "jsonld"
    assert records[0].fields["sku"].source == "microdata"


def test_opengraph_alone_still_produces_one_record():
    records = merge(jsonld=[], microdata=[], opengraph={"title": "Only OG"})

    assert records[0].fields["title"].source == "opengraph"
    assert records[0].type is None


def test_nothing_declared_gives_no_records():
    assert merge(jsonld=[], microdata=[], opengraph={}) == []


def test_two_jsonld_objects_of_one_type_stay_two_records():
    records = merge(
        jsonld=[{"@type": "Product", "name": "First"}, {"@type": "Product", "sku": "X9"}],
        microdata=[],
        opengraph={},
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
        jsonld=[{"@type": "Product", "name": "First"}, {"@type": "Product", "sku": "X9"}],
        microdata=[{"@type": "Product", "colour": "red"}],
        opengraph={},
    )

    assert len(records) == 2
    assert "colour" in records[0].fields
    assert "colour" not in records[1].fields


def test_opengraph_fills_only_the_first_record():
    records = merge(
        jsonld=[{"@type": "Product", "name": "First"}, {"@type": "Product", "sku": "X9"}],
        microdata=[],
        opengraph={"title": "Page title"},
    )

    assert len(records) == 2
    assert "title" in records[0].fields
    assert "title" not in records[1].fields


def test_a_list_valued_type_keeps_every_type_and_names_the_first():
    records = merge(
        jsonld=[{"@type": ["Person", "Organization"], "name": "Yoast style"}],
        microdata=[],
        opengraph={},
    )

    assert len(records) == 1
    assert records[0].type == "Person"
    assert records[0].types == ("Person", "Organization")


def test_records_fold_when_they_share_any_type():
    records = merge(
        jsonld=[{"@type": ["Product", "Thing"], "name": "From JSON-LD"}],
        microdata=[{"@type": "Thing", "sku": "X1"}],
        opengraph={},
    )

    assert len(records) == 1
    assert records[0].fields["name"].source == "jsonld"
    assert records[0].fields["sku"].source == "microdata"


def test_records_sharing_no_type_stay_apart():
    records = merge(
        jsonld=[{"@type": ["Product", "Thing"], "name": "From JSON-LD"}],
        microdata=[{"@type": "Offer", "price": "41.99"}],
        opengraph={},
    )

    assert len(records) == 2
    assert "price" not in records[0].fields


def test_untyped_records_never_fold_into_each_other():
    records = merge(
        jsonld=[{"name": "An untyped JSON-LD entry"}],
        microdata=[{"sku": "An unrelated untyped scope"}],
        opengraph={},
    )

    assert len(records) == 2
    assert records[0].fields["name"].source == "jsonld"
    assert "sku" not in records[0].fields
    assert records[1].fields["sku"].source == "microdata"


def test_a_json_null_is_an_absence_not_the_text_none():
    records = merge(
        jsonld=[{"@type": "Product", "name": "Brake pad set", "gtin": None}],
        microdata=[],
        opengraph={},
    )

    assert "gtin" not in records[0].fields


def test_a_null_does_not_shadow_a_real_value_from_a_later_reader():
    records = merge(
        jsonld=[{"@type": "Product", "gtin": None}],
        microdata=[{"@type": "Product", "gtin": "4001234567890"}],
        opengraph={},
    )

    assert records[0].fields["gtin"].value == "4001234567890"
    assert records[0].fields["gtin"].source == "microdata"


def test_a_boolean_is_recorded_the_way_the_page_declared_it():
    records = merge(
        jsonld=[{"@type": "Product", "isAccessibleForFree": True, "isFamilyFriendly": False}],
        microdata=[],
        opengraph={},
    )

    assert records[0].fields["isAccessibleForFree"].value == "true"
    assert records[0].fields["isFamilyFriendly"].value == "false"


def test_an_empty_value_does_not_shadow_a_real_one_from_a_later_reader():
    records = merge(
        jsonld=[{"@type": "Product", "name": "", "sku": "   "}],
        microdata=[{"@type": "Product", "name": "Brake pad set", "sku": "ATD-1187"}],
        opengraph={},
    )

    assert len(records) == 1
    assert records[0].fields["name"].value == "Brake pad set"
    assert records[0].fields["name"].source == "microdata"
    assert records[0].fields["sku"].value == "ATD-1187"
    assert records[0].fields["sku"].source == "microdata"
