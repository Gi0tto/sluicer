"""Every answer says where it came from, and what it says is true.

The summary's promise is that each answer "can be checked against the records
it was chosen from": its ``source`` is the reader that declared it and its
``key`` is what was read. That is only worth something if it holds on every
page, so it is checked here the way a caller would check it -- against the
records, and against the page's own tags -- on every page drawn.

The tags are looked up with XPath over the parsed page, not through sluicer's
readers, so a reader that lost a tag cannot also vouch for it.

And every place a record, a field or an answer gives is followed the way a
caller would follow it: its XPath must name one element of the page, and a
JSON pointer after ``#`` must name a value inside that ``<script>`` block --
the very value, for a field that holds text.
"""

from __future__ import annotations

import re

from hypothesis import given, strategies as st
from strategies import (
    broken_pages,
    main_entity_pages,
    multiplying_pages,
    pages,
)

from sluicer import extract
from sluicer.declared.jsonld import _parse
from sluicer.declared.merge import ABOUT_A_THING, Field, Record, _json
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
    """Each ``<meta>``'s ``attribute``, lowercased, if it has content.

    ``name`` is one name; ``property`` is a list of terms, as RDFa makes it and
    the readers read it, so ``property="name og:title"`` is both.
    """
    found: set[str] = set()
    for meta in tree.xpath(f"//meta[@{attribute}]"):
        if not (meta.get("content") or "").strip():
            continue
        value = (meta.get(attribute) or "").lower()
        found.update(value.split() if attribute == "property" else [value.strip()])
    return found


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


def _with_main_entities(records) -> list:
    """The records, and each thing one of them declares its ``mainEntity``.

    The summary's subject can be a page's main entity, nested in the page's
    record, and an answer read from it names the entity's type.
    """
    found = list(records)
    for record in records:
        declared = record.fields.get("mainEntity")
        if declared is None or not isinstance(declared.value, dict):
            continue
        kinds = declared.value.get("@type")
        kinds = [k for k in (kinds if isinstance(kinds, list) else [kinds]) if k]
        found.append(
            Record(
                type=kinds[0] if kinds else None,
                types=tuple(kinds),
                fields={
                    key: Field(value, declared.source)
                    for key, value in declared.value.items()
                    if not key.startswith("@")
                },
                source=declared.source,
            )
        )
    return found


def _declared_by_a_record(records, answer) -> bool:
    """Whether a record the answer names holds what the answer says it read."""
    records = _with_main_entities(records)
    if answer.key == "@type":
        return any(
            record.type == answer.value and record.source == answer.source
            for record in records
        )
    for record in records:
        # A type can hold dots of its own -- https://example.org/ns#Widget --
        # so the record's type is matched as the key's prefix, not split out.
        if not record.type or not answer.key.startswith(record.type + "."):
            continue
        steps = answer.key[len(record.type) + 1 :].split(".")
        first = steps[0].split("[")[0]
        if (
            first in record.fields
            and record.fields[first].source == answer.source
            and _reaches(record.fields[first].value, steps, first)
        ):
            return True
    return False


def _reaches(value, steps, first) -> bool:
    """Whether the path an answer names -- ``offers[0].priceSpecification[1]
    .price`` -- leads somewhere in the field it starts from."""
    for number, step in enumerate(steps):
        name, _, index = step.partition("[")
        if number > 0:
            if not isinstance(value, dict) or name not in value:
                return False
            value = value[name]
        elif name != first:
            return False
        if index:
            position = int(index.rstrip("]"))
            if not isinstance(value, list) or position >= len(value):
                return False
            value = value[position]
    return True


def _followed(tree, where: str) -> object:
    """What ``where`` names on the page: its element, or the JSON value inside.

    Fails when the XPath names no element or several, or the pointer names
    nothing in the block.
    """
    path, hashed, fragment = where.partition("#")
    found = tree.xpath(path)
    assert isinstance(found, list), f"{where} is not a path: it gives {found!r}"
    assert len(found) == 1, f"{where} names {len(found)} elements"
    [element] = found
    if not hashed:
        return element
    assert element.tag == "script", where
    value = _parse((element.text_content() or "").strip())
    for token in fragment.split("/")[1:]:
        token = token.replace("~1", "/").replace("~0", "~")
        if isinstance(value, list):
            assert token.isdigit() and int(token) < len(value), where
            value = value[int(token)]
        else:
            assert isinstance(value, dict) and token in value, where
            value = value[token]
    return value


def _names_the_property(element, key: str) -> bool:
    """Whether ``element`` declares ``key``, in microdata or RDFa, however spelt.

    By the name's last part, since RDFa expands ``dc:title`` to
    ``http://purl.org/dc/terms/title`` and a vocabulary may shorten one.
    """
    tokens = f"{element.get('itemprop') or ''} {element.get('property') or ''}"
    return any(_local(token) == _local(key) for token in tokens.split())


def _local(name: str) -> str:
    return re.split(r"[/#:]", name)[-1]


def _placed(result, tree) -> None:
    for record in result.records:
        if record.where is not None:
            _followed(tree, record.where)
        for key, field in record.fields.items():
            if field.where is None:
                continue
            found = _followed(tree, field.where)
            if "#" in field.where and isinstance(field.value, str):
                assert _json(found, 0) == field.value, (key, field)
            elif (
                "#" not in field.where
                and field.where != record.where
                and isinstance(field.value, str)
            ):
                assert _names_the_property(found, key), (key, field)
    for answer in result.summary.values():
        if answer.where is not None:
            _followed(tree, answer.where)
    for conflict in result.conflicts:
        # A conflict starts with what the summary said, and holds at least
        # one other declaration, each placed where it says.
        assert len(conflict.answers) > 1, conflict
        said = result.summary[conflict.question]
        first = conflict.answers[0]
        assert (first.value, first.source, first.key) == (
            said.value,
            said.source,
            said.key,
        ), (conflict, said)
        for answer in conflict.answers:
            if answer.where is not None:
                _followed(tree, answer.where)


def _check(html: str | bytes, url: str | None) -> None:
    result = extract(html, url=url, induce=True)
    tree = load(html, url=url).tree
    _placed(result, tree)

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


def test_the_oracle_reads_a_property_as_a_list_of_terms():
    """Found by the fuzz profile: ``property="name og:title"`` declares og:title,
    as the readers read it, and the oracle still read it as one name."""
    import lxml.html

    tree = lxml.html.fromstring(
        '<html><head><meta property="name og:title" content="Pad"></head></html>'
    )

    assert _declared_on_the_page(tree, "opengraph", "og:title")


# What a summary answers about: a thing, not a page, a site or furniture.
_THINGS = {
    "Product",
    "ProductGroup",
    "Article",
    "NewsArticle",
    "BlogPosting",
    "Report",
    "Recipe",
    "Event",
    "JobPosting",
}


@given(main_entity_pages())
def test_a_page_s_main_entity_is_its_subject_and_placed_inside_it(drawn):
    """A thing the page declares its main entity is what the summary is
    about, and each answer read from it is placed at the property it was read
    from: a pointer ending in it, or the element that declares it. One that
    declares nothing but its type is no record, as it would not be alone."""
    html, kind, holds_any = drawn
    _check(html, None)
    result = extract(html)
    tree = load(html).tree
    if kind in _THINGS and holds_any:
        assert result.summary["type"].value == kind, result.summary
    for question, answer in result.summary.items():
        if answer.key == "@type" or answer.where is None:
            continue
        if answer.source not in ("jsonld", "microdata"):
            continue
        steps = [step.split("[")[0] for step in answer.key.split(".")[1:]]
        found = _followed(tree, answer.where)
        if "#" in answer.where:
            tokens = answer.where.partition("#")[2].split("/")[1:]
            named = [token for token in tokens if not token.isdigit()]
            assert named and named[-1] in steps, (question, answer)
        else:
            assert any(_names_the_property(found, step) for step in steps), (
                question,
                answer,
            )
