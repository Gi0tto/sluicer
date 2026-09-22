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
