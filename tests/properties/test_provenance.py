"""Every answer says where it came from, and what it says is true.

The summary's promise is that each answer "can be checked against the records
it was chosen from": its ``source`` is the reader that declared it and its
``key`` is what was read. That is only worth something if it holds on every
page, so it is checked here the way a caller would check it -- against the
records, and against the page's own tags -- on every page drawn.

The tags are looked up with XPath over the parsed page, not through sluicer's
readers, so a reader that lost a tag cannot also vouch for it.
"""

from __future__ import annotations

from hypothesis import given, strategies as st
from strategies import broken_pages, multiplying_pages, pages

from sluicer import extract
from sluicer.declared.merge import ABOUT_A_THING
from sluicer.document import load
from sluicer.summary import FIELDS

READERS = (
    "jsonld",
    "microdata",
    "microformats",
    "rdfa",
    "dublincore",
    "opengraph",
    "twitter",
    "html",
    "induced",
)


def _metas(tree, attribute: str) -> set[str]:
    """Each ``<meta>``'s ``attribute``, trimmed and lowercased, if it has content."""
    return {
        (meta.get(attribute) or "").strip().lower()
        for meta in tree.xpath(f"//meta[@{attribute}]")
        if (meta.get("content") or "").strip()
    }


def _declared_on_the_page(tree, source: str, key: str) -> bool:
    """Whether the page carries a tag that ``source`` reads as ``key``."""
    names = _metas(tree, "name")
    if source in ("opengraph", "twitter"):
        return key in names | _metas(tree, "property")
    if source == "dublincore":
        _, _, rest = key.partition(".")
        return f"dc.{rest}" in names or f"dcterms.{rest}" in names
    if source != "html":
        return False
    if key == "<title>":
        return bool(tree.xpath("//title"))
    if key == "<html lang>":
        return bool(tree.xpath("//html[@lang]"))
    if key == "<link rel=canonical>":
        return any(
            "canonical" in (link.get("rel") or "").lower().split()
            for link in tree.xpath("//link[@rel][@href]")
        )
    if key.startswith("meta name="):
        return key.removeprefix("meta name=") in names
    if key.startswith("<meta itemprop="):
        prop = key.removeprefix("<meta itemprop=").removesuffix(">")
        return any(
            prop in (meta.get("itemprop") or "").split()
            for meta in tree.xpath("//meta[@itemprop][not(ancestor::*[@itemscope])]")
        )
    return False


def _declared_by_a_record(records, answer) -> bool:
    """Whether a record the answer names holds what the answer says it read."""
    if answer.key == "@type":
        return any(
            record.type == answer.value and record.source == answer.source
            for record in records
        )
    type_, _, prop = answer.key.rpartition(".")
    return any(
        record.type == type_
        and prop in record.fields
        and record.fields[prop].source == answer.source
        for record in records
    )


def _check(html: str | bytes, url: str | None) -> None:
    result = extract(html, url=url, induce=True)
    tree = load(html, url=url).tree

    assert set(result.sources) <= set(READERS)
    assert result.sources == sorted(result.sources, key=READERS.index)
    for record in result.records:
        assert record.fields, "a record with no field is never reported"
        assert record.source is None or record.source in result.sources
        for field in record.fields.values():
            assert field.source in result.sources, (field, result.sources)

    assert list(result.summary) == [name for name in FIELDS if name in result.summary]
    for question, answer in result.summary.items():
        assert answer.value, (question, answer)
        assert answer.value == answer.value.strip(), (question, answer)
        # "html" also names what no reader reads -- <title>, <html lang> --
        # and those are checked against the page alone.
        if answer.source != "html":
            assert answer.source in result.sources, (question, answer)
        if answer.source in ABOUT_A_THING:
            assert _declared_by_a_record(result.records, answer), (question, answer)
        else:
            assert _declared_on_the_page(tree, answer.source, answer.key), (
                question,
                answer,
            )


@given(pages())
def test_every_answer_names_a_reader_and_a_key_the_page_has(page):
    _check(page.html(), page.url)


@given(st.one_of(broken_pages(), multiplying_pages().map(lambda p: (p.html(), p.url))))
def test_so_does_every_answer_on_a_broken_or_hostile_page(page):
    html, url = page
    _check(html, url)
