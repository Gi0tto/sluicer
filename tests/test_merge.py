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
