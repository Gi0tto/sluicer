"""The microformats reader, with mf2py faked so no test needs it installed.

Every parse tree below was copied out of a real ``mf2py`` 2.0.2 run on
2026-09-22 rather than invented, because the shapes are the whole point: a
property's value is always a list, a nested item is a dict, and what that
dict's ``value`` holds depends on the prefix of the class that nested it.
"""

import sys
import types
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"

# The fixture page, as mf2py parses it. `u-author h-card` puts the address in
# `value`; `p-category h-card` puts the name there and the address in the
# `url` property. One page, both prefixes.
ENTRY = {
    "type": ["h-entry"],
    "properties": {
        "name": ["Looking forward to Git 2.56"],
        "author": [
            {
                "type": ["h-card"],
                "properties": {"name": ["dimonomid"], "url": ["/~dimonomid"]},
                "value": "/~dimonomid",
            }
        ],
        "published": ["2026-09-22"],
        "url": ["/s/git-2-56"],
        "content": [
            {
                "value": "What lands in the next release.",
                "html": "<p>What lands in the <em>next</em> release.</p>",
            }
        ],
        "category": [
            {
                "type": ["h-card"],
                "properties": {"url": ["/~kellan"], "name": ["kellan"]},
                "value": "kellan",
            }
        ],
    },
}


def fake_mf2py(monkeypatch, items=(ENTRY,)):
    """Stand in for mf2py so no test needs it installed."""
    seen = {}

    def parse(**kwargs):
        seen["called_with"] = kwargs
        return {"items": list(items), "rels": {}, "rel-urls": {}}

    module = types.ModuleType("mf2py")
    module.parse = parse
    monkeypatch.setitem(sys.modules, "mf2py", module)
    return seen


def _absent_mf2py(monkeypatch, raising=None):
    """Make ``import mf2py`` fail, either as absent or as a broken install."""

    class Finder:
        def find_spec(self, name, path=None, target=None):
            if name == "mf2py" or name.startswith("mf2py."):
                missing = raising or "mf2py"
                raise ModuleNotFoundError(f"No module named {missing!r}", name=missing)

    monkeypatch.delitem(sys.modules, "mf2py", raising=False)
    monkeypatch.setattr(sys, "meta_path", [Finder(), *sys.meta_path])


def _read(html="<html><body></body></html>", url=None):
    from sluicer.declared.microformats import read_microformats
    from sluicer.document import load

    return read_microformats(load(html, url=url))


def test_a_top_level_item_becomes_one_record(monkeypatch):
    fake_mf2py(monkeypatch)

    found = _read((FIXTURES / "entry_microformats.html").read_text(encoding="utf-8"))

    assert len(found) == 1
    assert found[0]["@type"] == "h-entry"
    assert found[0]["name"] == "Looking forward to Git 2.56"
    assert found[0]["published"] == "2026-09-22"
    assert found[0]["url"] == "/s/git-2-56"


def test_a_nested_item_gives_its_name_the_slot_and_its_address_the_url_slot(
    monkeypatch,
):
    """The author is a name *and* a link, and both are kept.

    Dropping the nested item loses the author entirely; reporting its ``value``
    under the slot's own name reports a URL where a name belongs.
    """
    fake_mf2py(monkeypatch)

    found = _read()

    assert found[0]["author"] == "dimonomid"
    assert found[0]["author@url"] == "/~dimonomid"


def test_the_address_is_the_url_property_and_not_the_nested_value(monkeypatch):
    """Measured: for a ``p-`` prefixed nested item the value is the *name*.

    ``p-category h-card`` yields ``value == "kellan"`` while the address sits in
    ``properties["url"]``. Taking the value would put a name in an address slot
    and throw the address away, which is the same defect as dropping the item.
    """
    fake_mf2py(monkeypatch)

    found = _read()

    assert found[0]["category"] == "kellan"
    assert found[0]["category@url"] == "/~kellan"


def test_a_nested_item_with_only_an_address_gives_only_the_url_slot(monkeypatch):
    """An h-card built from a bare link: mf2py reports its name as ``""``."""
    fake_mf2py(
        monkeypatch,
        items=[
            {
                "type": ["h-entry"],
                "properties": {
                    "author": [
                        {
                            "type": ["h-card"],
                            "properties": {"url": ["/~c"], "name": [""]},
                            "value": "",
                        }
                    ]
                },
            }
        ],
    )

    found = _read()

    assert found[0]["author@url"] == "/~c"
    assert "author" not in found[0]


def test_a_nested_item_with_neither_a_name_nor_an_address_is_skipped(monkeypatch):
    """An h-geo carries a latitude and nothing this flat shape can name."""
    fake_mf2py(
        monkeypatch,
        items=[
            {
                "type": ["h-entry"],
                "properties": {
                    "location": [
                        {
                            "type": ["h-geo"],
                            "properties": {"latitude": ["37.3"]},
                            "value": "37.3",
                        }
                    ]
                },
            }
        ],
    )

    found = _read()

    assert found[0] == {"@type": "h-entry"}


def test_parsed_markup_keeps_its_text(monkeypatch):
    """``e-content`` is a dict with no ``type``: its value is text, not an address."""
    fake_mf2py(monkeypatch)

    found = _read()

    assert found[0]["content"] == "What lands in the next release."
    assert "content@url" not in found[0]


def test_parsed_markup_with_no_text_declares_nothing(monkeypatch):
    """An empty ``e-content`` is an empty value, and an empty value is not one."""
    fake_mf2py(
        monkeypatch,
        items=[
            {
                "type": ["h-entry"],
                "properties": {"content": [{"value": "", "html": "<p></p>"}]},
            }
        ],
    )

    assert _read() == [{"@type": "h-entry"}]


def test_a_repeated_property_keeps_the_first_of_its_list(monkeypatch):
    fake_mf2py(
        monkeypatch,
        items=[{"type": ["h-entry"], "properties": {"category": ["one", "two"]}}],
    )

    found = _read()

    assert found[0]["category"] == "one"


def test_an_empty_value_is_not_a_value(monkeypatch):
    fake_mf2py(
        monkeypatch,
        items=[{"type": ["h-card"], "properties": {"name": [""], "note": ["  "]}}],
    )

    found = _read()

    assert found == [{"@type": "h-card"}]


def test_an_item_that_declares_nothing_at_all_is_dropped(monkeypatch):
    fake_mf2py(monkeypatch, items=[{}, {"type": [], "properties": {}}])

    assert _read() == []


def test_a_page_with_no_microformats_reads_as_nothing(monkeypatch):
    fake_mf2py(monkeypatch, items=[])

    assert _read() == []


def test_a_property_that_is_not_a_list_is_left_alone(monkeypatch):
    """mf2py always returns lists; a reader that assumed it must not crash if not."""
    fake_mf2py(
        monkeypatch,
        items=[{"type": ["h-card"], "properties": {"name": "Alice", "note": []}}],
    )

    assert _read() == [{"@type": "h-card"}]


def test_the_page_and_its_url_reach_mf2py_with_metaformats_off(monkeypatch):
    """All three arguments, not just the page.

    ``url`` is what lets mf2py resolve a relative link into one that can be
    followed. ``metaformats`` is off on purpose: switched on, mf2py reports
    OpenGraph and Twitter card tags as microformats, and this package has
    readers of its own for both, each naming the vocabulary it really came
    from.
    """
    seen = fake_mf2py(monkeypatch)

    _read("<html><body>hi</body></html>", url="https://example.com/p")

    assert seen["called_with"]["doc"] == "<html><body>hi</body></html>"
    assert seen["called_with"]["url"] == "https://example.com/p"
    assert seen["called_with"]["metaformats"] is False


def test_bytes_reach_mf2py_undecoded(monkeypatch):
    seen = fake_mf2py(monkeypatch)

    _read(b"<html><body>hi</body></html>")

    assert isinstance(seen["called_with"]["doc"], bytes)


def test_a_missing_extra_says_how_to_install_it(monkeypatch):
    import sluicer.declared.microformats as microformats_module

    _absent_mf2py(monkeypatch)

    with pytest.raises(microformats_module.MicroformatsExtraMissing) as raised:
        _read()

    assert "sluicer[microformats]" in str(raised.value)
    assert raised.value.extra == "microformats"


def test_a_broken_install_keeps_its_traceback(monkeypatch):
    """mf2py is there and its own dependency is not: that is a bug, not an extra."""
    import sluicer.declared.microformats as microformats_module

    _absent_mf2py(monkeypatch, raising="bs4")

    with pytest.raises(ModuleNotFoundError) as raised:
        _read()

    assert not isinstance(raised.value, microformats_module.MicroformatsExtraMissing)
    assert "sluicer[microformats]" not in str(raised.value)


# extract(), which is where the reader is wired in.


def test_extract_reads_microformats_only_when_asked(monkeypatch):
    import sluicer

    fake_mf2py(monkeypatch)
    html = (FIXTURES / "entry_microformats.html").read_text(encoding="utf-8")

    assert sluicer.extract(html).sources == []
    assert sluicer.extract(html, microformats=True).sources == ["microformats"]


def test_extract_leaves_mf2py_alone_when_it_was_not_asked(monkeypatch):
    """Off by default means never imported, not imported and ignored."""
    import sluicer

    _absent_mf2py(monkeypatch)

    assert sluicer.extract("<html><body><p>hi</p></body></html>").records == []


def test_a_microformats_field_says_where_it_came_from(monkeypatch):
    import sluicer

    fake_mf2py(monkeypatch)

    result = sluicer.extract(
        (FIXTURES / "entry_microformats.html").read_text(encoding="utf-8"),
        microformats=True,
    )

    assert result.records[0].type == "h-entry"
    assert result.records[0].fields["author"].value == "dimonomid"
    assert result.records[0].fields["author"].source == "microformats"
    assert result.records[0].fields["author@url"].value == "/~dimonomid"


def test_microformats_fills_a_gap_microdata_left_and_never_overwrites_it(monkeypatch):
    """Precedence: after microdata, before RDFa."""
    import sluicer

    fake_mf2py(
        monkeypatch,
        items=[
            {
                "type": ["Product"],
                "properties": {"name": ["From microformats"], "sku": ["MF-1"]},
            }
        ],
    )
    html = (
        '<html><body><div itemscope itemtype="https://schema.org/Product">'
        '<span itemprop="name">From microdata</span></div>'
        '<div vocab="https://schema.org/" typeof="Product">'
        '<span property="sku">From RDFa</span>'
        '<span property="colour">From RDFa</span></div></body></html>'
    )

    result = sluicer.extract(html, microformats=True)

    assert result.sources == ["microdata", "microformats", "rdfa"]
    fields = result.records[0].fields
    assert fields["name"].source == "microdata"
    assert fields["sku"].value == "MF-1"
    assert fields["sku"].source == "microformats"
    assert fields["colour"].source == "rdfa"


def test_a_page_declaring_only_microformats_is_not_induced_over(monkeypatch):
    """Microformats describes a thing, so it closes the induction gate."""
    import sluicer
    from sluicer.api import _declared_about_its_things

    fake_mf2py(monkeypatch)
    html = (FIXTURES / "entry_microformats.html").read_text(encoding="utf-8")

    result = sluicer.extract(html, induce=True, microformats=True)

    assert _declared_about_its_things(result.records)
    assert "induced" not in result.sources


def test_the_exception_is_exported_from_the_package_root():
    """A caller who turns the flag on has to be able to catch it by name."""
    import sluicer
    from sluicer.declared.microformats import MicroformatsExtraMissing

    assert sluicer.MicroformatsExtraMissing is MicroformatsExtraMissing
    assert "MicroformatsExtraMissing" in sluicer.__all__


def test_a_page_mf2py_refuses_to_read_declares_no_microformats(monkeypatch):
    """Found by the property that ``extract`` never raises.

    mf2py 2.0.2 raised ``ValueError`` out of ``extract(html,
    microformats=True)`` for any page whose ``<base href>`` has a bracketed
    host that is not IPv6 -- ``https://[domain]/``, as an unfilled template
    writes -- microformats or none, before reading anything.
    """
    from sluicer import extract

    def refuse(**kwargs):
        raise ValueError("'domain' does not appear to be an IPv4 or IPv6 address")

    module = types.ModuleType("mf2py")
    module.parse = refuse
    monkeypatch.setitem(sys.modules, "mf2py", module)

    result = extract('<base href="https://[domain]/p"><p>x</p>', microformats=True)

    assert "microformats" not in result.sources


@pytest.mark.parametrize("base", ["https://[domain]/p", "http://[::1"])
def test_the_real_mf2py_is_asked_and_the_page_still_reads(base):
    """The same page against mf2py itself, wherever the extra is installed."""
    pytest.importorskip("mf2py")
    from sluicer import extract

    html = (
        f'<html><head><base href="{base}"><title>T</title></head>'
        '<body><p class="h-card"><a class="p-name u-url" href="/me">Jane</a></p>'
        "</body></html>"
    )

    assert extract(html, microformats=True).summary["title"].value == "T"
